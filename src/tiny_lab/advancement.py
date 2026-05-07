"""Shared completion advancement for the engine and native runner hooks."""
from __future__ import annotations

import fnmatch
import glob as g
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from .conditions import resolve_condition, select_next_target
from .constraints import constraints_validation_issues
from .gates import (
    completion_artifact_quality_issue,
    completion_quality_issue,
    requires_completion_artifact_quality_gate,
    requires_completion_quality_artifact,
)
from .paths import (
    iter_dir,
    iterations_path,
    normalize_project_relative_path,
    phases_dir,
    reflect_path,
    research_relative_path_issue,
    results_dir,
)
from .phase_contract import phase_script_stem_matches, select_phase_script
from .runtime_placeholders import resolve_runtime_placeholders
from .state import LoopState, load_state, set_state
from .workflow import CompletionSpec, ConditionSpec, StateSpec

if TYPE_CHECKING:
    from .runner_contract import RunnerStateContract


ITERATION_ENTRY_STATES = frozenset({"IDEA_REFINE", "DOMAIN_RESEARCH"})
ITERATION_SEED_FILENAME = ".iteration_seed.json"
NEW_ITERATION_SOURCE_STATES = frozenset({
    "EXPLORE",
    "REFLECT_DONE",
    "REVIEW_DONE",
    "ROUTE",
})
SESSION_RESET_STATES = frozenset({
    "SHAPE_FULL",
    "PHASE_SELECT",
    "STORY_TELL",
})


@dataclass(frozen=True)
class CompletionAdvance:
    """Result of checking whether a state completion artifact can advance."""

    relevant: bool
    pattern: str = ""
    matches: tuple[Path, ...] = field(default_factory=tuple)
    artifact_path: Path | None = None
    next_state: str | None = None
    problem: str | None = None


@dataclass(frozen=True)
class AppliedStateTransition:
    """Result of applying a resolved state transition."""

    state_before: str
    state_after: str
    iteration_before: int
    iteration_after: int
    created_iteration: bool = False
    reset_session: bool = False


def resolve_completion_advance(
    project_dir: Path,
    spec: StateSpec | Mapping[str, Any],
    state_id: str,
    iteration: int,
    *,
    current_phase_id: str | None = None,
    written_file: str | Path | None = None,
) -> CompletionAdvance:
    """Resolve artifact-based completion for an AI-session state.

    This is the SSOT used by both the CLI engine and PostToolUse native
    runner hook. It intentionally performs only deterministic checks and
    returns the transition to apply; callers remain responsible for writing
    `.state.json`.
    """
    completion = _completion(spec)
    if completion is None or not completion.artifact:
        return CompletionAdvance(relevant=False)

    return _resolve_completion_advance_from_values(
        project_dir,
        state_id=state_id,
        iteration=iteration,
        current_phase_id=current_phase_id,
        completion_artifact=completion.artifact,
        completion_required_fields=completion.required_fields,
        condition=_condition(spec),
        next_value=_get(spec, "next"),
        written_file=written_file,
    )


def resolve_runner_completion_advance(
    project_dir: Path,
    contract: "RunnerStateContract" | Mapping[str, Any],
    *,
    written_file: str | Path | None = None,
) -> CompletionAdvance:
    """Resolve artifact completion from the shared runner state contract."""
    completion_artifact = _contract_get(contract, "completion_artifact")
    if not completion_artifact:
        return CompletionAdvance(relevant=False)

    return _resolve_completion_advance_from_values(
        project_dir,
        state_id=str(_contract_get(contract, "state", "")),
        iteration=_coerce_iteration(_contract_get(contract, "iteration", 1)),
        current_phase_id=_optional_contract_str(_contract_get(contract, "current_phase_id")),
        completion_artifact=str(completion_artifact),
        completion_required_fields=_contract_get(contract, "completion_required_fields", ()),
        condition=_contract_get(contract, "condition"),
        next_value=_contract_get(contract, "next"),
        written_file=written_file,
    )


