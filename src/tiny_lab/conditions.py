"""Conditional transition resolver.

Handles both file-based conditions (read YAML field) and
built-in checks (has_pending_phases, etc.).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import StateError
from .workflow import ConditionSpec


def resolve_condition(
    condition: ConditionSpec,
    next_map: dict[str, str],
    project_dir: Path,
    iteration: int,
) -> str:
    """Evaluate a condition and return the next state id."""
    if condition.check:
        value = _run_builtin_check(condition.check, project_dir, iteration)
    elif condition.source and condition.field:
        value = _read_field(condition.source, condition.field, project_dir, iteration)
    else:
        raise StateError("Condition must have 'check' or 'source'+'field'")

    value_str = str(value).lower() if isinstance(value, bool) else str(value)
    if value_str in next_map:
        return next_map[value_str]
    if "default" in next_map:
        return next_map["default"]
    raise StateError(f"No matching next for condition value '{value_str}'. "
                     f"Available: {list(next_map.keys())}")


def _read_field(source: str, field_name: str, project_dir: Path, iteration: int) -> Any:
    """Read a field from a YAML file."""
    resolved = source.replace("{iter}", f"iter_{iteration}")
    path = project_dir / "research" / resolved
    if not path.exists():
        raise StateError(f"Condition source not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or field_name not in data:
        raise StateError(f"Field '{field_name}' not found in {path}")
    return data[field_name]


def _run_builtin_check(check_name: str, project_dir: Path, iteration: int) -> bool:
    """Run a built-in check function."""
    checks = {
        "has_pending_phases": _check_has_pending_phases,
    }
    fn = checks.get(check_name)
    if fn is None:
        raise StateError(f"Unknown built-in check: {check_name}")
    return fn(project_dir, iteration)


def _check_has_pending_phases(project_dir: Path, iteration: int) -> bool:
    """Check if the research plan has any pending phases."""
    from .plan import load_plan, pending_phases
    try:
        plan = load_plan(project_dir, iteration)
        return len(pending_phases(plan)) > 0
    except Exception:
        return False
