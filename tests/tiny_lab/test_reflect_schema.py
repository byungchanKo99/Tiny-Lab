"""Tests for v7.9 reflect schema extensions: framing_log section + delta + drift."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiny_lab.workflow import load_workflow


PRESETS_DIR = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets"


class TestFramingLogSection:
    """Research presets must declare the framing_log section so the board
    knows to render any framing_change entries."""

    @pytest.mark.parametrize(
        "preset",
        ["ml-experiment", "novel-method", "data-analysis", "review-paper"],
    )
    def test_framing_log_in_sections(self, preset):
        wf_data = json.loads((PRESETS_DIR / f"{preset}.json").read_text())
        sections = wf_data.get("board", {}).get("sections", [])
        assert "framing_log" in sections, (
            f"{preset} must include 'framing_log' in board.sections so the "
            f"v7.9 framing_change entries surface in `tiny-lab board`."
        )

    def test_ideate_does_not_require_framing_log(self):
        """ideate is short-lived (3 iters max) and intentionally omits framing_log."""
        wf_data = json.loads((PRESETS_DIR / "ideate.json").read_text())
        # Not required — but assert it loads cleanly
        load_workflow(PRESETS_DIR / "ideate.json")


class TestBoardRendersFramingLog:
    """The board CLI must scan iter_*/reflect.json and render framing_change
    entries when the framing_log section is enabled."""

    def test_board_renders_framing_change(self, tmp_path, capsys):
        """Set up a project with two iters, one carrying a framing_change,
        run `tiny-lab board`, and check the output contains the framing log."""
        import os
        import sys
        from tiny_lab.cli import main

        rd = tmp_path / "research"
        rd.mkdir()
        (rd / "iter_1").mkdir()
        (rd / "iter_2").mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "DONE", "type": "process"}],
            "board": {
                "title": "Test",
                "sections": ["constraints", "reflect", "framing_log"],
            },
        }))
        (rd / ".state.json").write_text(json.dumps({
            "state": "DONE",
            "current_iteration": 2,
            "current_phase_id": None,
            "session_id": None,
            "consecutive_failures": 0,
            "phase_retries": 0,
            "resumable": False,
        }))
        (rd / "iter_1" / "reflect.json").write_text(json.dumps({
            "decision": "idea_mutation",
            "reason": "baseline plateaued",
            "delta_from_previous_iter": "new_track",
            "framing_change": {
                "from_frame": "empirical hyperparameter sweep",
                "to_frame": "control-theoretic regularization formulation",
                "axis": "justification",
                "evidence_artifact": "research/iter_1/.method_design.json",
            },
        }))
        (rd / "iter_2" / "reflect.json").write_text(json.dumps({
            "decision": "add_phases",
            "reason": "ablation",
            "delta_from_previous_iter": "deepened",
            "drift_warning": True,
        }))

        cwd = os.getcwd()
        old_argv = sys.argv
        try:
            os.chdir(tmp_path)
            sys.argv = ["tiny-lab", "board"]
            main()
        finally:
            os.chdir(cwd)
            sys.argv = old_argv

        captured = capsys.readouterr().out
        # delta and drift should surface on the current-iter Reflect line
        assert "delta=deepened" in captured
        assert "drift" in captured
        # Framing Log section should pull from iter_1
        assert "Framing Log" in captured
        assert "control-theoretic" in captured


class TestReflectPromptDocumentsNewFields:
    """The reflect.md prompt must instruct the model to fill the v7.9 fields."""

    def test_prompt_mentions_new_fields(self):
        prompt_path = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "prompts" / "reflect.md"
        text = prompt_path.read_text()
        for required_field in (
            "delta_from_previous_iter",
            "delta_evidence",
            "delta_trigger",
            "drift_warning",
            "pivot_trigger",
            "framing_change",
            "idea_portfolio",
            "selected_direction",
            "selection_rationale",
            "abandoned_hypotheses",
        ):
            assert required_field in text, (
                f"reflect.md must teach the model to write the `{required_field}` "
                f"field — missing from the prompt."
            )
