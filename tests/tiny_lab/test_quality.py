"""Tests for reusable research quality helpers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tiny_lab.quality import (
    audit_evaluation_result_consistency,
    audit_final_paper,
    audit_phase_outputs,
    render_final_paper_contract,
    validate_reflection_strategy,
)

PNG_SIGNATURE = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_final_paper_contract_renders_quality_ssot():
    text = render_final_paper_contract()

    assert "Final Paper Contract" in text
    assert "tiny_lab.quality" in text
    assert "*.ref_verification.json" in text
    assert "reference-bearing `research/iter_*/*.json`" in text
    assert "research/final_paper.md" in text
    assert "research/iter_*/results/*.json" in text
    assert "valid non-empty result artifacts" in text
    assert "research/iter_*/results/*.png" in text
    assert "no `.` or `..` path segments" in text
    assert "valid non-empty image artifacts" in text
    assert "same sentence" in text
    assert "Sample-size claims" in text
    assert "`n=120`" in text
    assert "`n_samples`" in text
    assert "Repetition-count claims" in text
    assert "`3 random seeds`" in text
    assert "`n_trials`" in text
    assert "Split-ratio claims" in text
    assert "`80/20 holdout`" in text
    assert "`split_protocol`" in text
    assert "evidence family" in text
    assert "causal design" in text
    assert "robustness/stability" in text
    assert "generalization" in text
    assert "external/OOD generalization" in text
    assert "statistical uncertainty" in text
    assert "statistical significance" in text
    assert "support counts alone do not trigger this family" in text
    assert "fairness/bias audit" in text
    assert "efficiency/resource evidence" in text


def test_reflection_strategy_requires_portfolio_for_new_iteration():
    data = {
        "decision": "idea_mutation",
        "reason": "The current result exposes a residual failure mode.",
        "diagnosis": [{"gap": "slice RMSE", "evidence": "research/iter_1/results/phase_0.json"}],
        "new_idea": "Test slice-aware robust regression.",
        "idea_portfolio": [
            {
                "direction": "Test slice-aware robust regression.",
                "rationale": "Targets the observed slice failure.",
                "evidence": "research/iter_1/results/phase_0.json",
                "scores": {
                    "novelty": 4,
                    "feasibility": 4,
                    "expected_information_gain": 5,
                    "risk": 2,
                    "artifact_cost": 3,
                },
                "score": 18,
                "status": "promote_next",
            },
            {
                "direction": "Run broader seed stress tests.",
                "rationale": "Checks whether the failure is stable.",
                "evidence": "research/iter_1/results/phase_0.json",
                "scores": {
                    "novelty": 2,
                    "feasibility": 5,
                    "expected_information_gain": 3,
                    "risk": 1,
                    "artifact_cost": 2,
                },
                "score": 15,
                "status": "defer",
            },
            {
                "direction": "Pivot to held-out subgroup generalization.",
                "rationale": "Tests transfer beyond the current split.",
                "evidence": "research/iter_1/results/phase_0.json",
                "scores": {
                    "novelty": 4,
                    "feasibility": 3,
                    "expected_information_gain": 4,
                    "risk": 3,
                    "artifact_cost": 4,
                },
                "score": 14,
                "status": "defer",
            },
        ],
        "selected_direction": {
            "direction": "Test slice-aware robust regression.",
            "reason": "Best information-gain and feasibility tradeoff.",
            "evidence": "research/iter_1/results/phase_0.json",
            "selection_rule": "highest score",
            "score": 18,
        },
        "selection_rationale": "The selected direction has the best information-gain and feasibility tradeoff.",
        "future_iteration_seeds": [{
            "direction": "Test slice-aware robust regression.",
            "status": "promote_next",
            "reason": "Best candidate.",
        }],
    }

    assert validate_reflection_strategy(data, 1) == []


def test_reflection_strategy_rejects_unselected_mutation():
    data = {
        "decision": "idea_mutation",
        "reason": "Need a new direction.",
        "diagnosis": [{"gap": "unknown"}],
        "new_idea": "Try something else.",
        "future_iteration_seeds": [{"direction": "Try something else.", "status": "promote_next"}],
    }

    issues = validate_reflection_strategy(data, 1)

    assert "reflect non-terminal decision requires idea_portfolio with at least 3 candidate directions" in issues
    assert "reflect non-terminal decision requires selected_direction object" in issues


def test_final_paper_audit_accepts_experimental_structure(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_accepts_review_structure(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Review\n\n"
        "## Abstract\nA complete summary of the review.\n\n"
        "## Methodology\nThe literature search strategy and screening process.\n\n"
        "## Taxonomy / Analysis\nA synthesis of themes and findings across papers.\n\n"
        "## Discussion\nBroader implications and open gaps.\n\n"
        "## Limitations\nLimitations of the review process and source corpus. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_rejects_missing_structure(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text("Short paper")

    assert audit_final_paper(tmp_path) == ["final_paper.md is too short to be a complete paper"]


def test_final_paper_audit_requires_section_headings_not_just_keywords(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "This long paper mentions abstract, method, results, and limitations in prose, "
        "but it does not provide the actual Markdown section headings expected from a "
        "complete research paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md missing expected sections: ['abstract', 'method', 'results_or_analysis', 'limitations']"
    ]


def test_final_paper_audit_requires_result_artifact_citation_when_results_exist(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model improves the primary metric, but the paper omits artifact paths.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md must cite every research result artifact; missing: ['research/iter_1/results/phase_0.json']"
    ]


def test_final_paper_audit_accepts_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json).\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_non_numeric_iteration_result_artifacts(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    noise_dir = tmp_path / "research" / "iter_x" / "results"
    rdir.mkdir(parents=True)
    noise_dir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (noise_dir / "noise.json").write_text(json.dumps({"mae_mean": 999}))
    (noise_dir / "noise.png").write_bytes(b"not a real figure")
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json).\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_every_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "phase_1.json").write_text(json.dumps({"mae_mean": 0.39}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe baseline reports MAE = 0.42 (research/iter_1/results/phase_0.json).\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md must cite every research result artifact; missing: ['research/iter_1/results/phase_1.json']"
    ]


def test_final_paper_audit_accepts_every_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "phase_1.json").write_text(json.dumps({"mae_mean": 0.39}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\n"
        "The baseline reports MAE = 0.42 (research/iter_1/results/phase_0.json). "
        "The refined model reports MAE = 0.39 (research/iter_1/results/phase_1.json).\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_rejects_out_of_scope_result_artifact_citation(tmp_path: Path):
    rdir1 = tmp_path / "research" / "iter_1" / "results"
    rdir2 = tmp_path / "research" / "iter_2" / "results"
    rdir1.mkdir(parents=True)
    rdir2.mkdir(parents=True)
    (rdir1 / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir2 / "phase_0.json").write_text(json.dumps({"mae_mean": 0.39}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\n"
        "The current run reports MAE = 0.39 (research/iter_2/results/phase_0.json), "
        "but it also cites stale evidence (research/iter_1/results/phase_0.json).\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path, iteration=2) == [
        "final_paper.md cites out-of-scope research result artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_final_paper_audit_requires_every_figure_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json).\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md must cite every research figure artifact; missing: ['research/iter_1/results/phase_0_error.png']"
    ]


def test_final_paper_audit_accepts_every_figure_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json), "
        "with the error distribution shown in research/iter_1/results/phase_0_error.png.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_rejects_nonexistent_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json), "
        "and a missing analysis is also cited in research/iter_1/results/missing.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites missing research result artifacts: ['research/iter_1/results/missing.json']"
    ]


def test_final_paper_audit_rejects_invalid_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text("{bad json")
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports results in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites invalid research result artifacts: ['research/iter_1/results/phase_0.json']"
    ]


def test_final_paper_audit_rejects_non_substantive_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports results in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites non-substantive research result artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_final_paper_audit_rejects_result_artifact_with_invalid_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 1.2,
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports results in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "final_paper.md cites invalid research result artifacts" in issues[0]
    assert "research/iter_1/results/phase_0.json" in issues[0]
    assert "p_value p-value must be between 0 and 1" in issues[0]


def test_final_paper_audit_rejects_result_artifact_with_invalid_alpha_threshold(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "alpha": 1.2,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports results in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "final_paper.md cites invalid research result artifacts" in issues[0]
    assert "research/iter_1/results/phase_0.json" in issues[0]
    assert "alpha significance threshold must be > 0 and < 1" in issues[0]


def test_final_paper_audit_rejects_result_artifact_with_malformed_interval(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_ci95": [0.2],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports results in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "final_paper.md cites invalid research result artifacts" in issues[0]
    assert "research/iter_1/results/phase_0.json" in issues[0]
    assert "mae_ci95 interval must provide exactly two numeric bounds" in issues[0]


def test_final_paper_audit_rejects_unsafe_result_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({"verdict": "ACCEPT"}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json), "
        "and the paper cites an unsafe result path "
        "research/iter_1/results/../../evaluation.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites unsafe research result artifact paths: "
        "['research/iter_1/results/../../evaluation.json']"
    ]


def test_final_paper_audit_rejects_nonexistent_figure_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json), "
        "with diagnostics in research/iter_1/results/missing.png.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites missing research figure artifacts: ['research/iter_1/results/missing.png']"
    ]


def test_final_paper_audit_rejects_unsafe_figure_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json), "
        "with the error distribution shown in research/iter_1/results/phase_0_error.png. "
        "An unsafe figure path also appears as research/iter_1/results/../phase_0_error.png.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites unsafe research figure artifact paths: "
        "['research/iter_1/results/../phase_0_error.png']"
    ]


def test_final_paper_audit_rejects_invalid_figure_artifact_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "phase_0_error.png").write_bytes(b"not a png")
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe model reports MAE = 0.42 (research/iter_1/results/phase_0.json), "
        "with diagnostics in research/iter_1/results/phase_0_error.png.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md cites invalid research figure artifacts: ['research/iter_1/results/phase_0_error.png']"
    ]


def test_final_paper_audit_requires_discussion_of_result_evidence_families(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance": 0.72}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "ablation or feature-importance" in issues[0]


def test_final_paper_audit_accepts_discussion_of_result_evidence_families(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance": 0.72}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe feature importance analysis is reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_ablation_metadata_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance_method": [{"feature": "lag_1", "importance": 0.72}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_sota_comparison_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "prior_work_results": [{"name": "Smith et al. 2024", "accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "SOTA or prior-work comparison" in issues[0]


def test_final_paper_audit_accepts_sota_comparison_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "prior_work_results": [{"name": "Smith et al. 2024", "accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe prior work comparison is reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_statistical_uncertainty_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "statistical uncertainty" in issues[0]


def test_final_paper_audit_does_not_treat_support_count_as_uncertainty_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_statistical_significance_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 0.03,
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "statistical significance" in issues[0]


def test_final_paper_audit_accepts_statistical_significance_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 0.03,
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe p-value is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_significance_discussion_for_comparison_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12],
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe baseline comparison and confidence interval are reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "statistical significance" in issues[0]


def test_final_paper_audit_accepts_significance_discussion_for_comparison_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12],
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe baseline comparison confidence interval excludes zero, "
        "supporting statistical significance in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_accepts_zero_exclusion_discussion_for_comparison_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12],
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe baseline comparison confidence interval excludes zero in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_accepts_statistical_uncertainty_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "n_samples": 100,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe uncertainty is summarized by the standard deviation in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_rejects_uncertainty_result_without_sample_support(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe uncertainty is summarized by the standard deviation in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "uncertainty evidence requires sample/repetition support" in issues[0]


def test_final_paper_audit_ignores_negated_statistical_uncertainty_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_mae_std": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_negated_reproducibility_code_path_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "no_script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": "sha256:" + "1" * 64,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_evidence_discussion_to_cite_source_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance": 0.72}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes feature importance as a planned analysis.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "ablation or feature-importance" in issues[0]


def test_final_paper_audit_requires_causal_evidence_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "causal_identification": "matched control with propensity score adjustment",
        "causal_effect": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "causal design" in issues[0]


def test_final_paper_audit_accepts_causal_evidence_discussion_with_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "causal_identification": "matched control with propensity score adjustment",
        "causal_effect": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe causal identification evidence is reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_robustness_and_generalization_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "robustness_checks": [
            {"run_label": "stress_a", "mae_mean": 0.42},
            {"run_label": "stress_b", "mae_mean": 0.43},
        ],
        "external_validation_results": [{"source_label": "external_holdout", "mae_mean": 0.46}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "robustness or stability" in issues[0]
    assert "generalization" in issues[0]


def test_final_paper_audit_accepts_robustness_and_generalization_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "robustness_checks": [
            {"run_label": "stress_a", "mae_mean": 0.42},
            {"run_label": "stress_b", "mae_mean": 0.43},
        ],
        "external_validation_results": [{"source_label": "external_holdout", "mae_mean": 0.46}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe robustness checks are reported in research/iter_1/results/phase_0.json. "
        "The external validation generalization evidence is reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_accepts_independent_cohort_generalization_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "independent_cohort_results": [{"cohort": "site_b", "mae_mean": 0.46}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe independent cohort generalization evidence is reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_external_generalization_discussion(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"source_label": "external_site", "mae_mean": 0.46}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe held-out generalization result is reported in "
        "research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "external/OOD generalization" in issues[0]


def test_final_paper_audit_ignores_seed_only_robustness_marker(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "repeated_seed_results": [
            {"seed": 1},
            {"seed": 2},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_unlabeled_numeric_robustness_marker(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "robustness_checks": [{"mae_mean": 0.43}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_unlabeled_numeric_external_generalization_marker(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "external_validation_results": [{"mae_mean": 0.46}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_causal_effect_without_design_marker(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "causal_effect": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the artifact-backed study.\n\n"
        "## Method\nThe method describes the experimental setup.\n\n"
        "## Results\nThe model result is reported in research/iter_1/results/phase_0.json.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_requires_related_work_when_reference_artifacts_exist(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Known Paper", "doi": "10.1234/example"}]
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md must include a related work or references section when reference artifacts exist"
    ]


def test_final_paper_audit_requires_related_work_heading_not_just_prose(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Known Paper", "doi": "10.1234/example"}]
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nPrior work establishes the baseline context for this complete study.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md must include a related work or references section when reference artifacts exist"
    ]


def test_final_paper_audit_requires_reference_artifact_citations(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Known Paper", "doi": "10.1234/example"}]
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Related Work\nPrior work establishes the baseline context.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md must cite every reference artifact; missing: ['research/iter_1/.domain_research.json']"
    ]


def test_final_paper_audit_scopes_reference_citations_to_requested_iteration(tmp_path: Path):
    iter1 = tmp_path / "research" / "iter_1"
    iter2 = tmp_path / "research" / "iter_2"
    iter1.mkdir(parents=True)
    iter2.mkdir(parents=True)
    (iter1 / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Known Paper", "doi": "10.1234/example"}]
    }))
    (iter2 / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Later Paper", "doi": "10.1234/later"}]
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Related Work\nPrior work establishes the baseline context "
        "(research/iter_1/.domain_research.json).\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path, iteration=1) == []
    assert audit_final_paper(tmp_path) == [
        "final_paper.md must cite every reference artifact; missing: ['research/iter_2/.domain_research.json']"
    ]


def test_final_paper_audit_accepts_related_work_when_reference_artifacts_are_cited(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Known Paper", "doi": "10.1234/example"}]
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nA complete summary of the study.\n\n"
        "## Related Work\nPrior work establishes the baseline context "
        "(research/iter_1/.domain_research.json).\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_ignores_negated_novelty_sota_disclaimer(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nNo broader SOTA or novelty claims are made.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nThe measured outcomes are scoped to the local experiment only.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "The method is not a novel contribution, and the paper does not claim SOTA performance. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_final_paper_audit_rejects_novelty_claim_after_negated_disclaimer(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nNo broader SOTA claims are made, but this paper introduces a novel method.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md novelty or SOTA claims require reference artifacts"
    ]


def test_final_paper_audit_rejects_novelty_claim_without_reference_artifacts(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThis paper introduces a novel method for the target task.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md novelty or SOTA claims require reference artifacts"
    ]


def test_final_paper_audit_rejects_prior_work_superiority_without_reference_artifacts(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThe proposed model beats prior work on the target task.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md novelty or SOTA claims require reference artifacts"
    ]


def test_final_paper_audit_rejects_past_tense_prior_work_superiority_without_reference_artifacts(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThe proposed model outperformed previous work on the target task.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md novelty or SOTA claims require reference artifacts"
    ]


def test_final_paper_audit_rejects_published_method_superiority_without_reference_artifacts(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThe proposed model is better than published methods on the target task.\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == [
        "final_paper.md novelty or SOTA claims require reference artifacts"
    ]


def test_final_paper_audit_rejects_novelty_claim_without_reference_verification_sidecar(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Known Paper", "doi": "10.1234/example"}]
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThis paper introduces a novel method for the target task.\n\n"
        "## Related Work\nPrior work establishes the baseline context "
        "(research/iter_1/.domain_research.json).\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "novelty or SOTA claims require reference artifacts with passing verification sidecars" in issues[0]
    assert "missing ref verification sidecar" in issues[0]


def test_final_paper_audit_rejects_novelty_claim_with_unverified_references(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    raw_ref = {"title": "Known Paper", "doi": "10.1234/example"}
    (idir / ".domain_research.json").write_text(json.dumps({"references": [raw_ref]}))
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": {"total": 1, "verified": 0, "unverified": 1, "not_found": 0, "error": 0},
        "refs": [{"raw": raw_ref, "status": "unverified"}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThis paper introduces a novel method for the target task.\n\n"
        "## Related Work\nPrior work establishes the baseline context "
        "(research/iter_1/.domain_research.json).\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "with passing verification sidecars" in issues[0]
    assert "has 1 unverified references" in issues[0]


def test_final_paper_audit_rejects_novelty_claim_with_url_only_verified_reference(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    raw_ref = {"title": "Known Paper", "url": "https://example.com/known-paper"}
    (idir / ".domain_research.json").write_text(json.dumps({"references": [raw_ref]}))
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [{
            "raw": raw_ref,
            "title": "Known Paper",
            "url": "https://example.com/known-paper",
            "method": "url_head",
            "status": "verified",
        }],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThis paper introduces a novel method for the target task.\n\n"
        "## Related Work\nPrior work establishes the baseline context "
        "(research/iter_1/.domain_research.json).\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    issues = audit_final_paper(tmp_path)

    assert len(issues) == 1
    assert "with passing verification sidecars" in issues[0]
    assert "identity verification required" in issues[0]


def test_final_paper_audit_accepts_novelty_claim_with_verified_reference_sidecars(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    raw_ref = {"title": "Known Paper", "doi": "10.1234/example"}
    (idir / ".domain_research.json").write_text(json.dumps({"references": [raw_ref]}))
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [{
            "raw": raw_ref,
            "title": "Known Paper",
            "doi": "10.1234/example",
            "method": "crossref",
            "canonical_title": "Known Paper",
            "status": "verified",
        }],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Paper\n\n"
        "## Abstract\nThis paper introduces a novel method for the target task.\n\n"
        "## Related Work\nPrior work establishes the baseline context "
        "(research/iter_1/.domain_research.json).\n\n"
        "## Method\nA detailed account of the experimental setup.\n\n"
        "## Results\nA detailed account of measured outcomes.\n\n"
        "## Limitations\nA detailed account of threats to validity. "
        "Additional text makes this a complete-looking paper. " * 20
    )

    assert audit_final_paper(tmp_path) == []


def test_phase_audit_rejects_pending_phase(tmp_path: Path):
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "pending",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
            "visualization": ["phase_0_plot.png"],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert issues == ["phase_0 status is 'pending', expected 'done'"]


def test_phase_audit_accepts_done_phase_with_outputs(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    (rdir / "phase_0_plot.png").write_bytes(PNG_SIGNATURE)
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
            "visualization": ["phase_0_plot.png"],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_report_fields_not_declared_by_closed_schema(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "score": 0.9,
        "unsupported_claim_metric": 0.99,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "score": {"type": "number"},
                        },
                    },
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 report has undeclared fields: ['unsupported_claim_metric']" in issues


def test_phase_audit_reports_required_fields_not_declared_in_properties_as_missing(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "required": ["score", "ghost_score"],
                        "properties": {
                            "score": {"type": "number"},
                        },
                    },
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 report missing fields: ['ghost_score']" in issues
    assert "phase_0 report.ghost_score is required" in issues


def test_phase_audit_uses_shared_schema_expected_fields_for_malformed_required(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "required": "score",
                        "properties": {
                            "score": {"type": "number"},
                        },
                    },
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 report.required must be a list of strings" in issues
    assert not any("report missing fields" in issue for issue in issues)


def test_phase_audit_rejects_mismatched_result_phase_id(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "phase_id": "phase_1",
        "score": 0.9,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "phase_id": {"type": "string"},
                        "score": {"type": "number"},
                    },
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 phase_id metadata must match planned phase id `phase_0`" in issues


def test_phase_audit_rejects_report_without_schema(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {"path": "research/iter_1/results/phase_0.json"}
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 expected_outputs.report.schema is required" in issues


def test_phase_audit_rejects_report_without_path(tmp_path: Path):
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {"schema": {"score": {"type": "number"}}}
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 expected_outputs.report.path is required" in issues


def test_phase_audit_rejects_unsafe_report_path(tmp_path: Path):
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "../escape.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 unsafe report path: expected_outputs.report.path must not contain '..'" in issues


def test_phase_audit_rejects_report_path_with_current_dir_segment(tmp_path: Path):
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/./phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 unsafe report path: expected_outputs.report.path must not contain '.'" in issues


def test_phase_audit_rejects_report_path_from_other_iteration(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_2" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_2/results/phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 unsafe report path: expected_outputs.report.path must be under research/iter_1/results/" in issues


def test_phase_audit_rejects_non_object_report_json(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps([{"score": 0.9}]))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {"path": "research/iter_1/results/phase_0.json"}
            },
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 report is not a JSON object (got list)" in issues


def test_phase_audit_rejects_empty_visualization_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    (rdir / "phase_0_plot.png").write_bytes(b"")
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
            "visualization": ["phase_0_plot.png"],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 empty visualizations: ['phase_0_plot.png']" in issues


def test_phase_audit_rejects_invalid_png_visualization_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    (rdir / "phase_0_plot.png").write_bytes(b"not a png")
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
            "visualization": ["phase_0_plot.png"],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 invalid PNG visualizations: ['phase_0_plot.png']" in issues


def test_phase_audit_rejects_png_signature_only_visualization_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
    (rdir / "phase_0_plot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"score": {"type": "number"}},
                }
            },
            "visualization": ["phase_0_plot.png"],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 invalid PNG visualizations: ['phase_0_plot.png']" in issues


def test_phase_audit_rejects_missing_baseline_comparison_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include baseline comparison evidence" in issues


def test_phase_audit_accepts_baseline_comparison_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "mae_mean": 0.58},
            {"name": "linear regression", "mae_mean": 0.49},
        ],
        "improvement_over_baseline": 0.1429,
    }))
    plan = {
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_negated_baseline_comparison_results_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_baseline_results": [
            {"name": "linear regression", "mae_mean": 0.49},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "no_baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include baseline comparison evidence" in issues


def test_phase_audit_accepts_non_ml_baseline_comparison_results_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_ml_baseline_results": [
            {"name": "seasonal naive", "mae_mean": 0.58},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "non_ml_baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_baseline_comparison_metric_alias(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy_mean": 0.91,
        "baseline_results": [
            {"name": "linear regression", "accuracy": 0.80},
        ],
    }))
    plan = {
        "metric": {"name": "acc", "direction": "maximize"},
        "baselines": [
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_support_only_baseline_metric_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "mae_std": 0.04},
            {"name": "linear regression", "mae_std": 0.03},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "experimental results missing numeric baseline metric values for planned baselines: "
        "['seasonal naive', 'linear regression']"
    ) in issues


def test_phase_audit_rejects_metadata_only_baseline_metric_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "mae_method": 0.58},
            {"name": "linear regression", "mae_method": 0.49},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "experimental results missing numeric baseline metric values for planned baselines: "
        "['seasonal naive', 'linear regression']"
    ) in issues


def test_phase_audit_rejects_negated_baseline_collection_metric_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "no_mae_mean": 0.58},
            {"name": "linear regression", "without_mae_mean": 0.49},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "experimental results missing numeric baseline metric values for planned baselines: "
        "['seasonal naive', 'linear regression']"
    ) in issues


def test_phase_audit_rejects_named_baselines_without_metric_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive"},
            {"name": "linear regression", "notes": "configured as a comparison"},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "experimental results missing numeric baseline metric values for planned baselines: "
        "['seasonal naive', 'linear regression']"
    ) in issues


def test_phase_audit_rejects_planned_sota_without_prior_work_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include SOTA or prior-work comparison evidence" in issues


def test_phase_audit_rejects_published_model_comparison_without_prior_work_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat the best published model MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include SOTA or prior-work comparison evidence" in issues


def test_phase_audit_rejects_negated_prior_work_results_key_when_sota_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_prior_work_results": [{"name": "Smith et al. 2024", "mae_mean": 0.50}],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "success_criteria": "Beat prior work MAE by at least 5%.",
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Compare against prior work results.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "no_prior_work_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include SOTA or prior-work comparison evidence" in issues


def test_phase_audit_rejects_prior_work_results_without_named_metric_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "prior_work_results": [{"name": "Smith et al. 2024", "metric_value": 0.50}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include numeric SOTA or prior-work metric values matching the plan metric" in issues


def test_phase_audit_rejects_prior_work_results_with_support_stat_only_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "prior_work_results": [{"name": "Smith et al. 2024", "mae_std": 0.03}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include numeric SOTA or prior-work metric values matching the plan metric" in issues


def test_phase_audit_rejects_prior_work_results_with_metadata_only_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "prior_work_results": [{"name": "Smith et al. 2024", "mae_method": 0.50}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include numeric SOTA or prior-work metric values matching the plan metric" in issues


def test_phase_audit_rejects_prior_work_results_with_negated_metric_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "prior_work_results": [{"name": "Smith et al. 2024", "no_mae_mean": 0.50}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include numeric SOTA or prior-work metric values matching the plan metric" in issues


def test_phase_audit_rejects_prior_work_results_with_placeholder_name(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "prior_work_results": [{"name": "unknown", "mae_mean": 0.50}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include SOTA or prior-work comparison evidence" in issues


def test_phase_audit_accepts_prior_work_results_with_named_metric_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "prior_work_results": [{"name": "Smith et al. 2024", "mae_mean": 0.50}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Beat prior work MAE by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_prior_work_metric_alias(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy_mean": 0.92,
        "prior_work_results": [{"name": "Smith et al. 2024", "accuracy": 0.88}],
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "acc", "direction": "maximize"},
        "goal": {"success_criteria": "Beat prior work accuracy by at least 5%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy_mean": {"type": "number"},
                        "prior_work_results": {"type": "array"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_dict_keyed_baseline_metric_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": {
            "seasonal naive": {"mae_mean": 0.58},
            "linear regression": {"mae_mean": 0.49},
        },
        "improvement_over_baseline": 0.07,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "object"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_nested_baseline_metric_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "metrics": {"mae_mean": 0.58}},
            {"name": "linear regression", "metrics": {"mae_mean": 0.49}},
        ],
        "improvement_over_baseline": 0.07,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_nested_non_finite_numbers(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "mae_mean": float("inf")},
            {"name": "linear regression", "mae_mean": 0.49},
        ],
        "error_slices": [{"slice": "high_load", "mae_mean": float("nan")}],
    }))
    plan = {
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "error_slices": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 non-finite numeric value at baseline_results[0].mae_mean" in issues
    assert "phase_0 non-finite numeric value at error_slices[0].mae_mean" in issues


def test_phase_audit_rejects_missing_ablation_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include ablation, feature importance, or sensitivity evidence" in issues


def test_phase_audit_accepts_ablation_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "feature_importance": [{"feature": "lag_1", "importance": 0.81}],
    }))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "feature_importance": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_boolean_ablation_marker_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "feature_importance": True,
    }))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "feature_importance": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include ablation, feature importance, or sensitivity evidence" in issues


def test_phase_audit_rejects_string_ablation_marker_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "feature_importance": "computed separately",
    }))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "feature_importance": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include ablation, feature importance, or sensitivity evidence" in issues


def test_phase_audit_rejects_unlabeled_numeric_ablation_values_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "feature_importance": [0.81, 0.12],
    }))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "feature_importance": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include ablation, feature importance, or sensitivity evidence" in issues


def test_phase_audit_rejects_ablation_metadata_key_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "feature_importance_method": [{"feature": "lag_1", "importance": 0.81}],
    }))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "feature_importance_method": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include ablation, feature importance, or sensitivity evidence" in issues


def test_phase_audit_rejects_ablation_metadata_only_score_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "feature_importance": [{"feature": "lag_1", "importance_method": 0.81}],
    }))
    plan = {
        "experiment_checklist": {"has_ablation_study": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "feature_importance": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include ablation, feature importance, or sensitivity evidence" in issues


def test_phase_audit_rejects_missing_cross_validation_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include cross-validation or multiple-split evidence" in issues


def test_phase_audit_accepts_cross_validation_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 2,
        "per_fold_metrics": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold": 1, "mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_negated_cross_validation_keys_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_fold_count": 2,
        "non_cross_validation_results": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold": 1, "mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "no_fold_count": {"type": "integer"},
                        "non_cross_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include cross-validation or multiple-split evidence" in issues


def test_phase_audit_rejects_missing_causal_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "experiment_checklist": {"has_causal_design": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Estimate the causal effect with a matched control design.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include causal design or identification evidence" in issues


def test_phase_audit_accepts_causal_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "causal_identification": "matched control with propensity score adjustment",
        "causal_effect": 0.12,
    }))
    plan = {
        "experiment_checklist": {"has_causal_design": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Estimate the causal effect with a matched control design.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "causal_identification": {"type": "string"},
                        "causal_effect": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_negated_causal_design_key_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_causal_design": "matched control with propensity score adjustment",
        "causal_effect": 0.12,
    }))
    plan = {
        "experiment_checklist": {"has_causal_design": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Estimate the causal effect with a matched control design.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "non_causal_design": {"type": "string"},
                        "causal_effect": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include causal design or identification evidence" in issues


def test_phase_audit_rejects_causal_effect_without_identification_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "causal_effect": 0.12,
    }))
    plan = {
        "experiment_checklist": {"has_causal_design": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Estimate the causal effect with a matched control design.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "causal_effect": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include causal design or identification evidence" in issues


def test_phase_audit_rejects_boolean_causal_design_marker_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "causal_design": True,
        "causal_effect": 0.12,
    }))
    plan = {
        "experiment_checklist": {"has_causal_design": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Estimate the causal effect with a matched control design.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "causal_design": {"type": "boolean"},
                        "causal_effect": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include causal design or identification evidence" in issues


def test_phase_audit_rejects_missing_robustness_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include robustness or stability evidence" in issues


def test_phase_audit_accepts_robustness_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [
            {"seed": 1, "mae_mean": 0.43},
            {"seed": 2, "mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "repeated_seed_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_negated_robustness_key_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_robustness_results": [{"seed": 1, "mae_mean": 0.43}],
    }))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "non_robustness_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include robustness or stability evidence" in issues


def test_phase_audit_rejects_marker_only_robustness_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "robustness_checks": [{"name": "seed sensitivity planned"}],
    }))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "robustness_checks": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include robustness or stability evidence" in issues


def test_phase_audit_rejects_unlabeled_numeric_robustness_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "robustness_checks": [{"mae_mean": 0.43}],
    }))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "robustness_checks": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include robustness or stability evidence" in issues


def test_phase_audit_rejects_seed_only_robustness_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [
            {"seed": 1},
            {"seed": 2},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "repeated_seed_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include robustness or stability evidence" in issues


def test_phase_audit_rejects_count_only_robustness_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "robustness_checks": [
            {"name": "stress_a", "n_samples": 100},
            {"name": "stress_b", "n_samples": 100},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_robustness_checks": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Report robustness across random seeds.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "robustness_checks": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include robustness or stability evidence" in issues


def test_phase_audit_rejects_missing_generalization_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_holdout_only_when_external_validation_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "split_protocol": "80/20 holdout",
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "split_id": {"type": "string"},
                        "split_protocol": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_accepts_generalization_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"source_label": "external_holdout", "mae_mean": 0.46}],
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "external_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_independent_cohort_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "independent_cohort_results": [{"cohort": "site_b", "mae_mean": 0.46}],
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on an independent cohort.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "independent_cohort_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_negated_external_generalization_key_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_external_validation_results": [{"source_label": "external_holdout", "mae_mean": 0.46}],
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "non_external_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_marker_only_generalization_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"source_label": "external_holdout"}],
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "external_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_unlabeled_numeric_external_generalization_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"mae_mean": 0.46}],
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "external_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_placeholder_external_generalization_label_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"source_label": "unknown", "mae_mean": 0.46}],
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "external_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_support_only_external_generalization_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{
            "source_label": "external_site",
            "sample_size": 120,
            "p_value": 0.03,
        }],
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "external_validation_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_scalar_external_generalization_without_source_label(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": 0.46,
    }))
    plan = {
        "experiment_checklist": {"has_external_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Test generalization on external validation data.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "external_validation_results": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include external, cross-dataset, or OOD generalization evidence" in issues


def test_phase_audit_rejects_declared_fold_count_mismatch(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 5,
        "per_fold_metrics": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold": 1, "mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "fold_count=5 must match materialized per-fold/split metric result count(s) [2]" in issue
        for issue in issues
    )


def test_phase_audit_accepts_repeated_kfold_split_ids_with_repeated_fold_ids(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_count": 4,
        "fold_count": 4,
        "n_splits": 2,
        "n_repeats": 2,
        "split_audit": [
            {"split_id": "repeat_00_fold_00", "repeat_id": 0, "fold_id": 0, "n_train": 8, "n_test": 2},
            {"split_id": "repeat_00_fold_01", "repeat_id": 0, "fold_id": 1, "n_train": 8, "n_test": 2},
            {"split_id": "repeat_01_fold_00", "repeat_id": 1, "fold_id": 0, "n_train": 8, "n_test": 2},
            {"split_id": "repeat_01_fold_01", "repeat_id": 1, "fold_id": 1, "n_train": 8, "n_test": 2},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "split_count": {"type": "integer"},
                        "fold_count": {"type": "integer"},
                        "n_splits": {"type": "integer"},
                        "n_repeats": {"type": "integer"},
                        "split_audit": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("must match materialized per-fold/split metric result count" in issue for issue in issues)


def test_phase_audit_rejects_duplicate_fold_ids_as_repeated_split_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 2,
        "per_fold_metrics": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold": 0, "mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "per-fold/split metric results" in issues[-1]


def test_phase_audit_rejects_duplicate_fold_alias_ids_as_repeated_split_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 2,
        "per_fold_metrics": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold_id": "fold_0", "mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "per-fold/split metric results" in issues[-1]


def test_phase_audit_rejects_single_fold_when_cross_validation_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 1,
        "per_fold_metrics": [{"fold": 0, "mae_mean": 0.42}],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "at least 2 folds/splits" in issues[-1]


def test_phase_audit_rejects_fold_count_without_per_fold_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 5,
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "per-fold/split metric results" in issues[-1]


def test_phase_audit_rejects_fold_id_only_per_fold_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 2,
        "per_fold_metrics": [
            {"fold": 0},
            {"fold": 1},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "per-fold/split metric results" in issues[-1]


def test_phase_audit_rejects_unidentified_per_fold_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 2,
        "per_fold_metrics": [
            {"mae_mean": 0.43},
            {"mae_mean": 0.41},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "per_fold_metrics": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "per-fold/split metric results" in issues[-1]


def test_phase_audit_rejects_cv_summary_dict_as_repeated_split_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "cv_results": {
            "mean_mae": 0.42,
            "std_mae": 0.03,
        },
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "cv_results": {"type": "object"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "at least 2 folds/splits" in issues[-1]


def test_phase_audit_accepts_dict_keyed_cross_validation_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "cv_results": {
            "fold_0": {"mae_mean": 0.43},
            "fold_1": {"mae_mean": 0.41},
        },
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "cv_results": {"type": "object"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_duplicate_dict_keyed_fold_alias_ids(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 2,
        "cv_results": {
            "fold_0": {"mae_mean": 0.43},
            "fold_00": {"mae_mean": 0.41},
        },
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "fold_count": {"type": "integer"},
                        "cv_results": {"type": "object"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("per-fold/split metric result" in issue for issue in issues)


def test_phase_audit_rejects_cross_validation_label_without_repetition_count(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "validation_scheme": "cross-validation",
    }))
    plan = {
        "experiment_checklist": {"has_cross_validation": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "validation_scheme": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "at least 2 folds/splits" in issues[-1]


def test_phase_audit_rejects_missing_error_analysis_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include error analysis evidence" in issues


def test_phase_audit_accepts_error_analysis_evidence_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "error_slices": [{"slice": "high_load", "mae_mean": 0.61}],
    }))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "error_slices": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_boolean_error_analysis_marker_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "error_analysis": True,
    }))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "error_analysis": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include error analysis evidence" in issues


def test_phase_audit_rejects_string_error_analysis_marker_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "error_analysis": "reviewed manually",
    }))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "error_analysis": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include error analysis evidence" in issues


def test_phase_audit_rejects_unlabeled_numeric_error_values_when_claimed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "error_analysis": [0.61, 0.72],
    }))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "error_analysis": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include error analysis evidence" in issues


def test_phase_audit_accepts_confusion_matrix_as_error_analysis(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "confusion_matrix": [[18, 2], [3, 17]],
    }))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "confusion_matrix": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_scalar_calibration_metric_as_error_analysis(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "expected_calibration_error": 0.02,
    }))
    plan = {
        "experiment_checklist": {"has_error_analysis": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "expected_calibration_error": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_requires_fairness_evidence_when_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"accuracy": 0.91}))
    plan = {
        "experiment_checklist": {"has_fairness_audit": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Audit demographic parity across protected groups.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"accuracy": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include fairness or bias-audit evidence" in issues


def test_phase_audit_accepts_group_fairness_metrics_when_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "fairness_by_group": [
            {"protected_group": "A", "false_positive_rate": 0.08},
            {"protected_group": "B", "false_positive_rate": 0.11},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_fairness_audit": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Audit demographic parity across protected groups.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "fairness_by_group": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_unlabeled_group_fairness_metrics_when_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "fairness_by_group": [
            {"false_positive_rate": 0.08},
            {"false_positive_rate": 0.11},
        ],
    }))
    plan = {
        "experiment_checklist": {"has_fairness_audit": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Audit demographic parity across protected groups.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "fairness_by_group": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include fairness or bias-audit evidence" in issues


def test_phase_audit_requires_efficiency_evidence_when_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"accuracy": 0.91}))
    plan = {
        "experiment_checklist": {"has_efficiency_profile": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Profile inference latency and memory usage.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"accuracy": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include efficiency or resource evidence" in issues


def test_phase_audit_accepts_efficiency_metrics_when_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "latency_ms": 12.4,
        "peak_memory_mb": 512,
        "benchmark_device": "M2 Pro",
        "batch_size": 32,
    }))
    plan = {
        "experiment_checklist": {"has_efficiency_profile": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Profile inference latency and memory usage.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "latency_ms": {"type": "number"},
                        "peak_memory_mb": {"type": "number"},
                        "benchmark_device": {"type": "string"},
                        "batch_size": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_requires_efficiency_benchmark_context_when_planned(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "latency_ms": 12.4,
    }))
    plan = {
        "experiment_checklist": {"has_efficiency_profile": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Profile inference latency and memory usage.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "latency_ms": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results must include efficiency benchmark context" in issues


def test_phase_audit_rejects_non_positive_efficiency_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy": 0.91,
        "latency_ms": 0,
        "parameter_count": -1,
        "benchmark_device": "M2 Pro",
    }))
    plan = {
        "experiment_checklist": {"has_efficiency_profile": "yes"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "methodology": "Profile inference latency and memory usage.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy": {"type": "number"},
                        "latency_ms": {"type": "number"},
                        "parameter_count": {"type": "integer"},
                        "benchmark_device": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 latency_ms efficiency/resource value must be > 0" in issues
    assert "phase_0 parameter_count efficiency/resource value must be > 0" in issues


def test_phase_audit_rejects_beats_baseline_contradiction_for_minimize_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "beats_baseline": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "beats_baseline": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("beats_baseline=true contradicts mae=0.62 vs best baseline 0.58" in issue for issue in issues)


def test_phase_audit_rejects_beats_baseline_contradiction_with_non_ml_collection_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "non_ml_baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "beats_baseline": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "non_ml_baseline_results": {"type": "array"},
                        "beats_baseline": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("beats_baseline=true contradicts mae=0.62 vs best baseline 0.58" in issue for issue in issues)


def test_phase_audit_ignores_candidate_rows_inside_baseline_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "WAPE": 0.50,
        "baseline_results": [
            {"baseline": "emro_forecast", "baseline_type": "company_baseline", "WAPE": 0.55},
            {"baseline": "regular_model", "baseline_type": "regular_feature_candidate", "WAPE": 0.50},
        ],
        "baseline_metrics": [
            {"baseline": "emro_forecast", "WAPE": 0.55},
            {"baseline": "regular_model", "WAPE": 0.50},
        ],
        "method_results": [
            {
                "method": "regular_model",
                "WAPE": 0.50,
                "delta_vs_baseline": 0.05,
                "relative_improvement": 0.090909,
                "beats_baseline": True,
            },
        ],
        "delta_vs_baseline": 0.05,
        "relative_improvement": 0.090909,
        "beats_baseline": True,
    }))
    plan = {
        "metric": {"name": "wape", "direction": "minimize"},
        "baselines": [{"name": "emro_forecast", "type": "company"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "WAPE": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "baseline_metrics": {"type": "array"},
                        "method_results": {"type": "array"},
                        "delta_vs_baseline": {"type": "number"},
                        "relative_improvement": {"type": "number"},
                        "beats_baseline": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("contradicts wape=0.5 vs best baseline 0.5" in issue for issue in issues)


def test_phase_audit_infers_candidate_rows_from_method_comparison(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "WAPE": 0.50,
        "baseline_results": [
            {"baseline": "regular_model", "WAPE": 0.50},
            {"baseline": "emro_forecast", "WAPE": 0.55},
        ],
        "method_results": [
            {
                "method": "regular_model",
                "baseline": "emro_forecast",
                "WAPE": 0.50,
                "delta_vs_baseline": 0.05,
                "relative_improvement": 0.090909,
                "beats_baseline": True,
            },
            {
                "method": "emro_forecast",
                "baseline": "emro_forecast",
                "WAPE": 0.55,
                "delta_vs_baseline": 0.0,
                "relative_improvement": 0.0,
                "beats_baseline": False,
            },
        ],
        "delta_vs_baseline": 0.05,
        "relative_improvement": 0.090909,
        "beats_baseline": True,
    }))
    plan = {
        "metric": {"name": "wape", "direction": "minimize"},
        "baselines": [{"name": "emro_forecast", "type": "company"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "WAPE": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "method_results": {"type": "array"},
                        "delta_vs_baseline": {"type": "number"},
                        "relative_improvement": {"type": "number"},
                        "beats_baseline": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("contradicts wape=0.5 vs best baseline 0.5" in issue for issue in issues)


def test_phase_audit_ignores_negated_direct_baseline_metric_for_consistency(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "no_baseline_mae": 0.58,
        "beats_baseline": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "no_baseline_mae": {"type": "number"},
                        "beats_baseline": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("beats_baseline=true contradicts" in issue for issue in issues)


def test_phase_audit_ignores_negated_beats_baseline_flag_for_consistency(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "no_beats_baseline": False,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "no_beats_baseline": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("no_beats_baseline=false contradicts" in issue for issue in issues)


def test_phase_audit_rejects_nested_beats_baseline_contradiction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "model_comparison": {"winner": {"beats_baseline": True}},
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "model_comparison": {"type": "object"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "model_comparison.winner.beats_baseline=true contradicts mae=0.62 vs best baseline 0.58"
        in issue
        for issue in issues
    )


def test_phase_audit_rejects_nested_beats_baseline_without_top_level_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "final_model": {
            "mae_mean": 0.62,
            "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
            "beats_baseline": True,
        },
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"final_model": {"type": "object"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "final_model.beats_baseline=true contradicts mae=0.62 vs best baseline 0.58"
        in issue
        for issue in issues
    )


def test_phase_audit_rejects_positive_improvement_contradiction_for_maximize_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy_mean": 0.71,
        "baseline_results": [{"name": "logistic regression", "accuracy_mean": 0.76}],
        "improvement_over_baseline": 0.05,
    }))
    plan = {
        "metric": {"name": "accuracy", "direction": "maximize"},
        "baselines": [{"name": "logistic regression", "type": "simple ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("positive improvement_over_baseline contradicts accuracy=0.71 vs best baseline 0.76" in issue for issue in issues)


def test_phase_audit_rejects_nested_positive_improvement_contradiction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy_mean": 0.71,
        "baseline_results": [{"name": "logistic regression", "accuracy_mean": 0.76}],
        "model_comparison": {"winner": {"improvement_over_baseline": 0.05}},
    }))
    plan = {
        "metric": {"name": "accuracy", "direction": "maximize"},
        "baselines": [{"name": "logistic regression", "type": "simple ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "model_comparison": {"type": "object"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "positive improvement_over_baseline contradicts accuracy=0.71 vs best baseline 0.76"
        in issue
        for issue in issues
    )


def test_phase_audit_rejects_nested_improvement_without_top_level_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "final_model": {
            "mae_mean": 0.42,
            "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
            "improvement_over_baseline": 0.30,
        },
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"final_model": {"type": "object"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "improvement_over_baseline=0.3 does not match mae=0.42 vs best baseline 0.58"
        in issue
        for issue in issues
    )


def test_phase_audit_rejects_wrong_absolute_baseline_improvement_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "improvement_over_baseline": 0.30,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "improvement_over_baseline=0.3 does not match mae=0.42 vs best baseline 0.58; expected about 0.16 or 0.275862"
        in issue
        for issue in issues
    )


def test_phase_audit_rejects_wrong_relative_baseline_improvement_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "relative_improvement": 0.10,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "relative_improvement": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        "relative_improvement=0.1 does not match mae=0.42 vs best baseline 0.58; expected about 0.275862"
        in issue
        for issue in issues
    )


def test_phase_audit_accepts_percentage_relative_baseline_improvement(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "relative_improvement": 27.6,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "relative_improvement": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_consistent_beats_baseline_for_minimize_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.58}],
        "beats_baseline": True,
        "improvement_over_baseline": 0.16,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [{"name": "seasonal naive", "type": "non-ML"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "beats_baseline": {"type": "boolean"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_per_split_comparison_against_labeled_local_baseline(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.50,
        "baseline_results": [
            {"model": "DummyRegressor_median", "mae_mean": 0.65},
            {"model": "Ridge", "mae_mean": 0.40},
        ],
        "comparison_table": [{
            "split_id": "repeat_00_fold_00",
            "baseline": "Ridge",
            "model": "RandomForestRegressor",
            "mae": 0.30,
            "ridge_mae": 0.31,
            "delta_vs_baseline": 0.01,
            "relative_improvement": 0.032258,
            "beats_baseline": True,
        }],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"name": "non-ML heuristic naive median DummyRegressor", "type": "non-ML"},
            {"name": "simple ML Ridge linear regression baseline", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "comparison_table": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("missing planned baseline comparisons" in issue for issue in issues)
    assert not any("beats_baseline=true contradicts" in issue for issue in issues)
    assert not any("relative_improvement=0.032258 does not match" in issue for issue in issues)


def test_phase_audit_accepts_comparison_table_row_with_explicit_comparator_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "WAPE": 0.57,
        "baseline_results": [
            {"baseline": "emro", "WAPE": 0.526},
            {"baseline": "moving_average", "WAPE": 0.575},
        ],
        "comparison_table": [{
            "method": "ridge",
            "comparator": "moving_average",
            "WAPE": 0.569,
            "comparator_WAPE": 0.575,
            "delta_vs_baseline": 0.006,
            "relative_improvement": 0.010435,
            "beats_baseline": True,
        }],
    }))
    plan = {
        "metric": {"name": "WAPE", "direction": "minimize"},
        "baselines": [{"name": "emro"}, {"name": "moving_average"}],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "WAPE": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "comparison_table": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("beats_baseline=true contradicts" in issue for issue in issues)
    assert not any("delta_vs_baseline=0.006 does not match" in issue for issue in issues)


def test_phase_audit_rejects_true_target_flag_when_minimize_metric_misses_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("target_achieved=true contradicts mae=0.42 vs target 0.4" in issue for issue in issues)


def test_phase_audit_skips_raw_metric_target_check_for_delta_target_interpretation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "WAPE": 0.503,
        "delta_vs_emro": 0.023,
        "delta_vs_simple_ml": 0.066,
        "target_achieved": True,
    }))
    plan = {
        "metric": {
            "name": "WAPE",
            "direction": "minimize",
            "target": 0.02,
            "target_interpretation": "minimum useful WAPE reduction/delta versus EMRO and simple ML",
        },
        "success_criteria": [
            "delta_vs_emro >= 0.02 and delta_vs_simple_ml >= 0.02",
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "WAPE": {"type": "number"},
                        "delta_vs_emro": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("target_achieved=true contradicts WAPE=0.503 vs target 0.02" in issue for issue in issues)


def test_phase_audit_accepts_true_target_flag_for_precision_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "precision": 0.92,
        "target_achieved": True,
    }))
    plan = {
        "metric": {"name": "precision", "direction": "maximize", "target": 0.9},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "precision": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_target_flag_with_support_stat_only_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_std": 0.03,
        "target_achieved": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_std": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("target_achieved requires mae metric value to verify target 0.4" in issue for issue in issues)


def test_phase_audit_rejects_target_flag_with_negated_primary_metric_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "no_mae_mean": 0.39,
        "target_achieved": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "no_mae_mean": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("target_achieved requires mae metric value to verify target 0.4" in issue for issue in issues)


def test_phase_audit_requires_target_flag_when_plan_metric_has_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("must include target_achieved, goal_achieved, or success_criteria_met" in issue for issue in issues)


def test_phase_audit_requires_goal_flag_when_plan_defines_success_criteria_without_metric_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Reduce MAE below the seasonal naive baseline by at least 10%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("when plan defines success criteria" in issue for issue in issues)


def test_phase_audit_rejects_negated_target_achievement_key_as_goal_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
        "not_target_achieved": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Reduce MAE below the seasonal naive baseline by at least 10%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "not_target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("when plan defines success criteria" in issue for issue in issues)


def test_phase_audit_rejects_ambiguous_goal_flag_for_success_criteria(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
        "success_criteria_met": "unknown",
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Reduce MAE below the seasonal naive baseline by at least 10%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "success_criteria_met": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("success_criteria_met goal-achievement flag must be a concrete true/false value" in issue for issue in issues)
    assert any("when plan defines success criteria" in issue for issue in issues)


def test_phase_audit_does_not_treat_goal_metric_metadata_as_goal_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
        "goal_metric": "mae",
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Reduce MAE below the seasonal naive baseline by at least 10%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "goal_metric": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("goal_metric goal-achievement flag" in issue for issue in issues)
    assert any("when plan defines success criteria" in issue for issue in issues)


def test_phase_audit_accepts_goal_flag_for_success_criteria_without_metric_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
        "success_criteria_met": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "goal": {"success_criteria": "Reduce MAE below the seasonal naive baseline by at least 10%."},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_missing_target_flag_when_target_metric_not_reported(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "fold_count": 5,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"fold_count": {"type": "integer"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("must include target_achieved" in issue for issue in issues)


def test_phase_audit_does_not_require_target_flag_for_negated_primary_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "no_mae_mean": 0.39,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"no_mae_mean": {"type": "number"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("must include target_achieved" in issue for issue in issues)


def test_phase_audit_does_not_use_error_slice_metric_as_primary_target_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "error_slices": [{"slice": "hard_cases", "mae_mean": 0.39}],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "error_slices": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "slice": {"type": "string"},
                                    "mae_mean": {"type": "number"},
                                },
                            },
                        },
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("must include target_achieved" in issue for issue in issues)


def test_phase_audit_rejects_nested_true_target_flag_when_metric_misses_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "final_model": {
            "mae_mean": 0.42,
            "target_achieved": True,
        },
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"final_model": {"type": "object"}},
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("final_model.target_achieved=true contradicts mae=0.42 vs target 0.4" in issue for issue in issues)


def test_phase_audit_rejects_false_target_flag_when_maximize_metric_meets_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy_mean": 0.91,
        "success_criteria_met": False,
    }))
    plan = {
        "metric": {"name": "accuracy", "direction": "maximize", "target": 0.9},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy_mean": {"type": "number"},
                        "success_criteria_met": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("success_criteria_met=false contradicts accuracy=0.91 vs target 0.9" in issue for issue in issues)


def test_phase_audit_accepts_nested_target_flags_with_local_metric_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "candidate_results": [
            {"name": "candidate_a", "mae_mean": 0.39, "target_achieved": True},
            {"name": "candidate_b", "mae_mean": 0.42, "target_achieved": False},
        ],
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"candidate_results": {"type": "array"}},
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_target_flag_consistent_with_metric_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.39,
        "target_achieved": True,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize", "target": "0.40"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_target_flag_with_metric_alias(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "accuracy_mean": 0.91,
        "target_achieved": True,
    }))
    plan = {
        "metric": {"name": "acc", "direction": "maximize", "target": 0.9},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "accuracy_mean": {"type": "number"},
                        "target_achieved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_missing_planned_baseline_names(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"name": "seasonal naive", "mae_mean": 0.58},
        ],
        "improvement_over_baseline": 0.1429,
    }))
    plan = {
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                        "improvement_over_baseline": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "experimental results missing planned baseline comparisons: ['linear regression']" in issues


def test_phase_audit_matches_planned_baseline_ids_and_ignores_context_only_sota(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_results": [
            {"baseline": "b0_emro", "mae_mean": 0.50},
            {"baseline": "b1_no_regular_ridge", "mae_mean": 0.47},
        ],
        "improvement_over_baseline": 0.05,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "baselines": [
            {"id": "b0_emro", "name": "EMRO company forecast baseline"},
            {"id": "b1_no_regular_ridge", "name": "simple ML ridge regression no-regular-feature control"},
            {
                "id": "b2_sota_context",
                "name": "SOTA/literature baselines not reproduced",
                "category": "context_only",
                "phase_ids": [],
            },
        ],
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "baseline_results": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("missing planned baseline comparisons" in issue for issue in issues)
    assert "experimental results must include SOTA or prior-work comparison evidence" not in issues


def test_phase_audit_accepts_zero_split_counts_for_no_split_eda_phase(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "phase_id": "phase_0",
        "mae_mean": 0.42,
        "split_protocol": "p0 performs no train/test split and fits no preprocessing.",
        "split_id": "p0_no_split_eda_only",
        "split_count": 0,
        "fold_count": 0,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "split_count": {"type": "integer"},
                        "fold_count": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }],
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert not any("must declare at least 2 folds/splits" in issue for issue in issues)


def test_phase_audit_rejects_empty_reproducibility_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "random_seed": 7,
        "dataset_fingerprint": "",
        "split_id": "fold_0",
        "python_version": "3.11",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "mae_std": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 dataset_fingerprint reproducibility metadata must be non-empty" in issues


def test_phase_audit_rejects_placeholder_reproducibility_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "dataset_fingerprint": "not collected",
        "split_id": "not measured",
        "python_version": "not reported",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 dataset_fingerprint reproducibility metadata must not be a placeholder" in issues
    assert "phase_0 split_id reproducibility metadata must not be a placeholder" in issues
    assert "phase_0 python_version reproducibility metadata must not be a placeholder" in issues


def test_phase_audit_rejects_script_result_missing_reproducibility_bundle(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "random_seed": 7,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "random_seed": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        issue.startswith("phase_0 reproducibility metadata missing groups: ")
        and "data source/fingerprint" in issue
        and "split/protocol" in issue
        and "environment" in issue
        and "code provenance" in issue
        and "code path" in issue
        for issue in issues
    )


def test_phase_audit_accepts_script_result_with_reproducibility_bundle(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "n_samples": 100,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "mae_std": {"type": "number"},
                        "n_samples": {"type": "integer"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_negated_code_path_as_reproducibility_path(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "no_script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "mae_std": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "no_script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        issue.startswith("phase_0 reproducibility metadata missing groups: ")
        and "code path" in issue
        for issue in issues
    )


def test_phase_audit_rejects_experimental_script_result_missing_statistics(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        issue.startswith("phase_0 experimental script result must include statistical evidence")
        for issue in issues
    )
    assert any(
        "support counts alone do not satisfy the statistical inference requirement" in issue
        for issue in issues
    )


def test_phase_audit_rejects_negated_statistical_key_as_script_statistics(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_mae_std": 0.03,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "no_mae_std": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any(
        issue.startswith("phase_0 experimental script result must include statistical evidence")
        for issue in issues
    )


def test_phase_audit_rejects_support_only_statistics_for_experimental_results(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "n_samples": 100,
        "fold_count": 5,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "n_samples": {"type": "integer"},
                        "fold_count": {"type": "integer"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "experimental results must include statistical uncertainty or significance "
        "evidence such as std, CI, variance, p_value, or comparison CI"
    ) in issues


def test_phase_audit_rejects_p_value_without_sample_or_repetition_support(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 0.03,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "p_value": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "phase_0 p_value significance evidence requires sample/repetition support "
        "such as n_samples, n_trials, or fold_count"
    ) in issues


def test_phase_audit_rejects_uncertainty_without_sample_or_repetition_support(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    plan = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "mae_std": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert (
        "phase_0 mae_std uncertainty evidence requires sample/repetition support "
        "such as n_samples, n_trials, or fold_count"
    ) in issues


def test_phase_audit_rejects_nested_schema_type_mismatch(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "run_metadata": {
            "random_seed": "7",
            "dataset_fingerprint": "sha256:abc",
            "environment": {
                "python_version": 3.11,
            },
        },
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "run_metadata": {
                            "type": "object",
                            "properties": {
                                "random_seed": {"type": "integer"},
                                "dataset_fingerprint": {"type": "string"},
                                "environment": {
                                    "type": "object",
                                    "properties": {
                                        "python_version": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 run_metadata.random_seed expected integer, got str" in issues
    assert "phase_0 run_metadata.environment.python_version expected string, got float" in issues


def test_phase_audit_rejects_properties_schema_without_explicit_object_type(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "run_metadata": "seed=7",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "run_metadata": {
                            "properties": {
                                "random_seed": {"type": "integer"},
                            },
                        },
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 run_metadata expected object, got str" in issues


def test_phase_audit_rejects_present_optional_substantive_schema_field(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 1.2,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "required": ["mae_mean"],
                        "properties": {
                            "mae_mean": {"type": "number"},
                            "p_value": {"type": "number"},
                        },
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 p_value p-value must be between 0 and 1" in issues


def test_phase_audit_rejects_extra_invalid_substantive_field_not_declared_in_schema(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 1.2,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 p_value p-value must be between 0 and 1" in issues


def test_phase_audit_rejects_invalid_alpha_threshold(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "alpha": 0,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 alpha significance threshold must be > 0 and < 1" in issues


def test_phase_audit_rejects_mismatched_code_provenance_hash(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    script = pdir / "phase_0.py"
    script.write_text("print('actual')\n")
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": "sha256:wrong",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 script_sha256 does not match research/iter_1/phases/phase_0.py" in issues


def test_phase_audit_rejects_nested_mismatched_code_provenance_hash(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    script = pdir / "phase_0.py"
    script.write_text("print('actual')\n")
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "run_metadata": {
            "script_path": "research/iter_1/phases/phase_0.py",
            "script_sha256": "sha256:wrong",
        },
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "run_metadata": {
                            "type": "object",
                            "properties": {
                                "script_path": {"type": "string"},
                                "script_sha256": {"type": "string"},
                            },
                        },
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 run_metadata.script_sha256 does not match research/iter_1/phases/phase_0.py" in issues


def test_phase_audit_rejects_code_provenance_path_without_hash(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    script = pdir / "phase_0.py"
    script.write_text("print('actual')\n")
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_path": "research/iter_1/phases/phase_0.py",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_path": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 code provenance must include at least one script/code hash" in issues


def test_phase_audit_rejects_code_hash_without_provenance_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_sha256": "sha256:" + "a" * 64,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 code provenance hash requires script_path or code_path" in issues


def test_phase_audit_rejects_conflicting_code_provenance_paths(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    script = pdir / "phase_0.py"
    script.write_text("print('actual')\n")
    digest = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_path": "research/iter_1/phases/phase_0.py",
        "code_path": "research/iter_1/phases/other.py",
        "script_sha256": digest,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_path": {"type": "string"},
                        "code_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("code provenance paths disagree" in issue for issue in issues)


def test_phase_audit_rejects_code_provenance_outside_project(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside.py"
    outside.write_text("print('outside')\n")
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_path": str(outside),
        "script_sha256": "sha256:wrong",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 code provenance path must be inside project_dir" in issues


def test_phase_audit_rejects_code_provenance_outside_current_phase_dir(tmp_path: Path):
    src_dir = tmp_path / "src"
    rdir = tmp_path / "research" / "iter_1" / "results"
    src_dir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    script = src_dir / "model.py"
    script.write_text("print('model')\n")
    digest = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_path": "src/model.py",
        "script_sha256": digest,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 code provenance path must be under research/iter_1/phases/" in issues


def test_phase_audit_accepts_matching_code_provenance_hash(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    script = pdir / "phase_0.py"
    script.write_text("print('actual')\n")
    digest = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": digest,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_evaluation_audit_rejects_high_goal_score_with_false_target_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_achieved": False}))
    evaluation = {
        "verdict": "ACCEPT",
        "summary": "The target was achieved.",
        "scores": {
            "goal_achievement": 8,
        },
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation goal achievement contradicts result flags: "
        "['research/iter_1/results/phase_0.json:target_achieved']"
    ]


def test_evaluation_audit_respects_iteration_scope(tmp_path: Path):
    rdir1 = tmp_path / "research" / "iter_1" / "results"
    rdir2 = tmp_path / "research" / "iter_2" / "results"
    rdir1.mkdir(parents=True)
    rdir2.mkdir(parents=True)
    (rdir1 / "phase_0.json").write_text(json.dumps({"target_achieved": False}))
    (rdir2 / "phase_0.json").write_text(json.dumps({"target_achieved": True}))
    evaluation = {
        "verdict": "ACCEPT",
        "summary": "The target was achieved.",
        "scores": {
            "goal_achievement": 8,
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation, iterations=(2,)) == []
    assert audit_evaluation_result_consistency(tmp_path, evaluation) == [
        "evaluation goal achievement contradicts result flags: "
        "['research/iter_1/results/phase_0.json:target_achieved']"
    ]


def test_evaluation_audit_allows_high_goal_score_with_negative_comparison_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "beats_baseline": False,
        "relative_improvement": 0,
        "model_comparison": {
            "winner": {
                "beats_sota": "no",
            },
        },
    }))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "goal_achievement": 8,
        },
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == []


def test_evaluation_audit_allows_low_goal_score_with_negative_comparison_flags(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "beats_baseline": False,
        "relative_improvement": -0.05,
        "beats_sota": False,
    }))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "goal_achievement": 5,
            "academic_rigor": 6,
            "experimental_sufficiency": 6,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_ignores_non_numeric_iteration_result_flags(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_x" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "target_achieved": False,
        "leakage_found": True,
        "baseline_results": False,
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "goal_achievement": 8,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_treats_clean_leakage_flags_as_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": False,
        "train_test_overlap": 0,
        "group_leakage": "no leakage",
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "goal_achievement": 8,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_allows_low_goal_score_with_false_target_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_achieved": False}))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "goal_achievement": 5,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_rejects_high_sufficiency_with_missing_baseline_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"baseline_results": False}))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 6,
            "experimental_sufficiency": 8,
            "goal_achievement": 5,
        },
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation rigor/sufficiency contradicts explicit missing experimental evidence flags: "
        "['research/iter_1/results/phase_0.json:baseline_results']"
    ]


def test_evaluation_audit_rejects_accept_with_missing_sota_and_statistical_flags(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "sota_results": [],
        "p_value": "not measured",
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "goal_achievement": 8,
        },
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation rigor/sufficiency contradicts explicit missing experimental evidence flags: "
        "['research/iter_1/results/phase_0.json:sota_results', "
        "'research/iter_1/results/phase_0.json:p_value']"
    ]


def test_evaluation_audit_ignores_context_reference_and_failure_case_optional_fields(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "prior_work_results": [],
        "reference_results": [],
        "failure_cases": [
            {"launch_age_weeks_from_train": None, "mae": 0.42},
        ],
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_rejects_accept_with_missing_advanced_evidence_flags(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "ablation_results": [],
        "cv_results": [],
        "error_analysis": "unknown",
        "causal_design": "",
        "robustness_checks": "not done",
        "external_validation_results": None,
        "fairness_by_group": [],
        "latency_ms": "not measured",
        "split_audit": "not reported",
        "script_path": "",
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "goal_achievement": 8,
        },
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation rigor/sufficiency contradicts explicit missing experimental evidence flags: "
        "['research/iter_1/results/phase_0.json:ablation_results', "
        "'research/iter_1/results/phase_0.json:cv_results', "
        "'research/iter_1/results/phase_0.json:error_analysis', "
        "'research/iter_1/results/phase_0.json:causal_design', "
        "'research/iter_1/results/phase_0.json:robustness_checks', "
        "'research/iter_1/results/phase_0.json:external_validation_results', "
        "'research/iter_1/results/phase_0.json:fairness_by_group', "
        "'research/iter_1/results/phase_0.json:latency_ms', "
        "'research/iter_1/results/phase_0.json:split_audit', "
        "'research/iter_1/results/phase_0.json:script_path']"
    ]


def test_evaluation_audit_allows_low_sufficiency_with_missing_baseline_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"baseline_results": False}))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 6,
            "experimental_sufficiency": 5,
            "goal_achievement": 5,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_ignores_negated_or_metadata_missing_evidence_flags(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "no_baseline_results": True,
        "baseline_results_method": "not collected",
        "no_ablation_results": True,
        "ablation_results_method": "not collected",
        "no_beats_baseline": False,
        "beats_baseline_method": False,
        "no_beats_sota": False,
        "beats_sota_method": False,
        "relative_improvement_method": 0,
        "row_id_leakage": False,
        "without_fairness_by_group": True,
        "fairness_by_group_method": "not collected",
        "no_latency_ms": True,
        "latency_ms_method": "not collected",
        "without_script_path": True,
        "script_path_method": "not collected",
    }))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "goal_achievement": 5,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_rejects_feedback_citing_missing_result_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "academic_rigor",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/missing.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites missing research artifacts: "
        "['research/iter_1/results/missing.json']"
    ]


def test_evaluation_audit_rejects_default_feedback_artifact_when_no_results_exist(tmp_path: Path):
    (tmp_path / "research").mkdir()
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "experimental_sufficiency",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites missing research artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_directory_as_artifact(tmp_path: Path):
    cited = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
    cited.mkdir(parents=True)
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "goal_achievement",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites missing research artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_unsafe_artifact_path(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text("{}")
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "academic_rigor",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on "
                "research/iter_1/results/../../evaluation.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites unsafe research artifact paths: "
        "['research/iter_1/results/../../evaluation.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_missing_iteration_artifact(tmp_path: Path):
    (tmp_path / "research").mkdir()
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "experimental_sufficiency",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_99/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites missing research artifacts: "
        "['research/iter_99/results/phase_0.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_invalid_json_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text("{not json")
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "academic_rigor",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites invalid JSON research artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_empty_result_json_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text("{}")
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "experimental_sufficiency",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites non-substantive JSON research artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_non_object_result_json_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text("[]")
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "goal_achievement",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites non-substantive JSON research artifacts: "
        "['research/iter_1/results/phase_0.json']"
    ]


def test_evaluation_audit_rejects_feedback_citing_result_json_with_invalid_values(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 1.2,
        "n_samples": 100,
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "academic_rigor",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert len(issues) == 1
    assert "evaluation.feedback cites invalid result JSON research artifacts" in issues[0]
    assert "research/iter_1/results/phase_0.json" in issues[0]
    assert "p_value p-value must be between 0 and 1" in issues[0]


def test_evaluation_audit_rejects_feedback_citing_result_json_with_malformed_interval(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_ci95": [0.2],
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "academic_rigor",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert len(issues) == 1
    assert "evaluation.feedback cites invalid result JSON research artifacts" in issues[0]
    assert "research/iter_1/results/phase_0.json" in issues[0]
    assert "mae_ci95 interval must provide exactly two numeric bounds" in issues[0]


def test_evaluation_audit_accepts_feedback_citing_substantive_result_json_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "experimental_sufficiency",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0.json."
            ),
        }],
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_evaluation_audit_rejects_feedback_citing_invalid_png_artifact(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0_error.png").write_bytes(b"not a png")
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "feedback": [{
            "criterion": "narrative_coherence",
            "score": 8,
            "recommendation": (
                "The accepted evaluation relies on research/iter_1/results/phase_0_error.png."
            ),
        }],
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation.feedback cites invalid PNG research artifacts: "
        "['research/iter_1/results/phase_0_error.png']"
    ]


def test_evaluation_audit_rejects_accept_with_unresolved_leakage(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": True,
        "train_test_overlap": 3,
    }))
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
        },
    }

    issues = audit_evaluation_result_consistency(tmp_path, evaluation)

    assert issues == [
        "evaluation validity scores contradict unresolved leakage findings: "
        "['research/iter_1/results/phase_0.json:leakage_found', "
        "'research/iter_1/results/phase_0.json:train_test_overlap']"
    ]


def test_evaluation_audit_allows_high_validity_score_after_leakage_mitigation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": True,
        "train_test_overlap": 3,
    }))
    (rdir / "phase_1.json").write_text(json.dumps({
        "leakage_mitigated": True,
    }))
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "goal_achievement": 5,
        },
    }

    assert audit_evaluation_result_consistency(tmp_path, evaluation) == []


def test_phase_audit_rejects_generic_leakage_flag_without_audit_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": False,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}, "leakage_found": {"type": "boolean"}},
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("experimental results must include leakage audit scope evidence" in issue for issue in issues)


def test_phase_audit_rejects_placeholder_leakage_audit_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": False,
        "train_test_overlap": "not measured",
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "string"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("experimental results must include leakage audit scope evidence" in issue for issue in issues)


def test_phase_audit_rejects_target_leakage_metadata_as_audit_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_leakage_metric": False,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "target_leakage_metric": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("experimental results must include leakage audit scope evidence" in issue for issue in issues)


def test_phase_audit_rejects_negated_leakage_key_as_audit_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_target_leakage": False,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "no_target_leakage": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert any("experimental results must include leakage audit scope evidence" in issue for issue in issues)


def test_phase_audit_accepts_leakage_audit_with_overlap_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": False,
        "train_test_overlap": 0,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_leakage_audit_with_group_overlap_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": False,
        "group_overlap": 0,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "group_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_unresolved_leakage(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": True,
        "train_test_overlap": 1,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "unresolved leakage findings" in issues[-1]


def test_phase_audit_accepts_resolved_leakage(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": True,
        "train_test_overlap": 1,
        "leakage_resolved": True,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                        "leakage_resolved": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_leakage_found_after_prior_resolution(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_resolved": True,
    }))
    (rdir / "phase_1.json").write_text(json.dumps({
        "mae_mean": 0.51,
        "leakage_found": True,
        "train_test_overlap": 1,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {"mae_mean": {"type": "number"}, "leakage_resolved": {"type": "boolean"}},
                }
            },
            "visualization": [],
        }, {
            "id": "phase_1",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_1.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "unresolved leakage findings" in issues[-1]
    assert "phase_1.leakage_found" in issues[-1]


def test_phase_audit_accepts_later_leakage_mitigation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": True,
        "train_test_overlap": 1,
    }))
    (rdir / "phase_1.json").write_text(json.dumps({
        "mae_mean": 0.45,
        "leakage_mitigated": True,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }, {
            "id": "phase_1",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_1.json",
                    "schema": {"mae_mean": {"type": "number"}, "leakage_mitigated": {"type": "boolean"}},
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_accepts_later_no_leakage_after_fix_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": True,
        "train_test_overlap": 1,
    }))
    (rdir / "phase_1.json").write_text(json.dumps({
        "mae_mean": 0.45,
        "no_leakage_after_fix": True,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }, {
            "id": "phase_1",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_1.json",
                    "schema": {"mae_mean": {"type": "number"}, "no_leakage_after_fix": {"type": "boolean"}},
                }
            },
            "visualization": [],
        }]
    }

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_leakage_resolution_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "leakage_found": True,
        "train_test_overlap": 1,
    }))
    (rdir / "phase_1.json").write_text(json.dumps({
        "mae_mean": 0.45,
        "leakage_mitigated_method": True,
    }))
    plan = {
        "phases": [{
            "id": "phase_0",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_found": {"type": "boolean"},
                        "train_test_overlap": {"type": "integer"},
                    },
                }
            },
            "visualization": [],
        }, {
            "id": "phase_1",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_1.json",
                    "schema": {
                        "mae_mean": {"type": "number"},
                        "leakage_mitigated_method": {"type": "boolean"},
                    },
                }
            },
            "visualization": [],
        }]
    }

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "unresolved leakage findings" in issues[-1]
    assert "phase_0.leakage_found" in issues[-1]


def test_phase_audit_accepts_optimize_trial_trace(tmp_path: Path):
    plan, data = _optimize_plan_and_result(tmp_path)
    result_path = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
    result_path.write_text(json.dumps(data))

    assert audit_phase_outputs(tmp_path, 1, plan) == []


def test_phase_audit_rejects_optimize_result_missing_trial_trace(tmp_path: Path):
    plan, data = _optimize_plan_and_result(tmp_path)
    data.pop("all_trials")
    data.pop("optimization_config")
    result_path = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
    result_path.write_text(json.dumps(data))

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 optimize result must record optimization_config" in issues
    assert "phase_0 optimize result must include non-empty all_trials" in issues


def test_phase_audit_rejects_optimize_result_with_inconsistent_best_trial(tmp_path: Path):
    plan, data = _optimize_plan_and_result(tmp_path)
    data["mae"] = 0.5
    data["n_trials"] = 3
    data["all_trials"][0].pop("command")
    data["all_trials"].append({"params": {}, "command": "python train.py", "value": "bad", "state": "complete"})
    result_path = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
    result_path.write_text(json.dumps(data))

    issues = audit_phase_outputs(tmp_path, 1, plan)

    assert "phase_0 all_trials[0].command must be non-empty" in issues
    assert "phase_0 all_trials[2].value must be numeric for completed trials" in issues
    assert "phase_0 best mae=0.5 does not match minimize all_trials best 0.3" in issues


def _optimize_plan_and_result(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    phase_dir = tmp_path / "research" / "iter_1" / "phases"
    result_dir = tmp_path / "research" / "iter_1" / "results"
    phase_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    script = phase_dir / "phase_0_optimize.py"
    script.write_text("print('optimize')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    plan: dict[str, object] = {
        "metric": {"name": "mae", "direction": "minimize"},
        "phases": [{
            "id": "phase_0",
            "type": "optimize",
            "status": "done",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": {
                        "mae": {"type": "number"},
                        "mae_std": {"type": "number"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                        "best_params": {"type": "object"},
                        "n_trials": {"type": "integer"},
                        "total_seconds": {"type": "number"},
                        "optimization_metric": {"type": "string"},
                        "optimization_direction": {"type": "string"},
                        "selection_criterion": {"type": "string"},
                        "optimization_config": {"type": "object"},
                        "all_trials": {"type": "array"},
                    },
                }
            },
            "visualization": [],
        }],
    }
    data: dict[str, object] = {
        "mae": 0.3,
        "mae_std": 0.01,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0_optimize.py",
        "script_sha256": script_sha,
        "best_params": {"lr": 0.01},
        "n_trials": 2,
        "total_seconds": 1.5,
        "optimization_metric": "mae",
        "optimization_direction": "minimize",
        "selection_criterion": "minimize mae",
        "optimization_config": {"n_trials": 2, "search_space": {"model": {"lr": {"type": "float"}}}},
        "all_trials": [
            {
                "approach": "model",
                "params": {"lr": 0.01},
                "command": "python train.py --lr 0.01",
                "value": 0.3,
                "state": "complete",
            },
            {
                "approach": "model",
                "params": {"lr": 0.02},
                "command": "python train.py --lr 0.02",
                "value": 0.4,
                "state": "complete",
            },
        ],
    }
    return plan, data
