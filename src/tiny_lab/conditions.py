"""Conditional transition resolver.

Handles both file-based conditions (read YAML field) and
built-in checks (has_pending_phases, etc.).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import json

from .errors import StateError
from .paths import convergence_log_path
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
    """Read a field from a JSON file."""
    resolved = source.replace("{iter}", f"iter_{iteration}")
    path = project_dir / "research" / resolved
    if not path.exists():
        raise StateError(f"Condition source not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise StateError(f"Invalid JSON in {path}: {e}")
    if not isinstance(data, dict) or field_name not in data:
        raise StateError(f"Field '{field_name}' not found in {path}")
    return data[field_name]


def _run_builtin_check(check_name: str, project_dir: Path, iteration: int) -> bool:
    """Run a built-in check function."""
    checks = {
        "has_pending_phases": _check_has_pending_phases,
        "is_converging": _check_is_converging,
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


def _check_is_converging(project_dir: Path, iteration: int) -> bool:
    """Check if recent iterations show convergence (repeating approaches).

    Uses Jaccard similarity on seed keywords and approach category streaks.
    Reads thresholds from .workflow.json exploration config.
    """
    log_path = convergence_log_path(project_dir)
    if not log_path.exists():
        return False

    try:
        log_data = json.loads(log_path.read_text())
        entries = log_data.get("entries", [])
    except Exception:
        return False

    # Load exploration config from workflow
    from .paths import workflow_path
    config: dict[str, Any] = {}
    wp = workflow_path(project_dir)
    if wp.exists():
        try:
            wf = json.loads(wp.read_text())
            config = wf.get("exploration", {})
        except Exception:
            pass

    window = config.get("convergence_window", 3)
    similarity_threshold = config.get("similarity_threshold", 0.7)
    force_after = config.get("force_explore_after", 5)

    if len(entries) < window:
        return False

    recent = entries[-window:]

    # Check 1: same approach_category streak
    categories = [e.get("approach_category", "") for e in entries]
    if len(categories) >= force_after and len(set(categories[-force_after:])) == 1:
        return True

    # Check 2: Jaccard similarity of seed keywords
    recent_kw = [set(e.get("seed_keywords", [])) for e in recent]
    similarities: list[float] = []
    for i in range(len(recent_kw) - 1):
        a, b = recent_kw[i], recent_kw[i + 1]
        union = len(a | b)
        if union > 0:
            similarities.append(len(a & b) / union)
    if similarities:
        avg_sim = sum(similarities) / len(similarities)
        if avg_sim > similarity_threshold:
            return True

    return False
