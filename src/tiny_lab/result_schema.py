"""Validation helpers for phase result JSON artifacts."""
from __future__ import annotations

import json
import math
import re
from typing import Any

from .evidence import (
    contains_metric_support_numeric_token,
    has_sample_or_repetition_support_evidence,
    is_efficiency_evidence_key,
    is_goal_achievement_evidence_key,
    is_reproducibility_evidence_key,
    is_statistics_evidence_key,
    metric_aliases,
)


def validate_result_object(data: Any, label: str = "report") -> str | None:
    """Require phase result artifacts to be JSON objects."""
    if not isinstance(data, dict):
        return f"{label} is not a JSON object (got {type(data).__name__})"
    return None


def validate_finite_numeric_values(data: dict[str, Any]) -> list[str]:
    """Reject NaN/Infinity anywhere in a phase result artifact."""
    errors: list[str] = []
    for key, value in _walk_named_values(data):
        if _is_non_finite_number(value):
            errors.append(f"non-finite numeric value at {key}")
    return errors


def validate_schema_types(data: dict[str, Any], schema: dict[str, Any], fields: list[str]) -> list[str]:
    """Validate a small JSON-schema subset used in research_plan outputs."""
    properties = _schema_properties(schema)
    errors: list[str] = _schema_definition_errors(schema, "report")
    errors.extend(_required_field_errors(data, schema, "report"))
    errors.extend(_object_constraint_errors(data, schema, "report"))
    for field in schema_fields_to_validate(data, schema, fields):
        if field not in data:
            continue
        spec = properties.get(field, {})
        if not isinstance(spec, dict):
            continue
        errors.extend(_validate_schema_node(data.get(field), spec, field))
    return list(dict.fromkeys(errors))


def schema_expected_fields(schema: dict[str, Any]) -> list[str]:
    """Return the report fields required by a local result schema."""
    required = _schema_required_fields(schema)
    if required:
        return required
    return list(_schema_properties(schema))


def schema_fields_to_validate(data: dict[str, Any], schema: dict[str, Any], fields: list[str]) -> list[str]:
    """Return required fields plus declared optional properties present in data."""
    properties = _schema_properties(schema)
    present_declared = [field for field in properties if field in data]
    return list(dict.fromkeys([*fields, *_schema_required_fields(schema), *present_declared]))


