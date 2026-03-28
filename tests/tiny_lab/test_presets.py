"""Tests for workflow presets — all presets must load and validate."""
from __future__ import annotations

from pathlib import Path

import pytest

from tiny_lab.workflow import load_workflow


PRESETS_DIR = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets"


@pytest.fixture(params=["ml-experiment", "review-paper", "novel-method", "data-analysis"])
def preset_path(request) -> Path:
    return PRESETS_DIR / f"{request.param}.yaml"


class TestPresets:
    def test_preset_loads(self, preset_path):
        """Every preset must load without validation errors."""
        wf = load_workflow(preset_path)
        assert len(wf.states) > 0

    def test_preset_has_autonomy(self, preset_path):
        wf = load_workflow(preset_path)
        assert wf.autonomy.mode in ("autonomous", "supervised")

    def test_preset_has_reflect(self, preset_path):
        """Every preset should have a REFLECT state."""
        wf = load_workflow(preset_path)
        ids = wf.state_ids()
        assert "REFLECT" in ids

    def test_preset_states_have_types(self, preset_path):
        wf = load_workflow(preset_path)
        for state in wf.states:
            assert state.type in ("ai_session", "process", "checkpoint")

    def test_preset_ai_sessions_have_prompt(self, preset_path):
        """All ai_session states should have a prompt template."""
        wf = load_workflow(preset_path)
        for state in wf.states:
            if state.type == "ai_session":
                assert state.prompt is not None, f"{state.id} has no prompt"


class TestCustomPreset:
    def test_custom_loads_empty(self):
        path = PRESETS_DIR / "custom.yaml"
        # Custom has empty states — should not crash but may not validate
        # (empty states list is caught by load_workflow)
        import yaml
        data = yaml.safe_load(path.read_text())
        assert data["states"] == []
