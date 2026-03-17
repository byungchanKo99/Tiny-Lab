"""Lightweight schema validation for Tiny-Lab data contracts.

No external dependencies — validates required fields, types, enums, and ranges.
"""
from __future__ import annotations

from typing import Any


class ValidationError(ValueError):
    """Raised when data fails schema validation."""

    def __init__(self, errors: list[str], schema_name: str = ""):
        self.errors = errors
        self.schema_name = schema_name
        msg = f"Validation failed for '{schema_name}':\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

HYPOTHESIS_ENTRY = {
    "required": {"id": str, "status": str, "description": str},
    "optional": {
        "reasoning": str,
        # v1 fields (lever-based)
        "lever": str,
        "value": (str, int, float, dict),
        # v2 fields (approach-based)
        "approach": str,
        "search_space": dict,
        "code_changes": str,
        "references": list,
        "optimize_type": str,
        "optimize_script": str,
    },
    "enums": {"status": {"pending", "running", "done", "skipped"}},
}

HYPOTHESIS_QUEUE = {
    "required": {"hypotheses": list},
}

EVAL_RESULT = {
    "required": {"score": (int, float)},
    "optional": {"reasoning": str, "criteria_scores": dict, "strengths": list, "weaknesses": list},
}

LEDGER_ENTRY = {
    "required": {
        "id": str,
        "question": str,
        "family": str,
        "changed_variable": str,
        "status": str,
        "class": str,
        "primary_metric": dict,
        "decision": str,
    },
    "optional": {
        "value": (str, int, float, dict, type(None)), "control": str, "notes": str,
        "hypothesis_id": str, "config": dict, "reasoning": str,
        "optimize_result": dict, "approach": str,
    },
    "enums": {"class": {"WIN", "LOSS", "INVALID", "INCONCLUSIVE", "BASELINE"}},
}

PROJECT_CONFIG = {
    "required": {"name": str, "baseline": dict, "metric": dict, "levers": dict},
    "optional": {
        "description": str, "build": dict, "run": dict, "evaluate": dict,
        "schema_version": int,
        "lane": str, "workdir": str, "calibration": dict, "rules": list,
        "immutable_files": list,
    },
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "hypothesis_entry": HYPOTHESIS_ENTRY,
    "hypothesis_queue": HYPOTHESIS_QUEUE,
    "eval_result": EVAL_RESULT,
    "ledger_entry": LEDGER_ENTRY,
    "project_config": PROJECT_CONFIG,
}


# ---------------------------------------------------------------------------
# Validation engine
# ---------------------------------------------------------------------------

def _check_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    """Check if value matches expected type(s)."""
    if isinstance(expected, tuple):
        return isinstance(value, expected)
    return isinstance(value, expected)


def _validate_data(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate data against a schema definition. Returns list of error strings."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    # Required fields
    for field, expected_type in schema.get("required", {}).items():
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
        elif not _check_type(data[field], expected_type):
            actual = type(data[field]).__name__
            if isinstance(expected_type, tuple):
                expected_names = "|".join(t.__name__ for t in expected_type)
            else:
                expected_names = expected_type.__name__
            errors.append(f"Field '{field}': expected {expected_names}, got {actual}")

    # Optional fields (type check only if present)
    for field, expected_type in schema.get("optional", {}).items():
        if field in data and data[field] is not None and not _check_type(data[field], expected_type):
            actual = type(data[field]).__name__
            if isinstance(expected_type, tuple):
                expected_names = "|".join(t.__name__ for t in expected_type)
            else:
                expected_names = expected_type.__name__
            errors.append(f"Field '{field}': expected {expected_names}, got {actual}")

    # Enum checks
    for field, allowed in schema.get("enums", {}).items():
        if field in data and data[field] not in allowed:
            errors.append(f"Field '{field}': '{data[field]}' not in {sorted(allowed)}")

    return errors


def validate(data: Any, schema_name: str, *, strict: bool = True) -> list[str]:
    """Validate data against a named schema.

    Args:
        data: The data to validate.
        schema_name: Key in SCHEMAS dict.
        strict: If True, raise ValidationError on failure. If False, return error list.

    Returns:
        List of error strings (empty if valid).

    Raises:
        ValidationError: If strict=True and validation fails.
        KeyError: If schema_name is not found.
    """
    if schema_name not in SCHEMAS:
        raise KeyError(f"Unknown schema: '{schema_name}'. Available: {sorted(SCHEMAS.keys())}")

    schema = SCHEMAS[schema_name]
    errors = _validate_data(data, schema)

    if errors and strict:
        raise ValidationError(errors, schema_name)

    return errors


def validate_hypothesis_entry(entry: dict[str, Any], *, strict: bool = True) -> list[str]:
    """Validate a single hypothesis entry.

    Supports two formats:
    - v1 (deprecated): lever + value (traditional flag-based)
    - v2 (preferred): approach (strategy-based, optimizer handles params)
    At least one format must be present.
    """
    errors = validate(entry, "hypothesis_entry", strict=False)

    # Cross-field validation: must have (lever + value) OR approach
    if isinstance(entry, dict):
        has_v1 = "lever" in entry and "value" in entry
        has_v2 = "approach" in entry
        if not has_v1 and not has_v2:
            hint = ""
            if "changed_variable" in entry:
                hint = " (use 'lever' not 'changed_variable')"
            elif "command" in entry:
                hint = " (don't include 'command' — it's built from lever+value)"
            errors.append(f"Hypothesis must have either ('lever' + 'value') or 'approach'{hint}")

    if errors and strict:
        raise ValidationError(errors, "hypothesis_entry")

    return errors


def validate_eval_result(data: dict[str, Any], score_range: tuple[int, int] = (1, 10), *, strict: bool = True) -> list[str]:
    """Validate an eval result with dynamic score range check."""
    errors = validate(data, "eval_result", strict=False)

    # Additional range check
    if "score" in data and isinstance(data["score"], (int, float)):
        lo, hi = score_range
        if not (lo <= data["score"] <= hi):
            errors.append(f"Field 'score': {data['score']} not in range [{lo}, {hi}]")

    if errors and strict:
        raise ValidationError(errors, "eval_result")

    return errors


def validate_project_deep(data: dict[str, Any], *, strict: bool = True) -> list[str]:
    """Validate project config including nested requirements."""
    errors = validate(data, "project_config", strict=False)

    # Nested checks
    if "metric" in data and isinstance(data["metric"], dict):
        if "name" not in data["metric"]:
            errors.append("metric.name is required")
    if "baseline" in data and isinstance(data["baseline"], dict):
        if "command" not in data["baseline"]:
            errors.append("baseline.command is required")
    if "levers" in data and isinstance(data["levers"], dict):
        for lever_name, lever in data["levers"].items():
            if not isinstance(lever, dict):
                errors.append(f"lever '{lever_name}': expected dict")
            elif "space" not in lever:
                errors.append(f"lever '{lever_name}': missing 'space'")

    if errors and strict:
        raise ValidationError(errors, "project_config")

    return errors
