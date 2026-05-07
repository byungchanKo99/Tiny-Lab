"""Tests for research plan parser."""
from __future__ import annotations

from pathlib import Path

import pytest
import json

from tiny_lab.errors import PlanError
from tiny_lab.plan import (
    load_plan,
    pending_phases,
    next_pending_phase,
    repair_plan_quality_issues,
    render_plan_quality_contract,
    update_phase_status,
    validate_plan_quality,
)


def _baseline_results_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "baseline": {"type": "string"},
                "mae_mean": {"type": "number"},
            },
        },
    }


def _prior_work_results_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "prior_work": {"type": "string"},
                "mae_mean": {"type": "number"},
            },
        },
    }


def _per_fold_metrics_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "fold": {"type": "integer"},
                "metric_value": {"type": "number"},
            },
        },
    }


@pytest.fixture()
def plan_dir(tmp_path: Path) -> Path:
    (tmp_path / "research" / "iter_1").mkdir(parents=True)
    plan = {
        "name": "test",
        "metric": {"name": "loss", "direction": "minimize"},
        "phases": [
            {"id": "p0", "status": "pending", "depends_on": [], "type": "script"},
            {"id": "p1", "status": "pending", "depends_on": ["p0"], "type": "script"},
            {"id": "p2", "status": "pending", "depends_on": ["p0", "p1"], "type": "optimize"},
        ],
    }
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps(plan))
    return tmp_path


def _valid_quality_schema() -> dict:
    return {
        "mae_mean": {},
        "mae_std": {},
        "baseline_results": _baseline_results_schema(),
        "improvement_over_baseline": {},
        "feature_importance": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string"},
                    "importance_score": {"type": "number"},
                },
            },
        },
        "fold_count": {},
        "per_fold_metrics": _per_fold_metrics_schema(),
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
        "leakage_found": {},
        "train_test_overlap": {},
        "target_achieved": {},
        "random_seed": {},
        "dataset_fingerprint": {},
        "split_id": {},
        "python_version": {},
        "script_path": {},
        "script_sha256": {},
    }


def _quality_plan_with_schema(schema: dict) -> dict:
    return {
        "name": "schema validation",
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
        "formal_notation": {"prediction": "y_hat = f(X)"},
        "baselines": [
            {"name": "seasonal naive", "type": "non-ML"},
            {"name": "linear regression", "type": "simple ML"},
        ],
        "experiment_checklist": {
            "has_non_ml_baseline": "yes",
            "has_simple_ml_baseline": "yes",
            "has_ablation_study": "yes",
            "has_cross_validation": "yes",
            "has_error_analysis": "yes",
        },
        "phases": [{
            "id": "phase_0",
            "name": "Model comparison",
            "why": "Compare baseline models under a leakage-safe split",
            "status": "pending",
            "depends_on": [],
            "type": "script",
            "methodology": "Run CV, baseline comparison, feature importance, error analysis, and leakage audit.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_0.json",
                    "schema": schema,
                }
            },
            "visualization": ["phase_0_errors.png"],
        }],
    }


class TestLoadPlan:
    def test_loads(self, plan_dir):
        plan = load_plan(plan_dir, 1)
        assert plan["name"] == "test"
        assert len(plan["phases"]) == 3

    def test_missing(self, tmp_path):
        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        with pytest.raises(PlanError):
            load_plan(tmp_path, 1)


class TestPendingPhases:
    def test_initial_only_p0(self, plan_dir):
        plan = load_plan(plan_dir, 1)
        pending = pending_phases(plan)
        assert len(pending) == 1
        assert pending[0]["id"] == "p0"

    def test_after_p0_done(self, plan_dir):
        update_phase_status(plan_dir, 1, "p0", "done")
        plan = load_plan(plan_dir, 1)
        pending = pending_phases(plan)
        assert len(pending) == 1
        assert pending[0]["id"] == "p1"

    def test_after_all_done(self, plan_dir):
        for pid in ["p0", "p1", "p2"]:
            update_phase_status(plan_dir, 1, pid, "done")
        plan = load_plan(plan_dir, 1)
        assert pending_phases(plan) == []

    def test_ignores_malformed_phase_entries(self):
        plan = {
            "phases": [
                "not an object",
                {"id": "p0", "status": "done", "depends_on": []},
                {"id": "p1", "status": "pending", "depends_on": ["p0"]},
                {"id": "p2", "status": "pending", "depends_on": "p1"},
            ]
        }

        pending = pending_phases(plan)

        assert [phase["id"] for phase in pending] == ["p1"]

    def test_todo_status_is_pending_alias(self):
        plan = {
            "phases": [
                {"id": "p0", "status": "todo", "depends_on": [], "type": "script"},
                {"id": "p1", "status": "todo", "depends_on": ["p0"], "type": "script"},
            ]
        }

        pending = pending_phases(plan)

        assert [phase["id"] for phase in pending] == ["p0"]

    def test_returns_empty_for_non_list_phases(self):
        assert pending_phases({"phases": {"id": "p0"}}) == []


class TestNextPendingPhase:
    def test_returns_first(self, plan_dir):
        plan = load_plan(plan_dir, 1)
        p = next_pending_phase(plan)
        assert p is not None
        assert p["id"] == "p0"

    def test_returns_none_when_empty(self, plan_dir):
        for pid in ["p0", "p1", "p2"]:
            update_phase_status(plan_dir, 1, pid, "done")
        plan = load_plan(plan_dir, 1)
        assert next_pending_phase(plan) is None


class TestUpdatePhaseStatus:
    def test_updates(self, plan_dir):
        update_phase_status(plan_dir, 1, "p0", "running")
        plan = load_plan(plan_dir, 1)
        assert plan["phases"][0]["status"] == "running"

    def test_rejects_unknown_phase_id(self, plan_dir):
        with pytest.raises(PlanError, match="Phase not found"):
            update_phase_status(plan_dir, 1, "missing", "done")

        plan = load_plan(plan_dir, 1)
        assert [phase["status"] for phase in plan["phases"]] == ["pending", "pending", "pending"]

    def test_rejects_non_list_phases(self, tmp_path: Path):
        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True)
        (idir / "research_plan.json").write_text(json.dumps({"phases": {"id": "p0"}}))

        with pytest.raises(PlanError, match="phases"):
            update_phase_status(tmp_path, 1, "p0", "done")

    def test_ignores_malformed_phase_entries_before_matching(self, tmp_path: Path):
        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True)
        (idir / "research_plan.json").write_text(json.dumps({
            "phases": [
                "not an object",
                {"status": "pending"},
                {"id": "p0", "status": "pending"},
            ]
        }))

        update_phase_status(tmp_path, 1, "p0", "done")

        plan = load_plan(tmp_path, 1)
        assert plan["phases"][2]["status"] == "done"