def _validate_schema_node(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    """Validate one value against the local JSON-schema subset."""
    errors: list[str] = _schema_definition_errors(spec, path)
    expected = spec.get("type")
    expected_types: list[str] = []
    if isinstance(expected, list):
        expected_types = [str(item) for item in expected]
    elif isinstance(expected, str):
        expected_types = [expected]

    if expected_types and not any(_matches_json_type(value, typ) for typ in expected_types):
        if "number" in expected_types and _is_non_finite_number(value):
            errors.append(f"{path} expected finite number, got non-finite float")
            return errors
        errors.append(f"{path} expected {expected}, got {type(value).__name__}")
        return errors
    if not expected_types:
        inferred_error = _inferred_container_type_error(value, spec, path)
        if inferred_error:
            errors.append(inferred_error)
            return errors

    errors.extend(_validate_schema_constraints(value, spec, path))
    errors.extend(_validate_object_properties(value, spec, path))
    errors.extend(_validate_array_items(value, spec, path))
    return errors


def _schema_definition_errors(spec: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    type_issue = _schema_type_issue(spec.get("type"), path)
    if type_issue:
        errors.append(type_issue)

    if "properties" in spec and not isinstance(spec.get("properties"), dict):
        errors.append(f"{path}.properties must be an object")

    required = spec.get("required")
    if "required" in spec:
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            errors.append(f"{path}.required must be a list of strings")

    if "items" in spec and not isinstance(spec.get("items"), dict):
        errors.append(f"{path}.items must be an object")

    errors.extend(_schema_enum_definition_errors(spec, path))
    errors.extend(_schema_numeric_definition_errors(spec, path))
    errors.extend(_schema_size_definition_errors(spec, path))
    errors.extend(_schema_pattern_definition_errors(spec, path))
    errors.extend(_schema_additional_properties_definition_errors(spec, path))

    for field, child in _schema_properties(spec).items():
        if isinstance(child, dict):
            errors.extend(_schema_definition_errors(child, f"{path}.{field}"))
        else:
            errors.append(f"{path}.{field} schema must be an object")

    item_spec = spec.get("items")
    if isinstance(item_spec, dict):
        errors.extend(_schema_definition_errors(item_spec, f"{path}[]"))
    return errors


def _schema_enum_definition_errors(spec: dict[str, Any], path: str) -> list[str]:
    if "enum" not in spec:
        return []
    enum = spec.get("enum")
    if not isinstance(enum, list) or not enum:
        return [f"{path}.enum must be a non-empty list"]
    try:
        normalized = [_json_identity(item) for item in enum]
    except (TypeError, ValueError):
        return [f"{path}.enum values must be JSON-serializable finite values"]
    if len(set(normalized)) != len(normalized):
        return [f"{path}.enum values must be unique"]
    return []


def _schema_numeric_definition_errors(spec: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    for keyword in ("minimum", "maximum"):
        if keyword in spec and _schema_number(spec.get(keyword)) is None:
            errors.append(f"{path}.{keyword} must be a finite number")

    for keyword in ("exclusiveMinimum", "exclusiveMaximum"):
        if keyword not in spec:
            continue
        value = spec.get(keyword)
        if isinstance(value, bool):
            continue
        if _schema_number(value) is None:
            errors.append(f"{path}.{keyword} must be a boolean or finite number")

    minimum = _schema_number(spec.get("minimum"))
    maximum = _schema_number(spec.get("maximum"))
    if minimum is not None and maximum is not None and minimum > maximum:
        errors.append(f"{path}.minimum must be <= maximum")
    return errors


def _schema_size_definition_errors(spec: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    bounds: dict[str, int] = {}
    for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
        if keyword not in spec:
            continue
        value = spec.get(keyword)
        if _schema_int(value) is None:
            errors.append(f"{path}.{keyword} must be a non-negative integer")
            continue
        bounds[keyword] = int(value)
    if "minLength" in bounds and "maxLength" in bounds and bounds["minLength"] > bounds["maxLength"]:
        errors.append(f"{path}.minLength must be <= maxLength")
    if "minItems" in bounds and "maxItems" in bounds and bounds["minItems"] > bounds["maxItems"]:
        errors.append(f"{path}.minItems must be <= maxItems")
    return errors


def _schema_pattern_definition_errors(spec: dict[str, Any], path: str) -> list[str]:
    if "pattern" not in spec:
        return []
    pattern = spec.get("pattern")
    if not isinstance(pattern, str):
        return [f"{path}.pattern must be a string"]
    try:
        re.compile(pattern)
    except re.error as e:
        return [f"{path}.pattern is invalid: {e}"]
    return []


def _schema_additional_properties_definition_errors(spec: dict[str, Any], path: str) -> list[str]:
    if "additionalProperties" not in spec:
        return []
    value = spec.get("additionalProperties")
    if isinstance(value, bool) or isinstance(value, dict):
        return []
    return [f"{path}.additionalProperties must be a boolean or object"]


_SUPPORTED_JSON_SCHEMA_TYPES = frozenset({
    "array",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "string",
})


def _schema_type_issue(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value not in _SUPPORTED_JSON_SCHEMA_TYPES:
            return f"{path}.type must be one of {sorted(_SUPPORTED_JSON_SCHEMA_TYPES)}, got {value!r}"
        return None
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        invalid = [item for item in value if item not in _SUPPORTED_JSON_SCHEMA_TYPES]
        if invalid:
            return f"{path}.type has unsupported values: {invalid}"
        return None
    return f"{path}.type must be a string or non-empty list of strings"


def _inferred_container_type_error(value: Any, spec: dict[str, Any], path: str) -> str | None:
    if _schema_properties(spec) and not isinstance(value, dict):
        return f"{path} expected object, got {type(value).__name__}"
    if isinstance(spec.get("items"), dict) and not isinstance(value, list):
        return f"{path} expected array, got {type(value).__name__}"
    return None


def _validate_object_properties(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    properties = _schema_properties(spec)
    required_fields = _schema_required_fields(spec)
    if not properties and not required_fields:
        return []
    if not isinstance(value, dict):
        return []

    fields = list(dict.fromkeys([*required_fields, *properties.keys()]))

    errors: list[str] = []
    for field in fields:
        child_spec = properties.get(field, {})
        if field not in value:
            if field in required_fields:
                errors.append(f"{path}.{field} is required")
            continue
        if isinstance(child_spec, dict):
            errors.extend(_validate_schema_node(value[field], child_spec, f"{path}.{field}"))
    return errors


def _required_field_errors(data: dict[str, Any], schema: dict[str, Any], path: str) -> list[str]:
    return [
        f"{path}.{field} is required"
        for field in _schema_required_fields(schema)
        if field not in data
    ]


def _schema_required_fields(schema: dict[str, Any]) -> list[str]:
    required = schema.get("required")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        return []
    return list(dict.fromkeys(required))


def _validate_array_items(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    item_spec = spec.get("items")
    if not isinstance(item_spec, dict) or not isinstance(value, list):
        return []
    errors: list[str] = []
    for index, item in enumerate(value):
        errors.extend(_validate_schema_node(item, item_spec, f"{path}[{index}]"))
    return errors


def _validate_schema_constraints(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    errors.extend(_enum_constraint_errors(value, spec, path))
    errors.extend(_numeric_constraint_errors(value, spec, path))
    errors.extend(_string_constraint_errors(value, spec, path))
    errors.extend(_array_constraint_errors(value, spec, path))
    errors.extend(_object_constraint_errors(value, spec, path))
    return errors


def _enum_constraint_errors(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    enum = spec.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path} expected one of {enum!r}, got {value!r}")
    if "const" in spec and value != spec["const"]:
        errors.append(f"{path} expected constant {spec['const']!r}, got {value!r}")
    return errors


def _numeric_constraint_errors(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        return []
    number = float(value)
    errors: list[str] = []
    minimum = _schema_number(spec.get("minimum"))
    maximum = _schema_number(spec.get("maximum"))
    exclusive_minimum = spec.get("exclusiveMinimum")
    exclusive_maximum = spec.get("exclusiveMaximum")
    if isinstance(exclusive_minimum, bool):
        if exclusive_minimum and minimum is not None and number <= minimum:
            errors.append(f"{path} must be > {minimum:g}")
    elif (bound := _schema_number(exclusive_minimum)) is not None and number <= bound:
        errors.append(f"{path} must be > {bound:g}")
    elif minimum is not None and number < minimum:
        errors.append(f"{path} must be >= {minimum:g}")
    if isinstance(exclusive_maximum, bool):
        if exclusive_maximum and maximum is not None and number >= maximum:
            errors.append(f"{path} must be < {maximum:g}")
    elif (bound := _schema_number(exclusive_maximum)) is not None and number >= bound:
        errors.append(f"{path} must be < {bound:g}")
    elif maximum is not None and number > maximum:
        errors.append(f"{path} must be <= {maximum:g}")
    return errors


def _string_constraint_errors(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    if not isinstance(value, str):
        return []
    errors: list[str] = []
    min_length = _schema_int(spec.get("minLength"))
    max_length = _schema_int(spec.get("maxLength"))
    if min_length is not None and len(value) < min_length:
        errors.append(f"{path} length must be >= {min_length}")
    if max_length is not None and len(value) > max_length:
        errors.append(f"{path} length must be <= {max_length}")
    pattern = spec.get("pattern")
    if isinstance(pattern, str):
        try:
            if re.search(pattern, value) is None:
                errors.append(f"{path} must match pattern {pattern!r}")
        except re.error as e:
            errors.append(f"{path} schema pattern is invalid: {e}")
    return errors


def _array_constraint_errors(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    if not isinstance(value, list):
        return []
    errors: list[str] = []
    min_items = _schema_int(spec.get("minItems"))
    max_items = _schema_int(spec.get("maxItems"))
    if min_items is not None and len(value) < min_items:
        errors.append(f"{path} length must be >= {min_items}")
    if max_items is not None and len(value) > max_items:
        errors.append(f"{path} length must be <= {max_items}")
    return errors


def _object_constraint_errors(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    if not isinstance(value, dict) or spec.get("additionalProperties") is not False:
        return []
    allowed = set(_schema_properties(spec))
    extras = sorted(str(key) for key in value if str(key) not in allowed)
    if extras:
        return [f"{path} has undeclared fields: {extras}"]
    return []


def _schema_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _schema_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _json_identity(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _schema_properties(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return {
            str(key): spec
            for key, value in properties.items()
            if (spec := _coerce_schema_spec(value)) is not None
        }
    direct = {
        str(key): spec
        for key, value in schema.items()
        if key not in _JSON_SCHEMA_KEYWORDS
        if (spec := _coerce_schema_spec(value)) is not None
    }
    return direct


def _coerce_schema_spec(value: Any) -> dict[str, Any] | None:
    """Normalize Tiny-Lab shorthand schema values into JSON-schema fragments."""
    if isinstance(value, dict):
        spec = dict(value)
        if isinstance(spec.get("properties"), dict):
            spec["properties"] = {
                str(key): child_spec
                for key, child in spec["properties"].items()
                if (child_spec := _coerce_schema_spec(child)) is not None
            }
        if "items" in spec:
            raw_items = spec.get("items")
            if raw_items != []:
                item_spec = _coerce_schema_spec(raw_items)
                if item_spec is not None:
                    spec["items"] = item_spec
        return spec
    if isinstance(value, str):
        return _coerce_string_schema_spec(value)
    if isinstance(value, list):
        if value:
            item_spec = _coerce_schema_spec(value[0])
            return {"type": "array", **({"items": item_spec} if item_spec is not None else {})}
        return {"type": "array"}
    return None


def _coerce_string_schema_spec(value: str) -> dict[str, Any] | None:
    text = value.strip()
    if not text:
        return None
    normalized = _normalize_field_path(text)
    aliases = {
        "float": "number",
        "double": "number",
        "number": "number",
        "numeric": "number",
        "int": "integer",
        "integer": "integer",
        "bool": "boolean",
        "boolean": "boolean",
        "str": "string",
        "string": "string",
        "dict": "object",
        "object": "object",
        "array": "array",
        "list": "array",
    }
    if normalized in aliases:
        return {"type": aliases[normalized]}
    first_token = re.match(r"([A-Za-z]+)\b", text)
    if first_token:
        prefix = first_token.group(1).lower()
        if prefix in aliases:
            return {"type": aliases[prefix]}
    list_match = re.fullmatch(r"list\[(.*)\]", text, flags=re.IGNORECASE)
    if list_match:
        inner = list_match.group(1).strip()
        if "," in inner:
            return {"type": "array"}
        item_spec = _coerce_string_schema_spec(inner)
        return {"type": "array", **({"items": item_spec} if item_spec is not None else {})}
    if text.startswith("list[") or normalized in {"list", "array"}:
        return {"type": "array"}
    return None


_JSON_SCHEMA_KEYWORDS = {
    "$schema",
    "$id",
    "additionalProperties",
    "const",
    "description",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "items",
    "maximum",
    "maxItems",
    "maxLength",
    "minimum",
    "minItems",
    "minLength",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
}


def validate_substantive_result_values(data: dict[str, Any], fields: list[str]) -> list[str]:
    """Catch vacuous statistics and reproducibility metadata values.

    Schema/type validation can prove that a field exists and has the requested
    JSON type. This adds a research-specific layer: metadata cannot be empty,
    support counts must be positive, diagnostic counts cannot be negative,
    dispersion statistics cannot be negative, and p-values must be valid
    probabilities.
    """
    errors: list[str] = []
    seen_paths: set[str] = set()
    for field in fields:
        if field not in data:
            continue
        for path, value in _walk_named_nodes(data[field], field):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            errors.extend(_substantive_value_errors(path, value, data))
    errors.extend(_alpha_threshold_errors(data))
    errors.extend(_significance_consistency_errors(data))
    errors.extend(_uncertainty_support_errors(data))
    errors.extend(_split_ratio_consistency_errors(data))
    return errors


def validate_phase_identity(data: dict[str, Any], phase_id: str) -> list[str]:
    """Reject result metadata that identifies a different phase."""
    expected = str(phase_id)
    errors: list[str] = []
    for path, value in _walk_named_values(data):
        if _leaf_key(path) not in _PHASE_ID_FIELDS:
            continue
        if not isinstance(value, str) or value.strip() != expected:
            errors.append(f"{path} metadata must match planned phase id `{expected}`")
    return errors


def _substantive_value_errors(field: str, value: Any, root_data: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    normalized = _normalize_field_path(field)
    reproducibility_key = _normalize_field_path(_leaf_key(field))
    if _is_reproducibility_field(field):
        if _is_empty(value):
            errors.append(f"{field} reproducibility metadata must be non-empty")
        else:
            reproducibility_error = _reproducibility_value_error(field, reproducibility_key, value)
            if reproducibility_error:
                errors.append(reproducibility_error)
    if _is_statistical_field(field):
        stat_error = _statistic_value_error(field, value, root_data)
        if stat_error:
            errors.append(stat_error)
        interval_error = _interval_value_error(field, value)
        if interval_error:
            errors.append(interval_error)
    if _is_confusion_matrix_field(field):
        matrix_error = _confusion_matrix_value_error(field, value)
        if matrix_error:
            errors.append(matrix_error)
    if _is_goal_achievement_field(normalized):
        goal_flag_error = _goal_achievement_flag_value_error(field, value)
        if goal_flag_error:
            errors.append(goal_flag_error)
    metric_error = _metric_value_error(field, value)
    if metric_error:
        errors.append(metric_error)
    return errors


def _matches_json_type(value: Any, expected: str) -> bool:
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return False


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


_PLACEHOLDER_REPRODUCIBILITY_VALUES = {
    "abc",
    "dummy",
    "example",
    "missing",
    "n_a",
    "na",
    "none",
    "not_applicable",
    "not_collected",
    "not_done",
    "not_measured",
    "not_reported",
    "null",
    "placeholder",
    "tbd",
    "test",
    "todo",
    "unknown",
}


def _reproducibility_value_error(field: str, normalized: str, value: Any) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    if isinstance(value, str):
        placeholder = _normalize_field_path(text)
        if placeholder in _PLACEHOLDER_REPRODUCIBILITY_VALUES:
            return f"{field} reproducibility metadata must not be a placeholder"
    if _is_data_digest_reproducibility_field(normalized) or "sha256" in normalized or text.lower().startswith("sha256:"):
        if isinstance(value, (dict, list)):
            if _contains_sha256_reproducibility_value(value):
                return None
            return f"{field} sha256 reproducibility metadata must include sha256:<64 hex chars>"
        if not _is_sha256_reproducibility_value(value):
            return f"{field} sha256 reproducibility metadata must use sha256:<64 hex chars>"
        return None
    if not isinstance(value, str):
        return None
    return None


def _is_sha256_reproducibility_value(value: Any) -> bool:
    if isinstance(value, str):
        text = value.strip()
        if _is_sha256_digest_text(text):
            return True
        if text.startswith(("{", "[")):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return False
            return _is_sha256_reproducibility_value(parsed)
        return False
    if isinstance(value, dict):
        return bool(value) and all(_is_sha256_reproducibility_value(item) for item in value.values())
    if isinstance(value, list):
        return bool(value) and all(_is_sha256_reproducibility_value(item) for item in value)
    return False


def _contains_sha256_reproducibility_value(value: Any) -> bool:
    if isinstance(value, str):
        return _is_sha256_digest_text(value.strip())
    if isinstance(value, dict):
        return any(_contains_sha256_reproducibility_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_sha256_reproducibility_value(item) for item in value)
    return False


def _is_sha256_digest_text(text: str) -> bool:
    digest = text.lower()
    if digest.startswith("sha256:"):
        digest = digest[len("sha256:"):]
    return re.fullmatch(r"[0-9a-f]{64}", digest) is not None


def _is_data_digest_reproducibility_field(normalized: str) -> bool:
    parts = {part for part in normalized.split("_") if part and not part.isdigit()}
    return bool(
        parts.intersection({"checksum", "fingerprint"})
        or ("hash" in parts and bool(parts.intersection({"data", "dataset"})))
    )


def _goal_achievement_flag_value_error(field: str, value: Any) -> str | None:
    if _goal_flag_truth_value(value) is None:
        return f"{field} goal-achievement flag must be a concrete true/false value"
    return None


def _goal_flag_truth_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = _normalize_field_path(value)
        if normalized in {"true", "yes", "met", "achieved", "passed", "1"}:
            return True
        if normalized in {"false", "no", "not_met", "failed", "0"}:
            return False
    return None


def _is_reproducibility_field(field: str) -> bool:
    return is_reproducibility_evidence_key(_leaf_key(field))


def _is_statistical_field(field: str) -> bool:
    leaf = _normalize_field_path(_leaf_key(field))
    if _is_statistical_metadata_field(leaf):
        return False
    if _is_statistical_identifier_field(leaf):
        return False
    if _is_statistical_boolean_flag_field(leaf):
        return False
    if _is_temporal_boundary_field(leaf):
        return False
    return is_statistics_evidence_key(leaf)


_STATISTICS_METADATA_SUFFIX_TOKENS = {
    "definition",
    "definitions",
    "description",
    "explanation",
    "explanations",
    "id",
    "ids",
    "index",
    "indices",
    "label",
    "method",
    "methods",
    "name",
    "notes",
    "rationale",
    "source",
    "type",
    "unit",
    "units",
}


def _normalize_field_path(field: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", field.lower()).strip("_")


def _leaf_key(path: str) -> str:
    return path.split(".")[-1].split("[", 1)[0]


_PHASE_ID_FIELDS = {"phase_id", "current_phase_id"}


def _statistic_value_error(field: str, value: Any, root_data: dict[str, Any] | None = None) -> str | None:
    values = _numeric_values(value)
    if not values:
        return f"{field} statistic must be numeric or a numeric list/object"
    if any(not math.isfinite(v) for v in values):
        return f"{field} statistic must be finite"
    normalized = _normalize_field_path(_leaf_key(field))
    if (
        _is_positive_support_count_field(normalized)
        and any(v <= 0 for v in values)
        and not _allows_zero_absent_split_count(field, root_data)
    ):
        return f"{field} count must be > 0"
    if _is_count_field(normalized) and any(v < 0 for v in values):
        return f"{field} count must be >= 0"
    if _is_dispersion_field(normalized) and any(v < 0 for v in values):
        return f"{field} dispersion statistic must be >= 0"
    if _is_p_value_field(normalized) and any(v < 0 or v > 1 for v in values):
        return f"{field} p-value must be between 0 and 1"
    return None


def _metric_value_error(field: str, value: Any) -> str | None:
    if _is_hyperparameter_path(field):
        return None
    normalized = _normalize_field_path(_leaf_key(field))
    if is_efficiency_evidence_key(normalized):
        values = _metric_numeric_values(value)
        if values and any(v <= 0 for v in values):
            return f"{field} efficiency/resource value must be > 0"
    if _is_metric_support_field(field) or _is_metric_support_field(normalized):
        return None
    if _is_derived_metric_field(normalized):
        return None
    values = _metric_numeric_values(value)
    if not values:
        return None
    if _is_non_negative_metric_field(normalized) and any(v < 0 for v in values):
        return f"{field} metric value must be >= 0"
    if _is_probability_metric_field(normalized):
        upper = 100.0 if _is_percentage_metric_field(normalized) else 1.0
        if any(v < 0 or v > upper for v in values):
            return f"{field} metric value must be between 0 and {upper:g}"
    if _is_r2_metric_field(normalized) and any(v > 1 for v in values):
        return f"{field} metric value must be <= 1"
    return None


def _confusion_matrix_value_error(field: str, value: Any) -> str | None:
    if not isinstance(value, list) or not value or not all(isinstance(row, list) and row for row in value):
        return f"{field} confusion matrix must be a non-empty square matrix"
    row_lengths = {len(row) for row in value}
    if len(row_lengths) != 1 or len(value) != next(iter(row_lengths)):
        return f"{field} confusion matrix must be a non-empty square matrix"
    if not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for row in value
        for item in row
    ):
        return f"{field} confusion matrix values must be non-negative integers"
    return None


def _metric_numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        out: list[float] = []
        for item in value:
            item_values = _metric_numeric_values(item)
            if not item_values:
                return []
            out.extend(item_values)
        return out
    if isinstance(value, dict):
        if not value:
            return []
        out: list[float] = []
        for key, item in value.items():
            normalized_key = _normalize_field_path(str(key))
            if _is_metric_support_field(normalized_key):
                continue
            item_values = _metric_numeric_values(item)
            if item_values:
                out.extend(item_values)
        return out
    return []


def _interval_value_error(field: str, value: Any) -> str | None:
    normalized = _normalize_field_path(field)
    if not _requires_interval_bounds_field(normalized):
        return None
    interval = _interval_bounds(value)
    if interval is None:
        return f"{field} interval must provide exactly two numeric bounds"
    low, high = interval
    if low > high:
        return f"{field} interval lower bound must be <= upper bound"
    if _is_derived_metric_field(normalized):
        return None
    if _is_non_negative_metric_field(normalized) and low < 0:
        return f"{field} interval bounds must be >= 0"
    if _is_probability_metric_field(normalized):
        upper = 100.0 if _is_percentage_metric_field(normalized) else 1.0
        if low < 0 or high > upper:
            return f"{field} interval bounds must be between 0 and {upper:g}"
    if _is_r2_metric_field(normalized) and high > 1:
        return f"{field} interval upper bound must be <= 1"
    return None


def _numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        out: list[float] = []
        for item in value:
            item_values = _numeric_values(item)
            if not item_values:
                return []
            out.extend(item_values)
        return out
    if isinstance(value, dict):
        if not value:
            return []
        out: list[float] = []
        for item in value.values():
            item_values = _numeric_values(item)
            if not item_values:
                return []
            out.extend(item_values)
        return out
    return []


def _interval_bounds(value: Any) -> tuple[float, float] | None:
    if isinstance(value, list) and len(value) == 2:
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return float(value[0]), float(value[1])
        return None
    if isinstance(value, dict):
        lower = _first_numeric_key(value, ("lower", "low", "lo", "lower_bound", "ci_lower"))
        upper = _first_numeric_key(value, ("upper", "high", "hi", "upper_bound", "ci_upper"))
        if lower is not None and upper is not None:
            return lower, upper
    return None


def _first_numeric_key(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _is_non_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(float(value))


def _walk_named_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_walk_named_values(item, child_prefix))
        return out
    if isinstance(value, list):
        out: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.extend(_walk_named_values(item, child_prefix))
        return out
    return [(prefix, value)]


def _walk_named_nodes(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out = [(prefix, value)]
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_walk_named_nodes(item, child_prefix))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.extend(_walk_named_nodes(item, child_prefix))
    return out


def _is_count_field(field: str) -> bool:
    normalized_leaf = _normalize_field_path(_leaf_key(field))
    normalized_full = _normalize_field_path(field)
    return _is_count_field_name(normalized_leaf) or (
        normalized_full != normalized_leaf and _is_count_field_name(normalized_full)
    )


def _is_count_field_name(normalized: str) -> bool:
    return (
        normalized in {"n", "samples"}
        or normalized.startswith(("n_", "num_"))
        or normalized.endswith(("_count", "_counts"))
        or any(
            _field_contains_token(normalized, token)
            for token in (
                "row_count",
                "row_counts",
                "method_row_count",
                "method_row_counts",
                "row_method_count",
                "row_method_counts",
                "n_samples",
                "sample_count",
                "fold_count",
                "split_count",
                "trial_count",
                "n_trials",
                "n_splits",
                "n_folds",
                "num_samples",
                "num_trials",
                "num_splits",
                "num_folds",
            )
        )
    )


def _is_positive_support_count_field(field: str) -> bool:
    normalized = _normalize_field_path(_leaf_key(field))
    return (
        normalized in {"n", "samples"}
        or any(
            _field_contains_token(normalized, token)
            for token in (
                "n_samples",
                "sample_count",
                "fold_count",
                "split_count",
                "trial_count",
                "n_trials",
                "n_splits",
                "n_folds",
                "num_samples",
                "num_trials",
                "num_splits",
                "num_folds",
            )
        )
    )


_ABSENT_SPLIT_COUNT_FIELDS = {
    "fold_count",
    "split_count",
    "n_splits",
    "n_folds",
    "num_splits",
    "num_folds",
}


def _allows_zero_absent_split_count(field: str, root_data: dict[str, Any] | None) -> bool:
    normalized = _normalize_field_path(_leaf_key(field))
    if normalized not in _ABSENT_SPLIT_COUNT_FIELDS:
        return False
    if "." in field or "[" in field:
        return False
    if not isinstance(root_data, dict):
        return False
    context = " ".join(
        str(root_data.get(key, ""))
        for key in ("phase_id", "split_id", "split_protocol", "evaluation_protocol")
    )
    normalized_context = _normalize_field_path(context)
    return any(
        token in normalized_context
        for token in (
            "no_split",
            "no_train_test_split",
            "no_cross_validation",
            "no_cv",
            "eda_only",
            "preprocessing_only",
        )
    )


def _is_statistical_metadata_field(field: str) -> bool:
    parts = [part for part in _normalize_field_path(field).split("_") if part]
    return bool(parts and parts[-1] in _STATISTICS_METADATA_SUFFIX_TOKENS)


def _is_statistical_identifier_field(field: str) -> bool:
    normalized = _normalize_field_path(field)
    return normalized in {"fold", "split", "trial", "repeat", "seed", "random_seed", "random_state"}


def _is_statistical_boolean_flag_field(field: str) -> bool:
    normalized = _normalize_field_path(field)
    parts = [part for part in normalized.split("_") if part]
    return (
        normalized.startswith(("is_", "has_", "was_", "no_"))
        or normalized.endswith(("_flag", "_found", "_detected", "_validated", "_valid", "_passed", "_failed"))
        or "flag" in parts
    )


def _is_temporal_boundary_field(field: str) -> bool:
    parts = set(part for part in _normalize_field_path(field).split("_") if part)
    return bool(
        parts.intersection({"date", "week", "month", "year", "time", "timestamp", "start", "end"})
        and parts.intersection({"min", "max"})
    )


def _is_dispersion_field(field: str) -> bool:
    parts = set(part for part in _normalize_field_path(field).split("_") if part)
    normalized = _normalize_field_path(field)
    return (
        "std" in field
        or bool(parts.intersection({"se", "sem", "stderr", "stdev", "variance"}))
        or "standard_deviation" in normalized
        or "standard_error" in normalized
    )


def _is_p_value_field(field: str) -> bool:
    return any(
        _field_contains_token_without_metadata_suffix(field, token, _STATISTICS_METADATA_SUFFIX_TOKENS)
        for token in ("p_value", "pvalue")
    )


def _is_uncertainty_field(field: str) -> bool:
    normalized = _normalize_field_path(field)
    return (
        is_statistics_evidence_key(normalized)
        and not _is_p_value_field(normalized)
        and not _is_count_field(normalized)
        and (_is_dispersion_field(normalized) or _is_interval_field(normalized))
    )


def _is_confusion_matrix_field(field: str) -> bool:
    leaf_segment = field.split(".")[-1]
    if "[" in leaf_segment:
        return False
    return _normalize_field_path(leaf_segment) == "confusion_matrix"


def _is_goal_achievement_field(field: str) -> bool:
    return is_goal_achievement_evidence_key(field)


def _alpha_threshold_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, value in _walk_named_values(data):
        if _is_hyperparameter_path(path):
            continue
        if not _is_alpha_threshold_field(_leaf_key(path)):
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            errors.append(f"{path} significance threshold must be numeric and finite")
            continue
        if not 0 < float(value) < 1:
            errors.append(f"{path} significance threshold must be > 0 and < 1")
    return errors


def _is_alpha_threshold_field(field: str) -> bool:
    return _normalize_field_path(field) in {"alpha", "significance_level"}


def _is_hyperparameter_path(field: str) -> bool:
    parts = set(part for part in _normalize_field_path(field).split("_") if part)
    return bool(
        parts.intersection({"params", "param", "hyperparameter", "hyperparameters"})
        or "selected_hyperparameters" in _normalize_field_path(field)
    )


def _is_derived_metric_field(field: str) -> bool:
    return any(
        _field_contains_token(field, token)
        for token in (
            "delta",
            "difference",
            "diff",
            "gain",
            "improvement",
            "lift",
            "relative",
        )
    )


def _is_metric_support_field(field: str) -> bool:
    return (
        _is_count_field(field)
        or contains_metric_support_numeric_token(field)
        or field in {"alpha", "seed", "random_seed", "random_state", "fold", "split", "trial"}
        or field.endswith(("_id", "_ids", "_index", "_indices"))
    )


def _is_non_negative_metric_field(field: str) -> bool:
    parts = set(part for part in field.split("_") if part)
    return (
        bool(parts.intersection({"mae", "rmse", "mse", "msle", "mape", "smape"}))
        or "mean_absolute_error" in field
        or "root_mean_squared_error" in field
        or "mean_squared_error" in field
        or "log_loss" in field
        or "cross_entropy" in field
        or field in {"loss", "test_loss", "val_loss", "validation_loss", "train_loss", "training_loss"}
        or field.endswith("_loss")
    )


def _is_probability_metric_field(field: str) -> bool:
    parts = set(part for part in field.split("_") if part)
    if "sensitivity" in parts and parts.intersection({"analysis", "comparison", "comparisons", "results", "study"}):
        return False
    return (
        any(_field_contains_metric_alias(field, alias) for alias in metric_aliases("accuracy"))
        or any(_field_contains_metric_alias(field, alias) for alias in metric_aliases("auc"))
        or bool(parts.intersection({"f1", "precision", "recall", "sensitivity", "specificity"}))
        or "f1_score" in field
    )


def _is_percentage_metric_field(field: str) -> bool:
    return any(token in field for token in ("percent", "percentage", "pct"))


def _is_r2_metric_field(field: str) -> bool:
    return any(_field_contains_metric_alias(field, alias) for alias in metric_aliases("r2"))


def _field_contains_token(field: str, token: str) -> bool:
    return re.search(rf"(?:^|_){re.escape(token)}(?:_|$)", field) is not None


def _field_contains_token_without_metadata_suffix(
    field: str,
    token: str,
    metadata_suffixes: set[str],
) -> bool:
    normalized = _normalize_field_path(field)
    pattern = re.compile(rf"(?:^|_){re.escape(token)}(?:_|$)")
    for match in pattern.finditer(normalized):
        prefix = normalized[:match.start()].strip("_")
        prefix_parts = [part for part in prefix.split("_") if part]
        if _field_prefix_has_negation(prefix_parts):
            continue
        tail = normalized[match.end():].strip("_")
        if tail and tail.split("_", 1)[0] in metadata_suffixes:
            continue
        return True
    return False


_FIELD_NEGATION_PREFIX_TOKENS = {"non", "no", "not", "without"}
_NON_NEGATING_NON_COMPOUNDS = {"ml", "parametric"}


def _field_prefix_has_negation(prefix_parts: list[str]) -> bool:
    index = 0
    while index < len(prefix_parts):
        part = prefix_parts[index]
        if part not in _FIELD_NEGATION_PREFIX_TOKENS:
            index += 1
            continue
        if (
            part == "non"
            and index + 1 < len(prefix_parts)
            and prefix_parts[index + 1] in _NON_NEGATING_NON_COMPOUNDS
        ):
            index += 2
            continue
        return True
    return False


def _field_contains_metric_alias(field: str, alias: str) -> bool:
    return re.search(rf"(?:^|_){re.escape(alias)}(?:_|$)", field) is not None


def _is_interval_field(field: str) -> bool:
    return _requires_interval_bounds_field(field) and any(
        _field_contains_token_without_metadata_suffix(field, token, _STATISTICS_METADATA_SUFFIX_TOKENS)
        for token in ("ci95", "ci", "confidence_interval", "interval")
    )


def _requires_interval_bounds_field(field: str) -> bool:
    normalized = _normalize_field_path(field)
    parts = [part for part in normalized.split("_") if part]
    if not parts:
        return False
    if parts[-1] in {"ci", "ci95", "interval"}:
        return True
    return len(parts) >= 2 and parts[-2:] == ["confidence", "interval"]


def _significance_consistency_errors(data: dict[str, Any]) -> list[str]:
    return _significance_scope_errors(data, "", (), (), _significance_alpha(data), False)


def _uncertainty_support_errors(data: dict[str, Any]) -> list[str]:
    return _uncertainty_scope_errors(data, "", False)


def _uncertainty_scope_errors(value: Any, prefix: str, inherited_support: bool) -> list[str]:
    if isinstance(value, list):
        errors: list[str] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            errors.extend(_uncertainty_scope_errors(item, child_prefix, inherited_support))
        return errors
    if not isinstance(value, dict):
        return []

    has_support = inherited_support or has_sample_or_repetition_support_evidence(value)
    errors: list[str] = []
    for key, item in value.items():
        path = _join_path(prefix, key)
        if (
            _is_uncertainty_field(key.lower())
            and _statistic_value_error(path, item) is None
            and not has_support
        ):
            errors.append(
                f"{path} uncertainty evidence requires sample/repetition support "
                "such as n_samples, n_trials, or fold_count"
            )
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            errors.extend(_uncertainty_scope_errors(item, _join_path(prefix, key), has_support))
    return errors


def _significance_scope_errors(
    value: Any,
    prefix: str,
    inherited_p_values: tuple[tuple[str, float], ...],
    inherited_intervals: tuple[tuple[str, tuple[float, float]], ...],
    inherited_alpha: float,
    inherited_support: bool,
) -> list[str]:
    if isinstance(value, list):
        errors: list[str] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            errors.extend(
                _significance_scope_errors(
                    item,
                    child_prefix,
                    inherited_p_values,
                    inherited_intervals,
                    inherited_alpha,
                    inherited_support,
                )
            )
        return errors
    if not isinstance(value, dict):
        return []

    alpha = _significance_alpha(value, default=inherited_alpha)
    local_p_values = _direct_p_values(value, prefix)
    local_intervals = _direct_comparison_intervals(value, prefix)
    p_values = local_p_values or inherited_p_values
    comparison_intervals = local_intervals or inherited_intervals
    has_support = inherited_support or has_sample_or_repetition_support_evidence(value)
    flags = [
        (_join_path(prefix, key), item)
        for key, item in value.items()
        if isinstance(item, bool) and _is_significance_flag(key.lower())
    ]
    errors: list[str] = []
    for key, _ in local_p_values:
        if not has_support and not _is_unrelated_p_value_key(key.lower()):
            errors.append(
                f"{key} significance evidence requires sample/repetition support "
                "such as n_samples, n_trials, or fold_count"
            )
    for key, flag in flags:
        relevant_p_values = _p_values_for_significance_flag(key, p_values)
        relevant_intervals = _comparison_intervals_for_significance_flag(key, comparison_intervals)
        has_statistical_basis = bool(relevant_p_values or relevant_intervals)
        if has_statistical_basis and not has_support:
            errors.append(
                f"{key} significance evidence requires sample/repetition support "
                "such as n_samples, n_trials, or fold_count"
            )
        if relevant_p_values:
            best_p = min(value for _, value in relevant_p_values)
            if flag and best_p > alpha:
                errors.append(f"{key}=true contradicts p_value {best_p:g} > alpha {alpha:g}")
            elif (
                not flag
                and best_p <= alpha
                and not _false_directional_improvement_flag_has_negative_interval(key, relevant_intervals)
            ):
                errors.append(f"{key}=false contradicts p_value {best_p:g} <= alpha {alpha:g}")
        for interval_key, (low, high) in relevant_intervals:
            crosses_zero = low <= 0 <= high
            if flag and crosses_zero:
                errors.append(f"{key}=true contradicts {interval_key} crossing zero")
            elif (
                flag
                and _is_directional_improvement_significance_flag(key)
                and high < 0
            ):
                errors.append(f"{key}=true contradicts {interval_key} below zero")
            elif (
                not flag
                and not crosses_zero
                and not (
                    _is_directional_improvement_significance_flag(key)
                    and high < 0
                )
            ):
                errors.append(f"{key}=false contradicts {interval_key} excluding zero")
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            errors.extend(
                _significance_scope_errors(
                    item,
                    _join_path(prefix, key),
                    p_values,
                    comparison_intervals,
                    alpha,
                    has_support,
                )
            )
    return errors


def _direct_p_values(data: dict[str, Any], prefix: str = "") -> tuple[tuple[str, float], ...]:
    return tuple(
        (_join_path(prefix, key), float(value))
        for key, value in data.items()
        if _is_p_value_field(key.lower())
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def _p_values_for_significance_flag(
    flag_key: str,
    p_values: tuple[tuple[str, float], ...],
) -> tuple[tuple[str, float], ...]:
    usable = tuple((key, value) for key, value in p_values if not _is_unrelated_p_value_key(key.lower()))
    if not usable:
        return ()
    if specific := _specific_comparator_tokens(flag_key):
        matched = tuple(
            (key, value)
            for key, value in usable
            if _path_contains_all_tokens(key, specific)
        )
        if matched:
            return matched
    if _is_comparison_significance_flag(flag_key.lower()):
        comparison = tuple((key, value) for key, value in usable if _is_comparison_p_value_key(key.lower()))
        if comparison:
            return comparison
        generic = tuple((key, value) for key, value in usable if _is_generic_p_value_key(key.lower()))
        return generic if len(generic) == 1 and len(usable) == 1 else ()
    generic = tuple((key, value) for key, value in usable if _is_generic_p_value_key(key.lower()))
    return generic or usable


def _comparison_intervals_for_significance_flag(
    flag_key: str,
    intervals: tuple[tuple[str, tuple[float, float]], ...],
) -> tuple[tuple[str, tuple[float, float]], ...]:
    if not intervals:
        return ()
    if specific := _specific_comparator_tokens(flag_key):
        matched = tuple(
            (key, bounds)
            for key, bounds in intervals
            if _path_contains_all_tokens(key, specific)
        )
        if matched:
            return matched
    if _is_comparison_significance_flag(flag_key.lower()):
        return intervals
    generic = tuple(
        (key, bounds)
        for key, bounds in intervals
        if not _is_specific_comparator_interval_key(key.lower())
    )
    return generic


def _is_comparison_significance_flag(field: str) -> bool:
    normalized = _normalize_field_path(_leaf_key(field))
    return any(
        _field_contains_token(normalized, token)
        for token in (
            "baseline",
            "comparator",
            "comparison",
            "delta",
            "difference",
            "diff",
            "effect",
            "emro",
            "simple_ml",
            "vs",
        )
    )


def _specific_comparator_tokens(field: str) -> tuple[str, ...]:
    leaf = _normalize_field_path(_leaf_key(field))
    if "_vs_" not in f"_{leaf}_":
        return ()
    suffix = leaf.split("_vs_", 1)[1]
    return tuple(part for part in suffix.split("_") if part)


def _path_contains_all_tokens(path: str, tokens: tuple[str, ...]) -> bool:
    parts = set(part for part in _normalize_field_path(path).split("_") if part)
    return all(token in parts for token in tokens)


def _is_directional_improvement_significance_flag(field: str) -> bool:
    normalized = _normalize_field_path(_leaf_key(field))
    return any(
        _field_contains_token(normalized, token)
        for token in ("improvement", "increase", "gain", "reduction")
    )


def _false_directional_improvement_flag_has_negative_interval(
    flag_key: str,
    intervals: tuple[tuple[str, tuple[float, float]], ...],
) -> bool:
    return bool(
        _is_directional_improvement_significance_flag(flag_key)
        and any(high < 0 for _, (_, high) in intervals)
    )


def _is_comparison_p_value_key(field: str) -> bool:
    normalized = _normalize_field_path(field)
    return any(
        _field_contains_token(normalized, token)
        for token in (
            "baseline",
            "comparison",
            "delta",
            "difference",
            "diff",
            "effect",
            "gain",
            "improvement",
            "increase",
            "decrease",
            "reduction",
            "vs_baseline",
            "over_baseline",
        )
    )


def _is_generic_p_value_key(field: str) -> bool:
    leaf = _normalize_field_path(_leaf_key(field))
    return leaf in {"p_value", "pvalue"}


def _is_specific_comparator_interval_key(field: str) -> bool:
    normalized = _normalize_field_path(field)
    return bool(
        "_vs_" in f"_{normalized}_"
        or any(
            _field_contains_token(normalized, token)
            for token in ("vs_baseline", "vs_emro", "vs_simple_ml", "over_baseline")
        )
    )


def _is_unrelated_p_value_key(field: str) -> bool:
    normalized = _normalize_field_path(field)
    return any(
        _field_contains_token(normalized, token)
        for token in (
            "calibration",
            "difficulty",
            "distribution",
            "homoscedasticity",
            "levene",
            "normality",
            "resolution",
            "shapiro",
            "stationarity",
        )
    )


def _direct_comparison_intervals(
    data: dict[str, Any],
    prefix: str,
) -> tuple[tuple[str, tuple[float, float]], ...]:
    return tuple(
        (_join_path(prefix, key), bounds)
        for key, value in data.items()
        for bounds in [_interval_bounds(value)]
        if bounds is not None and _is_comparison_interval_field(key.lower())
    )


def _join_path(prefix: str, key: Any) -> str:
    text = str(key)
    return f"{prefix}.{text}" if prefix else text


def _is_significance_flag(field: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", field).strip("_")
    flags = {
        "significant",
        "is_significant",
        "statistically_significant",
        "significance_detected",
        "significant_difference",
        "significant_improvement",
    }
    return (
        normalized in flags
        or any(normalized.endswith(f"_{flag}") for flag in flags)
        or any(normalized.startswith(f"{flag}_") for flag in flags)
    )


def _significance_alpha(data: dict[str, Any], default: float = 0.05) -> float:
    for key in ("alpha", "significance_level"):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 1:
            return float(value)
    return default


def _is_comparison_interval_field(field: str) -> bool:
    if not _is_interval_field(field):
        return False
    normalized = _normalize_field_path(field)
    return any(
        _field_contains_token(normalized, token)
        for token in (
            "improvement",
            "delta",
            "difference",
            "diff",
            "effect",
            "gain",
            "reduction",
            "increase",
            "decrease",
        )
    )


def _split_ratio_consistency_errors(data: dict[str, Any]) -> list[str]:
    text_pairs = _split_ratio_text_pairs(data)
    numeric_pairs, numeric_errors = _split_ratio_numeric_pairs(data)
    errors = list(numeric_errors)

    for text_path, text_pair in text_pairs:
        if not _valid_split_ratio_pair(*text_pair):
            errors.append(f"{text_path} split ratio must use positive train/test percentages summing to 100")
            continue
        text_parent = _parent_path(text_path)
        scoped_numeric_pairs = [
            (path, pair)
            for path, pair in numeric_pairs
            if _parent_path(path) == text_parent
        ]
        for numeric_path, numeric_pair in scoped_numeric_pairs:
            if not _split_ratio_pairs_match(text_pair, numeric_pair):
                errors.append(
                    f"{text_path} split ratio {text_pair[0]:g}/{text_pair[1]:g} "
                    f"must match {numeric_path} ratio {numeric_pair[0]:g}/{numeric_pair[1]:g}"
                )
    return errors


def _split_ratio_text_pairs(data: dict[str, Any]) -> list[tuple[str, tuple[float, float]]]:
    pairs: list[tuple[str, tuple[float, float]]] = []
    for path, value in _walk_named_values(data):
        if not isinstance(value, str):
            continue
        if not _is_split_ratio_text_field(path):
            continue
        pair = _split_ratio_pair_from_text(value)
        if pair is not None:
            pairs.append((path, pair))
    return pairs


def _split_ratio_numeric_pairs(data: dict[str, Any]) -> tuple[list[tuple[str, tuple[float, float]]], list[str]]:
    by_parent: dict[str, dict[str, list[tuple[str, float, str]]]] = {}
    for path, value in _walk_named_values(data):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        role = _split_ratio_numeric_role(path)
        if role is None:
            continue
        if _is_optional_zero_validation_split(path, float(value)):
            continue
        unit = _split_ratio_numeric_unit(path, float(value))
        if unit is None:
            continue
        parent = _parent_path(path)
        bucket = by_parent.setdefault(parent, {"train": [], "test": []})
        bucket[role].append((path, float(value), unit))

    pairs: list[tuple[str, tuple[float, float]]] = []
    errors: list[str] = []
    for parent, values in by_parent.items():
        for train_path, train_value, train_unit in values["train"]:
            for test_path, test_value, test_unit in values["test"]:
                pair, problem = _coerce_split_ratio_pair(
                    train_value,
                    test_value,
                    train_unit=train_unit,
                    test_unit=test_unit,
                )
                label = f"{train_path}/{test_path}"
                if problem:
                    errors.append(f"{label} {problem}")
                elif pair is not None:
                    pairs.append((label, pair))
    return pairs, errors


def _split_ratio_pair_from_text(value: str) -> tuple[float, float] | None:
    match = _SPLIT_RATIO_TEXT_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group("train")), float(match.group("test"))
    except ValueError:
        return None


def _split_ratio_numeric_role(path: str) -> str | None:
    leaf = _normalize_field_path(_leaf_key(path))
    if any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_TRAIN_FIELDS):
        return "train"
    if any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_TEST_FIELDS):
        return "test"
    return None


def _split_ratio_numeric_unit(path: str, value: float) -> str | None:
    leaf = _normalize_field_path(_leaf_key(path))
    if any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_FRACTION_FIELDS):
        return "fraction"
    if any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_PERCENT_FIELDS):
        return "percent"
    if any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_COUNT_FIELDS):
        if leaf.endswith("_size") and 0 < value <= 1:
            return "fraction"
        return "count"
    return None


def _is_optional_zero_validation_split(path: str, value: float) -> bool:
    if value != 0:
        return False
    leaf = _normalize_field_path(_leaf_key(path))
    return any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_VALIDATION_FIELDS)


def _coerce_split_ratio_pair(
    train: float,
    test: float,
    *,
    train_unit: str,
    test_unit: str,
) -> tuple[tuple[float, float] | None, str | None]:
    if train <= 0 or test <= 0:
        return None, "split counts/ratios must be positive"
    if train_unit != test_unit:
        return None, None
    if train_unit == "fraction":
        if not math.isclose(train + test, 1.0, rel_tol=1e-6, abs_tol=1e-6):
            return None, "split fractions must sum to 1"
        return (train * 100.0, test * 100.0), None
    if train_unit == "percent":
        if not math.isclose(train + test, 100.0, rel_tol=1e-6, abs_tol=1e-6):
            return None, "split percentages must sum to 100"
        return (train, test), None
    total = train + test
    return (train / total * 100.0, test / total * 100.0), None


def _is_split_ratio_text_field(path: str) -> bool:
    leaf = _normalize_field_path(_leaf_key(path))
    return any(_field_ends_with_token(leaf, token) for token in _SPLIT_RATIO_TEXT_FIELDS)


def _field_ends_with_token(field: str, token: str) -> bool:
    return field == token or field.endswith(f"_{token}")


def _parent_path(path: str) -> str:
    if "." not in path:
        return ""
    return path.rsplit(".", 1)[0]


def _valid_split_ratio_pair(train: float, test: float) -> bool:
    return (
        math.isfinite(train)
        and math.isfinite(test)
        and train > 0
        and test > 0
        and math.isclose(train + test, 100.0, rel_tol=1e-6, abs_tol=1e-6)
    )


def _split_ratio_pairs_match(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return math.isclose(left[0], right[0], abs_tol=0.25) and math.isclose(left[1], right[1], abs_tol=0.25)


_SPLIT_RATIO_TEXT_RE = re.compile(
    r"\b(?P<train>\d{1,3}(?:\.\d+)?)\s*/\s*(?P<test>\d{1,3}(?:\.\d+)?)\b"
)
_SPLIT_RATIO_TEXT_FIELDS = {
    "split_protocol",
    "train_test_split",
    "holdout_split",
    "heldout_split",
    "split_ratio",
    "split_description",
}
_SPLIT_RATIO_TRAIN_FIELDS = {
    "train_fraction",
    "training_fraction",
    "train_percent",
    "training_percent",
    "train_percentage",
    "training_percentage",
    "train_size",
    "training_size",
    "train_rows",
    "training_rows",
    "train_count",
    "training_count",
}
_SPLIT_RATIO_TEST_FIELDS = {
    "test_fraction",
    "validation_fraction",
    "holdout_fraction",
    "heldout_fraction",
    "test_percent",
    "validation_percent",
    "holdout_percent",
    "heldout_percent",
    "test_percentage",
    "validation_percentage",
    "holdout_percentage",
    "heldout_percentage",
    "test_size",
    "validation_size",
    "holdout_size",
    "heldout_size",
    "test_rows",
    "validation_rows",
    "holdout_rows",
    "heldout_rows",
    "test_count",
    "validation_count",
    "holdout_count",
    "heldout_count",
}
_SPLIT_RATIO_VALIDATION_FIELDS = {
    "validation_fraction",
    "validation_percent",
    "validation_percentage",
    "validation_size",
    "validation_rows",
    "validation_count",
}
_SPLIT_RATIO_FRACTION_FIELDS = {
    "train_fraction",
    "training_fraction",
    "test_fraction",
    "validation_fraction",
    "holdout_fraction",
    "heldout_fraction",
}
_SPLIT_RATIO_PERCENT_FIELDS = {
    "train_percent",
    "training_percent",
    "train_percentage",
    "training_percentage",
    "test_percent",
    "validation_percent",
    "holdout_percent",
    "heldout_percent",
    "test_percentage",
    "validation_percentage",
    "holdout_percentage",
    "heldout_percentage",
}
_SPLIT_RATIO_COUNT_FIELDS = {
    "train_size",
    "training_size",
    "train_rows",
    "training_rows",
    "train_count",
    "training_count",
    "test_size",
    "validation_size",
    "holdout_size",
    "heldout_size",
    "test_rows",
    "validation_rows",
    "holdout_rows",
    "heldout_rows",
    "test_count",
    "validation_count",
    "holdout_count",
    "heldout_count",
}
