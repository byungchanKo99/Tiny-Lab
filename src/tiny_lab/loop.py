"""Core research loop state machine."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .baseline import ensure_baseline
from .build import dispatch_build
from .errors import BuildError, RunError, TinyLabError
from .evaluate import dispatch_evaluate, judge_verdict
from .generate import generate_hypotheses
from .queue import load_queue, save_queue, pending_hypotheses
from .ledger import load_ledger, append_ledger, get_baseline_metric, find_best_result, next_experiment_id
from .lock import LockManager
from .logging import configure_log, log
from .project import load_project
from .providers import get_provider
from .events import emit_event, EventType
from .paths import lock_path as _lock_path, state_path as _state_path
from .run import dispatch_run

CYCLE_SLEEP = int(os.environ.get("CYCLE_SLEEP", "30"))
CIRCUIT_BREAKER_WINDOW = 20
CIRCUIT_BREAKER_THRESHOLD = 5
MAX_CONSECUTIVE_ERRORS = 3


class State(Enum):
    CHECK_QUEUE = "check_queue"
    GENERATE = "generate"
    SELECT = "select"
    BUILD_COMMAND = "build_command"
    RUN = "run"
    EVALUATE = "evaluate"
    RECORD = "record"


@dataclass
class CycleContext:
    """Per-experiment mutable state carried across loop iterations."""

    hypothesis: dict[str, Any] | None = None
    command: str | None = None
    exp_id: str | None = None
    run_result: subprocess.CompletedProcess[str] | None = None
    new_metric: float | None = None
    verdict: str = ""
    consecutive_generate_failures: int = 0

    def reset_experiment(self) -> None:
        """Clear per-experiment fields after RECORD."""
        self.hypothesis = None
        self.command = None
        self.exp_id = None
        self.run_result = None
        self.new_metric = None
        self.verdict = ""


class ResearchLoop:
    """Deterministic research loop with pluggable BUILD/RUN/EVALUATE."""

    def __init__(self, project_dir: Path, on_event_cmd: str | None = None):
        self.project_dir = project_dir.resolve()
        self.lock_path = _lock_path(self.project_dir)
        self.state_path = _state_path(self.project_dir)
        self.provider = get_provider(self.project_dir)
        self.on_event_cmd = on_event_cmd
        self._shutdown = False
        self._current_state: str | None = None

    def run(self) -> int:
        """Entry point: acquire lock, run loop, release lock."""
        configure_log(self.project_dir)

        try:
            load_project(self.project_dir)
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            return 1

        lock = LockManager(self.lock_path)
        if not lock.acquire():
            log("ERROR: another research loop is already running")
            return 1

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        with lock:
            self._emit(EventType.LOOP_STARTED, {"pid": os.getpid()})
            rc = self._run_loop()
            self._emit(EventType.LOOP_STOPPED, {"reason": "shutdown"})
            self.state_path.unlink(missing_ok=True)
            log("LOOP: stopped")
            return rc

    def _emit(self, event: EventType, data: dict[str, Any] | None = None) -> None:
        emit_event(self.project_dir, event, data, self.on_event_cmd,
                   loop_state=self._current_state)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self._shutdown = True

    def _check_circuit_breaker(self) -> bool:
        rows = load_ledger(self.project_dir)
        recent = rows[-CIRCUIT_BREAKER_WINDOW:]
        invalid_count = sum(1 for r in recent if r.get("class") == "INVALID")
        if invalid_count >= CIRCUIT_BREAKER_THRESHOLD - 1 and invalid_count < CIRCUIT_BREAKER_THRESHOLD:
            self._emit(EventType.CIRCUIT_BREAKER_WARNING, {
                "invalid_count": invalid_count,
                "threshold": CIRCUIT_BREAKER_THRESHOLD,
            })
        return invalid_count >= CIRCUIT_BREAKER_THRESHOLD

    def _recover_state(self) -> None:
        """Recover from a previous crash: reset orphaned 'running' hypotheses to 'pending'."""
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
            log(f"RECOVER: found stale state file (state={data.get('state')}, pid={data.get('pid')})")
        except (json.JSONDecodeError, OSError):
            log("RECOVER: corrupt state file, removing")
            self.state_path.unlink(missing_ok=True)
            return

        queue = load_queue(self.project_dir)
        recovered = 0
        for h in queue:
            if h.get("status") == "running":
                h["status"] = "pending"
                recovered += 1
        if recovered:
            save_queue(self.project_dir, queue)
            log(f"RECOVER: reset {recovered} orphaned hypothesis(es) to pending")
        self.state_path.unlink(missing_ok=True)

    def _save_state(self, state: State, context: dict[str, Any] | None = None) -> None:
        data = {
            "state": state.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        if context:
            data["context"] = context
        self.state_path.write_text(json.dumps(data, indent=2) + "\n")

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

    # ------------------------------------------------------------------
    # State handlers — each returns the next State
    # ------------------------------------------------------------------

    def _handle_check_queue(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        if self._check_circuit_breaker():
            log("CIRCUIT BREAKER: too many INVALID results. Stopping.")
            self._shutdown = True
            return State.CHECK_QUEUE  # will exit on next while check

        queue = load_queue(self.project_dir)
        pending = pending_hypotheses(queue)
        if pending:
            ctx.consecutive_generate_failures = 0
            return State.SELECT
        return State.GENERATE

    def _handle_generate(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        self._emit(EventType.GENERATE_ENTER)
        log("GENERATE: queue empty, asking agent for new hypotheses")
        before_count = len(pending_hypotheses(load_queue(self.project_dir)))
        generate_hypotheses(project, self.project_dir, self.provider)
        after_count = len(pending_hypotheses(load_queue(self.project_dir)))

        if after_count > before_count:
            log(f"GENERATE: {after_count - before_count} new hypotheses added")
            ctx.consecutive_generate_failures = 0
            return State.CHECK_QUEUE

        ctx.consecutive_generate_failures += 1
        log(f"GENERATE: no new hypotheses (attempt {ctx.consecutive_generate_failures})")
        if ctx.consecutive_generate_failures >= 3:
            log("GENERATE: 3 consecutive failures. Search space may be exhausted. Waiting.")
            ctx.consecutive_generate_failures = 0
            self._sleep(CYCLE_SLEEP * 10)
        else:
            self._sleep(CYCLE_SLEEP)
        return State.CHECK_QUEUE

    def _handle_select(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        queue = load_queue(self.project_dir)
        pending = pending_hypotheses(queue)
        if not pending:
            return State.CHECK_QUEUE
        ctx.hypothesis = pending[0]
        ctx.hypothesis["status"] = "running"
        save_queue(self.project_dir, queue)
        log(f"SELECT: {ctx.hypothesis['id']} -- {ctx.hypothesis['description']}")
        return State.BUILD_COMMAND

    def _handle_build_command(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.hypothesis is not None
        build_type = project.get("build", {}).get("type", "flag")
        ctx.exp_id = next_experiment_id(load_ledger(self.project_dir))
        try:
            ctx.command = dispatch_build(project, ctx.hypothesis, self.project_dir, self.provider)
            log(f"BUILD[{build_type}]: {ctx.exp_id} -> {ctx.command[:120]}")
            return State.RUN
        except BuildError as e:
            log(f"BUILD[{build_type}]: {ctx.hypothesis['id']} failed -- {e}")
            self._mark_hypothesis(ctx.hypothesis, "skipped")
            ctx.reset_experiment()
            return State.CHECK_QUEUE

    def _handle_run(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.command is not None and ctx.exp_id is not None
        run_type = project.get("run", {}).get("type", "surface")
        log(f"RUN[{run_type}]: launching {ctx.exp_id}")
        try:
            ctx.run_result = dispatch_run(project, ctx.command, ctx.exp_id, self.project_dir)
            log(f"RUN[{run_type}]: {ctx.exp_id} finished (exit={ctx.run_result.returncode})")
        except RunError as e:
            log(f"RUN[{run_type}]: {ctx.exp_id} failed -- {e}")
            ctx.run_result = None
        return State.EVALUATE

    def _handle_evaluate(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.hypothesis is not None and ctx.exp_id is not None
        eval_type = project.get("evaluate", {}).get("type", "stdout_json")
        metric_name = project["metric"]["name"]
        baseline_metric = get_baseline_metric(self.project_dir, metric_name)

        ctx.new_metric = dispatch_evaluate(
            project, ctx.run_result, ctx.hypothesis, ctx.exp_id,
            self.project_dir, self.provider,
        )
        ctx.verdict = judge_verdict(project, ctx.new_metric, baseline_metric)
        log(f"EVALUATE[{eval_type}]: {ctx.exp_id} -> {ctx.verdict} ({metric_name}={ctx.new_metric}, baseline={baseline_metric})")
        return State.RECORD

    def _handle_record(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.hypothesis is not None and ctx.exp_id is not None
        metric_name = project["metric"]["name"]
        baseline_metric = get_baseline_metric(self.project_dir, metric_name)
        value = ctx.hypothesis["value"]
        changed_var = ctx.hypothesis["lever"]
        if isinstance(value, dict):
            changed_var = "+".join(value.keys())
        entry = {
            "id": ctx.exp_id,
            "question": ctx.hypothesis["description"],
            "family": project["name"],
            "changed_variable": changed_var,
            "value": value,
            "control": "EXP-001",
            "status": "done",
            "class": ctx.verdict,
            "primary_metric": {
                metric_name: ctx.new_metric,
                "baseline": baseline_metric,
                "delta_pct": round((ctx.new_metric - baseline_metric) / baseline_metric * 100, 2) if ctx.new_metric and baseline_metric else None,
            },
            "decision": ctx.verdict.lower(),
            "notes": f"Command: {ctx.command}",
        }
        append_ledger(self.project_dir, entry)
        self._emit(EventType.EXPERIMENT_DONE, {
            "exp_id": ctx.exp_id,
            "verdict": ctx.verdict,
            "metric_value": ctx.new_metric,
        })

        # Detect new best result
        if ctx.verdict == "WIN" and ctx.new_metric is not None:
            direction = project["metric"].get("direction", "minimize")
            ledger = load_ledger(self.project_dir)
            best = find_best_result(ledger, metric_name, direction)
            if best and best.get("id") == ctx.exp_id:
                self._emit(EventType.NEW_BEST, {
                    "exp_id": ctx.exp_id,
                    "metric_value": ctx.new_metric,
                    "config": f"{changed_var}={value}",
                })

        self._mark_hypothesis(ctx.hypothesis, "done")
        log(f"RECORD: {ctx.exp_id} recorded as {ctx.verdict}")

        ctx.reset_experiment()
        self._sleep(CYCLE_SLEEP)
        return State.CHECK_QUEUE

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> int:
        self._recover_state()

        project = load_project(self.project_dir)
        build_type = project.get("build", {}).get("type", "flag")
        run_type = project.get("run", {}).get("type", "surface")
        eval_type = project.get("evaluate", {}).get("type", "stdout_json")
        log(f"LOOP: started '{project['name']}' [build={build_type}, run={run_type}, eval={eval_type}, provider={self.provider.name}]")

        if not ensure_baseline(project, self.project_dir):
            log("LOOP: WARNING — no baseline metric available. First experiments will be INCONCLUSIVE.")

        handlers = {
            State.CHECK_QUEUE: self._handle_check_queue,
            State.GENERATE: self._handle_generate,
            State.SELECT: self._handle_select,
            State.BUILD_COMMAND: self._handle_build_command,
            State.RUN: self._handle_run,
            State.EVALUATE: self._handle_evaluate,
            State.RECORD: self._handle_record,
        }

        ctx = CycleContext()
        state = State.CHECK_QUEUE
        consecutive_errors = 0

        while not self._shutdown:
            self._current_state = state.value
            self._save_state(state, {"hypothesis_id": ctx.hypothesis["id"] if ctx.hypothesis else None})

            # Reload project.yaml when AI may have modified it
            if state in (State.GENERATE, State.BUILD_COMMAND):
                project = load_project(self.project_dir)

            try:
                state = handlers[state](ctx, project)
                consecutive_errors = 0
            except TinyLabError as e:
                log(f"ERROR in {state.value}: {e}")
                if ctx.hypothesis:
                    self._mark_hypothesis(ctx.hypothesis, "skipped")
                ctx.reset_experiment()
                state = State.CHECK_QUEUE
                consecutive_errors += 1
            except Exception as e:
                log(f"UNEXPECTED in {state.value}: {e}")
                ctx.reset_experiment()
                state = State.CHECK_QUEUE
                consecutive_errors += 1

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log(f"TOO MANY ERRORS ({consecutive_errors} consecutive): stopping")
                break

        return 0
