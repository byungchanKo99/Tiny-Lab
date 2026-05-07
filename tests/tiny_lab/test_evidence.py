"""Tests for shared evidence key predicates."""
from __future__ import annotations

from tiny_lab.evidence import (
    baseline_names_match,
    contains_metric_support_numeric_token,
    has_efficiency_benchmark_context,
    has_efficiency_evidence,
    has_evidence_token_value,
    has_fairness_evidence,
    has_measurement_evidence_token_value,
    has_sample_or_repetition_support_evidence,
    has_significance_support_evidence,
    has_statistical_significance_evidence,
    has_substantive_leakage_audit_evidence,
    has_uncertainty_evidence,
    is_comparison_interval_significance_evidence_key,
    is_causal_evidence_key,
    is_efficiency_benchmark_context_key,
    is_efficiency_evidence_key,
    is_evaluation_protocol_evidence_key,
    is_fairness_evidence_key,
    is_leakage_audit_evidence_key,
    is_metric_evidence_key,
    is_metric_support_numeric_key,
    is_statistical_significance_evidence_key,
    is_uncertainty_evidence_key,
    reproducibility_bundle_missing_groups,
    sota_comparison_entries,
)


def test_causal_evidence_key_rejects_negated_and_metadata_fields():
    assert is_causal_evidence_key("causal_identification")
    assert is_causal_evidence_key("estimated_causal_effect")
    assert not is_causal_evidence_key("no_causal_identification")
    assert not is_causal_evidence_key("without_causal_effect")
    assert not is_causal_evidence_key("causal_identification_method")


def test_metric_evidence_key_rejects_negated_and_metadata_fields():
    assert is_metric_evidence_key("mae_mean", "mae")
    assert is_metric_evidence_key("mean_absolute_error_mean", "mae")
    assert not is_metric_evidence_key("no_mae_mean", "mae")
    assert not is_metric_evidence_key("mae_method", "mae")


def test_baseline_names_match_camelcase_model_labels():
    assert baseline_names_match("Random Forest", "RandomForest")
    assert baseline_names_match("Gradient Boosting", "GradientBoosting")


def test_sota_entries_use_prior_work_label_key():
    entries = sota_comparison_entries({
        "prior_work_results": [
            {"prior_work": "iter_1_Ridge", "RMSE": 10.0},
        ]
    }, "rmse")

    assert entries == [("iter_1_Ridge", True)]


def test_evaluation_protocol_evidence_key_rejects_negated_and_metadata_fields():
    assert is_evaluation_protocol_evidence_key("cv_results")
    assert is_evaluation_protocol_evidence_key("per_fold_metrics")
    assert is_evaluation_protocol_evidence_key("fold_count")
    assert not is_evaluation_protocol_evidence_key("no_cv_results")
    assert not is_evaluation_protocol_evidence_key("without_fold_count")
    assert not is_evaluation_protocol_evidence_key("cv_results_method")


def test_leakage_audit_evidence_key_rejects_negated_and_metadata_fields():
    assert is_leakage_audit_evidence_key("leakage_audit")
    assert is_leakage_audit_evidence_key("split_audit")
    assert is_leakage_audit_evidence_key("group_leakage")
    assert is_leakage_audit_evidence_key("row_id_leakage")
    assert not is_leakage_audit_evidence_key("no_leakage_audit")
    assert not is_leakage_audit_evidence_key("without_group_leakage")
    assert not is_leakage_audit_evidence_key("leakage_audit_method")


def test_substantive_leakage_audit_requires_scoped_non_placeholder_result():
    assert has_substantive_leakage_audit_evidence({
        "leakage_found": False,
        "train_test_overlap": 0,
    })
    assert has_substantive_leakage_audit_evidence({
        "leakage_found": "no leakage",
        "group_leakage": "not detected",
    })
    assert not has_substantive_leakage_audit_evidence({
        "leakage_found": False,
    })
    assert not has_substantive_leakage_audit_evidence({
        "leakage_found": False,
        "train_test_overlap": "not measured",
    })
    assert not has_substantive_leakage_audit_evidence({
        "leakage_found": "not checked",
        "split_audit": "completed",
    })
    assert not has_substantive_leakage_audit_evidence({
        "leakage_resolved": False,
        "split_audit": "completed",
    })
    assert has_substantive_leakage_audit_evidence({
        "leakage_resolved": True,
        "split_audit": "completed",
    })