class TestPlanQuality:
    def test_plan_quality_contract_renders_plan_ssot(self):
        text = render_plan_quality_contract()

        assert "Experimental Plan Quality Contract" in text
        assert "tiny_lab.plan" in text
        assert "`formal_notation`" in text
        assert "`formal_notation` and `experiment_checklist` must be non-empty" in text
        assert "`metric` must define" in text
        assert "`metric.target`" in text
        assert "`goal.success_criteria`" in text
        assert "Measurable success criteria" in text
        assert "`type` must be one of `script`, `optimize`, `manual`" in text
        assert '`status: "pending"`' in text
        assert '`status: "todo"` is accepted as a pending alias' in text
        assert "`expected_outputs`" in text
        assert "primary metric named by `metric.name`" in text
        assert "numeric primary metric" in text
        assert "baseline-comparison collection evidence" in text
        assert "`baseline_results`" in text
        assert "SOTA/prior-work comparison evidence" in text
        assert "per-fold/split metric evidence" in text
        assert "causal design/identification evidence" in text
        assert "robustness evidence" in text
        assert "generalization evidence" in text
        assert "fairness/bias-audit evidence" in text
        assert "efficiency/resource evidence" in text
        assert "baseline/prior_work/feature/fold/split/slice/run/source/scenario/protected_group" in text
        assert "scoped leakage-audit evidence" in text
        assert "`train_test_overlap`" in text
        assert "`group_overlap`" in text
        assert "goal-achievement evidence" in text
        assert "concrete statistical uncertainty" in text
        assert "concrete statistical significance" in text
        assert "comparison confidence intervals" in text
        assert "support counts alone are not enough" in text
        assert "sample/repetition support" in text
        assert "tiny_lab.evidence" in text

    def test_rejects_weak_experimental_plan(self):
        plan = {
            "name": "weak",
            "metric": {"name": "mae", "direction": "minimize"},
            "phases": [{
                "id": "phase_0",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "train a neural network",
                "expected_outputs": {"report": {"path": "research/iter_1/results/phase_0.json", "schema": {"mae": {}}}},
                "visualization": ["phase_0_loss.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "formal_notation must be non-empty for experimental plans" in issues
        assert "missing non-ML or heuristic baseline" in issues
        assert "missing simple ML baseline" in issues
        assert "missing leakage or split-protocol audit" in issues
        assert any("reproducibility metadata" in issue for issue in issues)

    def test_rejects_unknown_phase_type(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["phases"][0]["type"] = "notebook"

        issues = validate_plan_quality(plan)

        assert "phase_0 type must be one of ['script', 'optimize', 'manual']" in issues

    def test_rejects_unknown_phase_status(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["phases"][0]["status"] = "queued"

        issues = validate_plan_quality(plan)

        assert "phase_0 status must be one of ['pending', 'todo', 'running', 'done', 'skipped']" in issues

    def test_repair_plan_quality_adds_common_missing_evidence_schema_fields(self):
        plan = _quality_plan_with_schema({
            "mae_mean": {},
            "mae_std": {},
            "baseline_results": _baseline_results_schema(),
            "fold_count": {},
            "train_test_overlap": {},
            "target_achieved": {},
            "random_seed": {},
            "dataset_fingerprint": {},
            "split_id": {},
            "python_version": {},
            "script_path": {},
            "script_sha256": {},
        })
        plan["description"] = "Compare against prior work context with ablation and error analysis."
        plan["metric"]["target"] = None

        assert validate_plan_quality(plan, iteration=1)

        changed = repair_plan_quality_issues(plan, iteration=1)

        assert changed is True
        assert validate_plan_quality(plan, iteration=1) == []
        schema = plan["phases"][0]["expected_outputs"]["report"]["schema"]
        assert "prior_work_results" in schema
        assert "ablation_results" in schema
        assert "error_analysis" in schema
        assert "target" not in plan["metric"]

    def test_repair_plan_quality_normalizes_list_checklist(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["experiment_checklist"] = [
            {"item": "non-ML baseline included", "status": "planned"},
            {"item": "cross-validation included", "status": "planned"},
        ]

        changed = repair_plan_quality_issues(plan, iteration=1)

        assert changed is True
        assert isinstance(plan["experiment_checklist"], dict)
        assert validate_plan_quality(plan, iteration=1) == []

    def test_repair_plan_quality_does_not_inject_mae_std_for_non_mae_metric(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["metric"]["name"] = "RMSE"
        plan["metric"]["target"] = None
        schema = plan["phases"][0]["expected_outputs"]["report"]["schema"]
        schema.pop("mae_std", None)
        schema["cv_rmse_std_across_seeds"] = {"type": "number"}

        changed = repair_plan_quality_issues(plan, iteration=1)

        assert changed is True
        assert "mae_std" not in schema
        assert validate_plan_quality(plan, iteration=1) == []

    def test_repair_plan_quality_handles_nonstandard_metric_collection_fields(self):
        plan = _quality_plan_with_schema({
            "WAPE": {},
            "baseline_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "baseline": {"type": "string"},
                        "WAPE": {"type": "number"},
                    },
                },
            },
            "fold_count": {},
            "train_test_overlap": {},
            "target_achieved": {},
            "random_seed": {},
            "dataset_fingerprint": {},
            "split_id": {},
            "python_version": {},
            "script_path": {},
            "script_sha256": {},
        })
        plan["metric"]["name"] = "WAPE"
        plan["metric"]["target"] = None
        plan["description"] = (
            "Compare against prior work context with ablation, robustness, "
            "held-out generalization, fairness, and error analysis."
        )
        plan["experiment_checklist"]["has_fairness_audit"] = "yes"
        plan["experiment_checklist"]["has_robustness_checks"] = "yes"
        plan["experiment_checklist"]["has_generalization_check"] = "yes"

        assert validate_plan_quality(plan, iteration=1)

        changed = repair_plan_quality_issues(plan, iteration=1)

        assert changed is True
        assert validate_plan_quality(plan, iteration=1) == []
        schema = plan["phases"][0]["expected_outputs"]["report"]["schema"]
        assert schema["ablation_results"]["items"]["properties"]["metric_value"]["type"] == "number"
        assert schema["robustness_results"]["items"]["properties"]["metric_value"]["type"] == "number"
        assert schema["external_validation_results"]["items"]["properties"]["metric_value"]["type"] == "number"
        assert schema["fairness_by_group"]["items"]["properties"]["metric_value"]["type"] == "number"

    def test_repair_plan_quality_moves_evidence_fields_off_preprocessing_phase(self):
        misplaced_preprocess_schema = {
            "n_rows": {"type": "integer"},
            "leakage_found": {"type": "boolean"},
            "train_test_overlap": {"type": "integer"},
            "random_seed": {"type": "integer"},
            "dataset_fingerprint": {"type": "string"},
            "split_id": {"type": "string"},
            "python_version": {"type": "string"},
            "script_path": {"type": "string"},
            "script_sha256": {"type": "string"},
            "WAPE": {"type": "number"},
            "WAPE_std": {"type": "number"},
            "ci95": {"type": "array", "items": {"type": "number"}},
            "target_achieved": {"type": "boolean"},
            "baseline_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "baseline": {"type": "string"},
                        "WAPE": {"type": "number"},
                    },
                },
            },
            "prior_work_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "prior_work": {"type": "string"},
                        "WAPE": {"type": "number"},
                    },
                },
            },
            "ablation_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ablation": {"type": "string"},
                        "metric_value": {"type": "number"},
                    },
                },
            },
        }
        plan = _quality_plan_with_schema(misplaced_preprocess_schema)
        plan["metric"]["name"] = "WAPE"
        plan["metric"]["target"] = None
        plan["description"] = (
            "Compare against prior work with ablation, robustness, held-out "
            "generalization, fairness, and error analysis."
        )
        plan["success_criteria"] = "All planned phase artifacts validate and no leakage is found."
        plan["experiment_checklist"]["has_fairness_audit"] = "yes"
        plan["experiment_checklist"]["has_robustness_checks"] = "yes"
        plan["experiment_checklist"]["has_generalization_check"] = "yes"
        plan["phases"][0].update({
            "id": "phase_0_preprocess",
            "name": "Data Preprocessing and Leakage Audit",
            "why": "Prepare the dataset and verify the split before any model evaluation.",
            "methodology": "Aggregate rows, build split index, and run leakage audit.",
        })
        plan["phases"].append({
            "id": "phase_1_final_comparison",
            "name": "Final Method Comparison and Error Analysis",
            "why": "Compare model and baseline WAPE, evaluate ablations, and summarize error slices.",
            "status": "pending",
            "depends_on": ["phase_0_preprocess"],
            "type": "script",
            "methodology": (
                "Run final model comparison, baseline evaluation, ablation summary, "
                "held-out robustness checks, fairness audit, and error analysis."
            ),
            "expected_outputs": {
                "report": {
                    "path": "research/iter_1/results/phase_1_final_comparison.json",
                    "schema": {
                        "fold_count": {"type": "integer"},
                        "random_seed": {"type": "integer"},
                        "dataset_fingerprint": {"type": "string"},
                        "split_id": {"type": "string"},
                        "python_version": {"type": "string"},
                        "script_path": {"type": "string"},
                        "script_sha256": {"type": "string"},
                    },
                },
            },
            "visualization": ["phase_1_final_comparison.png"],
        })

        changed = repair_plan_quality_issues(plan, iteration=1)

        assert changed is True
        assert validate_plan_quality(plan, iteration=1) == []
        preprocess_schema = plan["phases"][0]["expected_outputs"]["report"]["schema"]
        final_schema = plan["phases"][1]["expected_outputs"]["report"]["schema"]
        for key in (
            "WAPE",
            "WAPE_std",
            "ci95",
            "target_achieved",
            "baseline_results",
            "prior_work_results",
            "ablation_results",
        ):
            assert key not in preprocess_schema
        assert "leakage_found" in preprocess_schema
        assert "train_test_overlap" in preprocess_schema
        assert final_schema["WAPE"]["type"] == "number"
        assert final_schema["baseline_results"]["items"]["properties"]["WAPE"]["type"] == "number"
        assert final_schema["prior_work_results"]["items"]["properties"]["WAPE"]["type"] == "number"
        assert final_schema["ablation_results"]["items"]["properties"]["metric_value"]["type"] == "number"

    def test_rejects_experimental_plan_without_checklist(self):
        plan = {
            "name": "missing checklist",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": _per_fold_metrics_schema(),
                            "baseline_results": {},
                            "feature_importance": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "feature": {"type": "string"},
                                        "importance_score": {"type": "number"},
                                    },
                                },
                            },
                            "error_analysis": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "slice": {"type": "string"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "success_criteria_met": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "experiment_checklist must be a non-empty object" in issues

    def test_rejects_empty_formal_notation(self):
        plan = {
            "name": "empty notation",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "feature_importance": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "feature": {"type": "string"},
                                        "importance_score": {"type": "number"},
                                    },
                                },
                            },
                            "error_analysis": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "slice": {"type": "string"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "success_criteria_met": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "formal_notation must be non-empty for experimental plans" in issues

    def test_accepts_rigorous_experimental_plan(self):
        plan = {
            "name": "rigorous",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [
                {
                    "id": "phase_0",
                    "name": "Leakage-safe split audit",
                    "why": "Avoid train/test leakage before modeling",
                    "status": "pending",
                    "depends_on": [],
                    "type": "script",
                    "methodology": "Create a held-out split protocol and check duplicate leakage.",
                    "expected_outputs": {
                        "report": {
                            "path": "research/iter_1/results/phase_0.json",
                            "schema": {
                                "n_samples": {},
                                "leakage_found": {},
                                "train_test_overlap": {},
                                "fold_count": {},
                                "per_fold_metrics": _per_fold_metrics_schema(),
                                "random_seed": {},
                                "dataset_fingerprint": {},
                                "split_id": {},
                                "python_version": {},
                                "script_path": {},
                                "script_sha256": {},
                            },
                        }
                    },
                    "visualization": ["phase_0_split_profile.png"],
                },
                {
                    "id": "phase_1",
                    "name": "Baselines and ablation error analysis",
                    "why": "Compare seasonal naive and linear regression under the same metric",
                    "status": "pending",
                    "depends_on": ["phase_0"],
                    "type": "script",
                    "methodology": "Run seasonal naive, linear regression, ablation, and residual error analysis over CV folds.",
                    "expected_outputs": {
                        "report": {
                            "path": "research/iter_1/results/phase_1.json",
                            "schema": {
                                "mae_mean": {},
                                "mae_std": {},
                                "ci95": {},
                                "min": {},
                                "max": {},
                                "fold_count": {},
                                "baseline_results": _baseline_results_schema(),
                                "improvement_over_baseline": {},
                                "feature_importance": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "feature": {"type": "string"},
                                            "importance_score": {"type": "number"},
                                        },
                                    },
                                },
                                "error_analysis": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "slice": {"type": "string"},
                                            "mae_mean": {"type": "number"},
                                        },
                                    },
                                },
                                "target_achieved": {},
                                "random_seed": {},
                                "dataset_fingerprint": {},
                                "split_id": {},
                                "environment": {},
                                "script_path": {},
                                "script_sha256": {},
                            },
                        }
                    },
                    "visualization": ["phase_1_error_analysis.png"],
                },
            ],
        }

        assert validate_plan_quality(plan) == []

    def test_accepts_numeric_string_metric_target_from_shared_contract(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["metric"]["target"] = "0.5"

        assert validate_plan_quality(plan) == []

    def test_rejects_experimental_plan_without_success_criteria(self):
        plan = {
            "name": "no success criteria",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": _per_fold_metrics_schema(),
                            "baseline_results": _baseline_results_schema(),
                            "feature_importance": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "feature": {"type": "string"},
                                        "importance_score": {"type": "number"},
                                    },
                                },
                            },
                            "error_analysis": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "slice": {"type": "string"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "success_criteria_met": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "experimental plan must define metric.target or goal.success_criteria" in issues

    def test_accepts_goal_success_criteria_instead_of_metric_target(self):
        plan = {
            "name": "goal criteria",
            "metric": {"name": "mae", "direction": "minimize"},
            "goal": {"success_criteria": "Reduce MAE below the seasonal naive baseline by at least 10%."},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": _per_fold_metrics_schema(),
                            "baseline_results": _baseline_results_schema(),
                            "feature_importance": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "feature": {"type": "string"},
                                        "importance_score": {"type": "number"},
                                    },
                                },
                            },
                            "error_analysis": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "slice": {"type": "string"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "success_criteria_met": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        assert validate_plan_quality(plan) == []

    def test_rejects_vague_goal_success_criteria_without_metric_target(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["metric"].pop("target")
        plan["goal"] = {"success_criteria": "Improve model quality over the baseline."}

        issues = validate_plan_quality(plan)

        assert "experimental plan success_criteria must be measurable" in issues

    def test_accepts_all_or_no_success_criteria_without_metric_target(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["metric"].pop("target")
        plan["goal"] = {"success_criteria": [
            "All planned result artifacts satisfy the declared schemas.",
            "No leakage audit reports train/test overlap.",
        ]}

        assert validate_plan_quality(plan) == []

    def test_rejects_success_criteria_plan_without_goal_achievement_schema(self):
        plan = {
            "name": "missing target flag schema",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.4},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert any("must request target_achieved" in issue for issue in issues)

    @pytest.mark.parametrize(
        ("report_path", "expected_issue"),
        [
            ("/tmp/phase_0.json", "phase_0 expected_outputs.report.path must be relative to project_dir"),
            ("../phase_0.json", "phase_0 expected_outputs.report.path must not contain '..'"),
            ("research/iter_1/results/./phase_0.json", "phase_0 expected_outputs.report.path must not contain '.'"),
            ("outputs/phase_0.json", "phase_0 expected_outputs.report.path must be under research/"),
            (
                "research/iter_x/results/phase_0.json",
                "phase_0 expected_outputs.report.path must be under research/iter_<n>/results/",
            ),
            (
                "research/iter_1/phase_0.json",
                "phase_0 expected_outputs.report.path must be under research/iter_<n>/results/",
            ),
        ],
    )
    def test_rejects_unsafe_report_paths(self, report_path, expected_issue):
        plan = {
            "name": "unsafe path",
            "metric": {"name": "mae", "direction": "minimize"},
            "phases": [{
                "id": "phase_0",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "why": "run experiment",
                "methodology": "train and evaluate under a held-out split",
                "expected_outputs": {
                    "report": {"path": report_path, "schema": {"mae": {"type": "number"}}}
                },
                "visualization": ["phase_0_results.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert expected_issue in issues

    def test_rejects_report_path_for_wrong_iteration_when_iteration_known(self):
        plan = {
            "name": "wrong iteration path",
            "metric": {"name": "mae", "direction": "minimize"},
            "phases": [{
                "id": "phase_0",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "why": "run experiment",
                "methodology": "train and evaluate under a held-out split",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_2/results/phase_0.json",
                        "schema": {"mae": {"type": "number"}},
                    }
                },
                "visualization": ["phase_0_results.png"],
            }],
        }

        issues = validate_plan_quality(plan, iteration=1)

        assert "phase_0 expected_outputs.report.path must be under research/iter_1/results/" in issues

    def test_rejects_experimental_plan_without_valid_metric(self):
        plan = {
            "name": "bad metric",
            "metric": {"name": "", "direction": "sideways"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "metric.name must be a non-empty string" in issues

    def test_rejects_experimental_plan_with_invalid_metric_direction(self):
        plan = {
            "name": "bad metric direction",
            "metric": {"name": "mae", "direction": "lower"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "metric.direction must be 'minimize' or 'maximize'" in issues

    def test_rejects_non_object_phase_without_crashing(self):
        plan = {
            "name": "malformed phase",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [
                "not a phase object",
                {
                    "id": "phase_0",
                    "name": "Model comparison",
                    "why": "Compare linear regression under cross-validation without leakage",
                    "status": "pending",
                    "depends_on": [],
                    "type": "script",
                    "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                    "expected_outputs": {
                        "report": {
                            "path": "research/iter_1/results/phase_0.json",
                            "schema": {
                                "mae_mean": {},
                                "mae_std": {},
                                "fold_count": {},
                                "per_fold_metrics": {},
                                "baseline_results": {},
                                "feature_importance": {},
                                "error_analysis": {},
                                "leakage_found": {},
                                "train_test_overlap": {},
                                "random_seed": {},
                                "dataset_fingerprint": {},
                                "split_id": {},
                                "python_version": {},
                                "script_path": {},
                                "script_sha256": {},
                            },
                        }
                    },
                    "visualization": ["phase_0_errors.png"],
                },
            ],
        }

        issues = validate_plan_quality(plan)

        assert "phase 0 must be an object" in issues

    def test_rejects_checklist_baselines_without_explicit_baseline_entries(self):
        plan = {
            "name": "claimed baselines only",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "Transformer forecaster", "type": "advanced ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "baselines must include an explicit non-ML or heuristic baseline" in issues
        assert "baselines must include an explicit simple ML baseline" in issues

    def test_rejects_single_baseline_entry_that_mentions_both_required_baseline_types(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["baselines"] = [{
            "name": "baseline suite",
            "description": "Compare seasonal naive and linear regression baselines.",
        }]

        issues = validate_plan_quality(plan)

        assert "baselines must include distinct non-ML and simple ML baseline entries" in issues

    def test_rejects_phase_without_reproducibility_schema(self):
        plan = {
            "name": "partial reproducibility",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [
                {
                    "id": "phase_0",
                    "name": "Leakage-safe split audit",
                    "why": "Avoid train/test leakage before modeling",
                    "status": "pending",
                    "depends_on": [],
                    "type": "script",
                    "methodology": "Create a held-out split protocol and check duplicate leakage.",
                    "expected_outputs": {
                        "report": {
                            "path": "research/iter_1/results/phase_0.json",
                            "schema": {
                                "mae_mean": {},
                                "mae_std": {},
                                "random_seed": {},
                                "dataset_fingerprint": {},
                                "split_id": {},
                                "python_version": {},
                                "script_path": {},
                                "script_sha256": {},
                            },
                        }
                    },
                    "visualization": ["phase_0_split_profile.png"],
                },
                {
                    "id": "phase_1",
                    "name": "Model comparison",
                    "why": "Compare linear regression and ablation under CV folds",
                    "status": "pending",
                    "depends_on": ["phase_0"],
                    "type": "script",
                    "methodology": "Run linear regression, ablation, residual error analysis, and cross-validation.",
                    "expected_outputs": {
                        "report": {
                            "path": "research/iter_1/results/phase_1.json",
                            "schema": {"mae_mean": {}, "mae_std": {}, "ci95": {}},
                        }
                    },
                    "visualization": ["phase_1_errors.png"],
                },
            ],
        }

        issues = validate_plan_quality(plan)

        assert any(issue.startswith("phase_1 expected output schema") for issue in issues)

    def test_rejects_reproducibility_schema_with_commit_only_code_provenance(self):
        plan = {
            "name": "commit only provenance",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare baselines under leakage-safe CV folds",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, seasonal naive, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "target_achieved": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "git_commit": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert any(
            "phase_0 expected output schema must request reproducibility metadata" in issue
            for issue in issues
        )

    def test_rejects_reproducibility_schema_without_split_metadata(self):
        plan = {
            "name": "missing split metadata",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare baselines under leakage-safe CV folds",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, seasonal naive, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "target_achieved": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert any(
            "phase_0 expected output schema must request reproducibility metadata" in issue
            for issue in issues
        )

    def test_rejects_phase_without_statistics_schema(self):
        plan = {
            "name": "partial statistics",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression and ablation under CV folds",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert any("phase_0 expected output schema must request statistics" in issue for issue in issues)
        assert any("support counts alone do not satisfy the statistical inference requirement" in issue for issue in issues)

    def test_rejects_plan_without_baseline_comparison_schema(self):
        plan = {
            "name": "no comparison schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under held-out split without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request baseline comparison evidence" in issues

    def test_rejects_plan_with_beats_baseline_only_schema(self):
        plan = {
            "name": "generic baseline flag only",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under held-out split without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "beats_baseline": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "target_achieved": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request baseline comparison evidence" in issues

    def test_rejects_collection_evidence_with_marker_schema_types(self):
        cases = [
            (
                "baseline_results",
                {"type": "boolean"},
                "at least one experimental phase schema must request baseline comparison evidence",
            ),
            (
                "feature_importance",
                {"type": "string"},
                "at least one experimental phase schema must request ablation, feature importance, or sensitivity evidence",
            ),
            (
                "per_fold_metrics",
                {"type": "boolean"},
                "at least one experimental phase schema must request cross-validation or "
                "multiple-split per-fold/split metric evidence",
            ),
            (
                "error_slices",
                {"type": "number"},
                "at least one experimental phase schema must request error analysis evidence",
            ),
        ]

        for field_name, bad_schema, expected_issue in cases:
            schema = _valid_quality_schema()
            schema[field_name] = bad_schema

            issues = validate_plan_quality(_quality_plan_with_schema(schema))

            assert expected_issue in issues

    def test_rejects_unstructured_baseline_collection_schema(self):
        schema = _valid_quality_schema()
        schema["baseline_results"] = {"type": "array"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request baseline comparison evidence" in issues

    def test_rejects_baseline_collection_without_named_metric_schema(self):
        schema = _valid_quality_schema()
        schema["baseline_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "baseline": {"type": "string"},
                    "metric_value": {"type": "number"},
                },
            },
        }

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request baseline comparison evidence" in issues

    def test_rejects_negated_baseline_collection_schema(self):
        for negated_field in ("no_baseline_results", "without_any_baseline_results"):
            schema = _valid_quality_schema()
            schema.pop("baseline_results")
            schema[negated_field] = _baseline_results_schema()

            issues = validate_plan_quality(_quality_plan_with_schema(schema))

            assert "at least one experimental phase schema must request baseline comparison evidence" in issues

    def test_accepts_non_ml_baseline_collection_schema(self):
        schema = _valid_quality_schema()
        schema.pop("baseline_results")
        schema["non_ml_baseline_results"] = _baseline_results_schema()

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request baseline comparison evidence" not in issues

    def test_rejects_sota_plan_without_prior_work_comparison_schema(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["success_criteria"] = "Beat prior work MAE by at least 5%."
        plan["phases"][0]["methodology"] += " Compare against prior work results."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request SOTA or prior-work comparison evidence" in issues

    def test_rejects_published_model_plan_without_prior_work_comparison_schema(self):
        plan = _quality_plan_with_schema(_valid_quality_schema())
        plan["success_criteria"] = "Beat the best published model MAE by at least 5%."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request SOTA or prior-work comparison evidence" in issues

    def test_accepts_sota_plan_with_named_metric_prior_work_schema(self):
        schema = _valid_quality_schema()
        schema["prior_work_results"] = _prior_work_results_schema()
        plan = _quality_plan_with_schema(schema)
        plan["success_criteria"] = "Beat prior work MAE by at least 5%."
        plan["phases"][0]["methodology"] += " Compare against prior work results."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request SOTA or prior-work comparison evidence" not in issues

    def test_rejects_negated_sota_collection_schema(self):
        for negated_field in ("no_prior_work_results", "not_collected_prior_work_results"):
            schema = _valid_quality_schema()
            schema[negated_field] = _prior_work_results_schema()
            plan = _quality_plan_with_schema(schema)
            plan["success_criteria"] = "Beat prior work MAE by at least 5%."
            plan["phases"][0]["methodology"] += " Compare against prior work results."

            issues = validate_plan_quality(plan)

            assert "at least one experimental phase schema must request SOTA or prior-work comparison evidence" in issues

    def test_rejects_sota_comparison_schema_without_named_metric(self):
        schema = _valid_quality_schema()
        schema["prior_work_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prior_work": {"type": "string"},
                    "metric_value": {"type": "number"},
                },
            },
        }
        plan = _quality_plan_with_schema(schema)
        plan["success_criteria"] = "Beat prior work MAE by at least 5%."
        plan["phases"][0]["methodology"] += " Compare against prior work results."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request SOTA or prior-work comparison evidence" in issues

    def test_rejects_unstructured_ablation_collection_schema(self):
        schema = _valid_quality_schema()
        schema["feature_importance"] = {"type": "array"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request ablation, feature importance, or sensitivity evidence" in issues

    def test_rejects_unstructured_per_fold_metric_schema(self):
        schema = _valid_quality_schema()
        schema["per_fold_metrics"] = {"type": "array"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert (
            "at least one experimental phase schema must request cross-validation or "
            "multiple-split per-fold/split metric evidence"
        ) in issues

    def test_rejects_unstructured_error_analysis_collection_schema(self):
        schema = _valid_quality_schema()
        schema["error_slices"] = {"type": "array"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request error analysis evidence" in issues

    def test_accepts_confusion_matrix_schema_as_error_analysis(self):
        schema = _valid_quality_schema()
        schema.pop("error_slices")
        schema["confusion_matrix"] = {"type": "array"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request error analysis evidence" not in issues

    def test_accepts_scalar_calibration_schema_as_error_analysis(self):
        schema = _valid_quality_schema()
        schema.pop("error_slices")
        schema["expected_calibration_error"] = {"type": "number"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request error analysis evidence" not in issues

    def test_rejects_fairness_plan_without_fairness_schema(self):
        schema = _valid_quality_schema()
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_fairness_audit"] = "yes"
        plan["phases"][0]["methodology"] += " Audit demographic parity across protected groups."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request fairness or bias-audit evidence" in issues

    def test_accepts_fairness_plan_with_group_metric_schema(self):
        schema = _valid_quality_schema()
        schema["fairness_by_group"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "protected_group": {"type": "string"},
                    "false_positive_rate": {"type": "number"},
                },
            },
        }
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_fairness_audit"] = "yes"
        plan["phases"][0]["methodology"] += " Audit demographic parity across protected groups."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request fairness or bias-audit evidence" not in issues

    def test_rejects_fairness_plan_with_unstructured_group_array_schema(self):
        schema = _valid_quality_schema()
        schema["fairness_by_group"] = {"type": "array"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_fairness_audit"] = "yes"
        plan["phases"][0]["methodology"] += " Audit demographic parity across protected groups."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request fairness or bias-audit evidence" in issues

    def test_accepts_fairness_plan_with_scalar_fairness_metric_schema(self):
        schema = _valid_quality_schema()
        schema["demographic_parity_difference"] = {"type": "number"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_fairness_audit"] = "yes"
        plan["phases"][0]["methodology"] += " Audit demographic parity across protected groups."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request fairness or bias-audit evidence" not in issues

    def test_rejects_efficiency_plan_without_efficiency_schema(self):
        schema = _valid_quality_schema()
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_efficiency_profile"] = "yes"
        plan["phases"][0]["methodology"] += " Profile inference latency and memory usage."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request efficiency or resource evidence" in issues

    def test_accepts_efficiency_plan_with_latency_schema(self):
        schema = _valid_quality_schema()
        schema["latency_ms"] = {"type": "number"}
        schema["benchmark_device"] = {"type": "string"}
        schema["batch_size"] = {"type": "integer"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_efficiency_profile"] = "yes"
        plan["phases"][0]["methodology"] += " Profile inference latency and memory usage."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request efficiency or resource evidence" not in issues
        assert "at least one experimental phase schema must request efficiency benchmark context" not in issues

    def test_rejects_efficiency_plan_without_benchmark_context_schema(self):
        schema = _valid_quality_schema()
        schema["latency_ms"] = {"type": "number"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_efficiency_profile"] = "yes"
        plan["phases"][0]["methodology"] += " Profile inference latency and memory usage."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request efficiency benchmark context" in issues

    def test_rejects_plan_with_robustness_claim_without_robustness_schema(self):
        schema = _valid_quality_schema()
        schema.pop("per_fold_metrics")
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_robustness_checks"] = "yes"
        plan["phases"][0]["methodology"] += " Report robustness across random seeds."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request robustness or stability evidence" in issues

    def test_accepts_plan_with_robustness_claim_and_repeated_seed_schema(self):
        schema = _valid_quality_schema()
        schema["repeated_seed_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seed": {"type": "integer"},
                    "mae_mean": {"type": "number"},
                },
            },
        }
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_robustness_checks"] = "yes"
        plan["phases"][0]["methodology"] += " Report robustness across random seeds."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request robustness or stability evidence" not in issues

    def test_rejects_plan_with_robustness_claim_and_unstructured_repeated_seed_schema(self):
        schema = _valid_quality_schema()
        schema.pop("per_fold_metrics")
        schema["repeated_seed_results"] = {"type": "array"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_robustness_checks"] = "yes"
        plan["phases"][0]["methodology"] += " Report robustness across random seeds."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request robustness or stability evidence" in issues

    def test_rejects_plan_with_generalization_claim_without_generalization_schema(self):
        schema = _valid_quality_schema()
        schema.pop("split_id")
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_external_validation"] = "yes"
        plan["phases"][0]["methodology"] += " Test generalization on external validation data."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" in issues

    def test_accepts_plan_with_generalization_claim_and_external_validation_schema(self):
        schema = _valid_quality_schema()
        schema["external_validation_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_label": {"type": "string"},
                    "mae_mean": {"type": "number"},
                },
            },
        }
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_external_validation"] = "yes"
        plan["phases"][0]["methodology"] += " Test generalization on external validation data."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" not in issues

    def test_rejects_plan_with_independent_cohort_claim_without_external_schema(self):
        schema = _valid_quality_schema()
        plan = _quality_plan_with_schema(schema)
        plan["phases"][0]["methodology"] += " Test generalization on an independent cohort."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" in issues

    def test_accepts_plan_with_independent_cohort_claim_and_schema(self):
        schema = _valid_quality_schema()
        schema["independent_cohort_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cohort": {"type": "string"},
                    "mae_mean": {"type": "number"},
                },
            },
        }
        plan = _quality_plan_with_schema(schema)
        plan["phases"][0]["methodology"] += " Test generalization on an independent cohort."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" not in issues

    def test_rejects_plan_with_external_claim_and_unstructured_external_validation_schema(self):
        schema = _valid_quality_schema()
        schema["external_validation_results"] = {"type": "array"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_external_validation"] = "yes"
        plan["phases"][0]["methodology"] += " Test generalization on external validation data."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" in issues

    def test_rejects_plan_with_external_claim_and_holdout_only_schema(self):
        schema = _valid_quality_schema()
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_external_validation"] = "yes"
        plan["phases"][0]["methodology"] += " Test generalization on external validation data."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" in issues

    def test_rejects_generalization_claim_with_unstructured_holdout_results_schema(self):
        schema = _valid_quality_schema()
        schema.pop("split_id")
        schema["holdout_results"] = {"type": "array"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_generalization_check"] = "yes"
        plan["phases"][0]["methodology"] += " Test generalization on a held-out validation set."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" in issues

    def test_accepts_generalization_claim_with_structured_holdout_results_schema(self):
        schema = _valid_quality_schema()
        schema.pop("split_id")
        schema["holdout_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "split": {"type": "string"},
                    "mae_mean": {"type": "number"},
                },
            },
        }
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_generalization_check"] = "yes"
        plan["phases"][0]["methodology"] += " Test generalization on a held-out validation set."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request held-out, external, or OOD generalization evidence" not in issues

    def test_rejects_plan_with_causal_claim_without_causal_schema(self):
        schema = _valid_quality_schema()
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_causal_design"] = "yes"
        plan["phases"][0]["methodology"] += " Estimate the causal effect with a matched control design."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request causal design or identification evidence" in issues

    def test_accepts_plan_with_causal_claim_and_causal_schema(self):
        schema = _valid_quality_schema()
        schema["causal_identification"] = {"type": "string"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_causal_design"] = "yes"
        plan["phases"][0]["methodology"] += " Estimate the causal effect with a matched control design."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request causal design or identification evidence" not in issues

    def test_rejects_plan_with_causal_claim_and_effect_only_schema(self):
        schema = _valid_quality_schema()
        schema["causal_effect"] = {"type": "number"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_causal_design"] = "yes"
        plan["phases"][0]["methodology"] += " Estimate the causal effect with a matched control design."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request causal design or identification evidence" in issues

    def test_rejects_plan_with_causal_claim_and_boolean_marker_schema(self):
        schema = _valid_quality_schema()
        schema["causal_design"] = {"type": "boolean"}
        plan = _quality_plan_with_schema(schema)
        plan["experiment_checklist"]["has_causal_design"] = "yes"
        plan["phases"][0]["methodology"] += " Estimate the causal effect with a matched control design."

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request causal design or identification evidence" in issues

    def test_rejects_schema_metadata_without_actual_evidence_fields(self):
        schema = {
            "mae_std": {},
            "target_achieved": {},
            "random_seed": {},
            "dataset_fingerprint": {},
            "split_id": {},
            "python_version": {},
            "script_path": {},
            "script_sha256": {},
            "description": (
                "Report mae_mean, baseline_results, feature_importance, "
                "per_fold_metrics, error_slices, and train_test_overlap."
            ),
            "required": [
                "mae_mean",
                "baseline_results",
                "feature_importance",
                "per_fold_metrics",
                "error_slices",
                "train_test_overlap",
            ],
        }

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request primary metric `mae` evidence" in issues
        assert "at least one experimental phase schema must request baseline comparison evidence" in issues
        assert (
            "at least one experimental phase schema must request ablation, "
            "feature importance, or sensitivity evidence"
        ) in issues
        assert (
            "at least one experimental phase schema must request cross-validation or "
            "multiple-split per-fold/split metric evidence"
        ) in issues
        assert "at least one experimental phase schema must request error analysis evidence" in issues
        assert "at least one experimental phase schema must request scoped leakage audit evidence" in issues

    def test_rejects_leakage_schema_with_null_marker_field(self):
        schema = _valid_quality_schema()
        schema["train_test_overlap"] = {"type": "null"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request scoped leakage audit evidence" in issues

    def test_accepts_group_overlap_as_scoped_leakage_schema(self):
        schema = _valid_quality_schema()
        schema.pop("leakage_found")
        schema.pop("train_test_overlap")
        schema["group_overlap"] = {"type": "integer"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request scoped leakage audit evidence" not in issues

    def test_accepts_group_overlap_as_plan_leakage_audit_signal(self):
        schema = _valid_quality_schema()
        schema.pop("leakage_found")
        schema.pop("train_test_overlap")
        schema["group_overlap"] = {"type": "integer"}
        plan = _quality_plan_with_schema(schema)
        plan["phases"][0]["why"] = "Compare baseline models under grouped splits"
        plan["phases"][0]["methodology"] = (
            "Run CV, baseline comparison, feature importance, error analysis, and group overlap checks."
        )

        issues = validate_plan_quality(plan)

        assert "missing leakage or split-protocol audit" not in issues

    def test_rejects_reproducibility_schema_terms_without_actual_fields(self):
        schema = _valid_quality_schema()
        for field in (
            "random_seed",
            "dataset_fingerprint",
            "split_id",
            "python_version",
            "script_path",
            "script_sha256",
        ):
            schema.pop(field)
        schema["description"] = (
            "Report random_seed, dataset_fingerprint, split_id, python_version, "
            "script_path, and script_sha256 for reproducibility."
        )
        schema["required"] = [
            "mae_mean",
            "random_seed",
            "dataset_fingerprint",
            "split_id",
            "python_version",
            "script_path",
            "script_sha256",
        ]

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert any(
            "phase_0 expected output schema must request reproducibility metadata" in issue
            for issue in issues
        )

    def test_rejects_reproducibility_schema_metadata_suffix_fields(self):
        replacements = {
            "random_seed": "random_seed_method",
            "dataset_fingerprint": "dataset_fingerprint_method",
            "split_id": "split_id_method",
            "python_version": "python_version_notes",
            "script_path": "script_path_method",
            "script_sha256": "script_sha256_method",
        }

        for actual_field, metadata_field in replacements.items():
            schema = _valid_quality_schema()
            schema.pop(actual_field)
            schema[metadata_field] = {}

            issues = validate_plan_quality(_quality_plan_with_schema(schema))

            assert any(
                "phase_0 expected output schema must request reproducibility metadata" in issue
                for issue in issues
            ), metadata_field

    def test_rejects_reproducibility_schema_negated_fields(self):
        replacements = {
            "random_seed": "no_random_seed",
            "dataset_fingerprint": "no_dataset_fingerprint",
            "split_id": "without_split_id",
            "python_version": "not_python_version",
            "script_path": "no_script_path",
            "script_sha256": "without_script_sha256",
        }

        for actual_field, negated_field in replacements.items():
            schema = _valid_quality_schema()
            schema.pop(actual_field)
            schema[negated_field] = {}

            issues = validate_plan_quality(_quality_plan_with_schema(schema))

            assert any(
                "phase_0 expected output schema must request reproducibility metadata" in issue
                for issue in issues
            ), negated_field

    def test_rejects_reproducibility_schema_with_boolean_marker_field(self):
        schema = _valid_quality_schema()
        schema["random_seed"] = {"type": "boolean"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert any(
            "phase_0 expected output schema must request reproducibility metadata" in issue
            for issue in issues
        )

    def test_rejects_statistics_schema_terms_without_actual_fields(self):
        schema = _valid_quality_schema()
        schema.pop("mae_std")
        schema.pop("fold_count")
        schema["per_fold_metrics"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "split": {"type": "string"},
                    "metric_value": {"type": "number"},
                },
            },
        }
        schema["description"] = "Report mae_std, fold_count, ci95, and n_samples."
        schema["required"] = ["mae_std", "fold_count", "ci95", "n_samples"]

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert any("phase_0 expected output schema must request statistics" in issue for issue in issues)

    def test_rejects_statistics_schema_metadata_suffix_fields(self):
        schema = _valid_quality_schema()
        schema.pop("mae_std")
        schema.pop("fold_count")
        schema["per_fold_metrics"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "split": {"type": "string"},
                    "metric_value": {"type": "number"},
                },
            },
        }
        schema["mae_std_method"] = {}
        schema["p_value_method"] = {}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert any("phase_0 expected output schema must request statistics" in issue for issue in issues)

    def test_rejects_support_count_only_statistics_for_statistical_inference(self):
        schema = _valid_quality_schema()
        schema.pop("mae_std")

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert (
            "at least one experimental phase schema must request statistical uncertainty "
            "or significance evidence such as std, CI, variance, p_value, or comparison CI with "
            "sample/repetition support such as n_samples, n_trials, or fold_count"
        ) in issues

    def test_rejects_statistical_inference_schema_without_support(self):
        schema = _valid_quality_schema()
        schema.pop("fold_count")

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert (
            "phase_0 expected output schema requests statistical uncertainty/significance "
            "but must also request sample/repetition support such as n_samples, n_trials, or fold_count"
        ) in issues

    def test_accepts_p_value_as_statistical_inference_schema(self):
        schema = _valid_quality_schema()
        schema.pop("mae_std")
        schema["p_value"] = {}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert not any("statistical uncertainty or significance evidence" in issue for issue in issues)

    def test_accepts_comparison_ci_as_statistical_inference_schema(self):
        schema = _valid_quality_schema()
        schema.pop("mae_std")
        schema["improvement_ci95"] = {"type": "array", "items": {"type": "number"}}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert not any("statistical uncertainty or significance evidence" in issue for issue in issues)

    def test_rejects_goal_achievement_schema_terms_without_actual_field(self):
        schema = _valid_quality_schema()
        schema.pop("target_achieved")
        schema["description"] = "Report target_achieved."
        schema["required"] = ["target_achieved"]

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert (
            "at least one experimental phase schema must request target_achieved, "
            "goal_achieved, or success_criteria_met evidence"
        ) in issues

    def test_rejects_goal_achievement_schema_metadata_suffix_field(self):
        schema = _valid_quality_schema()
        schema.pop("target_achieved")
        schema["target_achieved_method"] = {}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert (
            "at least one experimental phase schema must request target_achieved, "
            "goal_achieved, or success_criteria_met evidence"
        ) in issues

    def test_rejects_primary_metric_schema_metadata_suffix_field(self):
        schema = _valid_quality_schema()
        schema.pop("mae_mean")
        schema["mae_method"] = {}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request primary metric `mae` evidence" in issues

    def test_rejects_primary_metric_schema_negated_field(self):
        schema = _valid_quality_schema()
        schema.pop("mae_mean")
        schema["no_mae_mean"] = {}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request primary metric `mae` evidence" in issues

    def test_accepts_primary_metric_schema_long_alias_field(self):
        schema = _valid_quality_schema()
        schema.pop("mae_mean")
        schema["mean_absolute_error_mean"] = {}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request primary metric `mae` evidence" not in issues

    def test_accepts_primary_score_schema_with_confidence_score_field(self):
        schema = _valid_quality_schema()
        schema.pop("mae_mean")
        schema["model_confidence_score"] = {}
        plan = _quality_plan_with_schema(schema)
        plan["metric"] = {"name": "score", "direction": "maximize", "target": 0.9}

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request primary metric `score` evidence" not in issues

    def test_rejects_baseline_metric_schema_metadata_suffix_field(self):
        schema = _valid_quality_schema()
        schema["baseline_results"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "baseline": {"type": "string"},
                    "mae_method": {},
                },
            },
        }

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request baseline comparison evidence" in issues

    def test_rejects_labeled_metric_schema_metadata_suffix_field(self):
        schema = _valid_quality_schema()
        schema["feature_importance"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string"},
                    "importance_score_method": {},
                },
            },
        }

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert (
            "at least one experimental phase schema must request ablation, "
            "feature importance, or sensitivity evidence"
        ) in issues

    def test_rejects_plan_without_primary_metric_schema(self):
        plan = {
            "name": "no primary metric schema",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare linear regression under held-out split without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_std": {},
                            "baseline_mae": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "target_achieved": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request primary metric `mae` evidence" in issues

    def test_rejects_non_numeric_primary_metric_schema(self):
        schema = _valid_quality_schema()
        schema["mae_mean"] = {"type": "string"}

        issues = validate_plan_quality(_quality_plan_with_schema(schema))

        assert "at least one experimental phase schema must request primary metric `mae` evidence" in issues

    def test_rejects_plan_without_leakage_evidence_schema(self):
        plan = {
            "name": "no leakage schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare linear regression under held-out split without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request scoped leakage audit evidence" in issues

    def test_rejects_plan_with_leakage_found_only_schema(self):
        plan = {
            "name": "generic leakage schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare linear regression under held-out split without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request scoped leakage audit evidence" in issues

    def test_rejects_plan_without_ablation_evidence_schema(self):
        plan = {
            "name": "no ablation schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare linear regression under held-out split without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, linear regression, ablation, residual error analysis, and cross-validation.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert (
            "at least one experimental phase schema must request ablation, "
            "feature importance, or sensitivity evidence"
        ) in issues

    def test_rejects_plan_without_cross_validation_evidence_schema(self):
        plan = {
            "name": "no cv schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert (
            "at least one experimental phase schema must request cross-validation or "
            "multiple-split per-fold/split metric evidence"
        ) in issues

    def test_rejects_plan_with_fold_count_only_cross_validation_schema(self):
        plan = {
            "name": "fold count only schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "error_analysis": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert (
            "at least one experimental phase schema must request cross-validation or "
            "multiple-split per-fold/split metric evidence"
        ) in issues

    def test_rejects_plan_without_error_analysis_evidence_schema(self):
        plan = {
            "name": "no error schema",
            "metric": {"name": "mae", "direction": "minimize"},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe model comparison",
                "why": "Compare linear regression under cross-validation without leakage",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run cross-validation, linear regression, ablation, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {},
                            "mae_std": {},
                            "fold_count": {},
                            "per_fold_metrics": {},
                            "baseline_results": {},
                            "improvement_over_baseline": {},
                            "feature_importance": {},
                            "leakage_found": {},
                            "train_test_overlap": {},
                            "random_seed": {},
                            "dataset_fingerprint": {},
                            "split_id": {},
                            "python_version": {},
                            "script_path": {},
                            "script_sha256": {},
                        },
                    }
                },
                "visualization": ["phase_0_errors.png"],
            }],
        }

        issues = validate_plan_quality(plan)

        assert "at least one experimental phase schema must request error analysis evidence" in issues

    def test_ignores_non_experimental_review_artifacts(self):
        plan = {
            "name": "review",
            "phases": [{"id": "taxonomy", "status": "pending", "depends_on": [], "type": "manual"}],
        }

        assert validate_plan_quality(plan) == []
