"""Shared evidence-key contracts for research artifacts."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable


STATISTICS_EVIDENCE_TOKENS = (
    "std",
    "stdev",
    "standard_deviation",
    "stderr",
    "standard_error",
    "sem",
    "se",
    "variance",
    "ci95",
    "ci",
    "confidence",
    "min",
    "max",
    "n",
    "n_samples",
    "n_trials",
    "n_splits",
    "n_folds",
    "sample_count",
    "split_count",
    "trial_count",
    "samples",
    "fold",
    "fold_count",
    "num_samples",
    "num_trials",
    "num_splits",
    "num_folds",
    "p_value",
    "pvalue",
)


UNCERTAINTY_EVIDENCE_TOKENS = (
    "std",
    "stdev",
    "standard_deviation",
    "stderr",
    "standard_error",
    "sem",
    "se",
    "variance",
    "ci95",
    "ci",
    "confidence_interval",
)


STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS = (
    "p_value",
    "pvalue",
)
COMPARISON_INTERVAL_SIGNIFICANCE_TOKENS = (
    "improvement",
    "delta",
    "difference",
    "diff",
    "effect",
    "gain",
    "reduction",
    "increase",
    "decrease",
)


REPRODUCIBILITY_SEED_TOKENS = ("seed", "random_state", "rng")


REPRODUCIBILITY_DATA_SOURCE_TOKENS = (
    "dataset",
    "data_source",
    "fingerprint",
    "hash",
    "checksum",
)


REPRODUCIBILITY_SPLIT_TOKENS = (
    "split_id",
    "split_protocol",
    "split_scheme",
    "train_test_split",
    "holdout_split",
    "heldout_split",
    "cv_split",
    "fold_assignment",
    "fold_id",
)


REPRODUCIBILITY_DATA_TOKENS = (
    *REPRODUCIBILITY_DATA_SOURCE_TOKENS,
    *REPRODUCIBILITY_SPLIT_TOKENS,
)


REPRODUCIBILITY_ENV_TOKENS = (
    "environment",
    "python_version",
    "package",
    "dependencies",
    "platform",
)


REPRODUCIBILITY_CODE_PATH_TOKENS = (
    "script_path",
    "code_path",
)


REPRODUCIBILITY_CODE_HASH_TOKENS = (
    "script_sha",
    "script_hash",
    "code_sha",
    "code_hash",
    "source_hash",
)


REPRODUCIBILITY_CODE_COMMIT_TOKENS = (
    "git_commit",
    "commit_hash",
)


REPRODUCIBILITY_CODE_TOKENS = (
    *REPRODUCIBILITY_CODE_PATH_TOKENS,
    *REPRODUCIBILITY_CODE_HASH_TOKENS,
    *REPRODUCIBILITY_CODE_COMMIT_TOKENS,
)


BASELINE_COMPARISON_EVIDENCE_TOKENS = (
    "baseline_results",
    "baseline_metrics",
    "baseline_scores",
    "baseline_mae",
    "baseline_rmse",
    "baseline_accuracy",
    "baseline_score",
    "comparison_table",
    "model_comparison",
    "method_comparison",
    "method_results",
    "leaderboard",
    "improvement_over_baseline",
    "delta_vs_baseline",
    "relative_improvement",
    "beats_baseline",
    "outperforms_baseline",
)


SOTA_COMPARISON_EVIDENCE_TOKENS = (
    "prior_work_results",
    "previous_work_results",
    "sota_results",
    "state_of_the_art_results",
    "published_results",
    "literature_results",
    "leaderboard_results",
    "reference_results",
    "leaderboard",
    "prior_work_accuracy",
    "previous_work_accuracy",
    "sota_accuracy",
    "prior_work_mae",
    "previous_work_mae",
    "sota_mae",
    "prior_work_rmse",
    "previous_work_rmse",
    "sota_rmse",
    "beats_sota",
    "outperforms_sota",
    "beats_prior_work",
    "outperforms_prior_work",
)


BASELINE_COMPARISON_COLLECTION_TOKENS = (
    "baseline_results",
    "baseline_metrics",
    "baseline_scores",
)


SOTA_COMPARISON_COLLECTION_TOKENS = (
    "prior_work_results",
    "previous_work_results",
    "sota_results",
    "state_of_the_art_results",
    "published_results",
    "literature_results",
    "leaderboard_results",
    "reference_results",
    "leaderboard",
)


CAUSAL_EVIDENCE_TOKENS = (
    "causal_design",
    "causal_identification",
    "causal_effect",
    "causal_impact",
    "randomized_assignment",
    "randomized_control",
    "randomized_trial",
    "treatment_assignment",
    "control_group",
    "intervention",
    "counterfactual",
    "instrumental_variable",
    "difference_in_differences",
    "regression_discontinuity",
    "propensity_score",
    "matched_control",
)


ROBUSTNESS_EVIDENCE_TOKENS = (
    "robustness_checks",
    "robustness_results",
    "robustness_metrics",
    "stability_metrics",
    "seed_sensitivity",
    "seed_results",
    "repeated_seed_results",
    "stress_test_results",
    "perturbation_results",
    "sensitivity_results",
)


GENERALIZATION_EVIDENCE_TOKENS = (
    "external_validation_results",
    "external_test_results",
    "external_dataset_results",
    "independent_validation_results",
    "independent_cohort_results",
    "out_of_distribution_results",
    "ood_results",
    "cross_dataset_results",
    "heldout_results",
    "holdout_results",
)

EXTERNAL_GENERALIZATION_EVIDENCE_TOKENS = (
    "external_validation_results",
    "external_test_results",
    "external_dataset_results",
    "independent_validation_results",
    "independent_cohort_results",
    "out_of_distribution_results",
    "ood_results",
    "cross_dataset_results",
)


ABLATION_EVIDENCE_TOKENS = (
    "ablation_results",
    "ablation_study",
    "component_ablation",
    "feature_ablation",
    "leave_one_feature_out",
    "feature_importance",
    "feature_importances",
    "permutation_importance",
    "sensitivity_analysis",
    "sensitivity_results",
    "component_contribution",
    "shap_values",
    "shap_importance",
)


EVALUATION_PROTOCOL_EVIDENCE_TOKENS = (
    "fold_count",
    "cv_fold_count",
    "cv_folds",
    "n_folds",
    "n_splits",
    "split_count",
    "num_folds",
    "num_splits",
    "cross_validation_results",
    "cv_results",
    "per_fold_metrics",
    "fold_metrics",
    "split_results",
    "repeated_split_results",
    "multiple_split_results",
    "evaluation_splits",
    "validation_scheme",
    "holdout_results",
    "heldout_results",
)


CALIBRATION_ERROR_EVIDENCE_TOKENS = (
    "calibration_error",
    "calibration_errors",
    "calibration_metric",
    "calibration_metrics",
    "expected_calibration_error",
    "ece",
    "brier_score",
)
ERROR_ANALYSIS_EVIDENCE_TOKENS = (
    "error_analysis",
    "error_slices",
    "slice_metrics",
    "subgroup_metrics",
    "residual_analysis",
    "residual_summary",
    "failure_cases",
    "worst_case_errors",
    "misclassification_examples",
    "confusion_matrix",
    *CALIBRATION_ERROR_EVIDENCE_TOKENS,
)


FAIRNESS_EVIDENCE_TOKENS = (
    "fairness_metrics",
    "fairness_by_group",
    "subgroup_fairness",
    "group_fairness",
    "protected_group_metrics",
    "protected_attribute_metrics",
    "bias_audit",
    "bias_metrics",
    "demographic_parity",
    "demographic_parity_difference",
    "equalized_odds",
    "equalized_odds_difference",
    "equal_opportunity",
    "equal_opportunity_difference",
    "disparate_impact",
    "disparate_impact_ratio",
    "max_group_gap",
    "subgroup_performance_gap",
)


FAIRNESS_SCALAR_EVIDENCE_TOKENS = (
    "demographic_parity",
    "demographic_parity_difference",
    "equalized_odds",
    "equalized_odds_difference",
    "equal_opportunity",
    "equal_opportunity_difference",
    "disparate_impact",
    "disparate_impact_ratio",
    "max_group_gap",
    "subgroup_performance_gap",
)


EFFICIENCY_EVIDENCE_TOKENS = (
    "latency_ms",
    "inference_latency",
    "inference_time_ms",
    "runtime_seconds",
    "wall_clock_seconds",
    "training_time_seconds",
    "throughput",
    "samples_per_second",
    "memory_mb",
    "peak_memory_mb",
    "model_size_mb",
    "parameter_count",
    "n_parameters",
    "flops",
    "macs",
    "compute_cost",
    "gpu_hours",
    "cpu_seconds",
    "energy_kwh",
)

EFFICIENCY_PROFILE_EVIDENCE_TOKENS = (
    "latency_ms",
    "inference_latency",
    "inference_time_ms",
    "runtime_seconds",
    "wall_clock_seconds",
    "training_time_seconds",
    "throughput",
    "samples_per_second",
    "memory_mb",
    "peak_memory_mb",
    "compute_cost",
    "gpu_hours",
    "cpu_seconds",
    "energy_kwh",
)

EFFICIENCY_STATIC_EVIDENCE_TOKENS = (
    "model_size_mb",
    "parameter_count",
    "n_parameters",
    "flops",
    "macs",
)

EFFICIENCY_BENCHMARK_CONTEXT_TOKENS = (
    "benchmark_device",
    "benchmark_hardware",
    "hardware",
    "hardware_name",
    "device",
    "device_name",
    "accelerator",
    "gpu_name",
    "cpu_model",
    "batch_size",
    "batch_sizes",
    "input_shape",
    "precision",
    "dtype",
    "num_threads",
    "warmup_runs",
    "benchmark_repeats",
    "profile_repeats",
    "measurement_runs",
    "repeat_count",
    "sample_count",
)


LEAKAGE_INDICATOR_EVIDENCE_TOKENS = (
    "leakage_found",
    "leakage_detected",
    "target_leakage",
    "temporal_leakage",
    "preprocessing_leakage",
    "group_leakage",
    "row_id_leakage",
    "train_test_overlap",
    "duplicate_overlap",
    "group_overlap",
)
LEAKAGE_RESOLUTION_EVIDENCE_TOKENS = (
    "leakage_resolved",
    "leakage_mitigated",
    "leakage_fixed",
    "no_leakage_after_fix",
)
LEAKAGE_AUDIT_EVIDENCE_TOKENS = (
    "leakage",
    "data_leak",
    *LEAKAGE_INDICATOR_EVIDENCE_TOKENS,
    "split_audit",
    *LEAKAGE_RESOLUTION_EVIDENCE_TOKENS,
)
SPECIFIC_LEAKAGE_AUDIT_TOKENS = (
    "target_leakage",
    "temporal_leakage",
    "preprocessing_leakage",
    "group_leakage",
    "row_id_leakage",
    "train_test_overlap",
    "duplicate_overlap",
    "group_overlap",
    "split_audit",
)


GOAL_ACHIEVEMENT_EVIDENCE_TOKENS = (
    "target_achieved",
    "target_met",
    "goal_achieved",
    "goal_met",
    "success_criteria_met",
)


EVIDENCE_CONTRACT_MARKDOWN = """### Experimental Evidence Contract

