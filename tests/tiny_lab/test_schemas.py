"""Tests for schema validation functions."""
from __future__ import annotations

import pytest

from tiny_lab.schemas import (
    ValidationError,
    validate,
    validate_hypothesis_entry,
    validate_eval_result,
    validate_project_deep,
)


# ---------------------------------------------------------------------------
# validate_hypothesis_entry
# ---------------------------------------------------------------------------

class TestValidateHypothesisEntry:
    def test_valid_v1_entry(self):
        entry = {"id": "H-1", "status": "pending", "lever": "lr", "value": 0.01, "description": "test"}
        assert validate_hypothesis_entry(entry, strict=False) == []

    def test_valid_v1_entry_string_value(self):
        entry = {"id": "H-2", "status": "done", "lever": "algo", "value": "sgd", "description": "test"}
        assert validate_hypothesis_entry(entry, strict=False) == []

    def test_valid_v2_entry(self):
        entry = {
            "id": "H-10", "status": "pending", "approach": "xgboost_stacking",
            "description": "XGBoost+LightGBM stacking",
            "search_space": {"lr": {"type": "float", "low": 0.001, "high": 0.3}},
        }
        assert validate_hypothesis_entry(entry, strict=False) == []

    def test_valid_v2_entry_minimal(self):
        entry = {"id": "H-11", "status": "pending", "approach": "random_forest", "description": "RF baseline"}
        assert validate_hypothesis_entry(entry, strict=False) == []

    def test_missing_both_lever_and_approach(self):
        entry = {"id": "H-1", "status": "pending", "description": "test"}
        errors = validate_hypothesis_entry(entry, strict=False)
        assert any("lever" in e or "approach" in e for e in errors)

    def test_missing_required_field(self):
        entry = {"id": "H-1", "status": "pending", "lever": "lr"}
        errors = validate_hypothesis_entry(entry, strict=False)
        assert any("description" in e for e in errors)

    def test_invalid_status_enum(self):
        entry = {"id": "H-1", "status": "bogus", "lever": "lr", "value": 1, "description": "x"}
        errors = validate_hypothesis_entry(entry, strict=False)
        assert any("status" in e for e in errors)

    def test_wrong_type_for_id(self):
        entry = {"id": 123, "status": "pending", "lever": "lr", "value": 1, "description": "x"}
        errors = validate_hypothesis_entry(entry, strict=False)
        assert any("id" in e for e in errors)

    def test_strict_raises(self):
        with pytest.raises(ValidationError):
            validate_hypothesis_entry({"id": "H-1"})

    def test_non_dict_input(self):
        errors = validate_hypothesis_entry("not a dict", strict=False)
        assert errors

    def test_v2_with_optional_fields(self):
        entry = {
            "id": "H-12", "status": "pending", "approach": "xgboost",
            "description": "XGBoost with custom script",
            "search_space": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            "optimize_type": "grid",
            "references": ["paper-X"],
            "code_changes": "modify train.py to use XGBoost",
        }
        assert validate_hypothesis_entry(entry, strict=False) == []


# ---------------------------------------------------------------------------
# validate_eval_result
# ---------------------------------------------------------------------------

class TestValidateEvalResult:
    def test_valid_result(self):
        assert validate_eval_result({"score": 5}, strict=False) == []

    def test_valid_with_optional_fields(self):
        data = {"score": 7, "reasoning": "good", "strengths": ["a"], "weaknesses": ["b"]}
        assert validate_eval_result(data, strict=False) == []

    def test_score_out_of_range(self):
        errors = validate_eval_result({"score": 11}, score_range=(1, 10), strict=False)
        assert any("range" in e for e in errors)

    def test_score_at_boundary_low(self):
        assert validate_eval_result({"score": 1}, score_range=(1, 10), strict=False) == []

    def test_score_at_boundary_high(self):
        assert validate_eval_result({"score": 10}, score_range=(1, 10), strict=False) == []

    def test_custom_score_range(self):
        assert validate_eval_result({"score": 50}, score_range=(0, 100), strict=False) == []
        errors = validate_eval_result({"score": 101}, score_range=(0, 100), strict=False)
        assert errors

    def test_missing_score(self):
        errors = validate_eval_result({}, strict=False)
        assert any("score" in e for e in errors)

    def test_wrong_type_score(self):
        errors = validate_eval_result({"score": "five"}, strict=False)
        assert errors


# ---------------------------------------------------------------------------
# validate_project_deep
# ---------------------------------------------------------------------------

class TestValidateProjectDeep:
    def _minimal_project(self):
        return {
            "name": "test",
            "baseline": {"command": "echo hi"},
            "metric": {"name": "loss"},
            "levers": {"lr": {"space": [0.01, 0.1]}},
        }

    def test_valid_minimal(self):
        assert validate_project_deep(self._minimal_project(), strict=False) == []

    def test_missing_metric_name(self):
        proj = self._minimal_project()
        proj["metric"] = {"direction": "minimize"}
        errors = validate_project_deep(proj, strict=False)
        assert any("metric.name" in e for e in errors)

    def test_missing_baseline_command(self):
        proj = self._minimal_project()
        proj["baseline"] = {}
        errors = validate_project_deep(proj, strict=False)
        assert any("baseline.command" in e for e in errors)

    def test_lever_missing_space(self):
        proj = self._minimal_project()
        proj["levers"]["lr"] = {"flag": "--lr"}
        errors = validate_project_deep(proj, strict=False)
        assert any("space" in e for e in errors)

    def test_lever_not_dict(self):
        proj = self._minimal_project()
        proj["levers"]["lr"] = "not_a_dict"
        errors = validate_project_deep(proj, strict=False)
        assert errors

    def test_missing_top_level_required(self):
        errors = validate_project_deep({"name": "x"}, strict=False)
        assert any("baseline" in e for e in errors)


# ---------------------------------------------------------------------------
# validate (generic)
# ---------------------------------------------------------------------------

class TestValidateGeneric:
    def test_unknown_schema_raises(self):
        with pytest.raises(KeyError, match="Unknown schema"):
            validate({}, "nonexistent_schema")

    def test_ledger_entry_valid(self):
        entry = {
            "id": "EXP-001", "question": "q", "family": "f",
            "changed_variable": "x", "status": "done", "class": "WIN",
            "primary_metric": {"loss": 1.0}, "decision": "win",
        }
        assert validate(entry, "ledger_entry", strict=False) == []

    def test_ledger_entry_invalid_class(self):
        entry = {
            "id": "EXP-001", "question": "q", "family": "f",
            "changed_variable": "x", "status": "done", "class": "MAYBE",
            "primary_metric": {}, "decision": "win",
        }
        errors = validate(entry, "ledger_entry", strict=False)
        assert any("class" in e for e in errors)
