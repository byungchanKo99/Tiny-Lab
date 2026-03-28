"""Tests for state persistence."""
from __future__ import annotations

import json
from pathlib import Path

from tiny_lab.state import LoopState, load_state, save_state, set_state


class TestState:
    def test_default_state(self, tmp_path):
        (tmp_path / "research").mkdir()
        ls = load_state(tmp_path)
        assert ls.state == "INIT"
        assert ls.current_iteration == 1

    def test_save_and_load(self, tmp_path):
        (tmp_path / "research").mkdir()
        ls = LoopState(current_iteration=2, state="PLAN", current_phase_id="phase_0")
        save_state(tmp_path, ls)
        loaded = load_state(tmp_path)
        assert loaded.current_iteration == 2
        assert loaded.state == "PLAN"
        assert loaded.current_phase_id == "phase_0"

    def test_set_state(self, tmp_path):
        (tmp_path / "research").mkdir()
        save_state(tmp_path, LoopState())
        ls = set_state(tmp_path, "DOMAIN_RESEARCH", current_iteration=3)
        assert ls.state == "DOMAIN_RESEARCH"
        assert ls.current_iteration == 3
        # Verify persisted
        loaded = load_state(tmp_path)
        assert loaded.state == "DOMAIN_RESEARCH"

    def test_corrupt_state_file(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".state.json").write_text("not json")
        ls = load_state(tmp_path)
        assert ls.state == "INIT"  # fallback to default
