"""Tests for generate history injection and escalation logic."""
from __future__ import annotations

from tiny_lab.generate import _format_history, _check_escalation


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
