"""Shared state gate policy for native runner hooks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Mapping

try:  # Package import path
    from .command_paths import (
        bash_pattern_matches,
        bash_write_target_paths,
        matches_any,
        tiny_lab_relative_paths,
    )
    from .tool_names import WRITE_TOOL_NAMES
except ImportError:  # Script-copied hook path
    from command_paths import (  # type: ignore
        bash_pattern_matches,
        bash_write_target_paths,
        matches_any,
        tiny_lab_relative_paths,
    )
    from tool_names import WRITE_TOOL_NAMES  # type: ignore

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tiny_lab.phase_contract import phase_script_candidates, phase_script_stem_matches  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover - hooks should fail open if package import is unavailable
    phase_script_candidates = None
    phase_script_stem_matches = None


@dataclass(frozen=True)
class GateDecision:
    """Result of evaluating a state-gate tool request."""

    allowed: bool
    reason: str | None = None


def allow_decision() -> GateDecision:
    return GateDecision(allowed=True)


def deny_decision(reason: str) -> GateDecision:
    return GateDecision(allowed=False, reason=reason)


def evaluate_runner_state_gate(
    contract: Mapping[str, Any],
    state_data: Mapping[str, Any],
    *,
    tool_name: str,
    file_paths: tuple[str, ...] | list[str] = (),
    command: str = "",
    root: Path | None = None,
) -> GateDecision:
    """Evaluate whether a native runner tool call is allowed from SSOT contract.

    `contract` is the resolved `RunnerStateContract` shape emitted by
    `tiny_lab.runner_contract.resolve_runner_state_contract` and exposed via
    `tiny-lab brief --json`. The hook handles only runtime I/O; all gate
    policy consumes this contract so engine briefings and native gates cannot
    drift on path/tool interpretation.
    """
    current_state = str(contract.get("state") or state_data.get("state") or "INIT")
    iteration = _coerce_iteration(contract.get("iteration", state_data.get("current_iteration", 1)))
    root = root or Path.cwd()

    if current_state in ("INIT", "DONE"):
        return allow_decision()

    state_type = str(contract.get("state_type") or contract.get("type") or "ai_session")

    if state_type == "unknown" and (tool_name in WRITE_TOOL_NAMES or tool_name == "Bash"):
        tiny_lab_paths = (
            tiny_lab_relative_paths(file_paths, root)
            if tool_name in WRITE_TOOL_NAMES
            else bash_write_target_paths(command, root)
        )
        if tiny_lab_paths:
            return deny_decision(
                f"BLOCKED [{current_state}]: 현재 state가 workflow에 없음. tiny-lab 영역을 쓰기 전에 "
                "research/.workflow.json 또는 research/.state.json을 복구하세요."
            )
        return allow_decision()

    if state_type == "checkpoint" and (tool_name in WRITE_TOOL_NAMES or tool_name == "Bash"):
        tiny_lab_paths = (
            tiny_lab_relative_paths(file_paths, root)
            if tool_name in WRITE_TOOL_NAMES
            else bash_write_target_paths(command, root)
        )
        if tiny_lab_paths:
            return deny_decision(
                f"BLOCKED [{current_state}]: checkpoint 상태에서는 tiny-lab 영역 쓰기 불가. intervention을 기다리세요."
            )
        return allow_decision()

    if tool_name in WRITE_TOOL_NAMES and file_paths:
        tiny_lab_paths = tiny_lab_relative_paths(file_paths, root)
        if not tiny_lab_paths:
            return allow_decision()

        allowed_tools = _list_field(contract, "allowed_tools")
        if not _write_tool_allowed(tool_name, allowed_tools):
            return deny_decision(
                f"BLOCKED [{current_state}]: {tool_name} 는 이 상태에서 허용되지 않음\n"
                f"허용 도구: {allowed_tools}"
            )

        iter_str = f"iter_{iteration}"
        blocked_globs = _list_field(contract, "blocked_write_globs")
        for path in tiny_lab_paths:
            if matches_any(path, blocked_globs, iter_str):
                return deny_decision(
                    f"BLOCKED [{current_state}]: {path} 는 이 상태에서 금지됨\n"
                    f"금지 경로: {blocked_globs}"
                )

        allowed_globs = _list_field(contract, "allowed_write_globs")
        if allowed_globs:
            for path in tiny_lab_paths:
                if not matches_any(path, allowed_globs, iter_str):
                    return deny_decision(
                        f"BLOCKED [{current_state}]: {path} 는 이 상태에서 허용되지 않음\n"
                        f"허용 경로: {allowed_globs}"
                    )

        phase_issue = _phase_code_write_issue(current_state, contract, tiny_lab_paths, iteration, root)
        if phase_issue:
            return deny_decision(phase_issue)

    if tool_name == "Bash" and command:
        allowed_tools = _list_field(contract, "allowed_tools")
        if allowed_tools and "Bash" not in allowed_tools:
            return deny_decision(
                f"BLOCKED [{current_state}]: Bash 는 이 상태에서 허용되지 않음\n"
                f"허용 도구: {allowed_tools}"
            )
        iter_str = f"iter_{iteration}"
        write_paths = bash_write_target_paths(command, root)
        blocked_globs = _list_field(contract, "blocked_write_globs")
        for path in write_paths:
            if matches_any(path, blocked_globs, iter_str):
                return deny_decision(
                    f"BLOCKED [{current_state}]: Bash command writes blocked path {path}\n"
                    f"금지 경로: {blocked_globs}"
                )
        allowed_globs = _list_field(contract, "allowed_write_globs")
        if allowed_globs:
            for path in write_paths:
                if not matches_any(path, allowed_globs, iter_str):
                    return deny_decision(
                        f"BLOCKED [{current_state}]: Bash command writes path {path} outside allowed paths\n"
                        f"허용 경로: {allowed_globs}"
                    )
        phase_issue = _phase_code_write_issue(current_state, contract, write_paths, iteration, root)
        if phase_issue:
            return deny_decision(phase_issue)
        for pattern in _list_field(contract, "blocked_bash_patterns"):
            if bash_pattern_matches(command, pattern, iter_str):
                return deny_decision(f"BLOCKED [{current_state}]: 이 명령은 현재 상태에서 금지됨 ({pattern})")

    return allow_decision()


def evaluate_state_gate(
    spec: Mapping[str, Any],
    state_data: Mapping[str, Any],
    *,
    tool_name: str,
    file_paths: tuple[str, ...] | list[str] = (),
    command: str = "",
    root: Path | None = None,
) -> GateDecision:
    """Compatibility wrapper for callers that still pass raw workflow specs."""
    from tiny_lab.runner_contract import resolve_runner_state_contract

    current_state = str(state_data.get("state") or spec.get("id") or "INIT")
    iteration = _coerce_iteration(state_data.get("current_iteration", 1))
    current_phase_id = state_data.get("current_phase_id")
    contract = resolve_runner_state_contract(
        state_id=current_state,
        iteration=iteration,
        current_phase_id=None if current_phase_id is None else str(current_phase_id),
        spec=spec,
        default_engine=str(state_data.get("engine") or "claude"),
    ).to_dict()
    return evaluate_runner_state_gate(
        contract,
        state_data,
        tool_name=tool_name,
        file_paths=file_paths,
        command=command,
        root=root,
    )


def _list_field(spec: Mapping[str, Any], key: str) -> list[str]:
    value = spec.get(key, [])
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _coerce_iteration(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _write_tool_allowed(tool_name: str, allowed_tools: list[str]) -> bool:
    if not allowed_tools:
        return True
    if tool_name == "MultiEdit":
        return "MultiEdit" in allowed_tools or "Edit" in allowed_tools
    return tool_name in allowed_tools


def _phase_code_write_issue(
    current_state: str,
    state_data: Mapping[str, Any],
    tiny_lab_paths: list[str],
    iteration: int | str,
    root: Path,
) -> str | None:
    if current_state != "PHASE_CODE":
        return None
    if phase_script_candidates is None or phase_script_stem_matches is None:
        return None

    phase_dir = Path("research") / f"iter_{iteration}" / "phases"
    current_phase_id = state_data.get("current_phase_id")
    for path in tiny_lab_paths:
        rel = Path(path)
        if rel.parent != phase_dir or rel.suffix != ".py":
            continue
        if not current_phase_id:
            return "BLOCKED [PHASE_CODE]: current_phase_id 없음; phase script를 안전하게 선택할 수 없음"
        current_phase_id = str(current_phase_id)
        if not phase_script_stem_matches(rel.stem, current_phase_id):
            return (
                f"BLOCKED [PHASE_CODE]: {path} 는 현재 phase `{current_phase_id}`의 script가 아님\n"
                f"허용 stem: `{current_phase_id}`, `{current_phase_id}_...`, `{current_phase_id}-...`"
            )

        try:
            existing = [
                candidate.relative_to(root).as_posix()
                for candidate in phase_script_candidates(root / phase_dir, current_phase_id)
            ]
        except ValueError:
            existing = []
        conflicts = [candidate for candidate in existing if candidate != path]
        if conflicts:
            return (
                f"BLOCKED [PHASE_CODE]: {path} 를 쓰면 현재 phase `{current_phase_id}`의 "
                f"script가 여러 개가 됨\n기존 script: {conflicts}"
            )
    return None