def test_reproducibility_bundle_rejects_placeholder_group_values():
    data = {
        "random_seed": 7,
        "dataset_fingerprint": "not collected",
        "split_id": "not measured",
        "python_version": "not reported",
        "script_sha256": "sha256:" + "0" * 64,
    }

    missing = reproducibility_bundle_missing_groups(data)

    assert "data source/fingerprint" in missing
    assert "split/protocol" in missing
    assert "environment" in missing
    assert "seed" not in missing
    assert "code provenance" not in missing


def test_uncertainty_evidence_key_rejects_support_only_negated_and_metadata_fields():
    assert is_uncertainty_evidence_key("mae_std")
    assert is_uncertainty_evidence_key("mae_stdev")
    assert is_uncertainty_evidence_key("mae_standard_error")
    assert is_uncertainty_evidence_key("mae_ci95")
    assert is_uncertainty_evidence_key("mae_confidence_interval")
    assert not is_uncertainty_evidence_key("p_value")
    assert not is_uncertainty_evidence_key("n_samples")
    assert not is_uncertainty_evidence_key("model_confidence_score")
    assert not is_uncertainty_evidence_key("no_ci95")
    assert not is_uncertainty_evidence_key("without_standard_error")
    assert not is_uncertainty_evidence_key("mae_std_method")


def test_uncertainty_evidence_requires_numeric_uncertainty_not_support_counts():
    assert has_uncertainty_evidence({"mae_std": 0.03})
    assert has_uncertainty_evidence({"mae_ci95": [0.39, 0.45]})
    assert has_uncertainty_evidence({"confidence_interval": {"lower": 0.39, "upper": 0.45}})
    assert not has_uncertainty_evidence({"n_samples": 100, "fold_count": 5})
    assert not has_uncertainty_evidence({"p_value": 0.03})
    assert not has_uncertainty_evidence({"no_mae_std": 0.03})
    assert not has_uncertainty_evidence({"mae_std_method": "bootstrap"})


def test_statistical_significance_evidence_requires_numeric_p_value():
    assert is_statistical_significance_evidence_key("p_value")
    assert is_statistical_significance_evidence_key("mae_p_value")
    assert not is_statistical_significance_evidence_key("no_p_value")
    assert not is_statistical_significance_evidence_key("p_value_method")
    assert has_statistical_significance_evidence({"p_value": 0.03})
    assert has_statistical_significance_evidence({"comparison": {"mae_p_value": 0.03}})
    assert has_statistical_significance_evidence({"improvement_ci95": [0.02, 0.12]})
    assert has_statistical_significance_evidence({"difference_confidence_interval": {"lower": 0.02, "upper": 0.12}})
    assert not has_statistical_significance_evidence({"p_value": "not measured"})
    assert not has_statistical_significance_evidence({"p_value_method": "paired t-test"})
    assert not has_statistical_significance_evidence({"no_p_value": 0.03})
    assert not has_statistical_significance_evidence({"mae_ci95": [0.39, 0.45]})
    assert not has_statistical_significance_evidence({"difference_ci95_method": [0.02, 0.12]})
    assert not has_statistical_significance_evidence({"no_improvement_ci95": [0.02, 0.12]})
    assert not has_statistical_significance_evidence({"improvement_ci95": [0.02]})
    assert not has_statistical_significance_evidence({"improvement_ci95": [0.12, 0.02]})
    assert not has_statistical_significance_evidence({"difference_confidence_interval": {"lower": 0.12, "upper": 0.02}})


def test_evidence_contract_documents_alpha_threshold_range():
    from tiny_lab.evidence import render_evidence_contract

    text = render_evidence_contract()

    assert "`alpha` or `significance_level`" in text
    assert "`0 < value < 1`" in text


def test_comparison_interval_significance_key_rejects_metric_and_metadata_intervals():
    assert is_comparison_interval_significance_evidence_key("improvement_ci95")
    assert is_comparison_interval_significance_evidence_key("difference_confidence_interval")
    assert not is_comparison_interval_significance_evidence_key("mae_ci95")
    assert not is_comparison_interval_significance_evidence_key("no_improvement_ci95")
    assert not is_comparison_interval_significance_evidence_key("improvement_ci95_method")


