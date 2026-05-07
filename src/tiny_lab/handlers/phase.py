"""Phase handlers — select, run, evaluate, record."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import events
from ..errors import StateError
from ..logging import log
from ..paths import phases_dir, results_dir, intervention_path, knowledge_dir, resolve_research_results_path
from ..phase_contract import select_phase_script
from ..provenance import audit_code_provenance
from ..quality import audit_phase_result_artifact_contract, audit_phase_result_consistency
from ..plan import load_plan, next_pending_phase, update_phase_status
from ..result_schema import (
    schema_expected_fields,
    schema_fields_to_validate,
    validate_finite_numeric_values,
    validate_phase_identity,
    validate_result_object,
    validate_schema_types,
    validate_substantive_result_values,
)
from ..state import LoopState
from ..visualizations import phase_visualization_issues
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
                state_overrides={"current_phase_id": phase_id, "phase_retries": 0},
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
        elif phase_type == "script":
            _run_script(phase, ls, ctx)
        else:
            raise StateError(f"Unknown phase type for {phase_id}: {phase_type}")

        return StateResult()  # use spec.next


def _run_script(phase: dict[str, Any], ls: LoopState, ctx: EngineContext) -> None:
    phase_id = phase["id"]
    pdir = phases_dir(ctx.project_dir, ls.current_iteration)
    try:
        script = select_phase_script(pdir, phase_id)
    except ValueError as e:
        raise StateError(str(e)) from e
    log(f"ENGINE: running {script.name}")

    rdir = results_dir(ctx.project_dir, ls.current_iteration)
    rdir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(ctx.project_dir),
        env={
            **os.environ,
            "TINYLAB_PHASE_ID": phase_id,
            "TINYLAB_PROJECT_DIR": str(ctx.project_dir),
            "TINYLAB_RESULTS_DIR": str(rdir),
            "TINYLAB_ITERATION": str(ls.current_iteration),
            "TINYLAB_KNOWLEDGE_DIR": str(knowledge_dir(ctx.project_dir)),
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

    _stamp_script_provenance(phase, script, ls, ctx)
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
    try:
        script = select_phase_script(pdir, phase_id)
    except ValueError as e:
        raise StateError(str(e)) from e

    log(f"ENGINE: running optimize phase {phase_id}")
    result = run_optimize(
        base_command=f"{sys.executable} {script}",
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
        "optimization_metric": metric_name,
        "optimization_direction": direction,
        "selection_criterion": f"{direction} {metric_name}",
        "optimization_config": opt_config,
        "all_trials": result.all_trials,
        **_script_provenance(script, ctx.project_dir),
    }, indent=2, default=str))
    log(f"ENGINE: optimize phase {phase_id} done — best {metric_name}={result.best_value}")


def _stamp_script_provenance(phase: dict[str, Any], script: Path, ls: LoopState, ctx: EngineContext) -> None:
    """Record the actual executed script in the phase result JSON."""
    report_path = _phase_report_path(phase, ls, ctx)
    if not report_path.exists():
        return
    try:
        data = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return

    provenance = _script_provenance(script, ctx.project_dir)
    paths = _provenance_field_paths_to_write(data, phase)
    changed = False
    for path in paths:
        field = path[-1]
        if field in provenance and _get_provenance_path(data, path) != provenance[field]:
            if _set_provenance_path(data, path, provenance[field]):
                changed = True
    if not paths:
        for field in ("script_path", "script_sha256"):
            if data.get(field) != provenance[field]:
                data[field] = provenance[field]
                changed = True
    if changed:
        report_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _phase_report_path(phase: dict[str, Any], ls: LoopState, ctx: EngineContext) -> Path:
    report_path = phase.get("expected_outputs", {}).get("report", {}).get("path")
    if report_path:
        try:
            return resolve_research_results_path(
                ctx.project_dir,
                report_path,
                ls.current_iteration,
                "expected_outputs.report.path",
            )
        except ValueError as e:
            raise StateError(f"Unsafe report path for {phase['id']}: {e}") from e
    return results_dir(ctx.project_dir, ls.current_iteration) / f"{phase['id']}.json"


def _provenance_field_paths_to_write(data: dict[str, Any], phase: dict[str, Any]) -> list[tuple[str, ...]]:
    schema = phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
    paths = [
        *_schema_provenance_paths(schema),
        *_data_provenance_paths(data),
    ]
    paths = list(dict.fromkeys(paths))
    prefix = _preferred_provenance_prefix(paths)
    if not any(path[-1] in _CODE_PATH_FIELD_VALUES for path in paths):
        paths.append((*prefix, "script_path"))
    if not any(path[-1] in _CODE_HASH_FIELD_VALUES for path in paths):
        paths.append((*prefix, "script_sha256"))
    return list(dict.fromkeys(paths))


def _preferred_provenance_prefix(paths: list[tuple[str, ...]]) -> tuple[str, ...]:
    for path in paths:
        if path[-1] in _CODE_PATH_FIELD_VALUES or path[-1] in _CODE_HASH_FIELD_VALUES:
            return path[:-1]
    for path in paths:
        return path[:-1]
    return ()


def _schema_provenance_paths(schema: Any, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if isinstance(properties, dict):
        entries = properties.items()
    else:
        entries = (
            (key, value)
            for key, value in schema.items()
            if key not in _JSON_SCHEMA_CONTAINER_KEYS and isinstance(value, dict)
        )

    paths: list[tuple[str, ...]] = []
    for key, child in entries:
        child_path = (*prefix, str(key))
        if str(key) in _PROVENANCE_FIELD_VALUES:
            paths.append(child_path)
        paths.extend(_schema_provenance_paths(child, child_path))
    return paths


def _data_provenance_paths(value: Any, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if not isinstance(value, dict):
        return []
    paths: list[tuple[str, ...]] = []
    for key, child in value.items():
        child_path = (*prefix, str(key))
        if str(key) in _PROVENANCE_FIELD_VALUES:
            paths.append(child_path)
        paths.extend(_data_provenance_paths(child, child_path))
    return paths


def _get_provenance_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _set_provenance_path(data: dict[str, Any], path: tuple[str, ...], value: str) -> bool:
    target: Any = data
    for key in path[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]
        if not isinstance(target, dict):
            return False
    target[path[-1]] = value
    return True


def _script_provenance(script: Path, project_dir: Path) -> dict[str, str]:
    rel_script = _relative_posix(script, project_dir)
    digest = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    git_commit = _git_commit(project_dir)
    return {
        "script_path": rel_script,
        "code_path": rel_script,
        "script_sha256": digest,
        "script_sha": digest,
        "script_hash": digest,
        "code_sha256": digest,
        "code_sha": digest,
        "code_hash": digest,
        "source_hash": digest,
        "git_commit": git_commit,
        "commit_hash": git_commit,
    }


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _git_commit(project_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=2,
        )
    except Exception:
        return "unavailable"
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else "unavailable"


_PROVENANCE_FIELD_VALUES = {
    "script_path",
    "code_path",
    "script_sha256",
    "script_sha",
    "script_hash",
    "code_sha256",
    "code_sha",
    "code_hash",
    "source_hash",
    "git_commit",
    "commit_hash",
}

_CODE_PATH_FIELD_VALUES = {
    "script_path",
    "code_path",
}

_CODE_HASH_FIELD_VALUES = {
    "script_sha256",
    "script_sha",
    "script_hash",
    "code_sha256",
    "code_sha",
    "code_hash",
    "source_hash",
}

_JSON_SCHEMA_CONTAINER_KEYS = {
    "$schema",
    "$id",
    "additionalProperties",
    "description",
    "enum",
    "items",
    "properties",
    "required",
    "title",
    "type",
}


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

        try:
            report_path = resolve_research_results_path(
                ctx.project_dir,
                report_spec.get("path"),
                ls.current_iteration,
                "expected_outputs.report.path",
            )
        except ValueError as e:
            raise StateError(f"Unsafe report path for {phase_id}: {e}") from e
        if not report_path.exists():
            raise StateError(f"Expected report not found: {report_path}")

        try:
            data = json.loads(report_path.read_text())
        except json.JSONDecodeError as e:
            raise StateError(f"Invalid report JSON: {e}") from e
        object_error = validate_result_object(data)
        if object_error:
            raise StateError(object_error)
        finite_errors = validate_finite_numeric_values(data)
        if finite_errors:
            raise StateError(f"Report numeric value errors: {finite_errors}")
        provenance_errors = audit_code_provenance(ctx.project_dir, ls.current_iteration, data)
        if provenance_errors:
            raise StateError(f"Report code provenance errors: {provenance_errors}")
        identity_errors = validate_phase_identity(data, phase_id)
        if identity_errors:
            raise StateError(f"Report phase identity errors: {identity_errors}")

        schema = report_spec.get("schema", {})
        validation_fields: list[str] = []
        expected_fields: list[str] = []
        if schema:
            expected_fields = schema_expected_fields(schema)
            validation_fields = schema_fields_to_validate(data, schema, expected_fields)
            missing = [k for k in expected_fields if k not in data]
            if missing:
                raise StateError(f"Report missing fields: {missing}")
            type_errors = validate_schema_types(data, schema, expected_fields)
            if type_errors:
                raise StateError(f"Report schema type errors: {type_errors}")
        substantive_fields = list(dict.fromkeys([*validation_fields, *expected_fields, *data.keys()]))
        value_errors = validate_substantive_result_values(data, substantive_fields)
        if value_errors:
            raise StateError(f"Report substantive value errors: {value_errors}")
        consistency_errors = audit_phase_result_consistency(plan, phase_id, data)
        if consistency_errors:
            raise StateError(f"Report consistency errors: {consistency_errors}")
        contract_errors = audit_phase_result_artifact_contract(plan, phase, phase_id, data)
        if contract_errors:
            raise StateError(f"Report artifact contract errors: {contract_errors}")

        _validate_visualizations(phase, ls, ctx)

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


def _validate_visualizations(phase: dict[str, Any], ls: LoopState, ctx: EngineContext) -> None:
    """Validate that planned phase visualizations were actually generated."""
    phase_id = phase["id"]
    issues = phase_visualization_issues(ctx.project_dir, ls.current_iteration, phase)
    if not issues:
        return
    first = issues[0]
    if first.startswith("missing visualizations: "):
        raise StateError(f"Missing visualization files for {phase_id}: {first.removeprefix('missing visualizations: ')}")
    if first == "missing required PNG visualization":
        raise StateError(f"Phase {phase_id} did not generate a required PNG visualization")
    raise StateError(f"Phase {phase_id} visualization issues: {'; '.join(issues)}")
