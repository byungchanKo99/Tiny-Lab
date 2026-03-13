"""Tests for event system and action_needed logic."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tiny_lab.events import EventType, emit_event, load_events, compute_action_needed


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    research = tmp_path / "research"
    research.mkdir()
    return tmp_path


class TestEmitEvent:
    def test_writes_jsonl(self, project_dir: Path):
        emit_event(project_dir, EventType.LOOP_STARTED, {"pid": 123})
        events_path = project_dir / "research" / ".events.jsonl"
        assert events_path.exists()
        record = json.loads(events_path.read_text().strip())
        assert record["event"] == "loop_started"
        assert record["data"]["pid"] == 123
        assert "timestamp" in record

    def test_with_callback(self, project_dir: Path):
        with patch("tiny_lab.events.subprocess.Popen") as mock_popen:
            emit_event(project_dir, EventType.EXPERIMENT_DONE, {"exp_id": "EXP-001"}, on_event_cmd="echo test")
            mock_popen.assert_called_once()
            call_kwargs = mock_popen.call_args
            assert call_kwargs[0][0] == "echo test"
            env = call_kwargs[1]["env"]
            assert env["TINYLAB_EVENT"] == "experiment_done"

    def test_failure_safe(self, project_dir: Path):
        """Event failure must not raise."""
        # Make research dir read-only to force write failure
        events_path = project_dir / "research" / ".events.jsonl"
        events_path.write_text("")
        events_path.chmod(0o000)
        try:
            emit_event(project_dir, EventType.LOOP_STARTED, {"pid": 1})
        finally:
            events_path.chmod(0o644)
        # No exception raised

    def test_multiple_events(self, project_dir: Path):
        emit_event(project_dir, EventType.LOOP_STARTED, {"pid": 1})
        emit_event(project_dir, EventType.EXPERIMENT_DONE, {"exp_id": "EXP-001"})
        events = load_events(project_dir)
        assert len(events) == 2
        assert events[0]["event"] == "loop_started"
        assert events[1]["event"] == "experiment_done"


class TestLoadEvents:
    def test_loads_events(self, project_dir: Path):
        emit_event(project_dir, EventType.LOOP_STARTED, {"pid": 1})
        emit_event(project_dir, EventType.NEW_BEST, {"exp_id": "EXP-005", "metric_value": 0.95})
        events = load_events(project_dir)
        assert len(events) == 2
        assert events[1]["data"]["metric_value"] == 0.95

    def test_empty_when_no_file(self, project_dir: Path):
        assert load_events(project_dir) == []

    def test_respects_last_n(self, project_dir: Path):
        for i in range(10):
            emit_event(project_dir, EventType.EXPERIMENT_DONE, {"exp_id": f"EXP-{i}"})
        events = load_events(project_dir, last_n=3)
        assert len(events) == 3
        assert events[0]["data"]["exp_id"] == "EXP-7"


class TestComputeActionNeeded:
    def test_new_best(self):
        events = [{"event": "new_best", "data": {"exp_id": "EXP-010", "metric_value": 0.95}}]
        needed, reasons = compute_action_needed(True, events, [], {})
        assert needed
        assert any("New best" in r for r in reasons)

    def test_circuit_breaker(self):
        events = [{"event": "circuit_breaker_warning", "data": {"invalid_count": 4, "threshold": 5}}]
        needed, reasons = compute_action_needed(True, events, [], {})
        assert needed
        assert any("Circuit breaker" in r for r in reasons)

    def test_consecutive_failures(self):
        ledger = [
            {"class": "LOSS"},
            {"class": "LOSS"},
            {"class": "INVALID"},
        ]
        needed, reasons = compute_action_needed(True, [], ledger, {})
        assert needed
        assert any("Consecutive failures" in r for r in reasons)

    def test_loop_dead(self):
        needed, reasons = compute_action_needed(False, [], [], {}, lock_exists=True)
        assert needed
        assert any("stopped unexpectedly" in r for r in reasons)

    def test_queue_empty_while_running(self):
        needed, reasons = compute_action_needed(True, [], [], {"done": 5})
        assert needed
        assert any("Queue empty" in r for r in reasons)

    def test_all_clear(self):
        ledger = [{"class": "WIN"}, {"class": "LOSS"}, {"class": "WIN"}]
        needed, reasons = compute_action_needed(True, [], ledger, {"pending": 3})
        assert not needed
        assert reasons == []

    def test_not_dead_when_no_lock(self):
        """No lock file + not alive = clean stopped state, not unexpected."""
        needed, reasons = compute_action_needed(False, [], [], {}, lock_exists=False)
        # Only queue empty triggers if loop is not alive
        assert not needed
