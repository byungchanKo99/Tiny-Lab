"""Tests for conditional transition resolver."""
from __future__ import annotations

from pathlib import Path

import pytest
import json

from tiny_lab.conditions import resolve_condition
from tiny_lab.errors import StateError
from tiny_lab.workflow import ConditionSpec


class TestFileCondition:
    def test_reads_field(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        (tmp_path / "research" / "iter_1" / "reflect.json").write_text(
            json.dumps({"decision": "done", "reason": "target met"})
        )
        cond = ConditionSpec(source="iter_1/reflect.json", field="decision")
        result = resolve_condition(cond, {"done": "DONE", "retry": "PLAN"}, tmp_path, 1)
        assert result == "DONE"

    def test_missing_file_raises(self, tmp_path):
        (tmp_path / "research").mkdir(parents=True)
        cond = ConditionSpec(source="iter_1/nope.json", field="x")
        with pytest.raises(StateError, match="not found"):
            resolve_condition(cond, {"a": "B"}, tmp_path, 1)

    def test_missing_field_raises(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        (tmp_path / "research" / "iter_1" / "data.json").write_text(json.dumps({"x": 1}))
        cond = ConditionSpec(source="iter_1/data.json", field="y")
        with pytest.raises(StateError, match="not found"):
            resolve_condition(cond, {"1": "A"}, tmp_path, 1)

    def test_default_fallback(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        (tmp_path / "research" / "iter_1" / "r.json").write_text(json.dumps({"x": "unknown"}))
        cond = ConditionSpec(source="iter_1/r.json", field="x")
        result = resolve_condition(cond, {"a": "A", "default": "FALLBACK"}, tmp_path, 1)
        assert result == "FALLBACK"

    def test_no_match_raises(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        (tmp_path / "research" / "iter_1" / "r.json").write_text(json.dumps({"x": "unknown"}))
        cond = ConditionSpec(source="iter_1/r.json", field="x")
        with pytest.raises(StateError, match="No matching"):
            resolve_condition(cond, {"a": "A", "b": "B"}, tmp_path, 1)

    def test_iter_placeholder(self, tmp_path):
        (tmp_path / "research" / "iter_2").mkdir(parents=True)
        (tmp_path / "research" / "iter_2" / "r.json").write_text(json.dumps({"d": "yes"}))
        cond = ConditionSpec(source="{iter}/r.json", field="d")
        # iteration=2 → {iter} becomes iter_2
        result = resolve_condition(cond, {"yes": "GO"}, tmp_path, 2)
        assert result == "GO"


class TestBuiltinCheck:
    def test_has_pending_phases_true(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        plan = {
            "name": "test", "phases": [
                {"id": "p0", "status": "done"},
                {"id": "p1", "status": "pending", "depends_on": ["p0"]},
            ],
        }
        (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps(plan))
        cond = ConditionSpec(check="has_pending_phases")
        result = resolve_condition(cond, {"true": "CODE", "false": "REFLECT"}, tmp_path, 1)
        assert result == "CODE"

    def test_has_pending_phases_false(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        plan = {
            "name": "test", "phases": [
                {"id": "p0", "status": "done"},
            ],
        }
        (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps(plan))
        cond = ConditionSpec(check="has_pending_phases")
        result = resolve_condition(cond, {"true": "CODE", "false": "REFLECT"}, tmp_path, 1)
        assert result == "REFLECT"

    def test_unknown_check(self, tmp_path):
        cond = ConditionSpec(check="nonexistent")
        with pytest.raises(StateError, match="Unknown"):
            resolve_condition(cond, {}, tmp_path, 1)