These field-name families are generated from `tiny_lab.evidence`; update that module instead of copying token lists into prompts.

1. Statistics: {statistics}. Uncertainty evidence is limited to {uncertainty}; significance evidence is limited to {significance} or comparison confidence intervals using prefixes such as {comparison_interval_significance}. If a result declares a significance threshold, use `alpha` or `significance_level` with a finite numeric value satisfying `0 < value < 1`. Support counts such as `n_samples` or `fold_count` do not by themselves establish uncertainty or significance.
2. Reproducibility seed metadata: {repro_seed}
3. Reproducibility data source metadata: {repro_data}
4. Reproducibility split metadata: {repro_split}
5. Reproducibility environment metadata: {repro_env}
6. Code provenance: {repro_code}
7. Baseline comparison evidence: {baseline}
8. SOTA or prior-work comparison evidence: {sota_comparison}
9. Causal-effect evidence: {causal}
10. Robustness evidence: {robustness}
11. Generalization evidence: {generalization}
12. Ablation, feature-importance, or sensitivity evidence: {ablation}
13. Cross-validation or multiple-split evidence: {evaluation_protocol}
14. Error-analysis evidence: {error_analysis}
15. Fairness or bias-audit evidence: {fairness}
16. Efficiency or resource evidence: {efficiency}. Benchmark-style efficiency metrics such as latency, throughput, runtime, memory, compute cost, GPU hours, CPU seconds, or energy must be paired with context fields such as {efficiency_context}.
17. Leakage audit evidence: {leakage}
18. Goal-achievement evidence: {goal_achievement}
""".format(
    statistics=", ".join(f"`{token}`" for token in STATISTICS_EVIDENCE_TOKENS),
    uncertainty=", ".join(f"`{token}`" for token in UNCERTAINTY_EVIDENCE_TOKENS),
    significance=", ".join(f"`{token}`" for token in STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS),
    comparison_interval_significance=", ".join(f"`{token}`" for token in COMPARISON_INTERVAL_SIGNIFICANCE_TOKENS),
    repro_seed=", ".join(f"`{token}`" for token in REPRODUCIBILITY_SEED_TOKENS),
    repro_data=", ".join(f"`{token}`" for token in REPRODUCIBILITY_DATA_SOURCE_TOKENS),
    repro_split=", ".join(f"`{token}`" for token in REPRODUCIBILITY_SPLIT_TOKENS),
    repro_env=", ".join(f"`{token}`" for token in REPRODUCIBILITY_ENV_TOKENS),
    repro_code=", ".join(f"`{token}`" for token in REPRODUCIBILITY_CODE_TOKENS),
    baseline=", ".join(f"`{token}`" for token in BASELINE_COMPARISON_EVIDENCE_TOKENS),
    sota_comparison=", ".join(f"`{token}`" for token in SOTA_COMPARISON_EVIDENCE_TOKENS),
    causal=", ".join(f"`{token}`" for token in CAUSAL_EVIDENCE_TOKENS),
    robustness=", ".join(f"`{token}`" for token in ROBUSTNESS_EVIDENCE_TOKENS),
    generalization=", ".join(f"`{token}`" for token in GENERALIZATION_EVIDENCE_TOKENS),
    ablation=", ".join(f"`{token}`" for token in ABLATION_EVIDENCE_TOKENS),
    evaluation_protocol=", ".join(f"`{token}`" for token in EVALUATION_PROTOCOL_EVIDENCE_TOKENS),
    error_analysis=", ".join(f"`{token}`" for token in ERROR_ANALYSIS_EVIDENCE_TOKENS),
    fairness=", ".join(f"`{token}`" for token in FAIRNESS_EVIDENCE_TOKENS),
    efficiency=", ".join(f"`{token}`" for token in EFFICIENCY_EVIDENCE_TOKENS),
    efficiency_context=", ".join(f"`{token}`" for token in EFFICIENCY_BENCHMARK_CONTEXT_TOKENS),
    leakage=", ".join(f"`{token}`" for token in LEAKAGE_AUDIT_EVIDENCE_TOKENS),
    goal_achievement=", ".join(f"`{token}`" for token in GOAL_ACHIEVEMENT_EVIDENCE_TOKENS),
)


def render_evidence_contract() -> str:
    """Return the shared experimental evidence contract for prompts/docs."""
    return EVIDENCE_CONTRACT_MARKDOWN.strip()


def evaluation_protocol_evidence_values(data: dict[str, Any]) -> list[Any]:
    """Return substantive cross-validation or repeated-split evidence leaves."""
    return [
        value
        for key, value in _walk_named_values(data)
        if _is_evaluation_protocol_evidence_key(key) and _is_substantive_evidence_leaf(value)
    ]


def evaluation_protocol_repetition_counts(data: Any, prefix: str = "") -> list[int]:
    """Return declared or inferable fold/split/repeat counts from an artifact."""
    counts: list[int] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized = _normalize_evidence_key(path)
            if _is_evaluation_repetition_count_key(normalized):
                count = _repetition_count_value(value)
                if count is not None:
                    counts.append(count)
            if _is_evaluation_repeated_collection_key(normalized) and isinstance(value, (list, dict)):
                count = _repeated_collection_count(value)
                if count is not None:
                    counts.append(count)
            if isinstance(value, str) and _is_evaluation_protocol_evidence_key(normalized):
                count = _repetition_count_from_text(value)
                if count is not None:
                    counts.append(count)
            if isinstance(value, (dict, list)):
                counts.extend(evaluation_protocol_repetition_counts(value, path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            counts.extend(evaluation_protocol_repetition_counts(item, path))
    return counts


def evaluation_protocol_repeated_metric_counts(data: Any, prefix: str = "") -> list[int]:
    """Return counts for materialized per-fold/split metric records."""
    counts: list[int] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized = _normalize_evidence_key(path)
            if _is_evaluation_repeated_collection_key(normalized) and isinstance(value, (list, dict)):
                count = _repeated_metric_result_count(value)
                if count is not None:
                    counts.append(count)
            if isinstance(value, (dict, list)):
                counts.extend(evaluation_protocol_repeated_metric_counts(value, path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            counts.extend(evaluation_protocol_repeated_metric_counts(item, path))
    return counts


def is_evaluation_protocol_count_key(key: str) -> bool:
    """Return whether a key names a declared fold/split/repeat count."""
    return _is_evaluation_repetition_count_key(_normalize_evidence_key(key))


def is_baseline_comparison_collection_key(key: str) -> bool:
    """Return whether a key names a per-baseline metric collection."""
    normalized = _normalize_evidence_key(key)
    return any(
        _comparison_collection_key_matches(normalized, token)
        for token in BASELINE_COMPARISON_COLLECTION_TOKENS
    )


def is_sota_comparison_collection_key(key: str) -> bool:
    """Return whether a key names a per-SOTA/prior-work metric collection."""
    normalized = _normalize_evidence_key(key)
    return any(
        _comparison_collection_key_matches(normalized, token)
        for token in SOTA_COMPARISON_COLLECTION_TOKENS
    )


def is_baseline_comparison_evidence_key(key: str) -> bool:
    """Return whether a key names baseline comparison evidence."""
    normalized = _normalize_evidence_key(key)
    return any(
        _comparison_evidence_key_matches(normalized, token)
        for token in BASELINE_COMPARISON_EVIDENCE_TOKENS
    )


def is_sota_comparison_evidence_key(key: str) -> bool:
    """Return whether a key names SOTA or prior-work comparison evidence."""
    normalized = _normalize_evidence_key(key)
    return any(
        _comparison_evidence_key_matches(normalized, token)
        for token in SOTA_COMPARISON_EVIDENCE_TOKENS
    )


def is_statistics_evidence_key(key: str) -> bool:
    """Return whether a key names statistical uncertainty or support evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_statistics_key_matches(normalized, token) for token in STATISTICS_EVIDENCE_TOKENS)


