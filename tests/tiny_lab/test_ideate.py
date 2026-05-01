"""Tests for v7.4/v7.5 ideate preset and merger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiny_lab.workflow import load_workflow, validate_workflow, _parse_state, Workflow, AutonomySpec, InterventionSpec


PRESETS_DIR = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets"


class TestIdeatePresets:
    @pytest.mark.parametrize("preset", ["ideate", "ideate-deep"])
    def test_loads_and_validates(self, preset):
        wf = load_workflow(PRESETS_DIR / f"{preset}.json")
        assert len(wf.states) > 0
        assert wf.first_state() == "SHAPE_LITE"

    @pytest.mark.parametrize("preset", ["ideate", "ideate-deep"])
    def test_has_select_with_routing(self, preset):
        wf = load_workflow(PRESETS_DIR / f"{preset}.json")
        select = wf.get_state("SELECT")
        # SELECT must route to selected/redo/reshape
        assert isinstance(select.next, dict)
        assert set(select.next.keys()) >= {"selected", "redo", "reshape"}

    def test_ideate_deep_has_extra_states(self):
        wf = load_workflow(PRESETS_DIR / "ideate-deep.json")
        ids = set(wf.state_ids())
        assert "LITERATURE_SCAN" in ids
        assert "GAP_ANALYSIS" in ids

    @pytest.mark.parametrize("preset", ["ideate", "ideate-deep"])
    def test_visualize_candidates_between_evaluate_and_select(self, preset):
        """v7.6: VISUALIZE_CANDIDATES must sit between EVALUATE_MATRIX and SELECT."""
        wf = load_workflow(PRESETS_DIR / f"{preset}.json")
        em = wf.get_state("EVALUATE_MATRIX")
        viz = wf.get_state("VISUALIZE_CANDIDATES")
        assert em.next == "VISUALIZE_CANDIDATES"
        assert viz.next == "SELECT"
        # Manifest is the completion artifact
        assert "candidate_viz_manifest" in viz.completion.artifact


class TestDataVizPresets:
    @pytest.mark.parametrize("preset", ["ml-experiment", "novel-method", "data-analysis"])
    def test_visualize_data_between_deep_dive_and_idea_refine(self, preset):
        """v7.6: VISUALIZE_DATA must sit between DATA_DEEP_DIVE and IDEA_REFINE."""
        wf = load_workflow(PRESETS_DIR / f"{preset}.json")
        dd = wf.get_state("DATA_DEEP_DIVE")
        viz = wf.get_state("VISUALIZE_DATA")
        assert dd.next == "VISUALIZE_DATA"
        assert viz.next == "IDEA_REFINE"
        assert "data_viz_manifest" in viz.completion.artifact

    def test_review_paper_has_no_data_viz(self):
        """review-paper is text-only — should NOT include VISUALIZE_DATA."""
        wf = load_workflow(PRESETS_DIR / "review-paper.json")
        assert "VISUALIZE_DATA" not in wf.state_ids()


class TestMerger:
    @pytest.mark.parametrize("preset", ["ml-experiment", "review-paper", "novel-method", "data-analysis"])
    def test_merge_produces_valid_workflow(self, preset):
        from tiny_lab.cli import _merge_ideate_into_preset

        ideate = json.loads((PRESETS_DIR / "ideate.json").read_text())
        research = json.loads((PRESETS_DIR / f"{preset}.json").read_text())
        merged = _merge_ideate_into_preset(ideate, research)

        states = [_parse_state(s) for s in merged["states"]]
        wf = Workflow(states=states, autonomy=AutonomySpec(), intervention=InterventionSpec())
        validate_workflow(wf)

        # First state should be SHAPE_LITE (ideate prefix)
        assert wf.first_state() == "SHAPE_LITE"
        # Inline handoff state should exist and the original SHAPE_FULL should be gone
        ids = set(wf.state_ids())
        assert "IDEATE_INLINE_HANDOFF" in ids
        assert "SHAPE_FULL" not in ids

    def test_merge_redirects_dangling_shape_refs(self):
        """Any state in the research preset that pointed at SHAPE_FULL must be
        redirected (no dangling references after merge)."""
        from tiny_lab.cli import _merge_ideate_into_preset

        ideate = json.loads((PRESETS_DIR / "ideate.json").read_text())
        ml = json.loads((PRESETS_DIR / "ml-experiment.json").read_text())
        merged = _merge_ideate_into_preset(ideate, ml)

        # The validation in load_workflow walks all next targets — if any still
        # pointed at SHAPE_FULL it would raise. Run it directly:
        states = [_parse_state(s) for s in merged["states"]]
        wf = Workflow(states=states, autonomy=AutonomySpec(), intervention=InterventionSpec())
        validate_workflow(wf)  # raises on dangling refs


class TestRefsModule:
    def test_extract_references_from_diverge_shape(self):
        from tiny_lab.refs import extract_references

        sample = {
            "candidates": [
                {"id": "C1", "grounded_in": ["https://arxiv.org/abs/1706.03762"]},
            ],
            "literature_notes": [
                {"title": "Test", "url": "https://arxiv.org/abs/2005.14165"},
            ],
        }
        refs = extract_references(sample)
        # Both reference shapes should be discovered
        urls = {r.get("url") for r in refs}
        assert "https://arxiv.org/abs/1706.03762" in urls
        assert "https://arxiv.org/abs/2005.14165" in urls

    def test_arxiv_id_extraction(self):
        from tiny_lab.refs import _extract_arxiv_id

        assert _extract_arxiv_id({"url": "https://arxiv.org/abs/1706.03762"}) == "1706.03762"
        assert _extract_arxiv_id({"url": "https://arxiv.org/pdf/2005.14165v2"}) == "2005.14165"
        assert _extract_arxiv_id({"arxiv_id": "1810.04805"}) == "1810.04805"
        assert _extract_arxiv_id({"url": "https://example.com/paper.pdf"}) is None

    def test_doi_extraction(self):
        from tiny_lab.refs import _extract_doi

        assert _extract_doi({"doi": "10.1038/nature14539"}) == "10.1038/nature14539"
        assert _extract_doi({"url": "https://doi.org/10.1038/nature14539"}) == "10.1038/nature14539"
        assert _extract_doi({"url": "https://example.com/paper"}) is None
