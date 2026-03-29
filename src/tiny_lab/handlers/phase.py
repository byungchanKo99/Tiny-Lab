"""Phase handlers — select, run, evaluate, record."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .. import events
from ..errors import StateError
from ..logging import log
from ..paths import phases_dir, results_dir, intervention_path
from ..plan import load_plan, next_pending_phase, update_phase_status
from ..state import LoopState
from ..workflow import StateSpec
from . import EngineContext, StateResult


class PhaseSelectHandler:
    """Pick the next pending phase from research_plan."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        try:
            plan = load_plan(ctx.project_dir, ls.current_iteration)
        except Exception:
            log("ENGINE: no plan found, nothing to select")
            return StateResult(state_overrides={"current_phase_id": None})

        phase = next_pending_phase(plan)
        if phase:
            phase_id = phase["id"]
            reuse = phase.get("reuse_from")
            if reuse:
                import shutil
                src = ctx.project_dir / "research" / reuse
                dst = phases_dir(ctx.project_dir, ls.current_iteration) / src.name
                if src.exists():
                    shutil.copy2(src, dst)
                    log(f"ENGINE: reusing {reuse} for {phase_id}")
            events.phase_started(ctx.project_dir, phase_id, ls.current_iteration)
            log(f"ENGINE: selected phase {phase_id} — {phase.get('name', '')}")
            return StateResult(
                state_overrides={"current_phase_id": phase_id, "phase_retries": 0, "session_id": None},
            )
        else:
            log("ENGINE: no pending phases")
            return StateResult(state_overrides={"current_phase_id": None})