def is_uncertainty_evidence_key(key: str) -> bool:
    """Return whether a key names concrete uncertainty evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_statistics_key_matches(normalized, token) for token in UNCERTAINTY_EVIDENCE_TOKENS)


def is_statistical_significance_evidence_key(key: str) -> bool:
    """Return whether a key names p-value style significance evidence."""
    normalized = _normalize_evidence_key(key)
    return any(
        _statistics_key_matches(normalized, token)
        for token in STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS
    )


def is_comparison_interval_significance_evidence_key(key: str) -> bool:
    """Return whether a key names a comparison confidence interval usable for significance."""
    normalized = _normalize_evidence_key(key)
    return is_uncertainty_evidence_key(normalized) and any(
        _comparison_evidence_key_matches(normalized, token)
        for token in COMPARISON_INTERVAL_SIGNIFICANCE_TOKENS
    )


def is_reproducibility_evidence_key(key: str) -> bool:
    """Return whether a key names concrete reproducibility metadata."""
    normalized = _normalize_evidence_key(key)
    return any(
        _reproducibility_key_matches(normalized, token)
        for token in (
            *REPRODUCIBILITY_SEED_TOKENS,
            *REPRODUCIBILITY_DATA_TOKENS,
            *REPRODUCIBILITY_ENV_TOKENS,
            *REPRODUCIBILITY_CODE_TOKENS,
        )
    )


def baseline_comparison_entries(data: Any, metric_name: str | None = None) -> list[tuple[str, bool]]:
    """Return named baseline entries and whether each entry has metric evidence."""
    return [
        (name, _baseline_item_has_metric_value(item, metric_name))
        for name, item in baseline_comparison_items(data)
    ]


def baseline_comparison_names(data: Any) -> list[str]:
    """Return unique baseline names declared in baseline comparison evidence."""
    names = [name for name, _ in baseline_comparison_entries(data)]
    return list(dict.fromkeys(names))


def baseline_comparison_items(data: Any) -> list[tuple[str, Any]]:
    """Return named baseline comparison items with their source payload snippets."""
    return _comparison_items(data, is_baseline_comparison_collection_key)


def sota_comparison_entries(data: Any, metric_name: str | None = None) -> list[tuple[str, bool]]:
    """Return named SOTA/prior-work entries and whether each has metric evidence."""
    return [
        (name, _baseline_item_has_metric_value(item, metric_name))
        for name, item in sota_comparison_items(data)
    ]


def sota_comparison_names(data: Any) -> list[str]:
    """Return unique SOTA/prior-work names declared in comparison evidence."""
    names = [name for name, _ in sota_comparison_entries(data)]
    return list(dict.fromkeys(names))


def sota_comparison_items(data: Any) -> list[tuple[str, Any]]:
    """Return named SOTA/prior-work comparison items with their source payload snippets."""
    return _comparison_items(data, is_sota_comparison_collection_key)


def comparison_names_match(claimed: str, evidence: str) -> bool:
    """Return whether two human-written comparison names refer to the same item."""
    claimed_norm = _normalize_evidence_text(claimed)
    evidence_norm = _normalize_evidence_text(evidence)
    claimed_tokens = _comparison_name_tokens(claimed_norm)
    evidence_tokens = _comparison_name_tokens(evidence_norm)
    return bool(
        claimed_norm
        and evidence_norm
        and (
            claimed_norm == evidence_norm
            or claimed_norm in evidence_norm
            or evidence_norm in claimed_norm
            or (
                bool(claimed_tokens)
                and bool(evidence_tokens)
                and (
                    claimed_tokens.issubset(evidence_tokens)
                    or evidence_tokens.issubset(claimed_tokens)
                )
            )
        )
    )


_COMPARISON_NAME_STOPWORDS = {
    "baseline",
    "heuristic",
    "method",
    "ml",
    "model",
    "naive",
    "non",
    "simple",
}


def _comparison_name_tokens(value: str) -> set[str]:
    return {
        token
        for token in value.split()
        if token and token not in _COMPARISON_NAME_STOPWORDS
    }


def baseline_names_match(claimed: str, evidence: str) -> bool:
    """Return whether two human-written baseline names refer to the same baseline."""
    return comparison_names_match(claimed, evidence)


def is_ablation_evidence_key(key: str) -> bool:
    """Return whether a key names ablation, importance, or sensitivity evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in ABLATION_EVIDENCE_TOKENS)


def is_evaluation_protocol_repeated_collection_key(key: str) -> bool:
    """Return whether a key names a per-fold/split repeated metric collection."""
    return _is_evaluation_repeated_collection_key(_normalize_evidence_key(key))


def is_evaluation_protocol_evidence_key(key: str) -> bool:
    """Return whether a key names cross-validation or repeated-split evidence."""
    return _is_evaluation_protocol_evidence_key(key)


def is_error_analysis_evidence_key(key: str) -> bool:
    """Return whether a key names error analysis evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in ERROR_ANALYSIS_EVIDENCE_TOKENS)


def is_calibration_error_evidence_key(key: str) -> bool:
    """Return whether a key names scalar calibration/error evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in CALIBRATION_ERROR_EVIDENCE_TOKENS)


def is_fairness_evidence_key(key: str) -> bool:
    """Return whether a key names fairness or bias-audit evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in FAIRNESS_EVIDENCE_TOKENS)


def is_fairness_scalar_evidence_key(key: str) -> bool:
    """Return whether a key names aggregate scalar fairness evidence."""
    normalized = _normalize_evidence_key(_leaf_evidence_key(key))
    return any(_family_evidence_key_matches(normalized, token) for token in FAIRNESS_SCALAR_EVIDENCE_TOKENS)


def is_efficiency_evidence_key(key: str) -> bool:
    """Return whether a key names efficiency, latency, size, or resource evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in EFFICIENCY_EVIDENCE_TOKENS)


def is_efficiency_profile_evidence_key(key: str) -> bool:
    """Return whether a key names benchmark-style efficiency evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in EFFICIENCY_PROFILE_EVIDENCE_TOKENS)


def is_efficiency_static_evidence_key(key: str) -> bool:
    """Return whether a key names static model resource evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in EFFICIENCY_STATIC_EVIDENCE_TOKENS)


def is_efficiency_benchmark_context_key(key: str) -> bool:
    """Return whether a key names efficiency benchmark context."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in EFFICIENCY_BENCHMARK_CONTEXT_TOKENS)


def is_robustness_evidence_key(key: str) -> bool:
    """Return whether a key names robustness or stability evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in ROBUSTNESS_EVIDENCE_TOKENS)


def is_generalization_evidence_key(key: str) -> bool:
    """Return whether a key names external, held-out, or OOD generalization evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in GENERALIZATION_EVIDENCE_TOKENS)


def is_external_generalization_evidence_key(key: str) -> bool:
    """Return whether a key names external, cross-dataset, or OOD evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_family_evidence_key_matches(normalized, token) for token in EXTERNAL_GENERALIZATION_EVIDENCE_TOKENS)