def _resolve_completion_advance_from_values(
    project_dir: Path,
    *,
    state_id: str,
    iteration: int,
    current_phase_id: str | None,
    completion_artifact: str,
    completion_required_fields: Iterable[str],
    condition: ConditionSpec | Mapping[str, Any] | None,
    next_value: str | Mapping[str, str] | None,
    written_file: str | Path | None,
) -> CompletionAdvance:
    resolved_pattern = resolve_runtime_placeholders(
        completion_artifact,
        iteration=iteration,
        current_phase_id=current_phase_id,
    )
    artifact_issue = research_relative_path_issue(resolved_pattern, "completion.artifact")
    if artifact_issue:
        return CompletionAdvance(
            relevant=True,
            pattern=str(project_dir / resolved_pattern),
            problem=f"unsafe completion artifact: {artifact_issue}",
        )
    phase_matches = _matching_phase_code_artifacts(
        project_dir,
        state_id,
        iteration,
        current_phase_id,
        written_file,
    )
    if phase_matches is not None:
        matches, phase_problem = phase_matches
        if written_file is not None and matches is None:
            return CompletionAdvance(relevant=False, pattern=str(project_dir / resolved_pattern))
        if phase_problem:
            return CompletionAdvance(
                relevant=True,
                pattern=str(project_dir / resolved_pattern),
                matches=tuple(matches or []),
                problem=phase_problem,
            )
    else:
        matches = _matching_artifacts(project_dir, resolved_pattern, written_file)
    if written_file is not None and matches is None:
        return CompletionAdvance(relevant=False, pattern=str(project_dir / resolved_pattern))
    if not matches:
        return CompletionAdvance(relevant=True, pattern=str(project_dir / resolved_pattern), problem="artifact file not found")

    artifact_path = matches[0]
    requires_quality_gate = requires_completion_quality_artifact(state_id)
    requires_artifact_quality_gate = requires_completion_artifact_quality_gate(state_id)
    requires_constraints_gate = _is_constraints_artifact(resolved_pattern)
    if requires_artifact_quality_gate:
        artifact_quality_issue = completion_artifact_quality_issue(project_dir, state_id, artifact_path, iteration)
        if artifact_quality_issue:
            return CompletionAdvance(
                relevant=True,
                pattern=str(project_dir / resolved_pattern),
                matches=tuple(matches),
                artifact_path=artifact_path,
                problem=artifact_quality_issue,
            )
    required_fields = tuple(str(field) for field in completion_required_fields)
    if required_fields or requires_quality_gate or requires_constraints_gate:
        try:
            data = json.loads(artifact_path.read_text())
        except json.JSONDecodeError as e:
            return CompletionAdvance(
                relevant=True,
                pattern=str(project_dir / resolved_pattern),
                matches=tuple(matches),
                artifact_path=artifact_path,
                problem=f"invalid JSON in artifact: {e}",
            )
        if not isinstance(data, dict):
            return CompletionAdvance(
                relevant=True,
                pattern=str(project_dir / resolved_pattern),
                matches=tuple(matches),
                artifact_path=artifact_path,
                problem=f"artifact is not a JSON object (got {type(data).__name__})",
            )
        if required_fields:
            missing = [field for field in required_fields if field not in data]
            if missing:
                actual_keys = list(data.keys())
                return CompletionAdvance(
                    relevant=True,
                    pattern=str(project_dir / resolved_pattern),
                    matches=tuple(matches),
                    artifact_path=artifact_path,
                    problem=f"missing required fields {missing}, file has: {actual_keys}",
                )
        freshness_issue = _completion_freshness_issue(state_id, data, current_phase_id)
        if freshness_issue:
            return CompletionAdvance(
                relevant=True,
                pattern=str(project_dir / resolved_pattern),
                matches=tuple(matches),
                artifact_path=artifact_path,
                problem=freshness_issue,
            )
        if requires_quality_gate:
            quality_issue = completion_quality_issue(project_dir, state_id, data, iteration)
            if quality_issue:
                return CompletionAdvance(
                    relevant=True,
                    pattern=str(project_dir / resolved_pattern),
                    matches=tuple(matches),
                    artifact_path=artifact_path,
                    problem=quality_issue,
                )
        if requires_constraints_gate:
            constraints_issues = constraints_validation_issues(data)
            if constraints_issues:
                return CompletionAdvance(
                    relevant=True,
                    pattern=str(project_dir / resolved_pattern),
                    matches=tuple(matches),
                    artifact_path=artifact_path,
                    problem="invalid constraints: " + "; ".join(constraints_issues),
                )

    next_state, transition_problem = _resolve_next_state_values(
        condition,
        next_value,
        project_dir,
        iteration,
        current_phase_id=current_phase_id,
    )
    if transition_problem:
        return CompletionAdvance(
            relevant=True,
            pattern=str(project_dir / resolved_pattern),
            matches=tuple(matches),
            artifact_path=artifact_path,
            problem=transition_problem,
        )

    return CompletionAdvance(
        relevant=True,
        pattern=str(project_dir / resolved_pattern),
        matches=tuple(matches),
        artifact_path=artifact_path,
        next_state=next_state,
    )


