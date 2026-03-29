"""Tests for CLI commands."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


class TestInit:
    def test_init_creates_structure(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "ml-experiment")

        assert (tmp_path / "research" / ".workflow.json").exists()
        assert (tmp_path / ".claude" / "hooks" / "state-gate.sh").exists()
        assert (tmp_path / ".claude" / "hooks" / "state-advance.sh").exists()
        assert (tmp_path / "prompts" / "domain_research.md").exists()
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "shared").exists()

    def test_init_registers_hooks(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        hooks = settings["hooks"]
        assert any("state-gate" in e["command"] for e in hooks["PreToolUse"])
        assert any("state-advance" in e["command"] for e in hooks["PostToolUse"])

    def test_init_idempotent_hooks(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "ml-experiment")
        _cmd_init(tmp_path, "ml-experiment")  # second init

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        # Should not duplicate hook entries
        assert len(settings["hooks"]["PreToolUse"]) == 1
        assert len(settings["hooks"]["PostToolUse"]) == 1

    def test_init_preserves_existing_settings(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        # Pre-existing settings
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Read"]}, "hooks": {}})
        )
        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert settings["permissions"]["allow"] == ["Read"]
        assert "PreToolUse" in settings["hooks"]

    def test_init_review_preset(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "review-paper")

        wf = json.loads((tmp_path / "research" / ".workflow.json").read_text())
        state_ids = [s["id"] for s in wf["states"]]
        assert "SCOPE_DEFINITION" in state_ids
        assert "LITERATURE_SEARCH" in state_ids

    def test_init_copies_review_prompts(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "review-paper")

        assert (tmp_path / "prompts" / "review" / "scope.md").exists()
        assert (tmp_path / "prompts" / "review" / "literature_search.md").exists()
        assert (tmp_path / "prompts" / "review" / "synthesis.md").exists()


class TestStatus:
    def test_status_default(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_status
        from tiny_lab.state import save_state, LoopState
        (tmp_path / "research").mkdir()
        save_state(tmp_path, LoopState(state="PLAN", current_iteration=2))

        _cmd_status(tmp_path)
        output = capsys.readouterr().out
        assert "PLAN" in output
        assert "2" in output


class TestIntervene:
    def test_writes_intervention(self, tmp_path):
        from tiny_lab.cli import _cmd_intervene
        (tmp_path / "research").mkdir()
        _cmd_intervene(tmp_path, "approve", [])

        ipath = tmp_path / "research" / ".intervention.json"
        assert ipath.exists()
        data = json.loads(ipath.read_text())
        assert data["action"] == "approve"

    def test_skip_phase(self, tmp_path):
        from tiny_lab.cli import _cmd_intervene
        (tmp_path / "research").mkdir()
        _cmd_intervene(tmp_path, "skip", ["phase_2"])

        data = json.loads((tmp_path / "research" / ".intervention.json").read_text())
        assert data["action"] == "skip_phase"
        assert data["skip_phase"]["phase_id"] == "phase_2"
