"""Tests for v7.10: HYPOTHESIS_UPDATE state, timeline command, idea_provenance."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tiny_lab.workflow import load_workflow


PRESETS_DIR = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets"


class TestHypothesisUpdateState:
    """HYPOTHESIS_UPDATE must sit between PHASE_RECORD and CHECKPOINT in
    every research preset that has the phase loop."""

    @pytest.mark.parametrize(
        "preset", ["ml-experiment", "novel-method", "data-analysis"],
    )
    def test_hypothesis_update_between_record_and_checkpoint(self, preset):
        wf = load_workflow(PRESETS_DIR / f"{preset}.json")
        ids = wf.state_ids()
        assert "PHASE_RECORD" in ids
        assert "HYPOTHESIS_UPDATE" in ids
        assert "CHECKPOINT" in ids
        record = wf.get_state("PHASE_RECORD")
        update = wf.get_state("HYPOTHESIS_UPDATE")
        assert record.next == "HYPOTHESIS_UPDATE", (
            "PHASE_RECORD must hand off to HYPOTHESIS_UPDATE so the "
            "result-interpretation step is never skipped."
        )
        assert update.next == "CHECKPOINT"
        # Required fields enforce the schema
        assert update.completion is not None
        assert "iteration" in update.completion.required_fields
        assert "entries" in update.completion.required_fields

    def test_review_paper_does_not_have_hypothesis_update(self):
        """review-paper has no PHASE loop, so no HYPOTHESIS_UPDATE."""
        wf = load_workflow(PRESETS_DIR / "review-paper.json")
        assert "HYPOTHESIS_UPDATE" not in wf.state_ids()


class TestHypothesisUpdatePromptDocumented:
    def test_prompt_file_exists(self):
        p = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "prompts" / "hypothesis_update.md"
        assert p.exists()
        text = p.read_text()
        for required in (
            "incoming_hypothesis",
            "result_interpretation",
            "outgoing_hypothesis",
            "drift_axis",
            "Append",  # append-only rule
        ):
            assert required in text


class TestIdeaProvenance:
    def test_idea_refine_documents_idea_provenance(self):
        p = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "prompts" / "idea_refine.md"
        text = p.read_text()
        assert "idea_provenance" in text
        assert "inspirations" in text
        assert "differentiation" in text


class TestTimelineCommand:
    """`tiny-lab timeline` must produce a markdown table summarizing every
    iteration's reflect.json + hypothesis_log."""

    def _setup(self, tmp_path: Path) -> None:
        rd = tmp_path / "research"
        for n in (1, 2):
            (rd / f"iter_{n}" / "phases").mkdir(parents=True, exist_ok=True)
        (rd / "iter_1" / "reflect.json").write_text(json.dumps({
            "decision": "idea_mutation",
            "reason": "baseline plateaued; pivot to attention",
            "best_result": {"phase_id": "baseline", "metric_value": 3.41},
            "delta_from_previous_iter": "new_track",
            "delta_trigger": "internal",
            "framing_change": {"from_frame": "a", "to_frame": "b", "axis": "mechanism"},
        }))
        (rd / "iter_1" / "phases" / ".hypothesis_log.json").write_text(json.dumps({
            "iteration": 1,
            "entries": [
                {
                    "phase_id": "baseline",
                    "ran_at": "2026-04-01T10:00:00",
                    "incoming_hypothesis": "H1",
                    "result_interpretation": "OK",
                    "outgoing_hypothesis": "H2",
                    "drift_axis": "none",
                },
                {
                    "phase_id": "attention",
                    "ran_at": "2026-04-01T14:30:00",
                    "incoming_hypothesis": "H2",
                    "result_interpretation": "Better",
                    "outgoing_hypothesis": "H3",
                    "drift_axis": "mechanism",
                },
            ],
        }))
        (rd / "iter_2" / "reflect.json").write_text(json.dumps({
            "decision": "add_phases",
            "reason": "ablation needed",
            "best_result": {"metric_value": 2.85},
            "delta_from_previous_iter": "deepened",
            "delta_trigger": "internal",
            "drift_warning": False,
            "pivot_trigger": {
                "trigger_source": "paper",
                "trigger_artifact": "https://arxiv.org/abs/X",
                "trigger_date": "2026-04-08",
            },
        }))

    def test_timeline_to_stdout_summarizes_all_iters(self, tmp_path, capsys):
        from tiny_lab.cli import main

        self._setup(tmp_path)
        cwd = os.getcwd()
        old_argv = sys.argv
        try:
            os.chdir(tmp_path)
            sys.argv = ["tiny-lab", "timeline", "--out", "-"]
            main()
        finally:
            os.chdir(cwd)
            sys.argv = old_argv

        out = capsys.readouterr().out
        # Header + 2 data rows
        assert "Research Timeline" in out
        assert "| iter | delta |" in out
        # iter 1 — framing flag, paper-trigger should NOT appear here
        assert "| 1 | new_track |" in out
        assert "✓" in out  # framing flag for iter 1
        # iter 2 — pivot_trigger.trigger_source overrides delta_trigger
        assert "| 2 | deepened |" in out
        assert "paper" in out
        # Cycle length computed from hypothesis_log timestamps
        assert "4.5h" in out

    def test_timeline_writes_file(self, tmp_path):
        from tiny_lab.cli import main

        self._setup(tmp_path)
        out_path = tmp_path / "research" / "timeline.md"

        cwd = os.getcwd()
        old_argv = sys.argv
        try:
            os.chdir(tmp_path)
            sys.argv = ["tiny-lab", "timeline"]  # default --out
            main()
        finally:
            os.chdir(cwd)
            sys.argv = old_argv

        assert out_path.exists()
        text = out_path.read_text()
        assert text.startswith("# Research Timeline")