def _is_constraints_artifact(resolved_pattern: str) -> bool:
    return Path(resolved_pattern).as_posix() == "research/constraints.json"


def _completion_freshness_issue(state_id: str, data: dict[str, Any], current_phase_id: str | None) -> str | None:
    if state_id != "HYPOTHESIS_UPDATE":
        return None
    if not current_phase_id:
        return "hypothesis update requires current_phase_id"
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return "hypothesis log entries must include the current phase"
    latest = entries[-1]
    if not isinstance(latest, dict):
        return "latest hypothesis log entry must be an object"
    if latest.get("phase_id") != current_phase_id:
        return (
            "stale hypothesis log: latest entry phase_id "
            f"{latest.get('phase_id')!r} does not match current_phase_id {current_phase_id!r}"
        )
    return None


def _completion(spec: StateSpec | Mapping[str, Any]) -> CompletionSpec | None:
    raw = _get(spec, "completion")
    if raw is None:
        return None
    if isinstance(raw, CompletionSpec):
        return raw
    if isinstance(raw, Mapping):
        return CompletionSpec(
            artifact=str(raw.get("artifact", "")),
            required_fields=list(raw.get("required_fields", [])),
        )
    return None


def _condition(spec: StateSpec | Mapping[str, Any]) -> ConditionSpec | None:
    return _condition_from_value(_get(spec, "condition"))


def _condition_from_value(raw: Any) -> ConditionSpec | None:
    if raw is None:
        return None
    if isinstance(raw, ConditionSpec):
        return raw
    if isinstance(raw, Mapping):
        return ConditionSpec(
            source=raw.get("source"),
            field=raw.get("field"),
            check=raw.get("check"),
        )
    return None


