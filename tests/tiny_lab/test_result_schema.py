"""Tests for phase result schema value validation."""
from __future__ import annotations

import json

from tiny_lab.result_schema import (
    schema_expected_fields,
    schema_fields_to_validate,
    validate_finite_numeric_values,
    validate_schema_types,
    validate_substantive_result_values,
)


def test_rejects_empty_reproducibility_metadata():
    data = {
        "random_seed": 7,
        "dataset_fingerprint": "",
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_sha256": "",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "dataset_fingerprint reproducibility metadata must be non-empty" in issues
    assert "script_sha256 reproducibility metadata must be non-empty" in issues


def test_rejects_placeholder_reproducibility_metadata():
    data = {
        "dataset_fingerprint": "unknown",
        "split_id": "not collected",
        "python_version": "not reported",
        "script_path": "not measured",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "dataset_fingerprint reproducibility metadata must not be a placeholder" in issues
    assert "split_id reproducibility metadata must not be a placeholder" in issues
    assert "python_version reproducibility metadata must not be a placeholder" in issues
    assert "script_path reproducibility metadata must not be a placeholder" in issues


def test_rejects_ambiguous_goal_achievement_flags():
    data = {
        "success_criteria_met": "unknown",
        "target_achieved": "placeholder",
        "goal_achieved": 0.5,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "success_criteria_met goal-achievement flag must be a concrete true/false value" in issues
    assert "target_achieved goal-achievement flag must be a concrete true/false value" in issues
    assert "goal_achieved goal-achievement flag must be a concrete true/false value" in issues


def test_accepts_concrete_goal_achievement_flags():
    data = {
        "success_criteria_met": "met",
        "target_achieved": False,
        "goal_achieved": 1,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_does_not_treat_goal_metric_metadata_as_goal_flag():
    data = {
        "goal_metric": "mae",
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_malformed_sha256_reproducibility_metadata():
    data = {
        "dataset_fingerprint": "sha256:abc",
        "script_sha256": "sha256:test",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "dataset_fingerprint sha256 reproducibility metadata must use sha256:<64 hex chars>" in issues
    assert "script_sha256 sha256 reproducibility metadata must use sha256:<64 hex chars>" in issues


def test_rejects_loose_dataset_digest_reproducibility_metadata():
    data = {
        "dataset_fingerprint": "dataset_v1",
        "dataset_hash": "abc123",
        "data_checksum": "checksum_v1",
        "dataset_source": "public-dataset-v1",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "dataset_fingerprint sha256 reproducibility metadata must use sha256:<64 hex chars>" in issues
    assert "dataset_hash sha256 reproducibility metadata must use sha256:<64 hex chars>" in issues
    assert "data_checksum sha256 reproducibility metadata must use sha256:<64 hex chars>" in issues
    assert not any("dataset_source" in issue for issue in issues)


def test_accepts_raw_or_prefixed_sha256_dataset_digest_metadata():
    data = {
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "dataset_hash": "1" * 64,
        "data_checksum": "sha256:" + "abcdef0123456789" * 4,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_composite_sha256_dataset_fingerprint_metadata():
    digest_map = {
        "sales": "sha256:" + "0" * 64,
        "emro": "sha256:" + "1" * 64,
        "item_master": "sha256:" + "abcdef0123456789" * 4,
    }
    data = {
        "fingerprint": json.dumps(digest_map),
        "dataset_fingerprint": digest_map,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_dataset_fingerprint_manifest_with_metadata_and_nested_hashes():
    data = {
        "dataset_fingerprint": {
            "sources": [
                {
                    "path": "data/source.xlsx",
                    "size_bytes": 123,
                    "sheets": [{"name": "Sheet1", "loaded_data_rows": 10}],
                    "sha256": "sha256:" + "0" * 64,
                }
            ],
            "combined_sha256": "sha256:" + "1" * 64,
        }
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_temporal_boundary_fields_as_metadata_not_statistics():
    data = {
        "weekly_target_table": {
            "date_min": "2022-04-15",
            "date_max": "2026-05-01",
            "target_week_start_min": "2022-04-11",
            "target_week_start_max": "2026-04-27",
        }
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_does_not_treat_reproducibility_metadata_suffixes_as_values():
    data = {
        "dataset_fingerprint_method": "",
        "script_sha256_method": "sha256sum research/iter_1/phases/phase_0.py",
        "python_version_notes": "",
        "split_id_method": "stratified split",
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_does_not_treat_negated_reproducibility_fields_as_values():
    data = {
        "no_random_seed": 7,
        "no_dataset_fingerprint": "",
        "without_split_id": "",
        "not_python_version": "",
        "no_script_sha256": "bad",
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_still_rejects_reproducibility_values_with_numeric_suffixes():
    data = {
        "script_sha256": "sha256:test",
        "dataset_hash_1": "",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "script_sha256 sha256 reproducibility metadata must use sha256:<64 hex chars>" in issues
    assert "dataset_hash_1 reproducibility metadata must be non-empty" in issues


def test_rejects_invalid_statistical_values():
    data = {
        "mae_std": -0.1,
        "rmse_std": "not numeric",
        "fold_count": 0,
        "p_value": 1.4,
        "ci95": ["low", "high"],
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "mae_std dispersion statistic must be >= 0" in issues
    assert "rmse_std statistic must be numeric or a numeric list/object" in issues
    assert "fold_count count must be > 0" in issues
    assert "p_value p-value must be between 0 and 1" in issues
    assert "ci95 statistic must be numeric or a numeric list/object" in issues


def test_accepts_zero_based_fold_ids_and_statistic_definitions():
    data = {
        "split_size_summary": {
            "std_definition": "sample standard deviation across repeated splits",
        },
        "evaluation_splits": [
            {"fold_id": 0, "fold": 0, "mae_mean": 0.43},
            {"fold_id": "fold_1", "fold": "fold_1", "mae_mean": 0.41},
        ],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_does_not_treat_statistical_boolean_flags_as_numeric_statistics():
    data = {
        "emro_unit_validation": {
            "per_sku_ratio": {
                "1024236": {
                    "mean_ratio": 2.2,
                    "max_ratio": 43.1,
                    "flag_max_ratio_gt_2": True,
                },
            },
        },
    }

    assert validate_substantive_result_values(data, ["emro_unit_validation"]) == []


def test_rejects_impossible_metric_values():
    data = {
        "mae_mean": -0.1,
        "rmse": -0.2,
        "accuracy": 1.2,
        "auc": -0.01,
        "area_under_roc_mean": 1.2,
        "roc_auc": 1.3,
        "f1_score": 1.4,
        "precision": 1.2,
        "r2": 1.1,
        "r2_mean": 1.2,
        "test_r_squared_mean": 1.3,
        "accuracy_percent": 101,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "mae_mean metric value must be >= 0" in issues
    assert "rmse metric value must be >= 0" in issues
    assert "accuracy metric value must be between 0 and 1" in issues
    assert "auc metric value must be between 0 and 1" in issues
    assert "area_under_roc_mean metric value must be between 0 and 1" in issues
    assert "roc_auc metric value must be between 0 and 1" in issues
    assert "f1_score metric value must be between 0 and 1" in issues
    assert "precision metric value must be between 0 and 1" in issues
    assert "r2 metric value must be <= 1" in issues
    assert "r2_mean metric value must be <= 1" in issues
    assert "test_r_squared_mean metric value must be <= 1" in issues
    assert "accuracy_percent metric value must be between 0 and 100" in issues


def test_rejects_non_positive_efficiency_resource_values():
    data = {
        "latency_ms": 0,
        "throughput": -1,
        "peak_memory_mb": -512,
        "parameter_count": 0,
        "flops": -100,
        "no_latency_ms": -1,
        "latency_ms_method": "local benchmark",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "latency_ms efficiency/resource value must be > 0" in issues
    assert "throughput efficiency/resource value must be > 0" in issues
    assert "peak_memory_mb efficiency/resource value must be > 0" in issues
    assert "parameter_count efficiency/resource value must be > 0" in issues
    assert "flops efficiency/resource value must be > 0" in issues
    assert not any("no_latency_ms" in issue for issue in issues)
    assert not any("latency_ms_method" in issue for issue in issues)


def test_accepts_positive_efficiency_resource_values():
    data = {
        "latency_ms": 12.4,
        "throughput": 128.0,
        "peak_memory_mb": 512,
        "parameter_count": 125000,
        "flops": 1.2e9,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_probability_metric_with_diff_like_word_suffix():
    data = {
        "accuracy_difficulty": 1.2,
        "auc_difficult_cases": -0.01,
        "r2_difficulty": 1.2,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "accuracy_difficulty metric value must be between 0 and 1" in issues
    assert "auc_difficult_cases metric value must be between 0 and 1" in issues
    assert "r2_difficulty metric value must be <= 1" in issues


def test_accepts_actual_derived_metric_probability_deltas():
    data = {
        "accuracy_diff": 1.2,
        "auc_delta": -0.1,
        "r2_difference": 1.2,
        "relative_improvement": -0.05,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_sensitivity_result_containers_with_unbounded_metrics():
    data = {
        "sensitivity_results": {
            "feature": "feature_06",
            "rmse_q1": 12.5,
            "rmse_q2": 8.7,
            "rmse_range_across_quartiles": 3.8,
        },
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_valid_metric_ranges():
    data = {
        "mae_mean": 0.1,
        "rmse": 0.2,
        "accuracy": 0.92,
        "auc": 0.88,
        "area_under_roc_mean": 0.87,
        "roc_auc": 0.86,
        "f1_score": 0.81,
        "r2": -0.2,
        "r2_mean": 0.8,
        "test_r_squared_mean": 0.7,
        "accuracy_percent": 92.0,
        "relative_improvement": -0.05,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_metric_container_with_support_statistics():
    data = {
        "accuracy": {
            "mean": 0.92,
            "std": 0.02,
            "ci95": [0.88, 0.96],
            "n_samples": 100,
            "split_id": "heldout_0",
        },
        "mae": {
            "mean": 0.18,
            "std": 0.01,
            "fold_count": 5,
        },
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_method_row_counts_keyed_by_metric_like_method_names():
    data = {
        "same_rows_audit": {
            "method_row_counts": {
                "b4_simple_ml_decision_tree_sensitivity": 85,
                "m1_regular_product_aware_ridge": 85,
            },
            "row_method_count_min": 7,
            "row_method_count_max": 7,
        },
    }

    fields = [
        "same_rows_audit.method_row_counts.b4_simple_ml_decision_tree_sensitivity",
        "same_rows_audit.method_row_counts.m1_regular_product_aware_ridge",
        "same_rows_audit.row_method_count_min",
        "same_rows_audit.row_method_count_max",
    ]

    assert validate_substantive_result_values(data, fields) == []


def test_rejects_metric_container_with_impossible_metric_value():
    data = {
        "accuracy": {
            "mean": 1.2,
            "n_samples": 100,
        },
        "mae": {
            "mean": -0.1,
            "std": 0.01,
            "fold_count": 5,
        },
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "accuracy metric value must be between 0 and 1" in issues
    assert "mae metric value must be >= 0" in issues


def test_rejects_non_positive_generic_count_statistics():
    data = {
        "n_trials": 0,
        "split_count": 0,
        "num_samples": 0,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "n_trials count must be > 0" in issues
    assert "split_count count must be > 0" in issues
    assert "num_samples count must be > 0" in issues


def test_accepts_top_level_zero_split_counts_for_explicit_no_split_eda_phase():
    data = {
        "phase_id": "p0_weekly_panel_eda_preprocessing",
        "split_protocol": "p0 performs no train/test split and fits no preprocessing.",
        "split_id": "p0_no_split_eda_only",
        "split_count": 0,
        "fold_count": 0,
        "n_samples": 661,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_zero_diagnostic_observation_count():
    data = {
        "seasonal_naive_fallback_log": [
            {"n_same_month_obs_in_train": 0, "fallback_reason": "no_prior_year_same_month"},
        ],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_sensitivity_comparison_values_above_one():
    data = {
        "sensitivity_comparison_origins_1_2": [23.0, 47.5, 36.7],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_shorthand_schema_types_validate_nested_fields():
    data = {
        "comparison_table": [
            {"method": "emro", "WAPE_mean": 10.0, "WAPE_std": None, "beats_baseline": False}
        ],
    }
    schema = {
        "comparison_table": [
            {
                "method": "string",
                "WAPE_mean": "float",
                "WAPE_std": "float",
                "beats_baseline": "bool",
            }
        ]
    }

    issues = validate_schema_types(data, schema, schema_expected_fields(schema))

    assert "comparison_table[0].WAPE_std expected number, got NoneType" in issues


def test_shorthand_schema_types_accept_type_descriptions():
    data = {
        "data_source": ["data/source.xlsx"],
        "dataset_fingerprint": {"sha256": "0" * 64},
        "n_samples": 42,
        "WGT_SUM_std": 1.5,
        "script_path": "research/iter_1/phases/p0.py",
    }
    schema = {
        "type": "object",
        "required": [
            "data_source",
            "dataset_fingerprint",
            "n_samples",
            "WGT_SUM_std",
            "script_path",
        ],
        "properties": {
            "data_source": "array of local Excel source paths",
            "dataset_fingerprint": "object with source path and checksum",
            "n_samples": "integer count of weekly rows",
            "WGT_SUM_std": "number standard deviation",
            "script_path": "string path to generated script",
        },
    }

    assert validate_schema_types(data, schema, schema_expected_fields(schema)) == []


def test_accepts_required_only_object_item_schema_and_checks_presence():
    schema = {
        "type": "object",
        "required": ["metadata_missingness"],
        "properties": {
            "metadata_missingness": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["feature", "missing_pct"],
                },
            },
        },
    }
    data = {
        "metadata_missingness": [
            {"feature": "MSTAV", "missing_pct": 95.66},
            {"feature": "BISMT"},
        ],
    }

    issues = validate_schema_types(data, schema, schema_expected_fields(schema))

    assert "report.metadata_missingness[].required references undeclared fields" not in issues
    assert "metadata_missingness[1].missing_pct is required" in issues


def test_accepts_required_item_fields_not_declared_in_properties_and_checks_presence():
    schema = {
        "type": "object",
        "required": ["baseline_results"],
        "properties": {
            "baseline_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["baseline_type", "WAPE"],
                    "properties": {
                        "WAPE": {"type": "number"},
                    },
                },
            },
        },
    }
    data = {
        "baseline_results": [
            {"baseline_type": "non_ml", "WAPE": 0.72},
            {"WAPE": 0.81},
        ],
    }

    issues = validate_schema_types(data, schema, schema_expected_fields(schema))

    assert not any("required references undeclared" in issue for issue in issues)
    assert "baseline_results[1].baseline_type is required" in issues


def test_accepts_split_ratio_text_matching_row_counts():
    data = {
        "split_protocol": "80/20 holdout",
        "train_rows": 800,
        "test_rows": 200,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_split_ratio_text_conflicting_with_row_counts():
    data = {
        "split_protocol": "80/20 holdout",
        "train_rows": 700,
        "test_rows": 300,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert any("split_protocol split ratio 80/20" in issue for issue in issues)
    assert any("train_rows/test_rows ratio 70/30" in issue for issue in issues)


def test_rejects_split_fractions_that_do_not_sum_to_one():
    data = {
        "train_fraction": 0.8,
        "test_fraction": 0.3,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "train_fraction/test_fraction split fractions must sum to 1" in issues


def test_accepts_nested_split_ratio_consistency():
    data = {
        "split": {
            "split_protocol": "80/20 holdout",
            "train_fraction": 0.8,
            "test_fraction": 0.2,
        },
    }

    assert validate_substantive_result_values(data, ["split"]) == []


def test_accepts_zero_validation_rows_when_temporal_test_split_exists():
    data = {
        "evaluation_splits": [
            {
                "split": "temporal_holdout",
                "train_rows": 149,
                "validation_rows": 0,
                "test_rows": 130,
            }
        ],
    }

    assert validate_substantive_result_values(data, ["evaluation_splits"]) == []


def test_rejects_non_finite_schema_numbers():
    schema = {
        "mae_mean": {"type": "number"},
        "loss": {"type": ["number", "null"]},
    }
    data = {
        "mae_mean": float("nan"),
        "loss": float("inf"),
    }

    issues = validate_schema_types(data, schema, list(data))

    assert "mae_mean expected finite number, got non-finite float" in issues
    assert "loss expected finite number, got non-finite float" in issues


def test_rejects_nested_schema_type_mismatches():
    schema = {
        "run_metadata": {
            "type": "object",
            "properties": {
                "random_seed": {"type": "integer"},
                "environment": {
                    "type": "object",
                    "properties": {
                        "python_version": {"type": "string"},
                    },
                },
            },
        },
    }
    data = {
        "run_metadata": {
            "random_seed": "7",
            "environment": {
                "python_version": 3.11,
            },
        },
    }

    issues = validate_schema_types(data, schema, ["run_metadata"])

    assert "run_metadata.random_seed expected integer, got str" in issues
    assert "run_metadata.environment.python_version expected string, got float" in issues


def test_rejects_properties_schema_without_explicit_object_type_when_value_is_not_object():
    schema = {
        "run_metadata": {
            "properties": {
                "random_seed": {"type": "integer"},
            },
        },
    }
    data = {
        "run_metadata": "seed=7",
    }

    issues = validate_schema_types(data, schema, ["run_metadata"])

    assert "run_metadata expected object, got str" in issues


def test_rejects_nested_array_item_schema_type_mismatches():
    schema = {
        "per_fold_metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fold": {"type": "integer"},
                    "mae": {"type": "number"},
                },
            },
        },
    }
    data = {
        "per_fold_metrics": [
            {"fold": "0", "mae": float("nan")},
        ],
    }

    issues = validate_schema_types(data, schema, ["per_fold_metrics"])

    assert "per_fold_metrics[0].fold expected integer, got str" in issues
    assert "per_fold_metrics[0].mae expected finite number, got non-finite float" in issues


def test_rejects_items_schema_without_explicit_array_type_when_value_is_not_array():
    schema = {
        "per_fold_metrics": {
            "items": {
                "properties": {
                    "fold": {"type": "integer"},
                },
            },
        },
    }
    data = {
        "per_fold_metrics": {"fold": 0},
    }

    issues = validate_schema_types(data, schema, ["per_fold_metrics"])

    assert "per_fold_metrics expected array, got dict" in issues


def test_rejects_array_item_properties_schema_without_explicit_object_type():
    schema = {
        "per_fold_metrics": {
            "type": "array",
            "items": {
                "properties": {
                    "fold": {"type": "integer"},
                },
            },
        },
    }
    data = {
        "per_fold_metrics": ["fold_0"],
    }

    issues = validate_schema_types(data, schema, ["per_fold_metrics"])

    assert "per_fold_metrics[0] expected object, got str" in issues


def test_rejects_present_optional_schema_property_type_mismatch():
    schema = {
        "required": ["mae_mean"],
        "properties": {
            "mae_mean": {"type": "number"},
            "p_value": {"type": "number"},
        },
    }
    data = {
        "mae_mean": 0.42,
        "p_value": "0.2",
    }

    issues = validate_schema_types(data, schema, ["mae_mean"])

    assert schema_fields_to_validate(data, schema, ["mae_mean"]) == ["mae_mean", "p_value"]
    assert "p_value expected number, got str" in issues


def test_validate_schema_types_checks_root_required_without_caller_fields():
    schema = {
        "required": ["mae_mean", "split_id"],
        "properties": {
            "mae_mean": {"type": "number"},
            "split_id": {"type": "string"},
        },
    }
    data = {
        "mae_mean": "0.42",
    }

    issues = validate_schema_types(data, schema, [])

    assert schema_fields_to_validate(data, schema, []) == ["mae_mean", "split_id"]
    assert "mae_mean expected number, got str" in issues
    assert "report.split_id is required" in issues


def test_schema_expected_fields_ignores_malformed_required_definition():
    schema = {
        "required": "score",
        "properties": {
            "score": {"type": "number"},
        },
    }
    data = {"score": 0.9}

    issues = validate_schema_types(data, schema, [])

    assert schema_expected_fields(schema) == ["score"]
    assert "report.required must be a list of strings" in issues
    assert not any("report.s is required" in issue for issue in issues)


def test_rejects_schema_numeric_string_array_and_enum_constraint_violations():
    schema = {
        "required": ["mae_mean", "split_id", "per_fold_metrics", "status"],
        "properties": {
            "mae_mean": {"type": "number", "minimum": 0, "maximum": 1},
            "split_id": {"type": "string", "pattern": r"^fold_\d+$", "minLength": 6},
            "per_fold_metrics": {"type": "array", "minItems": 2, "maxItems": 3},
            "status": {"type": "string", "enum": ["done", "running"]},
        },
    }
    data = {
        "mae_mean": -0.1,
        "split_id": "todo",
        "per_fold_metrics": [{"fold": 0}],
        "status": "pending",
    }

    issues = validate_schema_types(data, schema, ["mae_mean", "split_id", "per_fold_metrics", "status"])

    assert "mae_mean must be >= 0" in issues
    assert "split_id length must be >= 6" in issues
    assert "split_id must match pattern '^fold_\\\\d+$'" in issues
    assert "per_fold_metrics length must be >= 2" in issues
    assert "status expected one of ['done', 'running'], got 'pending'" in issues


def test_rejects_nested_schema_constraints_and_additional_properties():
    schema = {
        "run_metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["random_seed"],
            "properties": {
                "random_seed": {"type": "integer", "exclusiveMinimum": 0},
                "environment": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "python_version": {"type": "string", "const": "3.11"},
                    },
                },
            },
        },
    }
    data = {
        "run_metadata": {
            "random_seed": 0,
            "environment": {
                "python_version": "3.10",
                "platform": "darwin",
            },
            "notes": "extra",
        },
    }

    issues = validate_schema_types(data, schema, ["run_metadata"])

    assert "run_metadata.random_seed must be > 0" in issues
    assert "run_metadata.environment.python_version expected constant '3.11', got '3.10'" in issues
    assert "run_metadata.environment has undeclared fields: ['platform']" in issues
    assert "run_metadata has undeclared fields: ['notes']" in issues


def test_rejects_root_additional_properties():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "mae_mean": {"type": "number"},
        },
    }
    data = {
        "mae_mean": 0.42,
        "unsupported_claim_metric": 0.99,
    }

    issues = validate_schema_types(data, schema, ["mae_mean"])

    assert "report has undeclared fields: ['unsupported_claim_metric']" in issues


def test_rejects_malformed_schema_required_and_properties_definitions():
    schema = {
        "required": ["mae_mean", "ghost_metric"],
        "properties": {
            "mae_mean": {"type": "number"},
            "run_metadata": {
                "type": "object",
                "required": "random_seed",
                "properties": {
                    "random_seed": {"type": "integer"},
                },
            },
            "folds": {
                "type": "array",
                "items": [],
            },
            "bad_properties": {
                "type": "object",
                "properties": [],
            },
        },
    }
    data = {
        "mae_mean": 0.42,
        "run_metadata": {"random_seed": 7},
        "folds": [],
        "bad_properties": {},
    }

    issues = validate_schema_types(data, schema, ["mae_mean"])

    assert "report.ghost_metric is required" in issues
    assert "run_metadata.required must be a list of strings" in issues
    assert "folds.items must be an object" in issues
    assert "bad_properties.properties must be an object" in issues


def test_rejects_unsupported_schema_type_definitions():
    schema = {
        "properties": {
            "mae_mean": {"type": "numbr"},
            "loss": {"type": ["number", "missing"]},
            "status": {"type": []},
            "metadata": {"type": {"kind": "object"}},
        },
    }
    data = {
        "mae_mean": 0.42,
        "loss": 0.1,
        "status": "done",
        "metadata": {},
    }

    issues = validate_schema_types(data, schema, list(data))

    assert any("mae_mean.type must be one of" in issue and "numbr" in issue for issue in issues)
    assert "mae_mean expected numbr, got float" in issues
    assert "loss.type has unsupported values: ['missing']" in issues
    assert "status.type must be a string or non-empty list of strings" in issues
    assert "metadata.type must be a string or non-empty list of strings" in issues


def test_rejects_malformed_schema_constraint_definitions():
    schema = {
        "properties": {
            "status": {"type": "string", "enum": []},
            "duplicate_status": {"type": "string", "enum": ["done", "done"]},
            "split_id": {"type": "string", "pattern": "["},
            "score": {
                "type": "number",
                "minimum": float("nan"),
                "maximum": "1",
                "exclusiveMinimum": "0",
                "exclusiveMaximum": {},
            },
            "tag": {"type": "string", "minLength": -1, "maxLength": 1.5},
            "folds": {"type": "array", "minItems": -1, "maxItems": "3"},
            "closed": {"type": "object", "additionalProperties": "false"},
        },
    }
    data = {
        "status": "done",
        "duplicate_status": "done",
        "split_id": "fold_0",
        "score": 0.9,
        "tag": "ok",
        "folds": [],
        "closed": {},
    }

    issues = validate_schema_types(data, schema, list(data))

    assert "status.enum must be a non-empty list" in issues
    assert "duplicate_status.enum values must be unique" in issues
    assert any(issue.startswith("split_id.pattern is invalid:") for issue in issues)
    assert "score.minimum must be a finite number" in issues
    assert "score.maximum must be a finite number" in issues
    assert "score.exclusiveMinimum must be a boolean or finite number" in issues
    assert "score.exclusiveMaximum must be a boolean or finite number" in issues
    assert "tag.minLength must be a non-negative integer" in issues
    assert "tag.maxLength must be a non-negative integer" in issues
    assert "folds.minItems must be a non-negative integer" in issues
    assert "folds.maxItems must be a non-negative integer" in issues
    assert "closed.additionalProperties must be a boolean or object" in issues


def test_rejects_inconsistent_schema_constraint_bounds():
    schema = {
        "properties": {
            "score": {"type": "number", "minimum": 2, "maximum": 1},
            "tag": {"type": "string", "minLength": 8, "maxLength": 4},
            "folds": {"type": "array", "minItems": 4, "maxItems": 2},
        },
    }
    data = {"score": 1.5, "tag": "abcdef", "folds": [1, 2, 3]}

    issues = validate_schema_types(data, schema, list(data))

    assert "score.minimum must be <= maximum" in issues
    assert "tag.minLength must be <= maxLength" in issues
    assert "folds.minItems must be <= maxItems" in issues


def test_rejects_nested_non_finite_numeric_values():
    data = {
        "baseline_results": [{"mae_mean": float("nan")}],
        "error_slices": [{"mae_mean": float("inf")}],
    }

    issues = validate_finite_numeric_values(data)

    assert "non-finite numeric value at baseline_results[0].mae_mean" in issues
    assert "non-finite numeric value at error_slices[0].mae_mean" in issues


def test_rejects_invalid_confusion_matrix_values():
    data = {
        "confusion_matrix": [[5, -1], [2, 4]],
        "folds": [{"confusion_matrix": [[1, 2, 3], [4, 5, 6]]}],
        "error_analysis": {"confusion_matrix": [[1.5, 2], [3, 4]]},
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "confusion_matrix confusion matrix values must be non-negative integers" in issues
    assert "folds[0].confusion_matrix confusion matrix must be a non-empty square matrix" in issues
    assert "error_analysis.confusion_matrix confusion matrix values must be non-negative integers" in issues


def test_accepts_valid_confusion_matrix():
    data = {
        "confusion_matrix": [[18, 2], [3, 17]],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_non_finite_statistical_values():
    data = {
        "mae_std": float("nan"),
        "ci95": [0.2, float("inf")],
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "mae_std statistic must be finite" in issues
    assert "ci95 statistic must be finite" in issues


def test_rejects_negative_dispersion_statistics_without_metric_name():
    data = {
        "variance": -0.1,
        "standard_error": -0.2,
        "stderr": -0.3,
        "sem": -0.4,
        "standard_deviation": -0.5,
        "stdev": -0.6,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "variance dispersion statistic must be >= 0" in issues
    assert "standard_error dispersion statistic must be >= 0" in issues
    assert "stderr dispersion statistic must be >= 0" in issues
    assert "sem dispersion statistic must be >= 0" in issues
    assert "standard_deviation dispersion statistic must be >= 0" in issues
    assert "stdev dispersion statistic must be >= 0" in issues


def test_support_statistics_are_not_revalidated_as_metric_values():
    data = {
        "mae_std": -0.1,
        "mae_standard_deviation": -0.2,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert issues == [
        "mae_std dispersion statistic must be >= 0",
        "mae_standard_deviation dispersion statistic must be >= 0",
    ]


def test_rejects_uncertainty_evidence_without_sample_or_repetition_support():
    data = {
        "mae_std": 0.03,
        "mae_ci95": [0.39, 0.45],
    }

    issues = validate_substantive_result_values(data, list(data))

    assert (
        "mae_std uncertainty evidence requires sample/repetition support "
        "such as n_samples, n_trials, or fold_count"
    ) in issues
    assert (
        "mae_ci95 uncertainty evidence requires sample/repetition support "
        "such as n_samples, n_trials, or fold_count"
    ) in issues


def test_accepts_uncertainty_evidence_with_sample_or_repetition_support():
    data = {
        "n_samples": 100,
        "mae_std": 0.03,
        "mae_ci95": [0.39, 0.45],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_does_not_treat_statistical_metadata_suffixes_as_statistics():
    data = {
        "mae_std_method": "bootstrap",
        "standard_error_notes": "computed across five folds",
        "p_value_method": "paired t-test",
        "fold_count_description": "five-fold cross validation",
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_does_not_treat_negated_statistical_fields_as_statistics():
    data = {
        "no_mae_std": -0.1,
        "no_p_value": 1.2,
        "not_n_trials": 0,
        "without_ci95": [0.2],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_still_rejects_statistical_values_with_non_metadata_suffixes():
    data = {
        "mae_std_fold": -0.1,
        "p_value_fold_1": 1.2,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "mae_std_fold dispersion statistic must be >= 0" in issues
    assert "p_value_fold_1 p-value must be between 0 and 1" in issues


def test_accepts_non_parametric_p_value_as_statistical_value():
    data = {
        "non_parametric_p_value": 1.2,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "non_parametric_p_value p-value must be between 0 and 1" in issues


def test_rejects_invalid_interval_order():
    data = {
        "improvement_ci95": [0.4, 0.2],
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "improvement_ci95 interval lower bound must be <= upper bound" in issues


def test_rejects_metric_intervals_outside_metric_domain():
    data = {
        "n_samples": 100,
        "mae_ci95": [-0.1, 0.2],
        "accuracy_ci95": [-0.1, 1.2],
        "accuracy_percent_ci95": [-1, 101],
        "r2_ci95": [-0.5, 1.2],
        "improvement_ci95": [-0.1, 0.2],
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "mae_ci95 interval bounds must be >= 0" in issues
    assert "accuracy_ci95 interval bounds must be between 0 and 1" in issues
    assert "accuracy_percent_ci95 interval bounds must be between 0 and 100" in issues
    assert "r2_ci95 interval upper bound must be <= 1" in issues
    assert not any("improvement_ci95" in issue for issue in issues)


def test_accepts_metric_intervals_inside_metric_domain():
    data = {
        "n_samples": 100,
        "mae_ci95": [0.1, 0.2],
        "accuracy_ci95": [0.8, 0.9],
        "accuracy_percent_ci95": [80, 90],
        "r2_ci95": [-0.5, 0.8],
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_interval_fields_without_two_numeric_bounds():
    data = {
        "ci95": [0.2],
        "improvement_confidence_interval": {"lower": 0.1},
        "model_confidence_score": 0.92,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "ci95 interval must provide exactly two numeric bounds" in issues
    assert "improvement_confidence_interval interval must provide exactly two numeric bounds" in issues
    assert not any("model_confidence_score" in issue for issue in issues)


def test_rejects_nested_invalid_statistical_values():
    data = {
        "baseline_results": [{
            "name": "linear regression",
            "mae_std": -0.1,
            "p_value": 1.2,
        }],
        "error_analysis": {
            "slice_metrics": [{
                "slice": "high_noise",
                "fold_count": 0,
            }]
        },
    }

    issues = validate_substantive_result_values(data, ["baseline_results", "error_analysis"])

    assert "baseline_results[0].mae_std dispersion statistic must be >= 0" in issues
    assert "baseline_results[0].p_value p-value must be between 0 and 1" in issues
    assert "error_analysis.slice_metrics[0].fold_count count must be > 0" in issues


def test_rejects_nested_empty_reproducibility_metadata():
    data = {
        "run_metadata": {
            "dataset_fingerprint": "",
            "environment": {
                "python_version": "",
            },
        },
    }

    issues = validate_substantive_result_values(data, ["run_metadata"])

    assert "run_metadata.dataset_fingerprint reproducibility metadata must be non-empty" in issues
    assert "run_metadata.environment.python_version reproducibility metadata must be non-empty" in issues


def test_rejects_significance_flag_contradicting_p_value():
    data = {
        "p_value": 0.21,
        "statistically_significant": True,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "statistically_significant=true contradicts p_value 0.21 > alpha 0.05" in issues


def test_rejects_non_significance_flag_contradicting_p_value():
    data = {
        "p_value": 0.01,
        "statistically_significant": False,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "statistically_significant=false contradicts p_value 0.01 <= alpha 0.05" in issues


def test_rejects_invalid_alpha_thresholds():
    data = {
        "alpha": 0,
        "comparison_results": {
            "linear_regression": {
                "significance_level": 1.2,
            },
        },
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "alpha significance threshold must be > 0 and < 1" in issues
    assert (
        "comparison_results.linear_regression.significance_level "
        "significance threshold must be > 0 and < 1"
    ) in issues


def test_rejects_non_numeric_alpha_threshold():
    data = {
        "alpha": "0.05",
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "alpha significance threshold must be numeric and finite" in issues


def test_alpha_validation_ignores_metadata_and_negated_fields():
    data = {
        "alpha_method": "benjamini-hochberg",
        "no_alpha": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_alpha_validation_ignores_model_hyperparameter_alpha_paths():
    data = {
        "cv_results": [
            {"params": {"alpha": 10.0}, "mean_WAPE": 0.61, "n_folds": 3},
        ],
        "selected_hyperparameters": {
            "ridge": {"alpha": 10.0},
        },
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_metric_validation_ignores_selected_hyperparameter_model_names():
    data = {
        "selected_hyperparameters": {
            "b4_simple_ml_decision_tree_sensitivity": {
                "max_depth": 4,
                "min_samples_leaf": 10,
            },
            "selection_metric": "inner temporal validation WAPE",
        },
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_uses_declared_alpha_threshold():
    data = {
        "n_trials": 5,
        "alpha": 0.2,
        "p_value": 0.12,
        "statistically_significant": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_nested_significance_consistency_uses_nearest_alpha_threshold():
    data = {
        "alpha": 0.05,
        "comparison_results": {
            "linear_regression": {
                "n_trials": 5,
                "alpha": 0.2,
                "p_value": 0.12,
                "significant_improvement": True,
            },
            "decision_tree": {
                "n_trials": 5,
                "p_value": 0.12,
                "significant_improvement": True,
            },
        },
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "comparison_results.decision_tree.significant_improvement=true contradicts p_value 0.12 > alpha 0.05" in issues
    assert not any("linear_regression.significant_improvement" in issue for issue in issues)


def test_rejects_nested_significance_flag_contradicting_p_value():
    data = {
        "comparison_results": {
            "linear_regression": {
                "p_value": 0.21,
                "significant_improvement": True,
            }
        }
    }

    issues = validate_substantive_result_values(data, ["comparison_results"])

    assert "comparison_results.linear_regression.significant_improvement=true contradicts p_value 0.21 > alpha 0.05" in issues


def test_nested_significance_uses_local_p_value_scope():
    data = {
        "comparison_results": {
            "linear_regression": {
                "n_trials": 5,
                "p_value": 0.01,
                "significant_improvement": True,
            },
            "decision_tree": {
                "n_trials": 5,
                "p_value": 0.21,
                "significant_improvement": True,
            },
        }
    }

    issues = validate_substantive_result_values(data, ["comparison_results"])

    assert "comparison_results.decision_tree.significant_improvement=true contradicts p_value 0.21 > alpha 0.05" in issues
    assert not any("linear_regression.significant_improvement" in issue for issue in issues)


def test_nested_non_significance_uses_local_p_value_scope():
    data = {
        "comparison_results": {
            "linear_regression": {
                "n_trials": 5,
                "p_value": 0.01,
                "significant_improvement": True,
            },
            "decision_tree": {
                "n_trials": 5,
                "p_value": 0.21,
                "significant_improvement": False,
            },
        }
    }

    assert validate_substantive_result_values(data, ["comparison_results"]) == []


def test_significance_consistency_ignores_unrelated_p_values():
    data = {
        "normality_p_value": 0.01,
        "significant_improvement": False,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_ignores_diff_like_unrelated_p_value_key():
    data = {
        "difficulty_p_value": 0.21,
        "n_samples": 30,
        "significant_improvement": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_ignores_p_value_metadata_suffix_key():
    data = {
        "p_value_method": 0.21,
        "n_samples": 30,
        "statistically_significant": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_ignores_p_value_resolution_metadata():
    data = {
        "comparison_table": [
            {
                "p_value": 0.347,
                "p_value_resolution": 0.0004997501249375312,
                "alpha": 0.05,
                "statistically_significant": False,
                "n_samples": 85,
            }
        ],
    }

    assert validate_substantive_result_values(data, ["comparison_table"]) == []


def test_generic_significance_flag_prefers_generic_p_value_and_interval_scope():
    data = {
        "p_value": 0.62,
        "p_value_vs_simple_ml": 0.001,
        "alpha": 0.05,
        "improvement_ci95": [-0.07, 0.12],
        "improvement_vs_simple_ml_ci95": [0.02, 0.11],
        "statistically_significant": False,
        "n_samples": 85,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_generic_significance_flag_in_comparison_table_uses_leaf_key_scope():
    data = {
        "comparison_table": [
            {
                "p_value": 0.62,
                "p_value_vs_simple_ml": 0.001,
                "alpha": 0.05,
                "improvement_ci95": [-0.07, 0.12],
                "improvement_vs_simple_ml_ci95": [0.02, 0.11],
                "statistically_significant": False,
                "significant_improvement": False,
                "significant_improvement_vs_simple_ml": True,
                "n_samples": 85,
            }
        ],
    }

    assert validate_substantive_result_values(data, ["comparison_table"]) == []


def test_specific_comparator_significance_flag_uses_specific_p_value_scope():
    data = {
        "p_value": 0.62,
        "p_value_vs_simple_ml": 0.001,
        "alpha": 0.05,
        "improvement_ci95": [-0.07, 0.12],
        "improvement_vs_simple_ml_ci95": [0.02, 0.11],
        "significant_improvement_vs_simple_ml": False,
        "n_samples": 85,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "significant_improvement_vs_simple_ml=false contradicts p_value 0.001 <= alpha 0.05" in issues


def test_significance_consistency_ignores_negated_p_value_key():
    data = {
        "no_p_value": 0.21,
        "n_samples": 30,
        "statistically_significant": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_significance_flag_contradicting_comparison_ci():
    data = {
        "improvement_ci95": [-0.01, 0.12],
        "significant_improvement": True,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "significant_improvement=true contradicts improvement_ci95 crossing zero" in issues


def test_accepts_false_significant_improvement_for_significant_negative_effect():
    data = {
        "p_value": 0.001,
        "alpha": 0.05,
        "improvement_ci95": [-5.5, -2.8],
        "significant_improvement": False,
        "n_samples": 85,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_true_significant_improvement_for_significant_negative_effect():
    data = {
        "p_value": 0.001,
        "alpha": 0.05,
        "improvement_ci95": [-5.5, -2.8],
        "significant_improvement": True,
        "n_samples": 85,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert "significant_improvement=true contradicts improvement_ci95 below zero" in issues


def test_significance_consistency_ignores_diff_like_unrelated_interval_key():
    data = {
        "difficulty_ci95": [0.1, 0.2],
        "n_samples": 30,
        "significant_improvement": False,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_ignores_negated_interval_key():
    data = {
        "no_improvement_ci95": [-0.01, 0.12],
        "n_samples": 30,
        "significant_improvement": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_does_not_treat_precision_as_ci_token():
    data = {
        "precision_improvement": [0.1, 0.2],
        "n_samples": 30,
        "significant_improvement": False,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_significance_consistency_does_not_treat_confidence_score_as_interval():
    data = {
        "confidence_score_improvement": [0.1, 0.2],
        "n_samples": 30,
        "significant_improvement": False,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_consistent_significance_evidence():
    data = {
        "n_trials": 5,
        "p_value": 0.03,
        "improvement_ci95": [0.02, 0.12],
        "statistically_significant": True,
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_rejects_significance_evidence_without_sample_or_repetition_support():
    data = {
        "p_value": 0.03,
        "improvement_ci95": [0.02, 0.12],
        "statistically_significant": True,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert (
        "statistically_significant significance evidence requires sample/repetition support "
        "such as n_samples, n_trials, or fold_count"
    ) in issues


def test_rejects_p_value_without_sample_or_repetition_support():
    data = {
        "p_value": 0.03,
    }

    issues = validate_substantive_result_values(data, list(data))

    assert (
        "p_value significance evidence requires sample/repetition support "
        "such as n_samples, n_trials, or fold_count"
    ) in issues


def test_accepts_nested_significance_evidence_with_parent_fold_count_support():
    data = {
        "fold_count": 5,
        "comparison_results": {
            "linear_regression": {
                "p_value": 0.01,
                "significant_improvement": True,
            },
            "decision_tree": {
                "p_value": 0.21,
                "significant_improvement": False,
            },
        },
    }

    assert validate_substantive_result_values(data, list(data)) == []


def test_accepts_substantive_metadata_and_statistics():
    digest = "sha256:" + "a" * 64
    data = {
        "mae_std": 0.1,
        "fold_count": 5,
        "p_value": 0.04,
        "ci95": [0.2, 0.4],
        "random_seed": 0,
        "dataset_fingerprint": digest,
        "split_id": "fold_0",
        "environment": {"python": "3.11"},
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": digest,
    }

    assert validate_substantive_result_values(data, list(data)) == []
