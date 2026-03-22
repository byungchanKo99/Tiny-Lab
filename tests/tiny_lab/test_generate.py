"""Tests for generate history injection and escalation logic."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from tiny_lab.generate import (
    _format_history, _format_failure_history, _check_escalation,
    _validate_new_entries, _build_trial_summary, _validate_optimize_changes,
    _OPTIMIZE_LIMITS, _MAX_CHANGE_RATIO,
)


class TestFormatHistory:
    def test_empty(self):
        assert _format_history([]) == ""

    def test_with_entries(self):
        entries = [
            {"state": "EXPLORING", "reasoning": "Testing lr values", "hypotheses_added_count": 3, "changes_made": ["extended lr space"]},
            {"state": "REFINING", "reasoning": "Narrowing around best", "hypotheses_added_count": 2, "changes_made": []},
            {"state": "SATURATED", "reasoning": "Trying ensembles", "hypotheses_added_count": 4, "changes_made": ["added ensemble lever"]},
        ]
        result = _format_history(entries)
        assert "PREVIOUS GENERATION CYCLES" in result
        assert "Cycle 1: state=EXPLORING, +3 hypotheses" in result
        assert "Cycle 2: state=REFINING, +2 hypotheses" in result
        assert "Cycle 3: state=SATURATED, +4 hypotheses" in result
        assert "Testing lr values" in result
        assert "extended lr space" in result

    def test_truncates_reasoning(self):
        entry = {"state": "EXPLORING", "reasoning": "x" * 200, "hypotheses_added_count": 1, "changes_made": []}
        result = _format_history([entry])
        # Reasoning truncated to 120 chars
        assert "x" * 120 in result
        assert "x" * 121 not in result


    def test_references_in_history(self):
        entries = [
            {"state": "EXPLORING", "reasoning": "Trying", "hypotheses_added_count": 1,
             "changes_made": [], "references": ["paper-X", "EXP-003 trend"]},
        ]
        result = _format_history(entries)
        assert "References: paper-X, EXP-003 trend" in result


class TestFormatFailureHistory:
    def test_empty_ledger(self, tmp_path):
        (tmp_path / "research").mkdir()
        (tmp_path / "research" / "ledger.jsonl").write_text("")
        assert _format_failure_history(tmp_path, "loss") == ""

    def test_no_failures(self, tmp_path):
        (tmp_path / "research").mkdir()
        entry = {"id": "EXP-002", "class": "WIN", "question": "test", "changed_variable": "lr",
                 "value": "0.05", "primary_metric": {"loss": 0.5, "baseline": 0.6, "delta_pct": -16.7},
                 "family": "t", "status": "done", "decision": "win"}
        (tmp_path / "research" / "ledger.jsonl").write_text(json.dumps(entry) + "\n")
        assert _format_failure_history(tmp_path, "loss") == ""

    def test_formats_failures(self, tmp_path):
        (tmp_path / "research").mkdir()
        entries = []
        for i, cls in enumerate(["LOSS", "INVALID", "WIN"]):
            entries.append(json.dumps({
                "id": f"EXP-{i:03d}", "class": cls, "question": f"test {cls}",
                "changed_variable": "lr", "value": f"0.{i}",
                "primary_metric": {"loss": 0.5 + i * 0.1, "baseline": 0.6, "delta_pct": -10 + i * 5},
                "family": "t", "status": "done", "decision": cls.lower(),
            }))
        (tmp_path / "research" / "ledger.jsonl").write_text("\n".join(entries) + "\n")
        result = _format_failure_history(tmp_path, "loss")
        assert "FAILED APPROACHES" in result
        assert "EXP-000 [LOSS]" in result
        assert "EXP-001 [INVALID]" in result
        assert "EXP-002" not in result  # WIN should not appear

    def test_limits_to_15(self, tmp_path):
        (tmp_path / "research").mkdir()
        entries = []
        for i in range(20):
            entries.append(json.dumps({
                "id": f"EXP-{i:03d}", "class": "LOSS", "question": f"test {i}",
                "changed_variable": "lr", "value": f"0.{i}",
                "primary_metric": {"loss": 0.5, "baseline": 0.6, "delta_pct": -10},
                "family": "t", "status": "done", "decision": "loss",
            }))
        (tmp_path / "research" / "ledger.jsonl").write_text("\n".join(entries) + "\n")
        result = _format_failure_history(tmp_path, "loss")
        # Should show last 15, not first 15
        assert "EXP-005" in result
        assert "EXP-019" in result
        assert "EXP-004" not in result


class TestCheckEscalation:
    def test_no_history(self):
        assert _check_escalation([]) is None

    def test_insufficient_history(self):
        assert _check_escalation([{"state": "EXPLORING"}]) is None

    def test_two_exploring(self):
        history = [
            {"state": "EXPLORING"},
            {"state": "EXPLORING"},
        ]
        assert _check_escalation(history) == "SATURATED"

    def test_mixed_no_escalation(self):
        history = [
            {"state": "EXPLORING"},
            {"state": "SATURATED"},
        ]
        assert _check_escalation(history) is None

    def test_refining_pattern(self):
        history = [
            {"state": "REFINING"},
            {"state": "REFINING"},
        ]
        assert _check_escalation(history) == "SATURATED"

    def test_exploring_and_refining_mixed(self):
        history = [
            {"state": "SATURATED"},
            {"state": "EXPLORING"},
            {"state": "REFINING"},
        ]
        assert _check_escalation(history) == "SATURATED"

    def test_three_with_one_saturated(self):
        """Only 1 non-saturated in last 3 → no escalation."""
        history = [
            {"state": "SATURATED"},
            {"state": "SATURATED"},
            {"state": "EXPLORING"},
        ]
        assert _check_escalation(history) is None

    def test_uses_last_three(self):
        """Escalation only looks at last 3 entries."""
        history = [
            {"state": "EXPLORING"},
            {"state": "EXPLORING"},
            {"state": "SATURATED"},
            {"state": "SATURATED"},
            {"state": "EXPLORING"},
        ]
        # Last 3: SATURATED, SATURATED, EXPLORING → only 1 non-saturated → no escalation
        assert _check_escalation(history) is None


class TestBuildTrialSummary:
    def test_empty_ledger(self):
        assert _build_trial_summary([], {"time_budget": 300, "n_trials": 20}) == ""

    def test_skips_baseline(self):
        ledger = [{"class": "BASELINE", "approach": "baseline"}]
        assert _build_trial_summary(ledger, {"time_budget": 300, "n_trials": 20}) == ""

    def test_flags_underexplored(self):
        ledger = [
            {
                "class": "WIN", "approach": "xgb_tuned", "id": "EXP-002",
                "optimize_result": {"n_trials": 20, "total_seconds": 180, "best_value": 0.85},
            },
            {
                "class": "WIN", "approach": "lgbm_tuned", "id": "EXP-003",
                "optimize_result": {"n_trials": 5, "total_seconds": 300, "best_value": 0.84},
            },
        ]
        result = _build_trial_summary(ledger, {"time_budget": 300, "n_trials": 20})
        assert "UNDEREXPLORED" in result
        assert "lgbm_tuned" in result
        # xgb_tuned should NOT be flagged (20/20 trials)
        assert "xgb_tuned" in result
        lines = result.split("\n")
        xgb_line = [l for l in lines if "xgb_tuned" in l][0]
        assert "UNDEREXPLORED" not in xgb_line

    def test_sufficient_trials_no_flag(self):
        ledger = [
            {
                "class": "WIN", "approach": "rf", "id": "EXP-002",
                "optimize_result": {"n_trials": 20, "total_seconds": 100, "best_value": 0.8},
            },
        ]
        result = _build_trial_summary(ledger, {"time_budget": 300, "n_trials": 20})
        rf_line = [l for l in result.split("\n") if "rf" in l][0]
        assert "UNDEREXPLORED" not in rf_line

    def test_no_optimize_result_skipped(self):
        ledger = [{"class": "WIN", "approach": "manual", "id": "EXP-002"}]
        assert _build_trial_summary(ledger, {"time_budget": 300, "n_trials": 20}) == ""


class TestValidateOptimizeChanges:
    def _setup_project(self, tmp_path, optimize_cfg):
        research = tmp_path / "research"
        research.mkdir(exist_ok=True)
        project = {
            "name": "test",
            "baseline": {"command": "echo test"},
            "metric": {"name": "loss"},
            "optimize": optimize_cfg,
        }
        (research / "project.yaml").write_text(yaml.dump(project))
        return tmp_path

    def test_no_changes_returns_empty(self, tmp_path):
        self._setup_project(tmp_path, {"type": "random", "time_budget": 300, "n_trials": 20})
        changes = _validate_optimize_changes(tmp_path, {"type": "random", "time_budget": 300, "n_trials": 20})
        assert changes == []

    def test_valid_increase(self, tmp_path):
        self._setup_project(tmp_path, {"type": "random", "time_budget": 600, "n_trials": 20})
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 300, "n_trials": 20})
        assert len(changes) == 1
        assert "time_budget" in changes[0]
        assert "600" in changes[0]

    def test_clamps_above_maximum(self, tmp_path):
        self._setup_project(tmp_path, {"type": "random", "time_budget": 5000, "n_trials": 20})
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 300, "n_trials": 20})
        # Should be clamped: 5000 > 1800 (max), and also 5000/300 > 3x ratio
        project = yaml.safe_load((tmp_path / "research" / "project.yaml").read_text())
        assert project["optimize"]["time_budget"] <= 1800

    def test_clamps_below_minimum(self, tmp_path):
        self._setup_project(tmp_path, {"type": "random", "time_budget": 10, "n_trials": 20})
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 300, "n_trials": 20})
        project = yaml.safe_load((tmp_path / "research" / "project.yaml").read_text())
        # 10/300 = 0.033x < 1/3x ratio → clamped to 100, then 100 >= 60 min → 100
        assert project["optimize"]["time_budget"] >= 60

    def test_clamps_ratio_increase(self, tmp_path):
        # 300 * 3x = 900. Setting to 1500 should be ratio-clamped to 900.
        self._setup_project(tmp_path, {"type": "random", "time_budget": 1500, "n_trials": 20})
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 300, "n_trials": 20})
        project = yaml.safe_load((tmp_path / "research" / "project.yaml").read_text())
        assert project["optimize"]["time_budget"] == 900

    def test_clamps_ratio_decrease(self, tmp_path):
        # 900 / 3x = 300. Setting to 100 should be ratio-clamped first, then abs-clamped.
        self._setup_project(tmp_path, {"type": "random", "time_budget": 100, "n_trials": 20})
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 900, "n_trials": 20})
        project = yaml.safe_load((tmp_path / "research" / "project.yaml").read_text())
        # 100/900 = 0.11x < 1/3x → clamped to max(900/3, 60) = 300
        assert project["optimize"]["time_budget"] == 300

    def test_n_trials_clamped(self, tmp_path):
        self._setup_project(tmp_path, {"type": "random", "time_budget": 300, "n_trials": 500})
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 300, "n_trials": 20})
        project = yaml.safe_load((tmp_path / "research" / "project.yaml").read_text())
        # 500/20 = 25x > 3x ratio → clamped to 60, then 60 >= 5 min → 60
        assert project["optimize"]["n_trials"] == 60

    def test_no_optimize_section(self, tmp_path):
        research = tmp_path / "research"
        research.mkdir(exist_ok=True)
        project = {"name": "test", "baseline": {"command": "echo"}, "metric": {"name": "loss"}}
        (research / "project.yaml").write_text(yaml.dump(project))
        changes = _validate_optimize_changes(tmp_path, {"time_budget": 300})
        assert changes == []


class TestValidateNewEntries:
    def test_generated_at_auto_inserted(self, tmp_path):
        """New entries get generated_at timestamp automatically."""
        research = tmp_path / "research"
        research.mkdir()
        before = [
            {"id": "H-1", "status": "done", "lever": "lr", "value": "0.01", "description": "old"},
        ]
        after = before + [
            {"id": "H-2", "status": "pending", "lever": "lr", "value": "0.05", "description": "new"},
        ]
        (research / "hypothesis_queue.yaml").write_text(yaml.dump({"hypotheses": after}))
        valid = _validate_new_entries(before, after, tmp_path)
        assert valid == 1
        # Check generated_at was inserted into the entry
        assert "generated_at" in after[1]

    def test_generated_at_not_overwritten(self, tmp_path):
        """Existing generated_at is preserved."""
        research = tmp_path / "research"
        research.mkdir()
        before = []
        after = [
            {"id": "H-1", "status": "pending", "lever": "lr", "value": "0.01",
             "description": "test", "generated_at": "2025-01-01T00:00:00+00:00"},
        ]
        (research / "hypothesis_queue.yaml").write_text(yaml.dump({"hypotheses": after}))
        _validate_new_entries(before, after, tmp_path)
        assert after[0]["generated_at"] == "2025-01-01T00:00:00+00:00"

    def test_hypothesis_with_reasoning_validates(self, tmp_path):
        """Hypothesis with reasoning field passes validation."""
        research = tmp_path / "research"
        research.mkdir()
        before = []
        after = [
            {"id": "H-1", "status": "pending", "lever": "lr", "value": "0.05",
             "description": "lower lr", "reasoning": "LR 0.01 won — try lower"},
        ]
        (research / "hypothesis_queue.yaml").write_text(yaml.dump({"hypotheses": after}))
        valid = _validate_new_entries(before, after, tmp_path)
        assert valid == 1
