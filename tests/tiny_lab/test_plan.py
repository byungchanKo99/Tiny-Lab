"""Tests for research plan parser."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tiny_lab.errors import PlanError
from tiny_lab.plan import load_plan, pending_phases, next_pending_phase, update_phase_status


@pytest.fixture()
def plan_dir(tmp_path: Path) -> Path:
    (tmp_path / "research" / "iter_1").mkdir(parents=True)
    plan = {
        "name": "test",
        "metric": {"name": "loss", "direction": "minimize"},
        "phases": [
            {"id": "p0", "status": "pending", "depends_on": [], "type": "script"},
            {"id": "p1", "status": "pending", "depends_on": ["p0"], "type": "script"},
            {"id": "p2", "status": "pending", "depends_on": ["p0", "p1"], "type": "optimize"},
        ],
    }
    (tmp_path / "research" / "iter_1" / "research_plan.yaml").write_text(yaml.dump(plan))
    return tmp_path


class TestLoadPlan:
    def test_loads(self, plan_dir):
        plan = load_plan(plan_dir, 1)
        assert plan["name"] == "test"
        assert len(plan["phases"]) == 3

    def test_missing(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        with pytest.raises(PlanError):
            load_plan(tmp_path, 1)


class TestPendingPhases:
    def test_initial_only_p0(self, plan_dir):
        plan = load_plan(plan_dir, 1)
        pending = pending_phases(plan)
        assert len(pending) == 1
        assert pending[0]["id"] == "p0"

    def test_after_p0_done(self, plan_dir):
        update_phase_status(plan_dir, 1, "p0", "done")
        plan = load_plan(plan_dir, 1)
        pending = pending_phases(plan)
        assert len(pending) == 1
        assert pending[0]["id"] == "p1"

    def test_after_all_done(self, plan_dir):
        for pid in ["p0", "p1", "p2"]:
            update_phase_status(plan_dir, 1, pid, "done")
        plan = load_plan(plan_dir, 1)
        assert pending_phases(plan) == []


class TestNextPendingPhase:
    def test_returns_first(self, plan_dir):
        plan = load_plan(plan_dir, 1)
        p = next_pending_phase(plan)
        assert p is not None
        assert p["id"] == "p0"

    def test_returns_none_when_empty(self, plan_dir):
        for pid in ["p0", "p1", "p2"]:
            update_phase_status(plan_dir, 1, pid, "done")
        plan = load_plan(plan_dir, 1)
        assert next_pending_phase(plan) is None


class TestUpdatePhaseStatus:
    def test_updates(self, plan_dir):
        update_phase_status(plan_dir, 1, "p0", "running")
        plan = load_plan(plan_dir, 1)
        assert plan["phases"][0]["status"] == "running"
