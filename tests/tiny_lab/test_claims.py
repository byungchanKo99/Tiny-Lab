"""Tests for final-paper claim verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tiny_lab.claims import verify_paper_numeric_claims


def test_accepts_metric_numbers_present_in_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "accuracy": 0.91,
        "split_id": "heldout_0",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model reaches MAE = 0.42 and accuracy = 91% on the held-out split "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_ignores_short_metric_hints_inside_words(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "All references above are cited from `research/iter_1/.domain_research.json`, "
        "which carries a passing sidecar confirming all 11 references are verified via arXiv or Crossref."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_ignores_baseline_superiority_research_question_framing(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The objective is to compare whether a random forest improves MAE over a "
        "leakage-safe linear baseline on a small tabular benchmark."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_ignores_sota_disclaimer_without_result_citation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "We do not claim SOTA performance and make no novelty claims beyond the protocol design."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_metric_numbers_rounded_to_two_decimals(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 44.523593,
        "mae_std": 3.262274,
        "n_samples": 442,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model reaches MAE = 44.52 with MAE standard deviation 3.26 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_plus_minus_metric_dispersion_claim(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 44.523593,
        "mae_std": 3.262274,
        "n_samples": 442,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model reaches MAE = 44.52 +/- 3.26 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_metric_after_closed_ci_context(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_1.json").write_text(json.dumps({
        "method_results": [
            {
                "model": "Ridge",
                "mae": 44.523593,
                "mae_std": 3.262274,
                "mae_ci95": [43.62, 45.43],
            },
            {
                "model": "RandomForestRegressor",
                "mae": 46.934868,
                "mae_std": 3.587,
                "mae_ci95": [45.94, 47.93],
            },
        ],
        "paired_delta_mae_mean": 2.411275,
        "paired_delta_mae_ci95": [1.89, 2.93],
        "p_value": 0.0,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "As reported in `research/iter_1/results/phase_1.json`, Ridge achieved a mean MAE of "
        "44.52 +/- 3.26 (95% CI: [43.62, 45.43]) versus RandomForestRegressor at "
        "46.93 +/- 3.59 (95% CI: [45.94, 47.93]); the paired delta was 2.41 "
        "(95% CI: [1.89, 2.93], p=0.0)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_plus_minus_dispersion_from_generic_sibling_std(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "method_results": [{
            "model": "Ridge",
            "mae": 44.523593,
            "std": 3.262274,
        }],
        "n_samples": 442,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Ridge reached MAE = 44.52 +/- 3.26 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_rejects_metric_claim_with_only_unsafe_result_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model reaches MAE = 0.42 on the held-out split "
        "(research/iter_1/results/../phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.42
    assert issues[0].reason == "metric sentence does not cite a concrete research/iter_*/results/*.json artifact path"


def test_flags_direct_metric_claim_matching_only_support_stat(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_std": 0.03}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 0.03 (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.03
    assert "mae-like key/value" in issues[0].reason


def test_accepts_numeric_uncertainty_claim_matching_support_stat(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_std": 0.03, "sample_size": 120}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The MAE standard deviation is 0.03 (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_numeric_uncertainty_claim_matching_only_metric_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.03,
        "sample_size": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The MAE standard deviation is 0.03 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 2
    assert issues[0].value == 0.03
    assert "mae-like key/value" in issues[0].reason
    assert "uncertainty claim requires" in issues[1].reason


def test_flags_ci_bound_claim_matching_only_metric_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.02,
        "mae_ci95": [0.40, 0.44],
        "sample_size": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval lower bound was 0.02 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.02
    assert "number does not match" in issues[0].reason


def test_flags_ci_bound_claim_matching_only_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "improvement_p_value": 0.02,
        "mae_ci95": [0.40, 0.44],
        "sample_size": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval lower bound was 0.02 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.02
    assert "number does not match" in issues[0].reason


def test_flags_p_value_claim_matching_only_ci_bound(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "improvement_ci95": [0.03, 0.12],
        "sample_size": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The p-value was 0.03 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.03
    assert "number does not match" in issues[0].reason


def test_accepts_confidence_level_percent_as_ci_modifier(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_ci95": [0.40, 0.44],
        "sample_size": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The 95% confidence interval was [0.40, 0.44] "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_confidence_level_percent_when_claimed_as_interval_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_ci95": [0.40, 0.44],
        "sample_size": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval was 95% "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 95
    assert "number does not match" in issues[0].reason


def test_flags_generic_metric_claim_matching_only_metadata_number(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "sample_size": 120,
        "random_seed": 7,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The primary metric is 120 (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 120
    assert "number does not match any value" in issues[0].reason


def test_flags_generic_metric_claim_matching_only_metadata_suffix_number(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "metric_method": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The primary metric is 120 (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 120
    assert "number does not match any value" in issues[0].reason


def test_flags_specific_metric_claim_matching_only_metric_scoped_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_sample_size": 120}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 120 (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 120
    assert "mae-like key/value" in issues[0].reason


def test_accepts_score_claim_with_score_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "sample_size": 120,
        "f1_score": 0.82,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final score is 0.82 (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_score_claim_with_model_confidence_score_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "sample_size": 120,
        "model_confidence_score": 0.92,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final confidence score is 0.92 (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_metric_numbers_missing_from_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model improves the baseline and reports MAE = 0.31."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.31
    assert "artifact path" in issues[0].reason


def test_ignores_non_metric_years(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Smith et al. published the dataset in 2024. The final MAE is 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_metric_numbers_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 0.42."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "artifact path" in issues[0].reason


def test_flags_metric_number_citing_wrong_result_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "baseline.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "winner.json").write_text(json.dumps({"mae_mean": 0.31}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model reports MAE = 0.31 "
        "(research/iter_1/results/baseline.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.31
    assert "cited" in issues[0].reason


def test_accepts_comma_formatted_metric_number_present_in_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 1234.56}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 1,234.56 (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_comma_formatted_metric_number_missing_from_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 1234.56}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 1,111.11 (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 1111.11


def test_accepts_metric_number_from_any_cited_result_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "baseline.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "winner.json").write_text(json.dumps({"mae_mean": 0.31}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model improves the baseline from MAE = 0.42 to MAE = 0.31 "
        "(research/iter_1/results/baseline.json; research/iter_1/results/winner.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_improvement_claim_with_wrong_lower_is_better_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "baseline.json").write_text(json.dumps({"mae_mean": 0.42}))
    (rdir / "winner.json").write_text(json.dumps({"mae_mean": 0.49}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model improves the baseline from MAE = 0.42 to MAE = 0.49 "
        "(research/iter_1/results/baseline.json; research/iter_1/results/winner.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.49
    assert "expected a lower value" in issues[0].reason


def test_flags_comma_formatted_improvement_claim_with_wrong_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "baseline.json").write_text(json.dumps({"mae_mean": 1000.0}))
    (rdir / "winner.json").write_text(json.dumps({"mae_mean": 1100.0}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model improves the baseline from MAE = 1,000 to MAE = 1,100 "
        "(research/iter_1/results/baseline.json; research/iter_1/results/winner.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 1100.0
    assert "expected a lower value" in issues[0].reason


def test_flags_vs_baseline_claim_with_wrong_lower_is_better_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_mae": 0.49,
        "baseline_mae": 0.42,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline with MAE = 0.49 vs baseline MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.49
    assert "expected a lower value" in issues[0].reason


def test_flags_vs_baseline_claim_with_wrong_higher_is_better_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.89,
        "baseline_accuracy": 0.91,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model is better than the baseline with accuracy = 0.89 compared to baseline accuracy = 0.91 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.89
    assert "expected a higher value" in issues[0].reason


def test_accepts_vs_baseline_claim_with_correct_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_mae": 0.31,
        "baseline_mae": 0.42,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline with MAE = 0.31 vs baseline MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_numeric_baseline_superiority_without_baseline_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline with MAE = 0.31 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires same-metric baseline comparison" in issues[0].reason


def test_accepts_numeric_baseline_superiority_with_model_and_baseline_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_mae": 0.42,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline with MAE = 0.31 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_improvement_claim_with_wrong_higher_is_better_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "baseline.json").write_text(json.dumps({"accuracy": 0.91}))
    (rdir / "winner.json").write_text(json.dumps({"accuracy": 0.89}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model improves the baseline from accuracy = 0.91 to accuracy = 0.89 "
        "(research/iter_1/results/baseline.json; research/iter_1/results/winner.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.89
    assert "expected a higher value" in issues[0].reason


def test_flags_metric_number_citing_missing_result_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 0.42 (research/iter_1/results/missing.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "missing" in issues[0].reason


def test_flags_number_matching_wrong_metric_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42, "accuracy": 0.91}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 0.91 (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.91
    assert "mae-like key/value" in issues[0].reason


def test_accepts_number_matching_nested_metric_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "metrics": {"mae": {"mean": 0.42}},
        "accuracy": 0.91,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final MAE is 0.42 (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_without_statistical_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "p-value" in issues[0].reason


def test_accepts_significance_claim_with_p_value_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_with_p_value_above_declared_alpha(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "alpha": 0.01,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "p-value" in issues[0].reason


def test_accepts_significance_claim_with_p_value_below_declared_alpha(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "alpha": 0.01,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.008,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_non_significance_claim_with_p_value_above_declared_alpha(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "alpha": 0.01,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not show a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_significance_claim_uses_nested_alpha_threshold(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "comparison_results": {
            "seasonal_naive": {
                "significance_level": 0.01,
                "improvement_p_value": 0.03,
            },
        },
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "p-value" in issues[0].reason


def test_significance_claim_accepts_nested_p_value_below_nested_alpha(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "comparison_results": {
            "seasonal_naive": {
                "significance_level": 0.01,
                "improvement_p_value": 0.008,
            },
        },
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_without_sample_or_repetition_support(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires sample/repetition support" in issues[0].reason


def test_flags_significant_improvement_claim_with_p_value_but_no_effect_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires same-metric baseline comparison" in issues[0].reason


def test_flags_significant_improvement_claim_when_p_value_contradicts_metric_direction(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.62,
        "baseline_mae": 0.58,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim contradicts explicit result artifact flags" in issues[0].reason


def test_accepts_significance_claim_with_nested_comparison_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "fold_count": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "comparison_results": {
            "seasonal_naive": {
                "delta_mae": -0.07,
                "p_value": 0.03,
            }
        },
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_with_unrelated_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "normality_p_value": 0.01,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "p-value" in issues[0].reason


def test_accepts_significance_claim_with_ci_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_significance_claim_with_object_ci_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": {"lower": 0.02, "upper": 0.12},
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_negated_significance_claim_with_object_ci_crossing_zero(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": {"ci_lower": -0.01, "ci_upper": 0.12},
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not show a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_with_non_significant_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "p_value": 0.22,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "p-value" in issues[0].reason


def test_accepts_negated_significance_claim_with_non_significant_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.22,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not show a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_negated_significance_claim_contradicted_by_significant_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not show a statistically significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "non-significance claim requires" in issues[0].reason


def test_accepts_negated_significance_claim_with_ci_crossing_zero(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [-0.01, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not show a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_significance_claim_without_metric_word_when_stat_evidence_exists(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "difference_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_significance_claim_with_single_generic_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_with_p_value_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "p_value_method": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The result was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "significance claim requires p-value" in issues[0].reason


def test_flags_significance_claim_with_negated_p_value_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "no_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "significance claim requires p-value" in issues[0].reason


def test_flags_significance_claim_with_negated_sample_support_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "p_value": 0.03,
        "no_n_trials": 5,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires sample/repetition support" in issues[0].reason


def test_accepts_negated_significance_claim_with_single_generic_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "p_value": 0.22,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was not statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_significance_claim_when_generic_p_value_is_ambiguous(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "p_value": 0.03,
        "normality_p_value": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "p-value" in issues[0].reason


def test_flags_significance_claim_with_ci_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "difference_ci95_method": [0.02, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "significance claim requires p-value" in issues[0].reason


def test_flags_significance_claim_without_metric_word_when_stat_evidence_is_missing(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The group difference was statistically significant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "p-value" in issues[0].reason


def test_flags_significance_claim_with_ci_crossing_zero(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [-0.01, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "confidence interval" in issues[0].reason


def test_flags_significance_claim_with_three_bound_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12, 0.2],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "confidence interval" in issues[0].reason


def test_flags_significance_claim_with_reversed_ci_bounds(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_trials": 5,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.12, 0.02],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "confidence interval" in issues[0].reason


def test_flags_significance_claim_with_only_metric_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "mae_ci95": [0.40, 0.44],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model shows a significant improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "confidence interval" in issues[0].reason


def test_accepts_ci_zero_exclusion_claim_with_comparison_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The comparison confidence interval excludes zero "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_ci_zero_exclusion_claim_with_object_ci_and_summary_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": {"lower": 0.02, "upper": 0.12, "mean": 0.07},
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The comparison confidence interval excludes zero "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_ci_zero_exclusion_claim_when_comparison_ci_crosses_zero(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [-0.01, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The comparison confidence interval excludes zero "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "zero-exclusion claim requires" in issues[0].reason


def test_flags_ci_zero_exclusion_claim_with_three_bound_ci(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12, 0.2],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The comparison confidence interval excludes zero "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "zero-exclusion claim requires" in issues[0].reason


def test_flags_ci_zero_crossing_claim_when_comparison_ci_excludes_zero(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_ci95": [0.02, 0.12],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The comparison confidence interval crosses zero "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "zero-crossing claim requires" in issues[0].reason


def test_flags_ci_zero_exclusion_claim_with_metric_ci_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "mae_ci95": [0.40, 0.44],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval excludes zero "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "zero-exclusion claim requires" in issues[0].reason


def test_accepts_uncertainty_claim_with_std_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "n_samples": 120,
        "mae_mean": 0.42,
        "mae_std": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Uncertainty was estimated using the standard deviation "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_uncertainty_claim_without_sample_or_repetition_support(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Uncertainty was estimated using the standard deviation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "uncertainty claim requires sample/repetition support" in issues[0].reason


def test_accepts_uncertainty_claim_with_ci_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "fold_count": 5,
        "mae_mean": 0.42,
        "mae_ci95": [0.40, 0.44],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval quantifies uncertainty "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_uncertainty_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_std": 0.03}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Uncertainty was estimated using the standard deviation."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "uncertainty claim does not cite" in issues[0].reason


def test_flags_uncertainty_claim_without_uncertainty_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Uncertainty was estimated using the standard deviation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "uncertainty claim requires" in issues[0].reason


def test_flags_uncertainty_claim_with_statistical_support_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "p_value": 0.03,
        "n_samples": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Uncertainty was estimated using confidence intervals "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "uncertainty claim requires" in issues[0].reason


def test_flags_uncertainty_claim_with_metadata_suffix_evidence_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "standard_error_method": 0.1,
        "mae_std_method": 0.1,
        "precision_ci_method": [0.8, 0.9],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval quantifies uncertainty "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "uncertainty claim requires" in issues[0].reason


def test_flags_uncertainty_claim_with_negated_uncertainty_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "no_ci95": [0.40, 0.44],
        "without_standard_error": 0.1,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The confidence interval quantifies uncertainty "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "uncertainty claim requires" in issues[0].reason


def test_ignores_honest_missing_uncertainty_limitation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Uncertainty was not estimated, which remains a limitation."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_ignores_uncertainty_section_metadata_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_std": 0.03}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The results section discusses uncertainty."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_causal_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The intervention caused lower error."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "causal claim does not cite" in issues[0].reason


def test_flags_causal_claim_without_causal_design_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The intervention caused lower error "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "causal claim requires causal design" in issues[0].reason


def test_accepts_causal_claim_with_causal_identification_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "causal_identification": "randomized controlled intervention",
        "randomized_assignment": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The intervention caused lower error "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_causal_claim_with_negated_design_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_causal_design": "matched control with propensity score adjustment",
        "causal_effect": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The intervention caused lower error "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "causal claim requires causal design" in issues[0].reason


def test_flags_causal_claim_with_effect_only_without_identification(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "causal_effect": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The intervention caused lower error "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "causal claim requires causal design" in issues[0].reason


def test_flags_causal_claim_with_boolean_design_marker(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "causal_design": True,
        "causal_effect": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The intervention caused lower error "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "causal claim requires causal design" in issues[0].reason


def test_ignores_honest_non_causal_limitation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment does not establish causality."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_robustness_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"robustness_checks": [{"name": "seed"}]}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across random seeds."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "robustness claim does not cite" in issues[0].reason


def test_flags_robustness_claim_without_repeated_or_robustness_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "robustness claim requires" in issues[0].reason


def test_flags_robustness_claim_with_marker_only_robustness_check(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "robustness_checks": [{"name": "seed sensitivity planned"}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "robustness claim requires" in issues[0].reason


def test_flags_robustness_claim_with_seed_ids_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [
            {"seed": 1},
            {"seed": 2},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "robustness claim requires" in issues[0].reason


def test_flags_robustness_claim_with_support_counts_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "robustness_checks": [
            {"name": "stress_a", "n_samples": 100},
            {"name": "stress_b", "n_samples": 100},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across stress tests "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "robustness claim requires" in issues[0].reason


def test_accepts_robustness_claim_with_repeated_seed_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [
            {"seed": 1, "mae_mean": 0.43},
            {"seed": 2, "mae_mean": 0.41},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_robustness_claim_with_negated_robustness_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_robustness_results": [{"seed": 1, "mae_mean": 0.43}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is robust across random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "robustness claim requires" in issues[0].reason


def test_flags_generalization_claim_without_split_or_external_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to unseen data "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "generalization claim requires" in issues[0].reason


def test_flags_generalization_claim_with_external_label_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"source_label": "external_holdout"}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to unseen data "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "generalization claim requires" in issues[0].reason


def test_accepts_generalization_claim_with_holdout_split_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "split_protocol": "80/20 holdout",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to unseen data "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_external_generalization_claim_with_holdout_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "split_protocol": "80/20 holdout",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to external validation data "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "external generalization claim requires" in issues[0].reason


def test_flags_independent_cohort_claim_with_holdout_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "split_protocol": "80/20 holdout",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to an independent cohort "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "external generalization claim requires" in issues[0].reason


def test_accepts_external_generalization_claim_with_external_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": [{"source_label": "external_site", "mae_mean": 0.47}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to external validation data "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_independent_cohort_claim_with_independent_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "independent_cohort_results": [{"cohort": "site_b", "mae_mean": 0.47}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to an independent cohort "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_external_generalization_claim_with_negated_external_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "non_external_validation_results": [{"source_label": "external_site", "mae_mean": 0.47}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to external validation data "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "external generalization claim requires" in issues[0].reason


def test_flags_external_generalization_claim_with_support_only_external_results(tmp_path: Path):
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
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to external validation data "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "external generalization claim requires" in issues[0].reason


def test_flags_external_generalization_claim_with_scalar_external_metric_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "external_validation_results": 0.47,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model generalizes to external validation data "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "external generalization claim requires" in issues[0].reason


def test_ignores_honest_missing_robustness_limitation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Robustness across seeds was not evaluated."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_sample_size_claim_with_matching_n_samples(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "n_samples": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used n=120 samples "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_metric_and_sample_size_claim_in_same_sentence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "n_samples": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model reaches MAE = 0.42 across 120 samples "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_sample_size_claim_with_wrong_n_samples(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "n_samples": 80,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used n=120 samples "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 120
    assert "sample-size claim count does not match" in issues[0].reason


def test_flags_sample_size_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"n_samples": 120}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used n=120 samples."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "sample-size claim does not cite" in issues[0].reason


def test_flags_sample_size_claim_with_negated_sample_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_n_samples": 120,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used n=120 samples "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires n_samples" in issues[0].reason


def test_accepts_repetition_count_claim_with_repeated_seed_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [
            {"seed": 1, "mae_mean": 0.43},
            {"seed": 2, "mae_mean": 0.41},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used 2 random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_repetition_count_claim_with_wrong_repeated_seed_count(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [
            {"seed": 1, "mae_mean": 0.43},
            {"seed": 2, "mae_mean": 0.41},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used 3 random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 3
    assert "repetition-count claim does not match" in issues[0].reason


def test_flags_repetition_count_claim_with_seed_id_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "repeated_seed_results": [{"seed": 1}, {"seed": 2}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The evaluation used 2 random seeds "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "repetition-count claim requires" in issues[0].reason


def test_accepts_trial_count_claim_with_declared_n_trials(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "best_mae": 0.42,
        "n_trials": 5,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Optimization ran 5 trials "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_repetition_count_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"n_trials": 5}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Optimization ran 5 trials."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "repetition-count claim does not cite" in issues[0].reason


def test_accepts_cross_validation_claim_with_matching_fold_count(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 5,
        "per_fold_metrics": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold": 1, "mae_mean": 0.41},
            {"fold": 2, "mae_mean": 0.42},
            {"fold": 3, "mae_mean": 0.40},
            {"fold": 4, "mae_mean": 0.44},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 5-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_cross_validation_claim_with_negated_protocol_keys_only(tmp_path: Path):
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
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 2-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires fold_count" in issues[0].reason


def test_flags_cross_validation_claim_with_wrong_fold_count(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 3,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 5-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 5
    assert "evaluation protocol claim count does not match" in issues[0].reason


def test_flags_cross_validation_claim_without_protocol_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 5,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 5-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires fold_count" in issues[0].reason


def test_flags_cross_validation_claim_with_fold_count_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "fold_count": 5,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 5-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "per-fold/split metric evidence" in issues[0].reason


def test_flags_cross_validation_claim_when_per_fold_count_conflicts(tmp_path: Path):
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
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 5-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "must be materialized" in issues[0].reason


def test_flags_cross_validation_claim_with_duplicate_fold_ids(tmp_path: Path):
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
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 2-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "per-fold/split metric evidence" in issues[0].reason


def test_flags_cross_validation_claim_with_duplicate_fold_alias_ids(tmp_path: Path):
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
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 2-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "per-fold/split metric evidence" in issues[0].reason


def test_flags_cross_validation_claim_with_duplicate_dict_keyed_fold_alias_ids(tmp_path: Path):
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
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 2-fold cross-validation "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "per-fold/split metric evidence" in issues[0].reason


def test_flags_cross_validation_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"fold_count": 5}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with 5-fold cross-validation."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "artifact path" in issues[0].reason


def test_accepts_heldout_split_claim_with_split_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated on a held-out test set "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_split_ratio_claim_with_matching_split_protocol(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "split_protocol": "80/20 holdout",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with an 80/20 holdout split "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_split_ratio_claim_with_wrong_split_protocol(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "split_protocol": "80/20 holdout",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with a 70/30 holdout split "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 30
    assert "split-ratio claim does not match" in issues[0].reason


def test_accepts_heldout_test_percent_claim_with_row_counts(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "split_id": "heldout_0",
        "train_rows": 800,
        "test_rows": 200,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model used a 20% held-out test set "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_split_ratio_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"split_protocol": "80/20 holdout"}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated with an 80/20 holdout split."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "split-ratio claim does not cite" in issues[0].reason


def test_flags_heldout_split_claim_with_negated_split_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "no_split_id": "heldout_0",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated on a held-out test set "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "split protocol claim requires" in issues[0].reason


def test_accepts_holdout_split_claim_with_holdout_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "holdout_results": {"mae_mean": 0.42},
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated on a holdout split "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_heldout_split_claim_without_split_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated on a held-out test set "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "split protocol claim requires" in issues[0].reason


def test_flags_heldout_split_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"split_id": "heldout_0"}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was evaluated on a held-out test set."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "split protocol claim does not cite" in issues[0].reason


def test_ignores_honest_missing_heldout_split_limitation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "A held-out test set was not available, which remains a limitation."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_feature_importance_claim_with_substantive_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance": 0.81}],
    }))
    (rdir / "phase_0_error.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "research" / "final_paper.md").write_text(
        "The feature importance analysis identified lag_1 as dominant "
        "(research/iter_1/results/phase_0.json), as visualized in "
        "research/iter_1/results/phase_0_error.png."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_feature_importance_claim_with_metadata_only_score(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance_method": 0.81}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The feature importance analysis identified lag_1 as dominant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive ablation" in issues[0].reason


def test_flags_feature_importance_claim_naming_missing_feature(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_2", "importance": 0.81}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The feature importance analysis identified `lag_1` as dominant "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "names evidence item(s) not present" in issues[0].reason
    assert "lag_1" in issues[0].reason


def test_flags_feature_importance_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance": 0.81}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The feature importance analysis identified lag_1 as dominant."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "ablation/feature-importance claim does not cite" in issues[0].reason


def test_flags_ablation_claim_with_marker_instead_of_substantive_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"feature_importance": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The ablation analysis supports the retained feature set "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive ablation" in issues[0].reason


def test_flags_ablation_claim_with_metadata_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance_method": [{"feature": "lag_1", "importance": 0.81}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The ablation analysis supports the retained feature set "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive ablation" in issues[0].reason


def test_ignores_honest_missing_ablation_limitation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No ablation was performed, which remains a limitation."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_ignores_evidence_family_section_metadata_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "feature_importance": [{"feature": "lag_1", "importance": 0.81}],
        "error_slices": [{"slice": "peak_load", "mae_mean": 0.55}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The method section describes ablation and error analysis procedures. "
        "It discusses feature importance and failure cases in detail."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_error_analysis_claim_with_confusion_matrix(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "confusion_matrix": [[18, 2], [3, 17]],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The error analysis is summarized by the confusion matrix "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_calibration_claim_with_expected_calibration_error(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "expected_calibration_error": 0.02,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was well calibrated with low ECE "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_calibration_claim_without_calibration_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model was well calibrated with low ECE "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive error-analysis evidence" in issues[0].reason


def test_accepts_fairness_claim_with_group_fairness_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "fairness_by_group": [
            {"protected_group": "A", "false_positive_rate": 0.08},
            {"protected_group": "B", "false_positive_rate": 0.11},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The fairness audit reports demographic parity across protected groups "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_fairness_claim_with_scalar_fairness_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "demographic_parity_difference": 0.03,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The fairness audit reports a demographic parity difference "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_fairness_claim_with_unlabeled_group_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "fairness_by_group": [
            {"false_positive_rate": 0.08},
            {"false_positive_rate": 0.11},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The fairness audit reports demographic parity across protected groups "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive fairness or bias-audit evidence" in issues[0].reason


def test_flags_fairness_claim_without_fairness_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"accuracy": 0.91}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is unbiased across protected groups "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive fairness or bias-audit evidence" in issues[0].reason


def test_accepts_efficiency_claim_with_latency_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "latency_ms": 12.4,
        "throughput": 128.0,
        "benchmark_device": "M2 Pro",
        "batch_size": 32,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is efficient at inference time with low latency "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_efficiency_claim_without_efficiency_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"accuracy": 0.91}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is efficient at inference time with low latency "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive efficiency or resource evidence" in issues[0].reason


def test_flags_latency_claim_without_benchmark_context(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"latency_ms": 12.4}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model is efficient at inference time with low latency "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive efficiency or resource evidence" in issues[0].reason


def test_accepts_error_analysis_claim_naming_present_slice(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "error_slices": [{"slice": "peak_load", "mae_mean": 0.55}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The error analysis identified `peak_load` as the largest residual slice "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_error_analysis_claim_naming_missing_slice(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "error_slices": [{"slice": "low_load", "mae_mean": 0.55}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The error analysis identified `peak_load` as the largest residual slice "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "names evidence item(s) not present" in issues[0].reason
    assert "peak_load" in issues[0].reason


def test_flags_error_analysis_claim_without_substantive_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The error analysis identified the largest residual slice "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires substantive error-analysis evidence" in issues[0].reason


def test_accepts_reproducibility_claim_with_complete_metadata_bundle(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment is reproducible "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_reproducibility_claim_without_code_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_sha256": "sha256:" + "1" * 64,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment is reproducible "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "valid code provenance" in issues[0].reason
    assert "script_path or code_path" in issues[0].reason


def test_flags_reproducibility_claim_with_mismatched_code_hash(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    rdir = tmp_path / "research" / "iter_1" / "results"
    pdir.mkdir(parents=True)
    rdir.mkdir()
    script = pdir / "phase_0.py"
    script.write_text("print('phase')\n")
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": "sha256:" + "1" * 64,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment is reproducible "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "valid code provenance" in issues[0].reason
    assert "does not match" in issues[0].reason


def test_flags_reproducibility_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_sha256": "sha256:" + "1" * 64,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment is reproducible."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "reproducibility claim does not cite" in issues[0].reason


def test_flags_reproducibility_claim_with_incomplete_metadata_bundle(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "unknown",
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment is reproducible "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "reproducibility claim requires seed" in issues[0].reason
    assert "data source/fingerprint" in issues[0].reason
    assert "split/protocol" in issues[0].reason
    assert "environment" in issues[0].reason
    assert "code provenance" in issues[0].reason


def test_flags_reproducibility_claim_with_metadata_suffix_bundle_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed_method": 7,
        "dataset_fingerprint_method": "sha256:" + "0" * 64,
        "split_id_method": "fold_0",
        "python_version_notes": "3.11",
        "script_sha256_method": "sha256:" + "1" * 64,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The experiment is reproducible "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "reproducibility claim requires seed" in issues[0].reason
    assert "data source/fingerprint" in issues[0].reason
    assert "split/protocol" in issues[0].reason
    assert "environment" in issues[0].reason
    assert "code provenance" in issues[0].reason


def test_ignores_honest_reproducibility_limitation(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The study is not fully reproducible because code provenance is incomplete."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_ignores_reproducibility_section_metadata_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_sha256": "sha256:" + "1" * 64,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The method section describes reproducibility metadata."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_percentage_improvement_from_improvement_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "relative_improvement": 0.1429,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model achieves a 14.29% improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_percentage_improvement_from_confidence_score_improvement_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_confidence_score": 0.92,
        "baseline_confidence_score": 0.81,
        "confidence_score_improvement": 0.1358,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model achieves a 13.58% improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_percentage_improvement_matching_only_improvement_p_value(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_p_value": 0.1429,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model achieves a 14.29% improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "improvement-like key/value" in issues[0].reason


def test_flags_percentage_improvement_matching_only_improvement_std(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "improvement_std": 0.1429,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model achieves a 14.29% improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "improvement-like key/value" in issues[0].reason


def test_flags_percentage_improvement_matching_wrong_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "baseline_mae": 0.49,
        "fold_count": 14.29,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model achieves a 14.29% improvement over the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 14.29
    assert "improvement-like key/value" in issues[0].reason


def test_flags_marker_only_baseline_superiority_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_baseline": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires same-metric baseline comparison" in issues[0].reason


def test_flags_baseline_superiority_claim_when_true_flag_contradicts_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "baseline_mae": 0.58,
        "beats_baseline": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_baseline_superiority_claim_when_positive_improvement_contradicts_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "baseline_mae": 0.58,
        "improvement_over_baseline": 0.04,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_non_numeric_baseline_superiority_with_false_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_baseline": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_non_numeric_baseline_superiority_without_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "baseline_results": [{"name": "linear regression", "mae_mean": 0.49}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model is better than the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires same-metric baseline comparison" in issues[0].reason


def test_flags_baseline_superiority_with_improvement_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"improvement_method": 0.12}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires" in issues[0].reason


def test_flags_baseline_superiority_with_nested_improvement_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "improvement_over_baseline_method": 0.12,
        "relative_improvement_method": 0.12,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires" in issues[0].reason


def test_flags_baseline_superiority_with_baseline_metric_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_mae_method": 0.42,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires same-metric baseline comparison" in issues[0].reason


def test_flags_baseline_superiority_with_negated_baseline_metric_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "no_baseline_mae": 0.49,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires same-metric baseline comparison" in issues[0].reason


def test_ignores_interrogative_baseline_superiority_heading(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "# Does the proposed model beat the baseline?\n\n"
        "The final MAE is 0.42 (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_baseline_superiority_with_non_ml_baseline_metric_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "non_ml_baseline_mae": 0.49,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_baseline_superiority_with_baseline_model_metric_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_mae": 0.31,
        "baseline_model_mae": 0.49,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_baseline_superiority_with_confidence_score_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_confidence_score": 0.92,
        "baseline_confidence_score": 0.81,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_named_baseline_claim_when_cited_artifact_names_baseline(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_results": [{"name": "linear regression", "mae_mean": 0.49}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_named_baseline_claim_with_model_metric_inside_item(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_results": [{"name": "linear regression", "model_mae": 0.49}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_baseline_claim_with_negated_baseline_results_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "no_baseline_results": [{"name": "linear regression", "mae_mean": 0.49}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline claim names baseline(s) not present" in issues[0].reason


def test_accepts_named_baseline_claim_with_non_ml_baseline_results_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "non_ml_baseline_results": [{"name": "seasonal naive", "mae_mean": 0.49}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `seasonal naive` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_baseline_claim_with_support_stat_only_baseline_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_results": [{"name": "linear regression", "mae_std": 0.03}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline superiority claim requires named baseline metric" in issues[0].reason


def test_accepts_named_baseline_claim_with_dict_keyed_baseline_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_results": {"linear regression": {"mae_mean": 0.49}},
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the linear regression baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_baseline_claim_when_cited_artifact_names_different_baseline(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "baseline_results": [{"name": "seasonal naive", "mae_mean": 0.49}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline claim names baseline(s) not present" in issues[0].reason
    assert "linear regression" in issues[0].reason


def test_accepts_named_baseline_claim_against_named_entry_not_best_baseline(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "baseline_results": [
            {"name": "linear regression", "accuracy": 0.88},
            {"name": "random forest", "accuracy": 0.95},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_baseline_claim_when_named_entry_not_beaten(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "baseline_results": [
            {"name": "linear regression", "accuracy": 0.95},
            {"name": "random forest", "accuracy": 0.88},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `linear regression` baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts named baseline comparison evidence" in issues[0].reason


def test_flags_marker_only_negated_baseline_superiority_with_false_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_baseline": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model does not outperform the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline non-superiority claim requires" in issues[0].reason


def test_flags_negated_baseline_superiority_when_true_flag_contradicts(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_baseline": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model does not outperform the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline non-superiority claim contradicts explicit result artifact flags" in issues[0].reason


def test_flags_negated_baseline_superiority_ignores_beats_baseline_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_baseline_method": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model does not outperform the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline non-superiority claim requires" in issues[0].reason


def test_flags_negated_baseline_superiority_when_false_flag_contradicts_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_mae": 0.31,
        "baseline_mae": 0.49,
        "beats_baseline": False,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model does not outperform the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline non-superiority claim contradicts explicit result artifact flags" in issues[0].reason


def test_accepts_negated_baseline_superiority_with_same_metric_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_mae": 0.62,
        "baseline_mae": 0.58,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model does not outperform the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_negated_baseline_superiority_without_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model does not outperform the baseline "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "baseline non-superiority claim requires" in issues[0].reason


def test_flags_sota_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_sota": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model achieves state-of-the-art performance."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work superiority claim does not cite" in issues[0].reason


def test_flags_sota_claim_without_prior_work_comparison_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.31,
        "beats_baseline": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model achieves state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires same-metric prior-work comparison evidence" in issues[0].reason


def test_flags_marker_only_sota_claim_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_sota": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model achieves state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires same-metric prior-work comparison evidence" in issues[0].reason


def test_accepts_sota_claim_with_model_and_prior_work_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_accuracy": 0.88,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_sota_claim_with_published_model_metric_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "published_model_accuracy": 0.88,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_sota_claim_with_confidence_score_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_confidence_score": 0.92,
        "prior_work_confidence_score": 0.81,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_named_sota_claim_when_cited_artifact_names_prior_work(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [{"name": "Smith et al. 2024", "accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_named_sota_claim_with_model_metric_inside_item(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [{"name": "Smith et al. 2024", "published_model_accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_sota_claim_with_negated_prior_work_results_key(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "no_prior_work_results": [{"name": "Smith et al. 2024", "accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work claim names comparison item(s) not present" in issues[0].reason


def test_flags_named_sota_claim_with_support_stat_only_prior_work_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [{"name": "Smith et al. 2024", "accuracy_std": 0.02}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work superiority claim requires named comparison metric" in issues[0].reason


def test_flags_named_sota_claim_with_placeholder_prior_work_name(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [{"name": "unknown", "accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work claim names comparison item(s) not present" in issues[0].reason


def test_accepts_named_sota_claim_with_dict_keyed_leaderboard_results(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "leaderboard_results": {"Smith et al. 2024": {"accuracy": 0.88}},
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms Smith et al. 2024 prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_sota_claim_when_cited_artifact_names_different_prior_work(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [{"name": "Jones et al. 2023", "accuracy": 0.88}],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work claim names comparison item(s) not present" in issues[0].reason
    assert "Smith et al. 2024" in issues[0].reason


def test_flags_named_sota_claim_with_only_generic_sota_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_sota": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work claim names comparison item(s) not present" in issues[0].reason


def test_accepts_named_sota_claim_against_named_entry_not_best_prior_work(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [
            {"name": "Smith et al. 2024", "accuracy": 0.88},
            {"name": "Jones et al. 2023", "accuracy": 0.95},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_named_sota_claim_when_named_prior_work_entry_not_beaten(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_results": [
            {"name": "Smith et al. 2024", "accuracy": 0.95},
            {"name": "Jones et al. 2023", "accuracy": 0.88},
        ],
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model outperforms the `Smith et al. 2024` prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work superiority claim contradicts named comparison evidence" in issues[0].reason


def test_flags_sota_claim_when_true_flag_contradicts_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.62,
        "sota_mae": 0.58,
        "beats_sota": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The proposed model achieves state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_marker_only_negated_sota_claim_with_false_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_sota": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model does not achieve state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work non-superiority claim requires" in issues[0].reason


def test_flags_negated_sota_claim_when_true_flag_contradicts(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_sota": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model does not achieve state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work non-superiority claim contradicts explicit result artifact flags" in issues[0].reason


def test_flags_negated_sota_claim_ignores_beats_sota_metadata(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"beats_sota_method": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model does not achieve state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work non-superiority claim requires" in issues[0].reason


def test_flags_negated_sota_claim_when_false_flag_contradicts_metrics(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.92,
        "prior_work_accuracy": 0.88,
        "beats_sota": False,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model does not achieve state-of-the-art performance "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work non-superiority claim contradicts explicit result artifact flags" in issues[0].reason


def test_accepts_negated_sota_claim_with_same_metric_prior_work_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "model_accuracy": 0.86,
        "prior_work_accuracy": 0.88,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model does not outperform prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_negated_sota_claim_without_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"accuracy": 0.86}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model does not outperform prior work "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "SOTA/prior-work non-superiority claim requires" in issues[0].reason


def test_accepts_target_achievement_claim_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_achieved": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_target_achievement_claim_with_false_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_achieved": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_target_achievement_claim_without_flag_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final goal was met "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires target_achieved" in issues[0].reason


def test_flags_target_achievement_claim_with_target_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "target_method": True,
        "target_metric": True,
        "goal_metric": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires target_achieved" in issues[0].reason


def test_flags_target_achievement_claim_with_negated_target_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "not_target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires target_achieved" in issues[0].reason


def test_flags_numeric_target_achievement_claim_without_flag_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "requires target_achieved" in issues[0].reason


def test_accepts_numeric_target_achievement_claim_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_target_achievement_claim_when_true_flag_matches_plan_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_target_achievement_claim_with_support_stat_only_plan_metric(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_std": 0.03,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires the plan target metric value" in issues[0].reason


def test_flags_target_achievement_claim_with_negated_plan_metric_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "no_mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires the plan target metric value" in issues[0].reason


def test_accepts_target_threshold_number_from_plan_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The target was MAE <= 0.5 and was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_target_threshold_number_that_contradicts_plan_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The target was MAE <= 0.4 and was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value == 0.4
    assert "plan target" in issues[0].reason


def test_flags_target_achievement_claim_when_plan_target_metric_is_missing(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "requires the plan target metric value" in issues[0].reason


def test_flags_target_achievement_claim_when_true_flag_contradicts_plan_target(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_target_achievement_claim_when_string_plan_target_is_missed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": "0.4"},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_numeric_target_achievement_claim_with_false_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "target_achieved": False,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The final target was achieved with MAE = 0.42 "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert issues[0].value is None
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_target_achievement_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"success_criteria_met": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The success criteria were met."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "artifact path" in issues[0].reason


def test_ignores_negated_target_achievement_sentence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_achieved": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not achieve the target "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_negated_target_achievement_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_achieved": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not achieve the target "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "target non-achievement claim contradicts explicit result artifact flags" in issues[0].reason


def test_accepts_negated_target_achievement_when_plan_target_is_missed(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps({
        "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not achieve the target "
        "(research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_negated_target_achievement_without_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The model did not achieve the target "
        "(research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "target non-achievement claim requires" in issues[0].reason


def test_flags_no_leakage_claim_with_generic_false_flag_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"leakage_found": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "scope evidence" in issues[0].reason


def test_accepts_no_leakage_claim_with_false_flag_and_audit_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": False,
        "train_test_overlap": 0,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_no_group_leakage_claim_without_group_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No group leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage absence claim requires" in issues[0].reason


def test_accepts_no_group_leakage_claim_with_group_overlap_scope(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": False,
        "group_overlap": 0,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No group leakage was detected (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_no_leakage_claim_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"leakage_found": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_no_leakage_claim_without_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage absence claim requires" in issues[0].reason


def test_flags_no_leakage_claim_with_target_leakage_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"target_leakage_metric": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage absence claim requires" in issues[0].reason


def test_flags_no_leakage_claim_with_negated_leakage_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"no_target_leakage": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage absence claim requires" in issues[0].reason


def test_flags_no_leakage_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"leakage_detected": False}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "No leakage was detected."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "artifact path" in issues[0].reason


def test_accepts_leakage_presence_claim_with_true_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"leakage_found": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Leakage was detected (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_leakage_presence_claim_with_negated_leakage_key_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"no_target_leakage": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage presence claim requires" in issues[0].reason


def test_accepts_overlap_presence_claim_with_positive_overlap(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"train_test_overlap": 3}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Train/test overlap was detected (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_group_overlap_presence_claim_with_positive_overlap(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"group_overlap": 3}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Group overlap was detected (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_leakage_presence_claim_with_false_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": False,
        "train_test_overlap": 0,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_leakage_presence_claim_without_evidence(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Leakage was detected (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage presence claim requires" in issues[0].reason


def test_flags_leakage_presence_claim_without_artifact_path(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"leakage_detected": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "Leakage was detected."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "artifact path" in issues[0].reason


def test_accepts_leakage_resolution_claim_with_resolution_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": True,
        "leakage_resolved": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The leakage issue was resolved (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_accepts_leakage_resolution_claim_with_no_leakage_after_fix_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": True,
        "no_leakage_after_fix": True,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The leakage issue was resolved (research/iter_1/results/phase_0.json)."
    )

    assert verify_paper_numeric_claims(tmp_path) == []


def test_flags_leakage_resolution_claim_with_false_resolution_flag(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({
        "leakage_found": True,
        "leakage_resolved": False,
    }))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The leakage issue was resolved (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "contradicts explicit result artifact flags" in issues[0].reason


def test_flags_leakage_resolution_claim_with_resolution_metadata_only(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"leakage_resolved_method": True}))
    (tmp_path / "research" / "final_paper.md").write_text(
        "The leakage issue was resolved (research/iter_1/results/phase_0.json)."
    )

    issues = verify_paper_numeric_claims(tmp_path)

    assert len(issues) == 1
    assert "leakage resolution claim requires" in issues[0].reason