def test_sample_or_repetition_support_evidence_aliases_legacy_significance_support():
    assert has_sample_or_repetition_support_evidence({"n_samples": 120})
    assert has_sample_or_repetition_support_evidence({"fold_count": 5})
    assert has_sample_or_repetition_support_evidence({"n_trials": 3})
    assert not has_sample_or_repetition_support_evidence({"no_n_samples": 120})
    assert not has_sample_or_repetition_support_evidence({"n_samples": 0})
    assert has_significance_support_evidence({"fold_count": 5})


def test_metric_support_numeric_key_uses_token_boundaries():
    assert is_metric_support_numeric_key("mae_std")
    assert is_metric_support_numeric_key("mae_p_value_fold_1")
    assert is_metric_support_numeric_key("mae_confidence_interval.lower")
    assert not is_metric_support_numeric_key("precision")
    assert not is_metric_support_numeric_key("model_confidence_score")
    assert not is_metric_support_numeric_key("mae_std_method")
    assert not is_metric_support_numeric_key("no_mae_std")


def test_metric_support_numeric_token_filter_keeps_metric_names_intact():
    assert contains_metric_support_numeric_token("no_mae_std")
    assert contains_metric_support_numeric_token("mae_std_method")
    assert contains_metric_support_numeric_token("improvement_no_p_value")
    assert contains_metric_support_numeric_token("improvement_confidence_interval")
    assert not contains_metric_support_numeric_token("precision_improvement")
    assert not contains_metric_support_numeric_token("confidence_score_improvement")


def test_evidence_token_value_rejects_negated_family_key():
    assert has_evidence_token_value(
        {"robustness_results": {"scenario": "stress", "mae_mean": 0.42}},
        ("robustness_results",),
    )
    assert not has_evidence_token_value(
        {"no_robustness_results": {"scenario": "stress", "mae_mean": 0.42}},
        ("robustness_results",),
    )
    assert not has_evidence_token_value(
        {"robustness_results_method": {"scenario": "stress", "mae_mean": 0.42}},
        ("robustness_results",),
    )


def test_baseline_names_match_accepts_token_subset_in_different_order():
    assert baseline_names_match("non-ML heuristic naive median DummyRegressor", "DummyRegressor_median")


def test_fairness_evidence_accepts_labeled_and_scalar_metrics():
    assert has_fairness_evidence({
        "fairness_by_group": [
            {"protected_group": "A", "false_positive_rate": 0.08},
            {"protected_group": "B", "false_positive_rate": 0.11},
        ]
    })
    assert has_fairness_evidence({"demographic_parity_difference": 0.03})
    assert has_fairness_evidence({"fairness_metrics": {"demographic_parity_difference": 0.03}})
    assert is_fairness_evidence_key("equalized_odds_difference")
    assert not has_fairness_evidence({
        "fairness_by_group": [
            {"false_positive_rate": 0.08},
            {"false_positive_rate": 0.11},
        ]
    })
    assert not has_fairness_evidence({"fairness_by_group_method": "not computed"})
    assert not is_fairness_evidence_key("no_demographic_parity")


def test_efficiency_evidence_accepts_numeric_resource_metrics():
    assert has_efficiency_evidence({"latency_ms": 12.4, "benchmark_device": "M2 Pro"})
    assert has_efficiency_evidence({"throughput": 128.0, "batch_size": 32})
    assert has_efficiency_evidence({"model_profile": {"peak_memory_mb": 512}, "gpu_name": "A100"})
    assert has_efficiency_evidence({"parameter_count": 125000})
    assert is_efficiency_evidence_key("gpu_hours")
    assert is_efficiency_benchmark_context_key("benchmark_repeats")
    assert has_efficiency_benchmark_context({"benchmark_repeats": 5})
    assert not has_efficiency_evidence({"latency_ms": 12.4})
    assert not has_efficiency_evidence({"latency_ms_method": "benchmarked locally"})
    assert not is_efficiency_evidence_key("no_latency_ms")
    assert not is_efficiency_benchmark_context_key("no_benchmark_device")


def test_measurement_evidence_token_value_rejects_negated_family_key():
    assert has_measurement_evidence_token_value(
        {"robustness_results": {"mae_mean": 0.42}},
        ("robustness_results",),
    )
    assert not has_measurement_evidence_token_value(
        {"no_robustness_results": {"mae_mean": 0.42}},
        ("robustness_results",),
    )
    assert not has_measurement_evidence_token_value(
        {"robustness_results_method": {"mae_mean": 0.42}},
        ("robustness_results",),
    )