def _contract_get(contract: "RunnerStateContract" | Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(contract, Mapping):
        return contract.get(key, default)
    return getattr(contract, key, default)


def _optional_contract_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _get(spec: StateSpec | Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(spec, Mapping):
        return spec.get(key, default)
    return getattr(spec, key, default)


def _matching_artifacts(
    project_dir: Path,
    resolved_pattern: str,
    written_file: str | Path | None,
) -> list[Path] | None:
    if written_file is not None:
        try:
            written_rel = normalize_project_relative_path(project_dir, written_file, "written_file")
        except ValueError:
            return None
        written = written_rel.as_posix()
        if not fnmatch.fnmatch(written, resolved_pattern):
            return None
        path = project_dir / written_rel
        return [path] if path.exists() else []

    return [Path(match) for match in sorted(g.glob(str(project_dir / resolved_pattern)))]


def _matching_phase_code_artifacts(
    project_dir: Path,
    state_id: str,
    iteration: int,
    current_phase_id: str | None,
    written_file: str | Path | None,
) -> tuple[list[Path] | None, str | None] | None:
    if state_id != "PHASE_CODE":
        return None
    if not current_phase_id:
        return [], "PHASE_CODE completion requires current_phase_id"

    pdir = project_dir / "research" / f"iter_{iteration}" / "phases"
    written_path: Path | None = None
    if written_file is not None:
        try:
            written_rel = normalize_project_relative_path(project_dir, written_file, "written_file")
        except ValueError:
            return None, None
        written_path = project_dir / written_rel
        if written_rel.parent.as_posix() != f"research/iter_{iteration}/phases" or written_rel.suffix != ".py":
            return None, None
        if not phase_script_stem_matches(written_rel.stem, current_phase_id):
            return [], (
                f"completion artifact {written_rel.as_posix()} does not match "
                f"current_phase_id {current_phase_id}"
            )
        if not written_path.exists():
            return [], "artifact file not found"

    try:
        selected = select_phase_script(pdir, current_phase_id)
    except ValueError as e:
        return [], str(e)
    if written_path is not None and selected != written_path:
        return [], (
            f"written artifact {written_path.relative_to(project_dir).as_posix()} is not "
            f"the unique selected script for current_phase_id {current_phase_id}"
        )
    return [selected], None


def apply_state_transition(
    project_dir: Path,
    next_state: str,
    *,
    current_state: LoopState | Mapping[str, Any] | None = None,
    state_overrides: Mapping[str, Any] | None = None,
    new_iteration_on_entry: bool = False,
) -> AppliedStateTransition:
    """Apply a resolved transition through the shared engine/native policy.

    The engine, AI-session artifact path, and native PostToolUse hook all call
    this function after transition resolution so session-reset and iteration
    entry semantics cannot drift.
    """
    current = _coerce_loop_state(project_dir, current_state)
    overrides = dict(state_overrides or {})
    iteration_before = _coerce_iteration(current.current_iteration)
    created_iteration = False
    reset_session = False

    if new_iteration_on_entry and next_state in ITERATION_ENTRY_STATES:
        iteration_after = iteration_before + 1
        create_iteration_dirs(project_dir, iteration_after)
        carry_over_iteration(project_dir, iteration_before, iteration_after, next_state)
        overrides["current_iteration"] = iteration_after
        overrides["session_id"] = None
        created_iteration = True
        reset_session = True
    else:
        iteration_after = iteration_before
        if next_state in SESSION_RESET_STATES:
            overrides["session_id"] = None
            reset_session = True

    applied = set_state(project_dir, next_state, **overrides)
    return AppliedStateTransition(
        state_before=current.state,
        state_after=next_state,
        iteration_before=iteration_before,
        iteration_after=_coerce_iteration(applied.current_iteration),
        created_iteration=created_iteration,
        reset_session=reset_session,
    )


def transition_starts_new_iteration(source_state: str | None, next_state: str | None) -> bool:
    """Return whether a source/target transition enters a fresh iteration."""
    return (
        str(source_state or "") in NEW_ITERATION_SOURCE_STATES
        and str(next_state or "") in ITERATION_ENTRY_STATES
    )


def create_iteration_dirs(project_dir: Path, iteration: int) -> None:
    """Create the standard directories for an iteration."""
    idir = iter_dir(project_dir, iteration)
    idir.mkdir(parents=True, exist_ok=True)
    phases_dir(project_dir, iteration).mkdir(exist_ok=True)
    results_dir(project_dir, iteration).mkdir(exist_ok=True)


def carry_over_iteration(project_dir: Path, from_iter: int, to_iter: int, entry_state: str) -> None:
    """Carry over reusable artifacts when entering a new iteration."""
    src = iter_dir(project_dir, from_iter)
    dst = iter_dir(project_dir, to_iter)

    carry_map = {
        "DATA_DEEP_DIVE": [".domain_research.json"],
        "DOMAIN_RESEARCH": [".explore_seed.json"],
        "IDEA_REFINE": [".domain_research.json", ".data_analysis.json", ".data_viz_manifest.json", "data_viz"],
        "PLAN": [".domain_research.json", ".data_analysis.json", ".idea_refined.json"],
    }
    for fname in carry_map.get(entry_state, []):
        src_file = src / fname
        if src_file.exists():
            dst.mkdir(parents=True, exist_ok=True)
            if src_file.is_dir():
                shutil.copytree(src_file, dst / fname, dirs_exist_ok=True)
            else:
                shutil.copy2(src_file, dst / fname)

    write_iteration_seed(project_dir, from_iter, to_iter, entry_state)
    update_iterations_log(project_dir, from_iter)


def write_iteration_seed(project_dir: Path, from_iter: int, to_iter: int, entry_state: str) -> bool:
    """Write the next-iteration seed from EXPLORE or reflect evidence."""
    if entry_state not in ITERATION_ENTRY_STATES:
        return False
    seed = _iteration_seed_payload(project_dir, from_iter, entry_state)
    if not seed:
        return False
    dst = iter_dir(project_dir, to_iter) / ITERATION_SEED_FILENAME
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
    return True


def _iteration_seed_payload(project_dir: Path, from_iter: int, entry_state: str) -> dict[str, Any] | None:
    explore_path = iter_dir(project_dir, from_iter) / ".explore_seed.json"
    explore = _load_json_object(explore_path)
    if explore:
        return {
            "source_iteration": from_iter,
            "source_artifact": f"research/iter_{from_iter}/.explore_seed.json",
            "entry_state": entry_state,
            "seed_type": "explore",
            "new_idea": _first_non_empty(
                explore.get("new_seed"),
                explore.get("selected_direction"),
                explore.get("direction"),
            ),
            "rationale": explore.get("rationale"),
            "selected_direction": explore.get("selected_direction"),
            "difference_from_recent": explore.get("difference_from_recent"),
            "approach_category": explore.get("approach_category"),
        }

    reflect = _load_json_object(reflect_path(project_dir, from_iter))
    if not reflect:
        return None
    seed = _promoted_seed(reflect.get("future_iteration_seeds"))
    new_idea = _first_non_empty(reflect.get("new_idea"), _seed_text(seed))
    if not new_idea and not seed and not reflect.get("framing_change"):
        return None
    return {
        "source_iteration": from_iter,
        "source_artifact": f"research/iter_{from_iter}/reflect.json",
        "entry_state": entry_state,
        "seed_type": "reflect",
        "decision": reflect.get("decision"),
        "new_idea": new_idea,
        "rationale": reflect.get("reason"),
        "selected_direction": reflect.get("selected_direction"),
        "selection_rationale": reflect.get("selection_rationale"),
        "idea_portfolio": reflect.get("idea_portfolio"),
        "future_iteration_seed": seed,
        "pivot_trigger": reflect.get("pivot_trigger"),
        "framing_change": reflect.get("framing_change"),
        "carry_over": reflect.get("carry_over"),
    }


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _promoted_seed(value: Any) -> Any:
    if not isinstance(value, list) or not value:
        return None
    for item in value:
        if isinstance(item, Mapping) and item.get("status") == "promote_next":
            return dict(item)
    return value[0]


def _seed_text(seed: Any) -> str | None:
    if isinstance(seed, str) and seed.strip():
        return seed.strip()
    if isinstance(seed, Mapping):
        for key in ("new_idea", "new_seed", "idea", "direction"):
            value = seed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return value.strip()
        elif value not in (None, "", [], {}):
            return value
    return None


def update_iterations_log(project_dir: Path, completed_iter: int) -> None:
    """Record that an iteration has been superseded."""
    ipath = iterations_path(project_dir)
    data: dict[str, Any] = {"current_iteration": completed_iter + 1, "iterations": []}
    if ipath.exists():
        try:
            loaded = json.loads(ipath.read_text())
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            pass

    rpath = reflect_path(project_dir, completed_iter)
    reflect: dict[str, Any] = {}
    if rpath.exists():
        try:
            loaded_reflect = json.loads(rpath.read_text())
            if isinstance(loaded_reflect, dict):
                reflect = loaded_reflect
        except json.JSONDecodeError:
            pass

    iterations = data.setdefault("iterations", [])
    if not isinstance(iterations, list):
        iterations = []
        data["iterations"] = iterations
    iterations.append({
        "id": completed_iter,
        "decision": reflect.get("decision", "unknown"),
        "reason": reflect.get("reason", ""),
    })
    data["current_iteration"] = completed_iter + 1
    ipath.parent.mkdir(parents=True, exist_ok=True)
    ipath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _coerce_loop_state(
    project_dir: Path,
    current_state: LoopState | Mapping[str, Any] | None,
) -> LoopState:
    if current_state is None:
        return load_state(project_dir)
    if isinstance(current_state, LoopState):
        return current_state
    return LoopState(
        current_iteration=_coerce_iteration(current_state.get("current_iteration", 1)),
        state=str(current_state.get("state", "INIT")),
        current_phase_id=(
            str(current_state["current_phase_id"])
            if current_state.get("current_phase_id") is not None
            else None
        ),
        resumable=bool(current_state.get("resumable", True)),
        consecutive_failures=_coerce_int(current_state.get("consecutive_failures", 0), 0),
        phase_retries=_coerce_int(current_state.get("phase_retries", 0), 0),
        session_id=(
            str(current_state["session_id"])
            if current_state.get("session_id") is not None
            else None
        ),
    )


def _coerce_iteration(value: Any) -> int:
    return _coerce_int(value, 1)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def resolve_next_state(
    spec: StateSpec | Mapping[str, Any],
    project_dir: Path,
    iteration: int,
    *,
    current_phase_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve `spec.next` for engine and native runner advancement paths.

    This keeps conditional transition handling in one place for parsed
    workflow specs and raw workflow JSON consumed by native hooks.
    """
    return _resolve_next_state_values(
        _condition(spec),
        _get(spec, "next"),
        project_dir,
        iteration,
        current_phase_id=current_phase_id,
    )


def _resolve_next_state_values(
    condition: ConditionSpec | Mapping[str, Any] | None,
    next_value: Any,
    project_dir: Path,
    iteration: int,
    *,
    current_phase_id: str | None = None,
) -> tuple[str | None, str | None]:
    if isinstance(next_value, str):
        return next_value, None
    if isinstance(next_value, Mapping):
        condition_spec = _condition_from_value(condition)
        if condition_spec is None:
            return None, "conditional transition is missing condition"
        try:
            return (
                resolve_condition(
                    condition_spec,
                    dict(next_value),
                    project_dir,
                    iteration,
                    current_phase_id=current_phase_id,
                ),
                None,
            )
        except Exception as e:
            return None, f"condition resolution failed: {e}"
    return None, None


def resolve_next_state_from_value(
    spec: StateSpec | Mapping[str, Any],
    value: Any,
    *,
    fallback_values: Iterable[Any] = (),
    default_state: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve `spec.next` when a handler has already computed the branch value.

    Checkpoint interventions and reflection decisions should use this instead
    of hand-reading `spec.next`, so their map selection policy stays aligned
    with conditional transitions and native hook advancement.
    """
    next_value = _get(spec, "next")
    if isinstance(next_value, str):
        return next_value, None
    if isinstance(next_value, Mapping):
        try:
            return (
                select_next_target(
                    next_value,
                    value,
                    fallback_values=fallback_values,
                    default_state=default_state,
                ),
                None,
            )
        except Exception as e:
            return None, f"next-state value resolution failed: {e}"
    return default_state, None