class PhaseRunHandler:
    """Execute the current phase script."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        phase_id = ls.current_phase_id
        if not phase_id:
            raise StateError("PHASE_RUN but no current_phase_id")

        plan = load_plan(ctx.project_dir, ls.current_iteration)
        phase = next((p for p in plan["phases"] if p["id"] == phase_id), None)
        if not phase:
            raise StateError(f"Phase {phase_id} not found in plan")

        update_phase_status(ctx.project_dir, ls.current_iteration, phase_id, "running")

        phase_type = phase.get("type", "script")
        if phase_type == "optimize":
            _run_optimize(phase, ls, ctx)
        elif phase_type == "manual":
            log(f"ENGINE: phase {phase_id} is manual — waiting for intervention")
            marker = {"phase_id": phase_id, "phase_name": phase.get("name", ""), "waiting_for": "manual input"}
            (intervention_path(ctx.project_dir).parent / ".manual_wait.json").write_text(
                json.dumps(marker, indent=2)
            )
            return StateResult(transition="CHECKPOINT")
        else:
            _run_script(phase, ls, ctx)

        return StateResult()  # use spec.next


def _run_script(phase: dict[str, Any], ls: LoopState, ctx: EngineContext) -> None:
    phase_id = phase["id"]
    pdir = phases_dir(ctx.project_dir, ls.current_iteration)
    scripts = list(pdir.glob(f"*{phase_id}*"))
    if not scripts:
        raise StateError(f"No script found for phase {phase_id} in {pdir}")

    script = scripts[0]
    log(f"ENGINE: running {script.name}")

    rdir = results_dir(ctx.project_dir, ls.current_iteration)
    rdir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["python", str(script)],
        capture_output=True,
        text=True,
        cwd=str(ctx.project_dir),
        env={
            **os.environ,
            "TINYLAB_PHASE_ID": phase_id,
            "TINYLAB_PROJECT_DIR": str(ctx.project_dir),
            "TINYLAB_RESULTS_DIR": str(rdir),
            "TINYLAB_ITERATION": str(ls.current_iteration),
        },
    )

    if result.returncode != 0:
        log(f"ENGINE: phase script failed (exit={result.returncode})")
        stderr_lines = result.stderr.strip().splitlines()[-20:] if result.stderr else []
        for line in stderr_lines[-10:]:
            log(f"ENGINE: stderr: {line}")

        # Append to attempt history
        error_file = ctx.project_dir / "research" / f"iter_{ls.current_iteration}" / ".phase_error.json"
        history: list[dict] = []
        if error_file.exists():
            try:
                loaded = json.loads(error_file.read_text())
                history = loaded if isinstance(loaded, list) else [loaded]
            except Exception:
                pass
        history.append({
            "attempt": len(history) + 1,
            "phase_id": phase_id,
            "script": script.name,
            "exit_code": result.returncode,
            "stderr": "\n".join(stderr_lines),
            "stdout_tail": "\n".join((result.stdout or "").strip().splitlines()[-15:]),
            "script_snippet": script.read_text()[:3000],
        })
        error_file.write_text(json.dumps(history, indent=2))
        raise StateError(f"Phase {phase_id} script failed")

    # Clear error history on success
    error_file = ctx.project_dir / "research" / f"iter_{ls.current_iteration}" / ".phase_error.json"
    if error_file.exists():
        error_file.unlink()

    log(f"ENGINE: phase {phase_id} script completed")


def _run_optimize(phase: dict[str, Any], ls: LoopState, ctx: EngineContext) -> None:
    from ..optimize import run_optimize

    phase_id = phase["id"]
    opt_config = phase.get("optimize", {})
    plan = load_plan(ctx.project_dir, ls.current_iteration)
    metric = plan.get("metric", {})
    metric_name = metric.get("name", "metric")
    direction = metric.get("direction", "minimize")

    pdir = phases_dir(ctx.project_dir, ls.current_iteration)
    scripts = list(pdir.glob(f"*{phase_id}*"))
    if not scripts:
        raise StateError(f"No script found for optimize phase {phase_id}")

    log(f"ENGINE: running optimize phase {phase_id}")
    result = run_optimize(
        base_command=f"python {scripts[0]}",
        phase_config=opt_config,
        metric_name=metric_name,
        direction=direction,
        project_dir=ctx.project_dir,
        levers=plan.get("levers", {}),
    )

    rdir = results_dir(ctx.project_dir, ls.current_iteration)
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / f"{phase_id}.json").write_text(json.dumps({
        metric_name: result.best_value,
        "best_params": result.best_params,
        "n_trials": result.n_trials,
        "total_seconds": result.total_seconds,
        "all_trials": result.all_trials,
    }, indent=2, default=str))
    log(f"ENGINE: optimize phase {phase_id} done — best {metric_name}={result.best_value}")


class PhaseEvaluateHandler:
    """Validate phase output against plan schema."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        phase_id = ls.current_phase_id
        if not phase_id:
            raise StateError("PHASE_EVALUATE but no current_phase_id")

        plan = load_plan(ctx.project_dir, ls.current_iteration)
        phase = next((p for p in plan["phases"] if p["id"] == phase_id), None)
        if not phase:
            raise StateError(f"Phase {phase_id} not found")

        expected = phase.get("expected_outputs", {})
        report_spec = expected.get("report", {})
        if not report_spec:
            log(f"ENGINE: no expected_outputs.report for {phase_id}, skipping validation")
            return StateResult()

        report_path = ctx.project_dir / report_spec["path"]
        if not report_path.exists():
            raise StateError(f"Expected report not found: {report_path}")

        schema = report_spec.get("schema", {})
        if schema:
            data = json.loads(report_path.read_text())
            if "properties" in schema:
                expected_fields = list(schema.get("required", schema["properties"].keys()))
            else:
                expected_fields = list(schema.keys())
            missing = [k for k in expected_fields if k not in data]
            if missing:
                raise StateError(f"Report missing fields: {missing}")

        log(f"ENGINE: phase {phase_id} output validated")
        return StateResult()


class PhaseRecordHandler:
    """Mark phase as done in plan."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        if ls.current_phase_id:
            update_phase_status(ctx.project_dir, ls.current_iteration, ls.current_phase_id, "done")
            events.phase_completed(ctx.project_dir, ls.current_phase_id, ls.current_iteration, "done")
            log(f"ENGINE: phase {ls.current_phase_id} recorded as done")
        return StateResult()
