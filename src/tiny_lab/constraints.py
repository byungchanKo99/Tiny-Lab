"""Validation helpers for research/constraints.json."""
from __future__ import annotations

import math
from typing import Any


def constraints_validation_issues(data: object) -> list[str]:
    """Return human-readable schema issues for constraints.json."""
    if not isinstance(data, dict):
        return ["constraints must be a JSON object"]

    issues: list[str] = []

    if not _non_empty_string(data.get("objective")):
        issues.append("'objective' must be a non-empty string")

    goal = data.get("goal")
    if not isinstance(goal, dict):
        issues.append("'goal' must be an object")
    else:
        success_criteria = goal.get("success_criteria")
        metric = goal.get("metric")
        direction = goal.get("direction")
        target = goal.get("target")

        has_success_criteria = _non_empty_string(success_criteria)
        has_metric_target = (
            _non_empty_string(metric)
            and direction in ("minimize", "maximize")
            and _finite_number(target)
        )

        if direction is not None and direction not in ("minimize", "maximize"):
            issues.append("'goal.direction' must be 'minimize', 'maximize', or null")
        if target is not None and not _finite_number(target):
            issues.append("'goal.target' must be a finite number or null")
        if not has_success_criteria and not has_metric_target:
            issues.append(
                "'goal' must define non-empty success_criteria or metric/direction/target"
            )

    invariants = data.get("invariants")
    if (
        not isinstance(invariants, list)
        or not invariants
        or not all(_non_empty_string(item) for item in invariants)
    ):
        issues.append("'invariants' must be a non-empty list of non-empty strings")

    exploration_bounds = data.get("exploration_bounds")
    if exploration_bounds is not None:
        if not isinstance(exploration_bounds, dict):
            issues.append("'exploration_bounds' must be an object when present")
        else:
            for key in ("allowed", "forbidden"):
                value = exploration_bounds.get(key)
                if value is not None and (
                    not isinstance(value, list)
                    or not all(_non_empty_string(item) for item in value)
                ):
                    issues.append(
                        f"'exploration_bounds.{key}' must be a list of non-empty strings"
                    )

    review_response = data.get("review_response")
    if review_response is not None and not isinstance(review_response, dict):
        issues.append("'review_response' must be an object when present")

    return issues


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