def is_causal_evidence_key(key: str) -> bool:
    """Return whether a key names causal design or identification evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_causal_key_matches(normalized, token) for token in CAUSAL_EVIDENCE_TOKENS)


def is_causal_design_evidence_key(key: str) -> bool:
    """Return whether a key can carry causal design or identification evidence."""
    return _is_causal_design_key(key)


def has_substantive_ablation_evidence(data: Any) -> bool:
    """Return whether an artifact contains labeled numeric ablation evidence."""
    return any(
        _has_labeled_numeric_evidence(value, _ABLATION_LABEL_KEYS)
        for key, value in _walk_named_subtrees(data)
        if is_ablation_evidence_key(key)
    )


def has_substantive_error_analysis_evidence(data: Any) -> bool:
    """Return whether an artifact contains labeled numeric error-analysis evidence."""
    return any(
        (
            is_calibration_error_evidence_key(key)
            and _has_metric_numeric_leaf(value, key)
        )
        or _has_labeled_numeric_evidence(value, _ERROR_ANALYSIS_LABEL_KEYS)
        or _has_numeric_matrix(value)
        for key, value in _walk_named_subtrees(data)
        if is_error_analysis_evidence_key(key)
    )


def reproducibility_bundle_missing_groups(data: Any) -> list[str]:
    """Return missing metadata groups for a reproducibility claim."""
    groups = (
        ("seed", _is_reproducibility_seed_key),
        ("data source/fingerprint", _is_reproducibility_data_key),
        ("split/protocol", _is_reproducibility_split_key),
        ("environment", _is_reproducibility_env_key),
        ("code provenance", _is_reproducibility_code_key),
    )
    return [
        label
        for label, key_predicate in groups
        if not _has_reproducibility_group(data, key_predicate)
    ]


def has_reproducibility_bundle(data: Any) -> bool:
    """Return whether an artifact contains all core reproducibility groups."""
    return not reproducibility_bundle_missing_groups(data)


def is_reproducibility_code_path_key(key: str) -> bool:
    """Return whether a key names a concrete script/code provenance path."""
    normalized = _normalize_evidence_key(key)
    return any(_reproducibility_key_matches(normalized, token) for token in REPRODUCIBILITY_CODE_PATH_TOKENS)


def has_split_protocol_evidence(data: Any) -> bool:
    """Return whether an artifact identifies a split, holdout, or evaluation protocol."""
    return _has_reproducibility_group(data, _is_reproducibility_split_key) or any(
        _is_evaluation_protocol_evidence_key(key) and _is_substantive_evidence_leaf(value)
        for key, value in _walk_named_values(data)
    )


def has_sample_or_repetition_support_evidence(data: Any) -> bool:
    """Return whether evidence has sample or repetition support."""
    return any(
        _is_significance_support_key(_normalize_evidence_key(key))
        and _is_positive_numeric_value(value)
        for key, value in _walk_named_values(data)
    )


def has_significance_support_evidence(data: Any) -> bool:
    """Return whether significance evidence has sample or repetition support."""
    return has_sample_or_repetition_support_evidence(data)


def has_uncertainty_evidence(data: Any) -> bool:
    """Return whether an artifact contains concrete uncertainty measurements."""
    return any(
        is_uncertainty_evidence_key(key)
        and _has_finite_numeric_leaf(value)
        for key, value in _walk_named_subtrees(data)
    )


def has_statistical_significance_evidence(data: Any) -> bool:
    """Return whether an artifact contains concrete significance measurements."""
    return any(
        is_statistical_significance_evidence_key(key)
        and _has_finite_numeric_leaf(value)
        for key, value in _walk_named_subtrees(data)
    ) or any(
        is_comparison_interval_significance_evidence_key(key)
        and _has_confidence_interval_bounds(value)
        for key, value in _walk_named_subtrees(data)
    )


def has_causal_evidence(data: Any) -> bool:
    """Return whether an artifact contains causal design or identification evidence."""
    return any(
        _is_causal_design_key(key) and _has_substantive_causal_design_value(value)
        for key, value in _walk_named_subtrees(data)
    )


def has_robustness_evidence(data: Any) -> bool:
    """Return whether an artifact contains repeated-run or explicit robustness evidence."""
    if any(count >= 2 for count in evaluation_protocol_repeated_metric_counts(data)):
        return True
    return has_explicit_robustness_evidence(data)


def has_explicit_robustness_evidence(data: Any) -> bool:
    """Return whether an artifact explicitly reports robustness/stability measurements."""
    return any(
        is_robustness_evidence_key(key)
        and _has_labeled_or_scalar_measurement(value, key, _ROBUSTNESS_LABEL_KEYS)
        for key, value in _walk_named_subtrees(data)
    )


def has_fairness_evidence(data: Any) -> bool:
    """Return whether an artifact contains numeric fairness or bias-audit evidence."""
    return any(
        _has_labeled_numeric_evidence(value, _FAIRNESS_LABEL_KEYS)
        or (
            is_fairness_scalar_evidence_key(key)
            and _has_metric_numeric_leaf(value, key)
        )
        for key, value in _walk_named_subtrees(data)
        if is_fairness_evidence_key(key)
    )


def has_efficiency_evidence(data: Any) -> bool:
    """Return whether an artifact contains credible numeric efficiency evidence."""
    static_evidence = any(
        _has_metric_numeric_leaf(value, key)
        for key, value in _walk_named_subtrees(data)
        if is_efficiency_static_evidence_key(key)
    )
    if static_evidence:
        return True
    profile_evidence = any(
        _has_metric_numeric_leaf(value, key)
        for key, value in _walk_named_subtrees(data)
        if is_efficiency_profile_evidence_key(key)
    )
    return profile_evidence and has_efficiency_benchmark_context(data)


def has_efficiency_benchmark_context(data: Any) -> bool:
    """Return whether an artifact gives context for efficiency benchmarking."""
    return any(
        is_efficiency_benchmark_context_key(key)
        and _is_substantive_evidence_leaf(value)
        for key, value in _walk_named_values(data)
    )


def has_generalization_evidence(data: Any) -> bool:
    """Return whether an artifact contains held-out, external, or OOD validation evidence."""
    if has_split_protocol_evidence(data) and _has_measurement_numeric_leaf(data):
        return True
    return has_explicit_generalization_evidence(data)


def has_explicit_generalization_evidence(data: Any) -> bool:
    """Return whether an artifact explicitly reports held-out, external, or OOD measurements."""
    return any(
        is_generalization_evidence_key(key)
        and _has_labeled_or_scalar_measurement(value, key, _GENERALIZATION_LABEL_KEYS)
        for key, value in _walk_named_subtrees(data)
    )


def has_external_generalization_evidence(data: Any) -> bool:
    """Return whether an artifact contains external, cross-dataset, or OOD metrics."""
    return any(
        is_external_generalization_evidence_key(key)
        and _has_labeled_numeric_evidence(value, _GENERALIZATION_LABEL_KEYS)
        for key, value in _walk_named_subtrees(data)
    )


def is_specific_leakage_audit_key(key: str) -> bool:
    """Return whether a key names a scoped leakage audit check."""
    normalized = _normalize_evidence_key(key)
    return any(_leakage_key_matches(normalized, token) for token in SPECIFIC_LEAKAGE_AUDIT_TOKENS)


def is_leakage_audit_evidence_key(key: str) -> bool:
    """Return whether a key names leakage audit evidence."""
    normalized = _normalize_evidence_key(key)
    return any(_leakage_key_matches(normalized, token) for token in LEAKAGE_AUDIT_EVIDENCE_TOKENS)


def is_leakage_indicator_evidence_key(key: str) -> bool:
    """Return whether a key names an explicit leakage finding/check result."""
    normalized = _normalize_evidence_key(key)
    return any(_leakage_key_matches(normalized, token) for token in LEAKAGE_INDICATOR_EVIDENCE_TOKENS)


def is_leakage_resolution_evidence_key(key: str) -> bool:
    """Return whether a key names an explicit leakage resolution flag/result."""
    normalized = _normalize_evidence_key(key)
    return any(_leakage_key_matches(normalized, token) for token in LEAKAGE_RESOLUTION_EVIDENCE_TOKENS)


def has_substantive_leakage_audit_evidence(data: Any) -> bool:
    """Return whether an artifact reports both leakage outcome and scoped audit evidence."""
    outcome = any(
        is_leakage_indicator_evidence_key(key)
        and _is_substantive_leakage_audit_value(value)
        for key, value in _walk_named_values(data)
    ) or any(
        is_leakage_resolution_evidence_key(key)
        and _is_substantive_leakage_resolution_value(value)
        for key, value in _walk_named_values(data)
    )
    scoped_check = any(
        is_specific_leakage_audit_key(key)
        and _is_substantive_leakage_audit_value(value)
        for key, value in _walk_named_values(data)
    )
    return outcome and scoped_check


def is_goal_achievement_evidence_key(key: str) -> bool:
    """Return whether a key names an explicit goal-achievement flag."""
    normalized = _normalize_evidence_key(key)
    return any(_goal_achievement_key_matches(normalized, token) for token in GOAL_ACHIEVEMENT_EVIDENCE_TOKENS)


def _goal_achievement_key_matches(normalized_key: str, normalized_token: str) -> bool:
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def plan_metric_target(plan: dict[str, Any]) -> tuple[str, str, float] | None:
    """Return the normalized metric target declared by a research plan."""
    metric = plan.get("metric")
    if not isinstance(metric, dict):
        return None
    metric_name = str(metric.get("name", "")).strip().lower()
    direction = str(metric.get("direction", "")).strip().lower()
    target = _numeric_scalar(metric.get("target"))
    if (
        not metric_name
        or direction not in {"minimize", "maximize"}
        or target is None
        or not math.isfinite(target)
    ):
        return None
    return canonical_metric_name(metric_name), direction, target


def canonical_metric_name(metric_name: str) -> str:
    """Return the canonical name for common metric aliases."""
    normalized = _normalize_evidence_key(metric_name)
    compact = normalized.replace("_", "")
    if compact in {"meanabsoluteerror", "mae"}:
        return "mae"
    if compact in {"rootmeansquarederror", "rmse"}:
        return "rmse"
    if compact in {"meansquarederror", "mse"}:
        return "mse"
    if compact in {"accuracy", "acc"}:
        return "accuracy"
    if compact in {"areaunderroc", "areaunderroccurve", "areaundercurve", "rocauc", "auroc", "auc"}:
        return "auc"
    if compact in {"rsquared", "r2"}:
        return "r2"
    return normalized


def metric_aliases(metric_name: str) -> tuple[str, ...]:
    """Return normalized aliases accepted for a metric name."""
    canonical = canonical_metric_name(metric_name)
    aliases = {canonical}
    if canonical == "mae":
        aliases.update(("mae", "mean_absolute_error"))
    elif canonical == "rmse":
        aliases.update(("rmse", "root_mean_squared_error"))
    elif canonical == "mse":
        aliases.update(("mse", "mean_squared_error"))
    elif canonical == "accuracy":
        aliases.update(("accuracy", "acc"))
    elif canonical == "auc":
        aliases.update(("area_under_curve", "area_under_roc", "area_under_roc_curve", "auc", "auroc", "roc_auc"))
    elif canonical == "r2":
        aliases.update(("r2", "r_squared", "r_2"))
    return tuple(sorted(aliases))


def is_metric_evidence_key(key: str, metric_name: str) -> bool:
    """Return whether a key names a concrete metric value for the metric."""
    normalized = _normalize_evidence_key(key)
    return any(
        _statistics_key_matches(normalized, alias)
        for alias in metric_aliases(metric_name)
    )


def is_metric_support_numeric_key(key: str) -> bool:
    """Return whether a numeric key is support/stat metadata, not a metric value."""
    normalized = _normalize_evidence_key(key)
    return any(
        _metric_support_numeric_key_matches(normalized, token)
        for token in _METRIC_SUPPORT_NUMERIC_KEYS
    )


def contains_metric_support_numeric_token(key: str) -> bool:
    """Return whether a key contains a support/stat token, even in negated or metadata fields."""
    normalized = _normalize_evidence_key(key)
    return any(
        _metric_support_numeric_token_present(normalized, token)
        for token in _METRIC_SUPPORT_NUMERIC_KEYS
    )


def checklist_yes(checklist: Any, token: str) -> bool:
    if not isinstance(checklist, dict):
        return False
    return any(
        token in str(key).lower()
        and str(value).lower() in ("yes", "true", "present", "complete")
        for key, value in checklist.items()
    )


def plan_requires_ablation_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "ablation") or _has_any_normalized(
        text,
        ("ablation", "feature importance", "permutation importance", "sensitivity"),
    )


def plan_requires_evaluation_protocol_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "cross") or _has_any_normalized(
        text,
        ("cross validation", "multiple split", "repeated split", "fold", "cv"),
    )


def plan_requires_error_analysis_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "error") or _has_any_normalized(
        text,
        ("error analysis", "failure case", "residual analysis", "subgroup", "slice analysis"),
    )


def plan_requires_fairness_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "fairness") or _has_any_normalized(
        text,
        (
            "fairness",
            "bias audit",
            "model bias",
            "demographic parity",
            "equalized odds",
            "equal opportunity",
            "disparate impact",
            "protected attribute",
            "protected group",
            "group fairness",
            "subgroup fairness",
            "unbiased",
        ),
    )


def plan_requires_efficiency_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return (
        checklist_yes(checklist, "efficiency")
        or checklist_yes(checklist, "latency")
        or _has_any_normalized(
            text,
            (
                "efficiency",
                "latency",
                "throughput",
                "runtime",
                "run time",
                "inference time",
                "training time",
                "wall clock",
                "memory usage",
                "peak memory",
                "model size",
                "parameter count",
                "n parameters",
                "flops",
                "macs",
                "compute cost",
                "gpu hours",
                "faster",
                "slower",
            ),
        )
    )


def plan_requires_efficiency_benchmark_context(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return (
        checklist_yes(checklist, "efficiency")
        or checklist_yes(checklist, "latency")
        or _has_any_normalized(
            text,
            (
                "efficiency profile",
                "profile inference",
                "benchmark latency",
                "benchmark throughput",
                "latency",
                "throughput",
                "runtime",
                "run time",
                "inference time",
                "training time",
                "wall clock",
                "memory usage",
                "peak memory",
                "compute cost",
                "gpu hours",
                "cpu seconds",
                "energy",
                "faster",
                "slower",
            ),
        )
    )


def plan_requires_robustness_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "robust") or checklist_yes(checklist, "stability") or _has_any_normalized(
        text,
        ("robustness", "robust across", "stable across", "stability", "seed sensitivity", "stress test"),
    )


def plan_requires_generalization_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "generalization") or checklist_yes(checklist, "external") or _has_any_normalized(
        text,
        (
            "generalization",
            "generalizes",
            "unseen data",
            "external validation",
            "external dataset",
            "external cohort",
            "independent validation",
            "independent cohort",
            "validation cohort",
            "out of distribution",
            "ood",
            "cross dataset",
        ),
    )


def plan_requires_external_generalization_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "external") or _has_any_normalized(
        text,
        (
            "external validation",
            "external dataset",
            "external test",
            "external cohort",
            "independent validation",
            "independent cohort",
            "validation cohort",
            "out of distribution",
            "ood",
            "cross dataset",
        ),
    )


def plan_requires_causal_evidence(plan: dict[str, Any]) -> bool:
    checklist = plan.get("experiment_checklist", {})
    text = _normalized_plan_text(plan)
    return checklist_yes(checklist, "causal") or _has_any_normalized(
        text,
        (
            "causal effect",
            "causal impact",
            "causal inference",
            "causal identification",
            "causality",
            "causation",
            "randomized assignment",
            "randomized control",
            "treatment assignment",
            "control group",
            "matched control",
            "counterfactual",
            "instrumental variable",
            "difference in differences",
            "regression discontinuity",
            "propensity score",
        ),
    )


def _normalized_plan_text(plan: Any) -> str:
    text = json.dumps(plan, ensure_ascii=False, sort_keys=True) if not isinstance(plan, str) else plan
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _comparison_items(data: Any, collection_key_predicate: Any) -> list[tuple[str, Any]]:
    entries: list[tuple[str, Any]] = []
    for key, value in _walk_named_subtrees(data):
        if not isinstance(value, (dict, list)):
            continue
        if collection_key_predicate(key):
            entries.extend(_comparison_items_from_collection(value))
    return entries


def _comparison_items_from_collection(value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, list):
        entries: list[tuple[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = _baseline_item_name(item)
            if _is_substantive_comparison_name(name):
                entries.append((name, item))
        return entries
    if isinstance(value, dict):
        own_name = _baseline_item_name(value)
        if _is_substantive_comparison_name(own_name):
            return [(own_name, value)]
        entries = []
        for key, item in value.items():
            name = _baseline_item_name(item) if isinstance(item, dict) else str(key)
            name = name or str(key)
            if _is_substantive_comparison_name(name):
                entries.append((name, item))
        return entries
    return []


def _baseline_item_name(item: dict[str, Any]) -> str | None:
    for key in (
        "name",
        "id",
        "baseline",
        "model",
        "method",
        "prior_work",
        "previous_work",
        "sota",
        "reference",
        "paper",
        "source",
        "citation",
        "work",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_substantive_comparison_name(value: str | None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return _is_substantive_label_value(value)


def _baseline_item_has_metric_value(item: dict[str, Any], metric_name: str | None) -> bool:
    if metric_name:
        return bool(_baseline_metric_values(item, metric_name))
    return _has_numeric_leaf(item)


def _baseline_metric_values(value: Any, metric_name: str) -> list[float]:
    if isinstance(value, list):
        values: list[float] = []
        for item in value:
            values.extend(_baseline_metric_values(item, metric_name))
        return values
    if not isinstance(value, dict):
        return []
    values = [
        float(item)
        for key, item in value.items()
        if isinstance(item, (int, float))
        and not isinstance(item, bool)
        and _is_metric_numeric_leaf_key(_normalize_evidence_key(key))
        and is_metric_evidence_key(key, metric_name)
    ]
    for item in value.values():
        if isinstance(item, (dict, list)):
            values.extend(_baseline_metric_values(item, metric_name))
    return values


def _has_any_normalized(text: str, needles: tuple[str, ...]) -> bool:
    return any(re.sub(r"[^a-z0-9]+", " ", needle.lower()).strip() in text for needle in needles)


def _is_evaluation_protocol_evidence_key(key: str) -> bool:
    normalized = _normalize_evidence_key(key)
    return any(_evaluation_protocol_key_matches(normalized, token) for token in EVALUATION_PROTOCOL_EVIDENCE_TOKENS)


def _is_evaluation_repetition_count_key(normalized: str) -> bool:
    return any(
        _evaluation_protocol_key_matches(normalized, key)
        for key in (
            "fold_count",
            "cv_fold_count",
            "cv_folds",
            "n_folds",
            "n_splits",
            "split_count",
            "num_folds",
            "num_splits",
        )
    )


def _is_evaluation_repeated_collection_key(normalized: str) -> bool:
    return any(
        _evaluation_protocol_key_matches(normalized, key)
        for key in (
            "per_fold_metrics",
            "fold_metrics",
            "split_results",
            "repeated_split_results",
            "multiple_split_results",
            "evaluation_splits",
            "cross_validation_results",
            "cv_results",
        )
    )


def _evaluation_protocol_key_matches(normalized_key: str, normalized_token: str) -> bool:
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def _repeated_collection_count(value: Any) -> int | None:
    if isinstance(value, list):
        unit_ids = _repeated_eval_unit_ids(
            item for item in value if isinstance(item, dict)
        )
        if unit_ids:
            return len(unit_ids)
        return len(value)
    if not isinstance(value, dict):
        return None
    repeated_keys = [
        key for key in value
        if _looks_like_repeated_eval_unit_key(str(key))
    ]
    if repeated_keys:
        unit_ids = {
            unit_id
            for key in repeated_keys
            if (unit_id := _repeated_eval_unit_id_from_key(str(key))) is not None
        }
        return len(unit_ids) if unit_ids else len(repeated_keys)
    repeated_items = [
        item for item in value.values()
        if isinstance(item, dict) and _dict_has_repeated_eval_unit_id(item)
    ]
    if repeated_items:
        unit_ids = _repeated_eval_unit_ids(repeated_items)
        return len(unit_ids) if unit_ids else len(repeated_items)
    return None


def _repeated_metric_result_count(value: Any) -> int | None:
    if isinstance(value, list):
        unit_ids = _repeated_metric_result_unit_ids(
            item for item in value if isinstance(item, dict)
        )
        return len(unit_ids) if unit_ids else None
    if not isinstance(value, dict):
        return None
    repeated_keys = [
        key for key in value
        if _looks_like_repeated_eval_unit_key(str(key))
    ]
    if repeated_keys:
        unit_ids = {
            unit_id
            for key in repeated_keys
            if _has_measurement_numeric_leaf(value[key])
            if (unit_id := _repeated_eval_unit_id_from_key(str(key))) is not None
        }
        return len(unit_ids) if unit_ids else None
    repeated_items = [
        item for item in value.values()
        if isinstance(item, dict) and _dict_has_repeated_eval_unit_id(item)
    ]
    if repeated_items:
        unit_ids = _repeated_metric_result_unit_ids(repeated_items)
        return len(unit_ids) if unit_ids else None
    return None


def _repeated_metric_result_unit_ids(items: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    return _repeated_eval_unit_ids(items, require_measurement=True)


def _repeated_eval_unit_ids(
    items: Iterable[dict[str, Any]],
    *,
    require_measurement: bool = False,
) -> set[tuple[str, str]]:
    unit_ids: set[tuple[str, str]] = set()
    for item in items:
        if require_measurement and not _has_measurement_numeric_leaf(item):
            continue
        unit_id = _repeated_eval_unit_id(item)
        if unit_id is not None:
            unit_ids.add(unit_id)
    return unit_ids


def _looks_like_repeated_eval_unit_key(key: str) -> bool:
    return _repeated_eval_unit_id_from_key(key) is not None


def _repeated_eval_unit_id_from_key(key: str) -> tuple[str, str] | None:
    normalized = _normalize_evidence_key(key)
    match = re.search(r"(?:^|_)(fold|split|repeat|seed|trial)_?(\d+)(?:_|$)", normalized)
    if not match:
        return None
    canonical_key = _canonical_repeated_eval_unit_key(match.group(1))
    return canonical_key, _canonical_repeated_eval_unit_value(canonical_key, match.group(2))


def _dict_has_repeated_eval_unit_id(value: dict[str, Any]) -> bool:
    return _repeated_eval_unit_id(value) is not None


def _repeated_eval_unit_id(value: dict[str, Any]) -> tuple[str, str] | None:
    split = _first_repeated_eval_unit_value(value, ("split_id", "split", "trial_id", "trial", "seed"))
    if split is not None:
        return split

    repeat = _first_repeated_eval_unit_value(value, ("repeat_id", "repeat"))
    fold = _first_repeated_eval_unit_value(value, ("fold_id", "fold"))
    if repeat is not None and fold is not None:
        return "split", f"{repeat[0]}={repeat[1]}|{fold[0]}={fold[1]}"
    return fold or repeat


def _first_repeated_eval_unit_value(
    value: dict[str, Any],
    keys: tuple[str, ...],
) -> tuple[str, str] | None:
    for key in keys:
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, str)):
            continue
        text = str(item).strip()
        if text:
            canonical_key = _canonical_repeated_eval_unit_key(key)
            return canonical_key, _canonical_repeated_eval_unit_value(canonical_key, text)
    return None


def _canonical_repeated_eval_unit_key(key: str) -> str:
    return {
        "fold_id": "fold",
        "split_id": "split",
        "repeat_id": "repeat",
        "trial_id": "trial",
    }.get(key, key)


def _canonical_repeated_eval_unit_value(canonical_key: str, value: str) -> str:
    normalized = _normalize_evidence_key(value)
    match = re.fullmatch(rf"{re.escape(canonical_key)}_?(.+)", normalized)
    if match:
        normalized = match.group(1)
    if normalized.isdigit():
        return str(int(normalized))
    return normalized


def _repetition_count_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return _repetition_count_from_text(value)
    if isinstance(value, (list, dict)):
        return len(value)
    return None


def _repetition_count_from_text(value: str) -> int | None:
    match = re.search(r"\b(\d+)\s*[- ]?\s*(?:fold|split|repeat)", value.lower())
    if not match:
        return None
    return int(match.group(1))


def _normalize_evidence_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _leaf_evidence_key(key: Any) -> str:
    return str(key).rsplit(".", 1)[-1].split("[", 1)[0]


def _normalize_evidence_text(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _walk_named_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_walk_named_values(item, child_prefix))
        return out
    if isinstance(value, list):
        out: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.extend(_walk_named_values(item, child_prefix))
        return out
    return [(prefix, value)]


def _walk_named_subtrees(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if prefix:
        out.append((prefix, value))
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_walk_named_subtrees(item, child_prefix))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.extend(_walk_named_subtrees(item, child_prefix))
    return out


def _has_numeric_leaf(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_has_numeric_leaf(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_numeric_leaf(item) for item in value)
    return False


def _has_finite_numeric_leaf(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return any(_has_finite_numeric_leaf(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_finite_numeric_leaf(item) for item in value)
    return False


def has_measurement_numeric_leaf(value: Any, prefix: str = "") -> bool:
    """Return whether a payload contains numeric measurements, excluding IDs."""
    return _has_measurement_numeric_leaf(value, prefix)


def has_evidence_token_value(data: Any, evidence_tokens: tuple[str, ...]) -> bool:
    """Return whether matching evidence keys contain substantive leaf values."""
    normalized_tokens = tuple(_normalize_evidence_key(token) for token in evidence_tokens)
    return any(
        any(_family_evidence_key_matches(_normalize_evidence_key(key), token) for token in normalized_tokens)
        and _is_substantive_evidence_leaf(value)
        for key, value in _walk_named_values(data)
    )


def has_measurement_evidence_token_value(data: Any, evidence_tokens: tuple[str, ...]) -> bool:
    """Return whether matching evidence keys contain actual measurement numbers."""
    normalized_tokens = tuple(_normalize_evidence_key(token) for token in evidence_tokens)
    return any(
        any(_family_evidence_key_matches(_normalize_evidence_key(key), token) for token in normalized_tokens)
        and _has_measurement_numeric_leaf(value, key)
        for key, value in _walk_named_subtrees(data)
    )


def _has_measurement_numeric_leaf(value: Any, prefix: str = "") -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        leaf = _numeric_leaf_key(prefix)
        return _is_measurement_numeric_leaf_key(leaf)
    if isinstance(value, dict):
        return any(
            _has_measurement_numeric_leaf(item, f"{prefix}.{key}" if prefix else str(key))
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(
            _has_measurement_numeric_leaf(item, f"{prefix}[{index}]" if prefix else f"[{index}]")
            for index, item in enumerate(value)
        )
    return False


def _has_metric_numeric_leaf(value: Any, prefix: str = "") -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        leaf = _numeric_leaf_key(prefix)
        return math.isfinite(float(value)) and _is_metric_numeric_leaf_key(leaf)
    if isinstance(value, dict):
        return any(
            _has_metric_numeric_leaf(item, f"{prefix}.{key}" if prefix else str(key))
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(
            _has_metric_numeric_leaf(item, f"{prefix}[{index}]" if prefix else f"[{index}]")
            for index, item in enumerate(value)
        )
    return False


def _numeric_leaf_key(prefix: str) -> str:
    return _normalize_evidence_key(prefix.split(".")[-1].split("[", 1)[0])


def _is_measurement_numeric_leaf_key(leaf: str) -> bool:
    if leaf not in _NUMERIC_IDENTIFIER_KEYS and not leaf.endswith("_id"):
        return not _leaf_has_metadata_suffix(leaf)
    return False


def _is_metric_numeric_leaf_key(leaf: str) -> bool:
    if not _is_measurement_numeric_leaf_key(leaf):
        return False
    return not is_metric_support_numeric_key(leaf)


def _leaf_has_metadata_suffix(leaf: str) -> bool:
    parts = [part for part in _normalize_evidence_key(leaf).split("_") if part]
    return bool(parts and parts[-1] in _EVIDENCE_METADATA_SUFFIX_TOKENS)


_NUMERIC_IDENTIFIER_KEYS = {
    "bootstrap_samples",
    "fold_count",
    "fold",
    "fold_id",
    "id",
    "n",
    "n_folds",
    "n_samples",
    "n_splits",
    "n_trials",
    "num_folds",
    "num_samples",
    "num_splits",
    "num_trials",
    "repeat",
    "repeat_id",
    "repeats",
    "replicates",
    "rng",
    "random_state",
    "sample_size",
    "sample_count",
    "samples",
    "seed",
    "split",
    "split_count",
    "split_id",
    "trial",
    "trial_count",
    "trial_id",
}
_METRIC_SUPPORT_NUMERIC_KEYS = {
    "alpha",
    "ci",
    "ci95",
    "confidence",
    "confidence_interval",
    "p_value",
    "pvalue",
    "q_value",
    "qvalue",
    "se",
    "sem",
    "standard_deviation",
    "standard_error",
    "std",
    "stdev",
    "stderr",
    "variance",
}


def _metric_support_numeric_key_matches(normalized_key: str, normalized_token: str) -> bool:
    if normalized_token == "confidence":
        return normalized_key == "confidence" or normalized_key.endswith("_confidence")
    return _statistics_key_matches(normalized_key, normalized_token)


def _metric_support_numeric_token_present(normalized_key: str, normalized_token: str) -> bool:
    token = _normalize_evidence_key(normalized_token)
    if token == "confidence":
        return normalized_key == "confidence" or normalized_key.endswith("_confidence")
    key_parts = normalized_key.split("_")
    token_parts = token.split("_")
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    return any(
        _key_parts_match_token(key_parts[start:start + len(token_parts)], token_parts)
        for start in range(0, len(key_parts) - len(token_parts) + 1)
    )


def _is_positive_numeric_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value > 0


def _has_confidence_interval_bounds(value: Any) -> bool:
    if isinstance(value, list) and len(value) == 2:
        if not all(_is_finite_numeric_value(item) for item in value):
            return False
        return float(value[0]) <= float(value[1])
    if isinstance(value, dict):
        lower = _first_finite_numeric_key(value, ("lower", "low", "lo", "lower_bound", "ci_lower"))
        upper = _first_finite_numeric_key(value, ("upper", "high", "hi", "upper_bound", "ci_upper"))
        return lower is not None and upper is not None and lower <= upper
    return False


def _first_finite_numeric_key(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = data.get(key)
        if _is_finite_numeric_value(value):
            return float(value)
    return None


def _is_finite_numeric_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_positive_evidence_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return math.isfinite(float(value)) and value > 0
    if isinstance(value, str):
        return _normalize_evidence_text(value) not in _PLACEHOLDER_EVIDENCE_VALUES
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return False


_PLACEHOLDER_EVIDENCE_VALUES = {
    "",
    "false",
    "missing",
    "n a",
    "na",
    "no",
    "none",
    "not applicable",
    "not collected",
    "not done",
    "not measured",
    "null",
    "todo",
    "unknown",
}


def _is_significance_support_key(key: str) -> bool:
    return (
        _is_evaluation_repetition_count_key(key)
        or _statistics_key_matches(key, "n")
        or _statistics_key_matches(key, "samples")
        or any(
            _statistics_key_matches(key, token)
            for token in (
                "n_samples",
                "sample_count",
                "sample_size",
                "n_trials",
                "trial_count",
                "num_samples",
                "num_trials",
                "replicates",
                "repeats",
                "bootstrap_samples",
            )
        )
    )


_ABLATION_LABEL_KEYS = {
    "feature",
    "component",
    "variable",
    "ablation",
    "name",
    "id",
    "removed_feature",
    "removed_component",
    "masked_feature",
    "parameter",
}
_ERROR_ANALYSIS_LABEL_KEYS = {
    "slice",
    "subgroup",
    "group",
    "bucket",
    "segment",
    "case",
    "case_id",
    "class",
    "label",
    "residual_bucket",
    "failure_type",
}
_FAIRNESS_LABEL_KEYS = {
    "attribute",
    "cohort",
    "demographic",
    "group",
    "group_id",
    "protected_attribute",
    "protected_group",
    "segment",
    "slice",
    "subgroup",
}
_ROBUSTNESS_LABEL_KEYS = {
    "condition",
    "fold",
    "id",
    "name",
    "perturbation",
    "repeat",
    "run",
    "run_id",
    "run_label",
    "scenario",
    "seed",
    "seed_id",
    "split",
    "stress_test",
    "trial",
}
_GENERALIZATION_LABEL_KEYS = {
    "cohort",
    "dataset",
    "dataset_id",
    "dataset_name",
    "domain",
    "domain_label",
    "external_source",
    "holdout",
    "ood_source",
    "site",
    "site_id",
    "source",
    "source_label",
    "split",
    "split_id",
    "test_set",
    "validation_set",
}
_CAUSAL_DESIGN_VALUE_TERMS = (
    "backdoor",
    "causal design",
    "causal identification",
    "control group",
    "counterfactual",
    "did",
    "difference in differences",
    "experiment",
    "frontdoor",
    "instrument",
    "instrumental variable",
    "intervention",
    "iv",
    "matched control",
    "matching",
    "propensity",
    "randomized",
    "regression discontinuity",
    "rct",
    "synthetic control",
    "treatment assignment",
)


def _is_causal_design_key(key: Any) -> bool:
    normalized = _normalize_evidence_key(key)
    return any(
        _causal_key_matches(normalized, token)
        for token in CAUSAL_EVIDENCE_TOKENS
        if token not in {"causal_effect", "causal_impact"}
    )


def _causal_key_matches(normalized_key: str, normalized_token: str) -> bool:
    token = _normalize_evidence_key(normalized_token)
    key_parts = [part for part in normalized_key.split("_") if part]
    token_parts = [part for part in token.split("_") if part]
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    for start in range(0, len(key_parts) - len(token_parts) + 1):
        if not _key_parts_match_token(key_parts[start:start + len(token_parts)], token_parts):
            continue
        if _key_prefix_has_negation(key_parts[:start], _EVIDENCE_NEGATION_PREFIX_TOKENS):
            continue
        tail = key_parts[start + len(token_parts):]
        if tail and any(part in _EVIDENCE_METADATA_SUFFIX_TOKENS for part in tail):
            continue
        return True
    return False


def _has_substantive_causal_design_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        text = _normalize_evidence_text(value)
        return text not in _PLACEHOLDER_EVIDENCE_VALUES and any(
            term in text for term in _CAUSAL_DESIGN_VALUE_TERMS
        )
    if isinstance(value, dict):
        return any(_has_substantive_causal_design_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_substantive_causal_design_value(item) for item in value)
    return False


def _has_labeled_numeric_evidence(value: Any, label_keys: set[str]) -> bool:
    if isinstance(value, dict):
        if _dict_has_label(value, label_keys) and _has_metric_numeric_leaf(value):
            return True
        return any(_has_labeled_numeric_evidence(item, label_keys) for item in value.values())
    if isinstance(value, list):
        return any(_has_labeled_numeric_evidence(item, label_keys) for item in value)
    return False


def _has_labeled_or_scalar_measurement(value: Any, key: str, label_keys: set[str]) -> bool:
    if isinstance(value, (dict, list)):
        return _has_labeled_numeric_evidence(value, label_keys)
    if "." in key or "[" in key:
        return False
    return _has_metric_numeric_leaf(value, key)


def _dict_has_label(value: dict[str, Any], label_keys: set[str]) -> bool:
    for key, item in value.items():
        normalized = _normalize_evidence_key(key)
        if normalized in label_keys and _is_substantive_label_value(item):
            return True
    return False


def _is_substantive_label_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False
    normalized = _normalize_evidence_key(value)
    return normalized not in {"", "unknown", "placeholder", "todo", "tbd", "na", "n_a", "none", "null"}


def _has_numeric_matrix(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(row, list)
        and row
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in row)
        for row in value
    )


def _has_reproducibility_group(data: Any, key_predicate: Any) -> bool:
    return any(
        key_predicate(_normalize_evidence_key(key))
        and _is_substantive_reproducibility_value(value)
        for key, value in _walk_named_values(data)
    )


def _is_reproducibility_seed_key(key: str) -> bool:
    return any(_reproducibility_key_matches(key, token) for token in REPRODUCIBILITY_SEED_TOKENS)


def _is_reproducibility_data_key(key: str) -> bool:
    if any(
        _reproducibility_key_matches(key, token)
        for token in ("dataset", "data_source", "fingerprint", "checksum")
    ):
        return True
    return (
        _reproducibility_key_matches(key, "dataset")
        or _reproducibility_key_matches(key, "data")
    ) and _reproducibility_key_matches(key, "hash")


def _is_reproducibility_split_key(key: str) -> bool:
    return any(_reproducibility_key_matches(key, token) for token in REPRODUCIBILITY_SPLIT_TOKENS)


def _is_reproducibility_env_key(key: str) -> bool:
    return any(_reproducibility_key_matches(key, token) for token in REPRODUCIBILITY_ENV_TOKENS)


def _is_reproducibility_code_key(key: str) -> bool:
    return any(
        _reproducibility_key_matches(key, token)
        for token in (*REPRODUCIBILITY_CODE_HASH_TOKENS, *REPRODUCIBILITY_CODE_COMMIT_TOKENS)
    )


def _reproducibility_key_matches(normalized_key: str, normalized_token: str) -> bool:
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def _family_evidence_key_matches(normalized_key: str, normalized_token: str) -> bool:
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def _comparison_evidence_key_matches(normalized_key: str, normalized_token: str) -> bool:
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def _statistics_key_matches(normalized_key: str, normalized_token: str) -> bool:
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def _comparison_collection_key_matches(normalized_key: str, normalized_token: str) -> bool:
    token = _normalize_evidence_key(normalized_token)
    key_parts = normalized_key.split("_")
    token_parts = token.split("_")
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    for start in range(0, len(key_parts) - len(token_parts) + 1):
        if not _key_parts_match_token(key_parts[start:start + len(token_parts)], token_parts):
            continue
        if _key_prefix_has_negation(key_parts[:start], _EVIDENCE_NEGATION_PREFIX_TOKENS):
            continue
        if key_parts[start + len(token_parts):]:
            continue
        return True
    return False


def _leakage_key_matches(normalized_key: str, normalized_token: str) -> bool:
    """Match leakage evidence keys without accepting negated or metadata-only variants."""
    return _token_key_matches_without_metadata_suffix(
        normalized_key,
        normalized_token,
        metadata_suffixes=_EVIDENCE_METADATA_SUFFIX_TOKENS,
        negation_prefixes=_EVIDENCE_NEGATION_PREFIX_TOKENS,
    )


def _token_key_matches_without_metadata_suffix(
    normalized_key: str,
    normalized_token: str,
    *,
    metadata_suffixes: set[str],
    negation_prefixes: set[str] | None = None,
) -> bool:
    token = _normalize_evidence_key(normalized_token)
    key_parts = normalized_key.split("_")
    token_parts = token.split("_")
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    for start in range(0, len(key_parts) - len(token_parts) + 1):
        if not _key_parts_match_token(key_parts[start:start + len(token_parts)], token_parts):
            continue
        if negation_prefixes and _key_prefix_has_negation(key_parts[:start], negation_prefixes):
            continue
        tail = key_parts[start + len(token_parts):]
        if tail and any(part in metadata_suffixes for part in tail):
            continue
        return True
    return False


def _key_prefix_has_negation(prefix_parts: list[str], negation_prefixes: set[str]) -> bool:
    index = 0
    while index < len(prefix_parts):
        part = prefix_parts[index]
        if part not in negation_prefixes:
            index += 1
            continue
        if part == "non" and index + 1 < len(prefix_parts) and prefix_parts[index + 1] in _NON_NEGATING_NON_COMPOUNDS:
            index += 2
            continue
        return True
    return False


def _key_parts_match_token(key_parts: list[str], token_parts: list[str]) -> bool:
    if len(key_parts) != len(token_parts):
        return False
    for index, token_part in enumerate(token_parts):
        key_part = key_parts[index]
        if key_part == token_part:
            continue
        if index == len(token_parts) - 1 and key_part.startswith(token_part):
            suffix = key_part[len(token_part):]
            if suffix.isdigit():
                continue
        return False
    return True


_EVIDENCE_METADATA_SUFFIX_TOKENS = {
    "approach",
    "approaches",
    "artifact",
    "column",
    "columns",
    "description",
    "feature",
    "features",
    "field",
    "fields",
    "file",
    "label",
    "metric",
    "metrics",
    "method",
    "methods",
    "model",
    "models",
    "name",
    "note",
    "notes",
    "path",
    "plan",
    "protocol",
    "rationale",
    "schema",
    "strategy",
    "strategies",
    "template",
    "type",
}


_EVIDENCE_NEGATION_PREFIX_TOKENS = {"non", "no", "not", "without"}
_NON_NEGATING_NON_COMPOUNDS = {"ml", "parametric"}


def _is_substantive_reproducibility_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        text = _normalize_evidence_key(value)
        return text not in _PLACEHOLDER_REPRODUCIBILITY_VALUES
    return not _is_empty(value)


_PLACEHOLDER_REPRODUCIBILITY_VALUES = {
    "",
    "missing",
    "not_applicable",
    "not_collected",
    "not_done",
    "not_measured",
    "not_reported",
    "unknown",
    "todo",
    "tbd",
    "placeholder",
    "n/a",
    "n_a",
    "na",
    "none",
    "null",
}


def _is_substantive_leakage_audit_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value))
    if isinstance(value, str):
        text = value.strip().lower()
        return text not in _PLACEHOLDER_LEAKAGE_AUDIT_VALUES
    return not _is_empty(value)


def _is_substantive_leakage_resolution_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "resolved", "mitigated", "fixed", "clean"}
    return False


_PLACEHOLDER_LEAKAGE_AUDIT_VALUES = {
    "",
    "missing",
    "n/a",
    "na",
    "not applicable",
    "not checked",
    "not collected",
    "not done",
    "not measured",
    "not reported",
    "not run",
    "placeholder",
    "tbd",
    "todo",
    "unknown",
}


def _is_substantive_evidence_leaf(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return not _is_empty(value)


def _numeric_scalar(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False
