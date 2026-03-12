"""Core research loop state machine."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .build import dispatch_build
from .evaluate import dispatch_evaluate, judge_verdict
from .generate import generate_hypotheses, load_queue, save_queue, pending_hypotheses
from .ledger import load_ledger, append_ledger, get_baseline_metric, next_experiment_id
from .logging import configure_log, log
from .project import load_project

CYCLE_SLEEP = int(os.environ.get("CYCLE_SLEEP", "30"))
CIRCUIT_BREAKER_WINDOW = 20
CIRCUIT_BREAKER_THRESHOLD = 5
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MAX_TURNS = int(os.environ.get("CLAUDE_MAX_TURNS", "20"))
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")


class State(Enum):
    CHECK_QUEUE = "check_queue"
    GENERATE = "generate"
    SELECT = "select"
    BUILD_COMMAND = "build_command"
    RUN = "run"
    EVALUATE = "evaluate"
    RECORD = "record"


class ResearchLoop:
    """Deterministic research loop with pluggable BUILD/RUN/EVALUATE."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir.resolve()
        self.lock_path = self.project_dir / "research" / ".loop-lock"
        self.state_path = self.project_dir / "research" / ".loop_state.json"
        self._shutdown = False

    def run(self) -> int:
        """Entry point: acquire lock, run loop, release lock."""
        configure_log(self.project_dir)

        try:
            load_project(self.project_dir)
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            return 1

        if not self._acquire_lock():
            log("ERROR: another research loop is already running")
            return 1

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        try:
            return self._run_loop()
        finally:
            self._release_lock()
            self.state_path.unlink(missing_ok=True)
            log("LOOP: stopped")

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self._shutdown = True

    def _get_provider(self) -> str:
        """Get AI provider from project.yaml or env var."""
        try:
            project = load_project(self.project_dir)
            return project.get("agent", {}).get("provider", "claude")
        except FileNotFoundError:
            return os.environ.get("TINYLAB_PROVIDER", "claude")

    def _run_ai(
        self,
        prompt: str,
        allowed_tools: str = "Read,Write,Edit",
        max_turns: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        provider = self._get_provider()
        if provider == "codex":
            return self._run_codex(prompt, cwd=cwd)
        return self._run_claude(prompt, allowed_tools, max_turns, cwd)

    def _run_claude(
        self,
        prompt: str,
        allowed_tools: str = "Read,Write,Edit",
        max_turns: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if not shutil.which(CLAUDE_BIN):
            raise RuntimeError(f"claude CLI not found ({CLAUDE_BIN}). Set agent.provider: codex in project.yaml if using Codex.")
        # Strip CLAUDECODE env var to allow subprocess invocations
        # from within a Claude Code session
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        return subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--allowedTools", allowed_tools,
             "--max-turns", str(max_turns or CLAUDE_MAX_TURNS), "--output-format", "text"],
            text=True, capture_output=True, cwd=cwd or str(self.project_dir),
            env=env,
        )

    def _run_codex(
        self,
        prompt: str,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if not shutil.which(CODEX_BIN):
            raise RuntimeError(f"codex CLI not found ({CODEX_BIN}). Set agent.provider: claude in project.yaml if using Claude Code.")
        return subprocess.run(
            [CODEX_BIN, "exec", prompt, "--full-auto", "--skip-git-repo-check"],
            text=True, capture_output=True, cwd=cwd or str(self.project_dir),
        )

    def _check_circuit_breaker(self) -> bool:
        rows = load_ledger(self.project_dir)
        recent = rows[-CIRCUIT_BREAKER_WINDOW:]
        invalid_count = sum(1 for r in recent if r.get("class") == "INVALID")
        return invalid_count >= CIRCUIT_BREAKER_THRESHOLD

    def _save_state(self, state: State, context: dict[str, Any] | None = None) -> None:
        data = {
            "state": state.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        if context:
            data["context"] = context
        self.state_path.write_text(json.dumps(data, indent=2) + "\n")

    def _acquire_lock(self) -> bool:
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text().strip())
                os.kill(pid, 0)
                return False
            except (ValueError, OSError):
                log(f"LOCK: removing orphan lock (pid={self.lock_path.read_text().strip()})")
                self.lock_path.unlink(missing_ok=True)
        self.lock_path.write_text(str(os.getpid()))
        return True

    def _release_lock(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    def _mark_hypothesis(self, hypothesis: dict[str, Any], status: str) -> None:
        queue = load_queue(self.project_dir)
        for h in queue:
            if h.get("id") == hypothesis["id"]:
                h["status"] = status
                break
        save_queue(self.project_dir, queue)

    def _sleep(self, seconds: int) -> None:
        for _ in range(seconds):
            if self._shutdown:
                return
            time.sleep(1)

    def _ensure_baseline(self, project: dict[str, Any]) -> bool:
        """Run baseline command and record to ledger if no BASELINE entry exists.

        Returns True if baseline is available (already existed or successfully recorded).
        """
        metric_name = project["metric"]["name"]
        if get_baseline_metric(self.project_dir, metric_name) is not None:
            log("BASELINE: already recorded in ledger")
            return True

        baseline_cmd = project.get("baseline", {}).get("command")
        if not baseline_cmd:
            log("BASELINE: no baseline.command in project.yaml — cannot establish baseline")
            return False

        log(f"BASELINE: running baseline command: {baseline_cmd[:120]}")
        try:
            from .run import dispatch_run
            run_result = dispatch_run(project, baseline_cmd, "BASELINE", self.project_dir)
        except (subprocess.TimeoutExpired, ValueError) as e:
            log(f"BASELINE: failed to run — {e}")
            return False

        if run_result.returncode != 0:
            log(f"BASELINE: command failed (exit={run_result.returncode})")
            log(f"BASELINE: stderr={run_result.stderr[:500]}")
            return False

        # Extract metric
        from .evaluate import evaluate_stdout_json, evaluate_with_script
        eval_type = project.get("evaluate", {}).get("type", "stdout_json")
        if eval_type == "stdout_json":
            metric_val = evaluate_stdout_json(project, run_result)
        elif eval_type == "script":
            metric_val = evaluate_with_script(project, run_result, "BASELINE", self.project_dir)
        else:
            # For LLM eval, baseline metric must be manually provided
            log("BASELINE: evaluate.type=llm — baseline metric must be set manually")
            return False

        if metric_val is None:
            log(f"BASELINE: could not extract {metric_name} from baseline output")
            log(f"BASELINE: stdout={run_result.stdout[:500]}")
            return False

        entry = {
            "id": "EXP-001",
            "question": "Baseline measurement",
            "family": project["name"],
            "changed_variable": "baseline",
            "value": "baseline",
            "control": "EXP-001",
            "status": "done",
            "class": "BASELINE",
            "primary_metric": {
                metric_name: metric_val,
                "baseline": metric_val,
                "delta_pct": 0.0,
            },
            "decision": "baseline",
            "notes": f"Command: {baseline_cmd}",
        }
        append_ledger(self.project_dir, entry)
        log(f"BASELINE: recorded {metric_name}={metric_val}")
        return True

    def _run_loop(self) -> int:
        project = load_project(self.project_dir)
        build_type = project.get("build", {}).get("type", "flag")
        run_type = project.get("run", {}).get("type", "surface")
        eval_type = project.get("evaluate", {}).get("type", "stdout_json")
        log(f"LOOP: started '{project['name']}' [build={build_type}, run={run_type}, eval={eval_type}]")

        # Ensure baseline is recorded before any experiments
        if not self._ensure_baseline(project):
            log("LOOP: WARNING — no baseline metric available. First experiments will be INCONCLUSIVE.")

        state = State.CHECK_QUEUE
        hypothesis: dict[str, Any] | None = None
        command: str | None = None
        exp_id: str | None = None
        run_result: subprocess.CompletedProcess[str] | None = None
        new_metric: float | None = None
        verdict: str = ""
        consecutive_generate_failures = 0

        while not self._shutdown:
            self._save_state(state, {"hypothesis_id": hypothesis["id"] if hypothesis else None})

            if state == State.CHECK_QUEUE:
                if self._check_circuit_breaker():
                    log("CIRCUIT BREAKER: too many INVALID results. Stopping.")
                    return 1

                queue = load_queue(self.project_dir)
                pending = pending_hypotheses(queue)
                if pending:
                    consecutive_generate_failures = 0
                    state = State.SELECT
                else:
                    state = State.GENERATE

            elif state == State.GENERATE:
                log("GENERATE: queue empty, asking agent for new hypotheses")
                project = load_project(self.project_dir)
                before_count = len(pending_hypotheses(load_queue(self.project_dir)))
                generate_hypotheses(project, self.project_dir, self._run_ai)
                after_count = len(pending_hypotheses(load_queue(self.project_dir)))

                if after_count > before_count:
                    log(f"GENERATE: {after_count - before_count} new hypotheses added")
                    consecutive_generate_failures = 0
                    state = State.CHECK_QUEUE
                else:
                    consecutive_generate_failures += 1
                    log(f"GENERATE: no new hypotheses (attempt {consecutive_generate_failures})")
                    if consecutive_generate_failures >= 3:
                        log("GENERATE: 3 consecutive failures. Search space may be exhausted. Waiting.")
                        consecutive_generate_failures = 0
                        self._sleep(CYCLE_SLEEP * 10)
                    else:
                        self._sleep(CYCLE_SLEEP)
                    state = State.CHECK_QUEUE

            elif state == State.SELECT:
                queue = load_queue(self.project_dir)
                pending = pending_hypotheses(queue)
                if not pending:
                    state = State.CHECK_QUEUE
                    continue
                hypothesis = pending[0]
                hypothesis["status"] = "running"
                save_queue(self.project_dir, queue)
                log(f"SELECT: {hypothesis['id']} -- {hypothesis['description']}")
                state = State.BUILD_COMMAND

            elif state == State.BUILD_COMMAND:
                assert hypothesis is not None
                project = load_project(self.project_dir)
                exp_id = next_experiment_id(load_ledger(self.project_dir))
                try:
                    command = dispatch_build(project, hypothesis, self.project_dir, self._run_ai)
                    log(f"BUILD[{build_type}]: {exp_id} -> {command[:120]}")
                    state = State.RUN
                except (ValueError, RuntimeError) as e:
                    log(f"BUILD[{build_type}]: {hypothesis['id']} failed -- {e}")
                    self._mark_hypothesis(hypothesis, "skipped")
                    hypothesis = None
                    state = State.CHECK_QUEUE

            elif state == State.RUN:
                assert command is not None and exp_id is not None
                log(f"RUN[{run_type}]: launching {exp_id}")
                try:
                    from .run import dispatch_run
                    run_result = dispatch_run(project, command, exp_id, self.project_dir)
                    log(f"RUN[{run_type}]: {exp_id} finished (exit={run_result.returncode})")
                except (subprocess.TimeoutExpired, ValueError) as e:
                    log(f"RUN[{run_type}]: {exp_id} failed -- {e}")
                    run_result = None
                state = State.EVALUATE

            elif state == State.EVALUATE:
                assert hypothesis is not None and exp_id is not None
                metric_name = project["metric"]["name"]
                baseline_metric = get_baseline_metric(self.project_dir, metric_name)

                new_metric = dispatch_evaluate(
                    project, run_result, hypothesis, exp_id,
                    self.project_dir, self._run_claude,
                )
                verdict = judge_verdict(project, new_metric, baseline_metric)
                log(f"EVALUATE[{eval_type}]: {exp_id} -> {verdict} ({metric_name}={new_metric}, baseline={baseline_metric})")
                state = State.RECORD

            elif state == State.RECORD:
                assert hypothesis is not None and exp_id is not None
                metric_name = project["metric"]["name"]
                baseline_metric = get_baseline_metric(self.project_dir, metric_name)
                entry = {
                    "id": exp_id,
                    "question": hypothesis["description"],
                    "family": project["name"],
                    "changed_variable": hypothesis["lever"],
                    "value": hypothesis["value"],
                    "control": "EXP-001",
                    "status": "done",
                    "class": verdict,
                    "primary_metric": {
                        metric_name: new_metric,
                        "baseline": baseline_metric,
                        "delta_pct": round((new_metric - baseline_metric) / baseline_metric * 100, 2) if new_metric and baseline_metric else None,
                    },
                    "decision": verdict.lower(),
                    "notes": f"Command: {command}",
                }
                append_ledger(self.project_dir, entry)
                self._mark_hypothesis(hypothesis, "done")
                log(f"RECORD: {exp_id} recorded as {verdict}")

                hypothesis = None
                command = None
                exp_id = None
                run_result = None
                new_metric = None
                verdict = ""

                self._sleep(CYCLE_SLEEP)
                state = State.CHECK_QUEUE

        return 0
