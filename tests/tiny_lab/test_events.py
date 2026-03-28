"""Tests for event system."""
from __future__ import annotations

import json
from pathlib import Path

from tiny_lab.events import (
    emit, load_events, state_entered, phase_started,
    phase_completed, iteration_started, error_occurred, loop_done,
)


class TestEmit:
    def test_basic_emit(self, tmp_path):
        (tmp_path / "research").mkdir()
        emit(tmp_path, "test_event", {"key": "value"})
        events = load_events(tmp_path)
        assert len(events) == 1
        assert events[0]["event"] == "test_event"
        assert events[0]["data"]["key"] == "value"
        assert "timestamp" in events[0]

    def test_multiple_events(self, tmp_path):
        (tmp_path / "research").mkdir()
        emit(tmp_path, "e1")
        emit(tmp_path, "e2")
        emit(tmp_path, "e3")
        events = load_events(tmp_path)
        assert len(events) == 3
        assert [e["event"] for e in events] == ["e1", "e2", "e3"]

    def test_load_last_n(self, tmp_path):
        (tmp_path / "research").mkdir()
        for i in range(10):
            emit(tmp_path, f"e{i}")
        events = load_events(tmp_path, last_n=3)
        assert len(events) == 3
        assert events[0]["event"] == "e7"

    def test_load_empty(self, tmp_path):
        (tmp_path / "research").mkdir()
        assert load_events(tmp_path) == []


class TestConvenienceEmitters:
    def test_state_entered(self, tmp_path):
        (tmp_path / "research").mkdir()
        state_entered(tmp_path, "DOMAIN_RESEARCH", 1)
        events = load_events(tmp_path)
        assert events[0]["event"] == "state_entered"
        assert events[0]["data"]["state"] == "DOMAIN_RESEARCH"

    def test_phase_started(self, tmp_path):
        (tmp_path / "research").mkdir()
        phase_started(tmp_path, "phase_0", 1)
        events = load_events(tmp_path)
        assert events[0]["data"]["phase_id"] == "phase_0"

    def test_phase_completed(self, tmp_path):
        (tmp_path / "research").mkdir()
        phase_completed(tmp_path, "phase_0", 1, "done")
        events = load_events(tmp_path)
        assert events[0]["data"]["status"] == "done"

    def test_error_occurred(self, tmp_path):
        (tmp_path / "research").mkdir()
        error_occurred(tmp_path, "PHASE_RUN", "script crashed")
        events = load_events(tmp_path)
        assert events[0]["event"] == "error"
        assert events[0]["data"]["error"] == "script crashed"

    def test_loop_done(self, tmp_path):
        (tmp_path / "research").mkdir()
        loop_done(tmp_path, "completed")
        events = load_events(tmp_path)
        assert events[0]["event"] == "loop_done"
