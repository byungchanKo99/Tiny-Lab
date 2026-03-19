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
from .errors import BuildError, OptimizeError, RunError, TinyLabError
from .evaluate import dispatch_evaluate, judge_verdict
from .generate import generate_hypotheses
from .queue import load_queue, save_queue, pending_hypotheses
from .ledger import load_ledger, append_ledger, get_baseline_metric, find_best_result, next_experiment_id
from .lock import LockManager
from .logging import configure_log, log
from .project import (
    load_project, project_name, metric_name, metric_direction,
    build_type, run_type, evaluate_type, search_space_for_approach,
    warn_missing_optimizer_config,
)
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
    OPTIMIZE = "optimize"
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
    optimize_result: Any | None = None  # OptimizeResult when inner loop runs

    def reset_experiment(self) -> None:
        """Clear per-experiment fields after RECORD."""
        self.hypothesis = None
        self.command = None
        self.exp_id = None
        self.run_result = None
        self.new_metric = None
        self.verdict = ""
        self.optimize_result = None


class ResearchLoop:
    """Deterministic research loop with pluggable BUILD/RUN/EVALUATE."""

    def __init__(self, project_dir: Path, on_event_cmd: str | None = None, *, until_idle: bool = False):
        self.project_dir = project_dir.resolve()
        self.lock_path = _lock_path(self.project_dir)
        self.state_path = _state_path(self.project_dir)
        self.provider = get_provider(self.project_dir)
        self.on_event_cmd = on_event_cmd
        self.until_idle = until_idle
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
        if self.until_idle:
            log("UNTIL-IDLE: queue exhausted, stopping.")
            self._emit(EventType.IDLE_STOP, {"reason": "queue_exhausted"})
            self._shutdown = True
            return State.CHECK_QUEUE
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
        from .schemas import validate_hypothesis_entry
        queue = load_queue(self.project_dir)
        pending = pending_hypotheses(queue)
        if not pending:
            return State.CHECK_QUEUE
        ctx.hypothesis = pending[0]

        # Validate hypothesis format before proceeding
        errors = validate_hypothesis_entry(ctx.hypothesis, strict=False)
        if errors:
            log(f"SELECT: INVALID hypothesis {ctx.hypothesis.get('id', '?')}: {errors}")
            log(f"SELECT: hypothesis must have ('lever' + 'value') or 'approach'. "
                f"Got keys: {list(ctx.hypothesis.keys())}")
            self._mark_hypothesis(ctx.hypothesis, "skipped")
            ctx.reset_experiment()
            return State.CHECK_QUEUE

        ctx.hypothesis["status"] = "running"
        save_queue(self.project_dir, queue)
        log(f"SELECT: {ctx.hypothesis['id']} -- {ctx.hypothesis['description']}")
        return State.BUILD_COMMAND

    def _handle_build_command(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.hypothesis is not None
        btype = build_type(project)
        ctx.exp_id = next_experiment_id(load_ledger(self.project_dir))
        try:
            ctx.command = dispatch_build(project, ctx.hypothesis, self.project_dir, self.provider)
            log(f"BUILD[{btype}]: {ctx.exp_id} -> {ctx.command[:120]}")
            return State.OPTIMIZE
        except BuildError as e:
            log(f"BUILD[{btype}]: {ctx.hypothesis['id']} failed -- {e}")
            self._mark_hypothesis(ctx.hypothesis, "skipped")
            ctx.reset_experiment()
            return State.CHECK_QUEUE

    def _handle_optimize(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        """OPTIMIZE state: dispatch inner loop or fall back to single RUN."""
        assert ctx.hypothesis is not None and ctx.command is not None and ctx.exp_id is not None
        approach = ctx.hypothesis.get("approach", "")
        ss = ctx.hypothesis.get("search_space") or search_space_for_approach(project, approach)
        if not ss:
            return self._handle_run_single(ctx, project)

        from .optimize import dispatch_optimize
        self._emit(EventType.OPTIMIZE_STARTED, {
            "exp_id": ctx.exp_id,
            "hypothesis_id": ctx.hypothesis["id"],
        })

        try:
            result = dispatch_optimize(project, ctx.command, ctx.hypothesis, self.project_dir, ctx.exp_id)
        except OptimizeError as e:
            log(f"OPTIMIZE: {ctx.exp_id} failed — {e}, falling back to single RUN")
            return self._handle_run_single(ctx, project)

        if result is None:
            return self._handle_run_single(ctx, project)

        ctx.optimize_result = result
        ctx.new_metric = result.best_value
        ctx.run_result = subprocess.CompletedProcess(
            args="optimize", returncode=0,
            stdout=result.best_stdout, stderr=result.best_stderr,
        )

        self._emit(EventType.OPTIMIZE_FINISHED, {
            "exp_id": ctx.exp_id,
            "n_trials": result.n_trials,
            "best_value": result.best_value,
            "total_seconds": round(result.total_seconds, 1),
        })

        return State.EVALUATE

    def _handle_run_single(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        """Single experiment run (legacy path or no search_space)."""
        assert ctx.command is not None and ctx.exp_id is not None
        rtype = run_type(project)
        log(f"RUN[{rtype}]: launching {ctx.exp_id}")
        try:
            ctx.run_result = dispatch_run(project, ctx.command, ctx.exp_id, self.project_dir)
            log(f"RUN[{rtype}]: {ctx.exp_id} finished (exit={ctx.run_result.returncode})")
        except RunError as e:
            log(f"RUN[{rtype}]: {ctx.exp_id} failed -- {e}")
            ctx.run_result = None
        return State.EVALUATE

    def _handle_evaluate(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.hypothesis is not None and ctx.exp_id is not None
        etype = evaluate_type(project)
        mname = metric_name(project)
        baseline_metric = get_baseline_metric(self.project_dir, mname)

        ctx.new_metric = dispatch_evaluate(
            project, ctx.run_result, ctx.hypothesis, ctx.exp_id,
            self.project_dir, self.provider,
        )
        ctx.verdict = judge_verdict(project, ctx.new_metric, baseline_metric)
        log(f"EVALUATE[{etype}]: {ctx.exp_id} -> {ctx.verdict} ({mname}={ctx.new_metric}, baseline={baseline_metric})")
        return State.RECORD

    def _handle_record(self, ctx: CycleContext, project: dict[str, Any]) -> State:
        assert ctx.hypothesis is not None and ctx.exp_id is not None
        mname = metric_name(project)
        baseline_metric = get_baseline_metric(self.project_dir, mname)

        # v2 hypothesis (approach-based) vs v1 (lever-based)
        if "approach" in ctx.hypothesis and "lever" not in ctx.hypothesis:
            changed_var = ctx.hypothesis["approach"]
            value = ctx.optimize_result.best_params if ctx.optimize_result else {}
            config = ctx.optimize_result.best_params if ctx.optimize_result else {}
        else:
            value = ctx.hypothesis["value"]
            changed_var = ctx.hypothesis["lever"]
            if isinstance(value, dict):
                changed_var = "+".join(value.keys())
            config = {changed_var: value}

        entry = {
            "id": ctx.exp_id,
            "question": ctx.hypothesis["description"],
            "family": project_name(project),
            "changed_variable": changed_var,
            "value": value,
            "control": "EXP-001",
            "status": "done",
            "class": ctx.verdict,
            "primary_metric": {
                mname: ctx.new_metric,
                "baseline": baseline_metric,
                "delta_pct": round((ctx.new_metric - baseline_metric) / baseline_metric * 100, 2) if ctx.new_metric and baseline_metric else None,
            },
            "decision": ctx.verdict.lower(),
            "notes": f"Command: {ctx.command}",
            "hypothesis_id": ctx.hypothesis["id"],
            "config": config,
            "reasoning": ctx.hypothesis.get("reasoning", ""),
        }

        # Include optimize_result in ledger for v2 hypotheses
        if ctx.optimize_result is not None:
            entry["optimize_result"] = {
                "n_trials": ctx.optimize_result.n_trials,
                "total_seconds": round(ctx.optimize_result.total_seconds, 1),
                "best_params": ctx.optimize_result.best_params,
                "best_value": ctx.optimize_result.best_value,
            }
            if "approach" in ctx.hypothesis:
                entry["approach"] = ctx.hypothesis["approach"]
        append_ledger(self.project_dir, entry)
        self._emit(EventType.EXPERIMENT_DONE, {
            "exp_id": ctx.exp_id,
            "verdict": ctx.verdict,
            "metric_value": ctx.new_metric,
        })

        # Detect new best result + stagnation
        ledger = load_ledger(self.project_dir)
        if ctx.verdict == "WIN" and ctx.new_metric is not None:
            direction = metric_direction(project)
            best = find_best_result(ledger, mname, direction)
            if best and best.get("id") == ctx.exp_id:
                self._emit(EventType.NEW_BEST, {
                    "exp_id": ctx.exp_id,
                    "metric_value": ctx.new_metric,
                    "config": f"{changed_var}={value}",
                })

        # Stagnation: warn if N experiments since last best
        non_baseline = [r for r in ledger if r.get("class") != "BASELINE"]
        if non_baseline:
            direction = metric_direction(project)
            best = find_best_result(ledger, mname, direction)
            if best:
                best_idx = next((i for i, r in enumerate(non_baseline) if r.get("id") == best.get("id")), None)
                if best_idx is not None:
                    since_best = len(non_baseline) - 1 - best_idx
                    if since_best > 0 and since_best % 20 == 0:
                        self._emit(EventType.STAGNATION_WARNING, {
                            "experiments_since_best": since_best,
                            "best_id": best.get("id"),
                            "best_value": best.get("primary_metric", {}).get(mname),
                        })
                        log(f"STAGNATION: {since_best} experiments since last best ({best.get('id')})")

        try:
            self._write_experiment_report(entry)
        except Exception:
            log(f"RECORD: warning — could not write report for {ctx.exp_id}")

        self._mark_hypothesis(ctx.hypothesis, "done")
        log(f"RECORD: {ctx.exp_id} recorded as {ctx.verdict}")

        ctx.reset_experiment()
        self._sleep(CYCLE_SLEEP)
        return State.CHECK_QUEUE

    def _write_experiment_report(self, entry: dict[str, Any]) -> None:
        """Auto-generate per-experiment markdown report."""
        from .paths import reports_dir
        rdir = reports_dir(self.project_dir)
        rdir.mkdir(exist_ok=True)
        exp_id = entry["id"]
        pm = entry.get("primary_metric", {})
        metric_name = next((k for k in pm if k not in ("baseline", "delta_pct")), "?")
        report = (
            f"# {exp_id}\n\n"
            f"## Hypothesis\n{entry.get('question', 'N/A')}\n\n"
            f"## Setup\n- Lever: {entry.get('changed_variable', 'N/A')}\n"
            f"- Value: {entry.get('value', 'N/A')}\n\n"
            f"## Result\n- Verdict: **{entry.get('class', 'N/A')}**\n"
            f"- {metric_name}: {pm.get(metric_name, 'N/A')}\n"
            f"- Baseline: {pm.get('baseline', 'N/A')}\n"
            f"- Delta: {pm.get('delta_pct', 'N/A')}%\n\n"
            f"## Notes\n{entry.get('notes', 'N/A')}\n"
        )
        (rdir / f"{exp_id}.md").write_text(report)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> int:
        self._recover_state()

        project = load_project(self.project_dir)
        warn_missing_optimizer_config(project)
        btype = build_type(project)
        rtype = run_type(project)
        etype = evaluate_type(project)
        mode = "until-idle" if self.until_idle else "infinite"
        log(f"LOOP: mode={mode}")
        log(f"LOOP: started '{project_name(project)}' [build={btype}, run={rtype}, eval={etype}, provider={self.provider.name}]")

        if not ensure_baseline(project, self.project_dir):
            log("LOOP: WARNING — no baseline metric available. First experiments will be INCONCLUSIVE.")

        handlers = {
            State.CHECK_QUEUE: self._handle_check_queue,
            State.GENERATE: self._handle_generate,
            State.SELECT: self._handle_select,
            State.BUILD_COMMAND: self._handle_build_command,
            State.RUN: self._handle_run_single,
            State.OPTIMIZE: self._handle_optimize,
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
