"""Research plan parser.

research_plan.json defines WHAT experiments to run (phases, methodology,
expected outputs). This module parses and queries it.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .evidence import (
    COMPARISON_INTERVAL_SIGNIFICANCE_TOKENS,
    EFFICIENCY_BENCHMARK_CONTEXT_TOKENS,
    CALIBRATION_ERROR_EVIDENCE_TOKENS,
    EFFICIENCY_EVIDENCE_TOKENS,
    FAIRNESS_EVIDENCE_TOKENS,
    FAIRNESS_SCALAR_EVIDENCE_TOKENS,
    GOAL_ACHIEVEMENT_EVIDENCE_TOKENS,
    REPRODUCIBILITY_CODE_HASH_TOKENS,
    REPRODUCIBILITY_CODE_PATH_TOKENS,
    REPRODUCIBILITY_DATA_SOURCE_TOKENS,
    REPRODUCIBILITY_ENV_TOKENS,
    REPRODUCIBILITY_SEED_TOKENS,
    REPRODUCIBILITY_SPLIT_TOKENS,
    STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS,
    STATISTICS_EVIDENCE_TOKENS,
    SPECIFIC_LEAKAGE_AUDIT_TOKENS,
    UNCERTAINTY_EVIDENCE_TOKENS,
    checklist_yes,
    is_ablation_evidence_key,
    is_baseline_comparison_collection_key,
    is_causal_design_evidence_key,
    is_evaluation_protocol_repeated_collection_key,
    is_error_analysis_evidence_key,
    is_efficiency_evidence_key,
    is_efficiency_benchmark_context_key,
    is_fairness_evidence_key,
    is_external_generalization_evidence_key,
    is_generalization_evidence_key,
    is_metric_evidence_key as _shared_is_metric_evidence_key,
    is_metric_support_numeric_key as _shared_is_metric_support_numeric_key,
    is_robustness_evidence_key,
    is_sota_comparison_collection_key,
    plan_metric_target as _shared_plan_metric_target,
    plan_requires_ablation_evidence,
    plan_requires_causal_evidence,
    plan_requires_error_analysis_evidence,
    plan_requires_efficiency_evidence,
    plan_requires_efficiency_benchmark_context,
    plan_requires_external_generalization_evidence,
    plan_requires_evaluation_protocol_evidence,
    plan_requires_generalization_evidence,
    plan_requires_fairness_evidence,
    plan_requires_robustness_evidence,
)
from .errors import PlanError
from .paths import plan_path, research_results_path_issue


PLAN_REQUIRED_PHASE_FIELDS = (
    "id",
    "why",
    "type",
    "depends_on",
    "methodology",
    "expected_outputs",
    "visualization",
    "status",
)
PLAN_REQUIRED_TOP_LEVEL_FIELDS = (
    "formal_notation",
    "baselines",
    "experiment_checklist",
    "phases",
)
PLAN_ALLOWED_PHASE_TYPES = ("script", "optimize", "manual")
PLAN_ALLOWED_PHASE_STATUSES = ("pending", "todo", "running", "done", "skipped")
PLAN_PENDING_PHASE_STATUSES = ("pending", "todo")


def load_plan(project_dir: Path, iteration: int) -> dict[str, Any]:
    """Load research_plan.json for a given iteration."""
    path = plan_path(project_dir, iteration)
    if not path.exists():
        raise PlanError(f"Research plan not found: {path}")
    data = json.loads(path.read_text())
    if not data or "phases" not in data:
        raise PlanError("Research plan must have 'phases' list")
    return data


def validate_plan_quality(plan: dict[str, Any], iteration: int | None = None) -> list[str]:
    """Return blocking quality issues for an experimental research plan.

    This is intentionally heuristic: the AI validator still performs the
    domain-aware review, while this function catches missing structural
    elements that a serious ML experiment should not proceed without.
    """
    phases = plan.get("phases", [])
    if not isinstance(phases, list) or not phases:
        return ["plan must define at least one phase"]
    if not _looks_experimental(plan):
        return []

    issues: list[str] = []
    _validate_phase_structure(phases, issues, iteration)
    _validate_phase_dag(phases, issues)
    _validate_experimental_coverage(plan, phases, issues)
    return issues


def repair_plan_quality_issues(plan: dict[str, Any], iteration: int | None = None) -> bool:
    """Apply conservative structural repairs for common plan-quality misses."""
    changed = False
    checklist = plan.get("experiment_checklist")
    if not isinstance(checklist, dict) or not checklist:
        plan["experiment_checklist"] = {
            "has_non_ml_baseline": "yes",
            "has_simple_ml_baseline": "yes",
            "has_ablation_study": "yes",
            "has_cross_validation": "yes",
            "has_error_analysis": "yes",
            "has_leakage_audit": "yes",
        }
        changed = True

    metric = plan.get("metric")
    metric_name = "metric_value"
    if isinstance(metric, dict):
        raw_metric_name = metric.get("name")
        if isinstance(raw_metric_name, str) and raw_metric_name.strip():
            metric_name = raw_metric_name.strip()
        if "target" in metric and not _is_finite_number(metric.get("target")):
            metric.pop("target", None)
            changed = True
            if not _has_success_criteria(plan):
                plan["success_criteria"] = (
                    "All planned phase result artifacts satisfy their schemas, include required "
                    "reproducibility metadata, and report no leakage findings."
                )
                changed = True

    phases = plan.get("phases")
    if not isinstance(phases, list):
        return changed
    evidence_phase = _select_plan_quality_evidence_phase(phases)
    structural_phase = _select_plan_quality_structural_phase(phases) or evidence_phase
    if evidence_phase is None or structural_phase is None:
        return changed
    if _remove_misplaced_plan_quality_evidence_fields(phases, evidence_phase, metric_name):
        changed = True

    evidence_report = _phase_report(evidence_phase)
    structural_report = _phase_report(structural_phase)
    if evidence_report is None or structural_report is None:
        return changed
    evidence_schema = evidence_report.get("schema")
    if not isinstance(evidence_schema, dict):
        evidence_schema = {}
        evidence_report["schema"] = evidence_schema
        changed = True
    structural_schema = structural_report.get("schema")
    if not isinstance(structural_schema, dict):
        structural_schema = {}
        structural_report["schema"] = structural_schema
        changed = True

    def ensure(schema: dict[str, Any], key: str, value: Any) -> None:
        nonlocal changed
        existing = schema.get(key)
        if isinstance(existing, dict) and existing:
            return
        if isinstance(existing, list) and existing:
            return
        schema[key] = value
        changed = True

    def ensure_collection(schema: dict[str, Any], key: str, label_key: str, value_key: str) -> None:
        nonlocal changed
        existing = schema.get(key)
        if _collection_schema_has_label_metric(existing, label_key, value_key):
            return
        schema[key] = _labeled_metric_collection_schema(label_key, value_key)
        changed = True

    def any_schema(predicate: Any) -> bool:
        return any(
            predicate(schema)
            for phase in phases
            if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
            for schema in [_phase_report_schema(phase)]
            if schema is not None
        )

    if not any_schema(lambda schema: _schema_requests_primary_metric(schema, metric_name)):
        ensure(evidence_schema, metric_name, {"type": "number"})
    if not any_schema(lambda schema: _schema_requests_baseline_comparison(schema, metric_name)):
        ensure_collection(evidence_schema, "baseline_results", "baseline", metric_name)
    if _plan_requires_sota_comparison_evidence(plan) and not any_schema(
        lambda schema: _schema_requests_sota_comparison(schema, metric_name)
    ):
        ensure_collection(evidence_schema, "prior_work_results", "prior_work", metric_name)
    generic_metric_key = "metric_value"
    if plan_requires_ablation_evidence(plan) and not any_schema(_schema_requests_ablation_evidence):
        ensure_collection(evidence_schema, "ablation_results", "ablation", generic_metric_key)
        ensure_collection(evidence_schema, "feature_importance", "feature", "importance")
    if plan_requires_evaluation_protocol_evidence(plan) and not any_schema(_schema_requests_evaluation_protocol_evidence):
        ensure_collection(evidence_schema, "per_fold_metrics", "fold", generic_metric_key)
    if plan_requires_error_analysis_evidence(plan) and not any_schema(_schema_requests_error_analysis_evidence):
        ensure_collection(evidence_schema, "error_analysis", "slice", generic_metric_key)
    if plan_requires_fairness_evidence(plan) and not any_schema(_schema_requests_fairness_evidence):
        ensure_collection(evidence_schema, "fairness_by_group", "protected_group", generic_metric_key)
    if plan_requires_robustness_evidence(plan) and not any_schema(
        lambda schema: _schema_contains_labeled_metric_collection_field(
            schema,
            is_robustness_evidence_key,
            _ROBUSTNESS_SCHEMA_LABEL_KEYS,
        )
    ):
        ensure_collection(evidence_schema, "robustness_results", "scenario", generic_metric_key)
    if plan_requires_generalization_evidence(plan) and not any_schema(
        lambda schema: _schema_contains_labeled_metric_collection_field(
            schema,
            is_generalization_evidence_key,
            _GENERALIZATION_SCHEMA_LABEL_KEYS,
        )
        or _schema_contains_labeled_metric_collection_field(
            schema,
            is_external_generalization_evidence_key,
            _GENERALIZATION_SCHEMA_LABEL_KEYS,
        )
    ):
        ensure_collection(evidence_schema, "external_validation_results", "source", generic_metric_key)
    if not any_schema(_schema_requests_statistical_support):
        ensure(evidence_schema, "fold_count", {"type": "integer"})
    if not any_schema(_schema_requests_statistical_inference):
        uncertainty_metric_name = re.sub(r"[^A-Za-z0-9]+", "_", metric_name).strip("_") or "metric"
        ensure(evidence_schema, f"{uncertainty_metric_name}_std", {"type": "number"})
        ensure(evidence_schema, "ci95", {"type": "array", "items": {"type": "number"}})
    if _has_success_criteria(plan) and not any_schema(_schema_requests_goal_achievement):
        ensure(evidence_schema, "target_achieved", {"type": "boolean"})
    if not any_schema(_schema_requests_leakage_audit):
        ensure(structural_schema, "train_test_overlap", {"type": "integer"})
        ensure(structural_schema, "leakage_found", {"type": "boolean"})
    ensure(structural_schema, "random_seed", {"type": "integer"})
    ensure(structural_schema, "dataset_fingerprint", {"type": "string"})
    ensure(structural_schema, "split_id", {"type": "string"})
    ensure(structural_schema, "python_version", {"type": "string"})
    ensure(structural_schema, "script_path", {"type": "string"})
    ensure(structural_schema, "script_sha256", {"type": "string"})
    if iteration is not None:
        for phase, report in ((evidence_phase, evidence_report), (structural_phase, structural_report)):
            if report.get("path"):
                continue
            phase_id = phase.get("id") if isinstance(phase.get("id"), str) else "phase_0"
            report["path"] = f"research/iter_{iteration}/results/{phase_id}.json"
            changed = True
    return changed


def render_plan_quality_contract() -> str:
    """Return the shared experimental plan contract for prompts and runner docs."""
    phase_fields = ", ".join(f"`{field}`" for field in PLAN_REQUIRED_PHASE_FIELDS)
    top_level = ", ".join(f"`{field}`" for field in PLAN_REQUIRED_TOP_LEVEL_FIELDS)
    phase_types = ", ".join(f"`{field}`" for field in PLAN_ALLOWED_PHASE_TYPES)
    non_ml = ", ".join(f"`{value}`" for value in _NON_ML_BASELINE_KEYWORDS)
    simple_ml = ", ".join(f"`{value}`" for value in _SIMPLE_ML_BASELINE_KEYWORDS)
    comparison_interval_significance = ", ".join(
        f"`{value}`" for value in COMPARISON_INTERVAL_SIGNIFICANCE_TOKENS[:3]
    )
    return f"""## Experimental Plan Quality Contract (SSOT)

This section is generated from `tiny_lab.plan`; update that module instead of copying plan-quality rules into prompts.

An experimental plan is any plan with `metric`, `baselines`, `experiment_checklist`, or `script`/`optimize` phases. For those plans:

1. Top-level fields must include {top_level}; `formal_notation` and `experiment_checklist` must be non-empty.
2. `metric` must define a non-empty `name` and `direction` of `minimize` or `maximize`.
   The plan must also define either numeric `metric.target` or measurable `goal.success_criteria` / top-level `success_criteria`.
   Measurable success criteria must include a numeric threshold/percentage or an explicit all/every/no/zero condition that can be verified from result artifacts.
3. Each phase must include {phase_fields}, and `type` must be one of {phase_types}.
   New executable phases should use `status: "pending"`; `status: "todo"` is accepted as a pending alias for compatibility.
4. Each phase must define `expected_outputs.report.path` and `expected_outputs.report.schema`.
5. Report paths must be project-relative and under `research/iter_N/results/` for the current iteration.
6. Phase IDs must be unique, `depends_on` must reference known phase IDs, and the dependency graph must be acyclic.
7. `baselines` must explicitly include at least one non-ML or heuristic baseline entry and at least one distinct simple ML baseline entry.
8. Non-ML/heuristic baseline keywords include: {non_ml}.
9. Simple ML baseline keywords include: {simple_ml}.
10. The plan must cover non-ML baseline, simple ML baseline, ablation or feature importance or sensitivity analysis, cross-validation or multiple splits, error analysis, and leakage or split-protocol audit.
11. At least one experimental phase schema must request the numeric primary metric named by `metric.name`, baseline-comparison collection evidence such as `baseline_results` with a baseline label and numeric metric field matching `metric.name`, SOTA/prior-work comparison evidence when SOTA/prior-work comparison is planned or claimed, ablation or feature-importance evidence when applicable, per-fold/split metric evidence when evaluation protocol evidence is applicable, causal design/identification evidence when causal effects are claimed, robustness evidence when robustness/stability is claimed, external/independent/held-out/OOD generalization evidence when generalization is claimed, error-analysis evidence when applicable, fairness/bias-audit evidence when fairness, bias, protected-group, or parity claims are planned, efficiency/resource evidence when latency, throughput, model size, memory, FLOPs, or compute-cost claims are planned, benchmark context when latency/throughput/runtime/memory/compute-cost evidence is planned, scoped leakage-audit evidence such as `train_test_overlap`, `group_overlap`, `target_leakage`, or `group_leakage`, and goal-achievement evidence when the plan defines `metric.target` or success criteria. Baseline-comparison, SOTA/prior-work comparison, ablation, per-fold/split, error-analysis, fairness/bias-audit, robustness, and external/independent/OOD generalization collection schemas must request both a concrete label such as baseline/prior_work/feature/fold/split/slice/run/source/scenario/protected_group and a numeric metric field.
12. Every `script` or `optimize` phase schema must request statistics and reproducibility metadata: seed, dataset fingerprint or source, split protocol, environment, script/code path, and script/code hash. At least one experimental phase schema must request concrete statistical uncertainty such as `std`, `ci95`, or `variance`, or concrete statistical significance such as `p_value` or comparison confidence intervals with prefixes such as {comparison_interval_significance}; support counts alone are not enough for this inference requirement, and uncertainty/significance fields must be paired with sample/repetition support such as `n_samples`, `n_trials`, or `fold_count`.
13. Evidence field-name families are defined by the shared Experimental Evidence Contract from `tiny_lab.evidence`.
"""


def pending_phases(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return executable pending phases, respecting depends_on."""
    all_phases = plan.get("phases", [])
    if not isinstance(all_phases, list):
        return []
    phase_objects = [phase for phase in all_phases if isinstance(phase, dict)]
    done_ids = {
        p["id"]
        for p in phase_objects
        if isinstance(p.get("id"), str) and p.get("status") in ("done", "skipped")
    }

    result = []
    for phase in phase_objects:
        if phase.get("status") not in PLAN_PENDING_PHASE_STATUSES:
            continue
        deps = phase.get("depends_on", [])
        if not isinstance(deps, list):
            continue
        if all(d in done_ids for d in deps):
            result.append(phase)
    return result


def _looks_experimental(plan: dict[str, Any]) -> bool:
    phases = plan.get("phases", [])
    if not isinstance(phases, list):
        return False
    if plan.get("metric") or plan.get("baselines") or plan.get("experiment_checklist"):
        return True
    return any(p.get("type") in ("script", "optimize") for p in phases if isinstance(p, dict))


def _labeled_metric_collection_schema(label_key: str, metric_key: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                label_key: {"type": "string"},
                metric_key: {"type": "number"},
            },
        },
    }


def _collection_schema_has_label_metric(value: Any, label_key: str, metric_key: str) -> bool:
    if isinstance(value, list):
        if not value:
            return False
        first = value[0]
        if isinstance(first, dict):
            return label_key in first and metric_key in first
        return False
    if not isinstance(value, dict):
        return False
    properties = value.get("properties")
    if isinstance(properties, dict) and label_key in properties and metric_key in properties:
        return True
    items = value.get("items")
    if isinstance(items, dict):
        item_properties = items.get("properties")
        return isinstance(item_properties, dict) and label_key in item_properties and metric_key in item_properties
    return False


_PLAN_QUALITY_EVIDENCE_PHASE_POSITIVE_TERMS: tuple[tuple[str, int], ...] = (
    ("method comparison", 12),
    ("model comparison", 12),
    ("final comparison", 10),
    ("comparison", 8),
    ("evaluation", 8),
    ("evaluate", 8),
    ("baseline", 7),
    ("ablation", 7),
    ("model", 6),
    ("feature importance", 6),
    ("error analysis", 6),
    ("holdout", 5),
    ("held-out", 5),
    ("metric", 4),
    ("wape", 4),
    ("mae", 3),
    ("rmse", 3),
)
_PLAN_QUALITY_EVIDENCE_PHASE_NEGATIVE_TERMS: tuple[tuple[str, int], ...] = (
    ("preprocess", 16),
    ("preprocessing", 16),
    ("data preparation", 14),
    ("data processing", 14),
    ("cleaning", 12),
    ("leakage audit", 5),
    ("split index", 5),
    ("schema validation", 4),
)
_PLAN_QUALITY_MIGRATABLE_EVIDENCE_KEYS = {
    "baseline_results",
    "prior_work_results",
    "ablation_results",
    "feature_importance",
    "per_fold_metrics",
    "error_analysis",
    "fairness_by_group",
    "robustness_results",
    "external_validation_results",
    "fold_count",
    "ci95",
    "target_achieved",
}


def _phase_report(phase: Any) -> dict[str, Any] | None:
    if not isinstance(phase, dict):
        return None
    expected_outputs = phase.get("expected_outputs")
    if not isinstance(expected_outputs, dict):
        return None
    report = expected_outputs.get("report")
    return report if isinstance(report, dict) else None


def _phase_report_schema(phase: Any) -> dict[str, Any] | None:
    report = _phase_report(phase)
    if report is None:
        return None
    schema = report.get("schema")
    return schema if isinstance(schema, dict) else None


def _report_phase_candidates(phases: list[Any]) -> list[dict[str, Any]]:
    return [phase for phase in phases if isinstance(phase, dict) and _phase_report(phase) is not None]


def _phase_intent_text(phase: dict[str, Any]) -> str:
    intent = {
        key: phase.get(key)
        for key in ("id", "name", "why", "type", "methodology", "visualization", "depends_on")
        if key in phase
    }
    return _normalized_text(intent)


def _plan_quality_evidence_phase_score(phase: dict[str, Any]) -> int:
    text = _phase_intent_text(phase)
    score = 0
    for term, weight in _PLAN_QUALITY_EVIDENCE_PHASE_POSITIVE_TERMS:
        if term in text:
            score += weight
    for term, weight in _PLAN_QUALITY_EVIDENCE_PHASE_NEGATIVE_TERMS:
        if term in text:
            score -= weight
    return score


def _select_plan_quality_evidence_phase(phases: list[Any]) -> dict[str, Any] | None:
    candidates = _report_phase_candidates(phases)
    executable = [phase for phase in candidates if phase.get("type") in ("script", "optimize")]
    candidates = executable or candidates
    if not candidates:
        return None
    return max(
        enumerate(candidates),
        key=lambda item: (_plan_quality_evidence_phase_score(item[1]), item[0]),
    )[1]


def _select_plan_quality_structural_phase(phases: list[Any]) -> dict[str, Any] | None:
    candidates = _report_phase_candidates(phases)
    if not candidates:
        return None
    leakage_or_preprocess = [
        phase
        for phase in candidates
        if any(term in _phase_intent_text(phase) for term in ("preprocess", "preprocessing", "leakage", "split"))
    ]
    return (leakage_or_preprocess or candidates)[0]


def _migratable_plan_quality_evidence_keys(metric_name: str) -> set[str]:
    uncertainty_metric_name = re.sub(r"[^A-Za-z0-9]+", "_", metric_name).strip("_") or "metric"
    return {
        *(_PLAN_QUALITY_MIGRATABLE_EVIDENCE_KEYS),
        metric_name,
        f"{uncertainty_metric_name}_std",
    }


def _schema_key_matches_any(key: str, candidates: set[str]) -> bool:
    normalized_candidates = {_normalize_schema_key(candidate) for candidate in candidates}
    return str(key) in candidates or _normalize_schema_key(key) in normalized_candidates


def _remove_misplaced_plan_quality_evidence_fields(
    phases: list[Any],
    evidence_phase: dict[str, Any],
    metric_name: str,
) -> bool:
    changed = False
    removable_keys = _migratable_plan_quality_evidence_keys(metric_name)
    for phase in phases:
        if phase is evidence_phase or not isinstance(phase, dict):
            continue
        if _plan_quality_evidence_phase_score(phase) >= 0:
            continue
        schema = _phase_report_schema(phase)
        if not isinstance(schema, dict):
            continue
        for key in list(schema):
            if _schema_key_matches_any(str(key), removable_keys):
                schema.pop(key, None)
                changed = True
    return changed


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_phase_structure(
    phases: list[dict[str, Any]],
    issues: list[str],
    iteration: int | None = None,
) -> None:
    seen: set[str] = set()
    for idx, phase in enumerate(phases):
        if not isinstance(phase, dict):
            issues.append(f"phase {idx} must be an object")
            continue
        phase_id = str(phase.get("id") or f"<phase {idx}>")
        if phase_id in seen:
            issues.append(f"duplicate phase id: {phase_id}")
        seen.add(phase_id)

        missing = [
            field for field in PLAN_REQUIRED_PHASE_FIELDS
            if field not in phase or phase.get(field) in (None, "") or (field != "depends_on" and phase.get(field) == [])
        ]
        if missing:
            issues.append(f"{phase_id} missing required fields: {missing}")
        phase_type = phase.get("type")
        if phase_type is not None and phase_type not in PLAN_ALLOWED_PHASE_TYPES:
            issues.append(
                f"{phase_id} type must be one of {list(PLAN_ALLOWED_PHASE_TYPES)}"
            )
        status = phase.get("status")
        if status is not None and status not in PLAN_ALLOWED_PHASE_STATUSES:
            issues.append(
                f"{phase_id} status must be one of {list(PLAN_ALLOWED_PHASE_STATUSES)}"
            )

        expected = phase.get("expected_outputs")
        if not isinstance(expected, dict):
            issues.append(f"{phase_id} expected_outputs must be an object")
            continue
        report = expected.get("report")
        if not isinstance(report, dict):
            issues.append(f"{phase_id} expected_outputs.report is required")
            continue
        if not report.get("path"):
            issues.append(f"{phase_id} expected_outputs.report.path is required")
        else:
            path_issue = research_results_path_issue(
                report.get("path"),
                iteration,
                field_name="expected_outputs.report.path",
            )
            if path_issue:
                issues.append(f"{phase_id} {path_issue}")
        if not report.get("schema"):
            issues.append(f"{phase_id} expected_outputs.report.schema is required")


def _validate_phase_dag(phases: list[dict[str, Any]], issues: list[str]) -> None:
    ids = [p.get("id") for p in phases if isinstance(p, dict)]
    id_set = {pid for pid in ids if isinstance(pid, str)}
    graph: dict[str, list[str]] = {}

    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_id = phase.get("id")
        if not isinstance(phase_id, str):
            continue
        deps = phase.get("depends_on", [])
        if not isinstance(deps, list):
            issues.append(f"{phase_id} depends_on must be a list")
            deps = []
        unknown = [dep for dep in deps if dep not in id_set]
        if unknown:
            issues.append(f"{phase_id} depends_on unknown phases: {unknown}")
        graph[phase_id] = [dep for dep in deps if dep in id_set]

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return False
        if node in visited:
            return True
        visiting.add(node)
        for dep in graph.get(node, []):
            if not visit(dep):
                return False
        visiting.remove(node)
        visited.add(node)
        return True

    if any(not visit(node) for node in graph):
        issues.append("phase dependency graph must be acyclic")


def _validate_experimental_coverage(
    plan: dict[str, Any],
    phases: list[dict[str, Any]],
    issues: list[str],
) -> None:
    text = _normalized_text(plan)
    checklist = plan.get("experiment_checklist", {})
    baselines = plan.get("baselines")

    formal_issue = _formal_notation_issue(plan.get("formal_notation"))
    if formal_issue:
        issues.append(formal_issue)
    checklist_issue = _experiment_checklist_issue(plan.get("experiment_checklist"))
    if checklist_issue:
        issues.append(checklist_issue)
    metric_issue = _metric_issue(plan.get("metric"))
    if metric_issue:
        issues.append(metric_issue)
    success_criteria_issue = _success_criteria_issue(plan)
    if success_criteria_issue:
        issues.append(success_criteria_issue)
    if not isinstance(baselines, list) or not baselines:
        issues.append("baselines must list non-ML and simple ML comparisons")
    else:
        non_ml_baseline_indices = _baseline_match_indices(baselines, _NON_ML_BASELINE_KEYWORDS)
        simple_ml_baseline_indices = _baseline_match_indices(baselines, _SIMPLE_ML_BASELINE_KEYWORDS)
        if not non_ml_baseline_indices:
            issues.append("baselines must include an explicit non-ML or heuristic baseline")
        if not simple_ml_baseline_indices:
            issues.append("baselines must include an explicit simple ML baseline")
        if (
            non_ml_baseline_indices
            and simple_ml_baseline_indices
            and not set(non_ml_baseline_indices).isdisjoint(simple_ml_baseline_indices)
            and len(set(non_ml_baseline_indices) | set(simple_ml_baseline_indices)) < 2
        ):
            issues.append("baselines must include distinct non-ML and simple ML baseline entries")

    if not (checklist_yes(checklist, "non") or _has_any(text, _NON_ML_BASELINE_KEYWORDS)):
        issues.append("missing non-ML or heuristic baseline")
    if not (checklist_yes(checklist, "simple") or _has_any(text, _SIMPLE_ML_BASELINE_KEYWORDS)):
        issues.append("missing simple ML baseline")
    if not plan_requires_ablation_evidence(plan):
        issues.append("missing ablation, feature importance, or sensitivity analysis")
    if not plan_requires_evaluation_protocol_evidence(plan):
        issues.append("missing cross-validation or multiple-split evaluation")
    if not plan_requires_error_analysis_evidence(plan):
        issues.append("missing error analysis phase or diagnostics")
    if not _has_any(text, _LEAKAGE_AUDIT_PLAN_TERMS):
        issues.append("missing leakage or split-protocol audit")
    issues.extend(_schema_primary_metric_issues(plan, phases))
    issues.extend(_schema_baseline_comparison_issues(plan, phases))
    issues.extend(_schema_sota_comparison_issues(plan, phases))
    issues.extend(_schema_ablation_issues(plan, phases))
    issues.extend(_schema_evaluation_protocol_issues(plan, phases))
    issues.extend(_schema_causal_issues(plan, phases))
    issues.extend(_schema_robustness_issues(plan, phases))
    issues.extend(_schema_generalization_issues(plan, phases))
    issues.extend(_schema_error_analysis_issues(plan, phases))
    issues.extend(_schema_fairness_issues(plan, phases))
    issues.extend(_schema_efficiency_issues(plan, phases))
    issues.extend(_schema_statistics_issues(phases))
    issues.extend(_schema_statistical_inference_issues(phases))
    issues.extend(_schema_leakage_issues(phases))
    issues.extend(_schema_goal_achievement_issues(plan, phases))
    reproducibility_issues = _schema_reproducibility_issues(phases)
    issues.extend(reproducibility_issues)


_NON_ML_BASELINE_KEYWORDS = (
    "non-ml", "non ml", "heuristic", "naive", "statistical baseline",
    "physical baseline", "persistence", "moving average", "seasonal naive",
)
_SIMPLE_ML_BASELINE_KEYWORDS = (
    "simple ml", "linear regression", "logistic regression", "ridge", "lasso",
    "decision tree", "random forest", "xgboost baseline",
)
_LEAKAGE_AUDIT_PLAN_TERMS = (
    "leakage",
    "data leak",
    "train/test",
    "train test",
    "train_test_overlap",
    "held-out",
    "holdout",
    "split protocol",
    "split_audit",
    "target_leakage",
    "temporal_leakage",
    "preprocessing_leakage",
    "group_leakage",
    "duplicate_overlap",
    "duplicate overlap",
    "group_overlap",
    "group overlap",
)


def _metric_issue(metric: Any) -> str | None:
    if not isinstance(metric, dict):
        return "metric must define name and direction"
    name = metric.get("name")
    direction = metric.get("direction")
    if not isinstance(name, str) or not name.strip():
        return "metric.name must be a non-empty string"
    if not isinstance(direction, str) or direction.strip().lower() not in {"minimize", "maximize"}:
        return "metric.direction must be 'minimize' or 'maximize'"
    if "target" in metric and _shared_plan_metric_target({"metric": metric}) is None:
        return "metric.target must be a finite numeric value when provided"
    return None


def _success_criteria_issue(plan: dict[str, Any]) -> str | None:
    if _shared_plan_metric_target(plan) is not None:
        return None
    criteria = plan.get("success_criteria")
    if _non_empty_success_criteria(criteria):
        if _measurable_success_criteria(criteria):
            return None
        return "experimental plan success_criteria must be measurable"
    goal = plan.get("goal")
    goal_criteria = goal.get("success_criteria") if isinstance(goal, dict) else None
    if _non_empty_success_criteria(goal_criteria):
        if _measurable_success_criteria(goal_criteria):
            return None
        return "experimental plan success_criteria must be measurable"
    return "experimental plan must define metric.target or goal.success_criteria"


def _non_empty_success_criteria(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(isinstance(item, str) and item.strip() for item in value)
    if isinstance(value, dict):
        return bool(value)
    return False


_SUCCESS_CRITERIA_NUMERIC_CONTEXT_TOKENS = (
    "%",
    "accuracy",
    "auc",
    "auroc",
    "below",
    "decrease",
    "error",
    "f1",
    "greater than",
    "improve",
    "increase",
    "less than",
    "mae",
    "mse",
    "over",
    "precision",
    "r2",
    "recall",
    "reduce",
    "rmse",
    "score",
    "target",
    "threshold",
    "under",
)
_SUCCESS_CRITERIA_UNIVERSAL_TOKENS = (
    "all",
    "every",
    "no ",
    "none",
    "without",
    "zero",
)


def _measurable_success_criteria(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        return _measurable_success_criteria_text(value)
    if isinstance(value, list):
        criteria = [item for item in value if _non_empty_success_criteria(item)]
        return bool(criteria) and all(_measurable_success_criteria(item) for item in criteria)
    if isinstance(value, dict):
        leaves = [item for item in _success_criteria_leaves(value) if _non_empty_success_criteria(item)]
        return bool(leaves) and all(_measurable_success_criteria(item) for item in leaves)
    return False


def _success_criteria_leaves(value: Any) -> list[Any]:
    if isinstance(value, dict):
        out: list[Any] = []
        for item in value.values():
            out.extend(_success_criteria_leaves(item))
        return out
    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            out.extend(_success_criteria_leaves(item))
        return out
    return [value]


def _measurable_success_criteria_text(value: str) -> bool:
    text = value.strip().lower()
    if not text:
        return False
    has_number = re.search(r"(?<![a-z])[-+]?(?:\d+(?:\.\d+)?|\.\d+)\s*%?", text) is not None
    if has_number and any(token in text for token in _SUCCESS_CRITERIA_NUMERIC_CONTEXT_TOKENS):
        return True
    return any(token in text for token in _SUCCESS_CRITERIA_UNIVERSAL_TOKENS)


def _formal_notation_issue(value: Any) -> str | None:
    if isinstance(value, dict) and value:
        return None
    if isinstance(value, str) and value.strip():
        return None
    return "formal_notation must be non-empty for experimental plans"


def _experiment_checklist_issue(value: Any) -> str | None:
    if isinstance(value, dict) and value:
        return None
    return "experiment_checklist must be a non-empty object"


def _baseline_matches(baseline: Any, keywords: tuple[str, ...]) -> bool:
    if isinstance(baseline, str):
        text = baseline
    elif isinstance(baseline, dict):
        fields = (
            baseline.get("name"),
            baseline.get("id"),
            baseline.get("type"),
            baseline.get("description"),
            baseline.get("method"),
        )
        text = " ".join(str(field) for field in fields if field)
    else:
        return False
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return any(re.sub(r"[^a-z0-9]+", " ", keyword.lower()).strip() in normalized for keyword in keywords)


def _baseline_match_indices(baselines: list[Any], keywords: tuple[str, ...]) -> list[int]:
    return [
        index
        for index, baseline in enumerate(baselines)
        if _baseline_matches(baseline, keywords)
    ]


def _normalized_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _schema_statistics_issues(phases: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for phase in phases:
        if not isinstance(phase, dict) or phase.get("type") not in ("script", "optimize"):
            continue
        phase_id = phase.get("id", "?")
        report = phase.get("expected_outputs", {}).get("report", {})
        if not _schema_requests_statistics(report.get("schema", {})):
            issues.append(
                f"{phase_id} expected output schema must request statistics such as "
                "std, CI, min/max, n, sample counts, or fold counts; "
                "support counts alone do not satisfy the statistical inference requirement"
            )
    return issues


def _schema_statistical_inference_issues(phases: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    has_supported_inference = False
    for phase in phases:
        if not isinstance(phase, dict) or phase.get("type") not in ("script", "optimize"):
            continue
        schema = phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        if not _schema_requests_statistical_inference(schema):
            continue
        if _schema_requests_statistical_support(schema):
            has_supported_inference = True
            continue
        phase_id = phase.get("id", "?")
        issues.append(
            f"{phase_id} expected output schema requests statistical uncertainty/significance "
            "but must also request sample/repetition support such as n_samples, n_trials, or fold_count"
        )
    if has_supported_inference:
        return issues
    if issues:
        return issues
    return [
        "at least one experimental phase schema must request statistical uncertainty "
        "or significance evidence such as std, CI, variance, p_value, or comparison CI with "
        "sample/repetition support such as n_samples, n_trials, or fold_count"
    ]


def _schema_requests_statistical_support(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        _STATISTICAL_SUPPORT_SCHEMA_TOKENS,
        _schema_field_allows_numeric_or_numeric_collection_value,
    )


def _schema_baseline_comparison_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    baselines = plan.get("baselines")
    if not isinstance(baselines, list) or not baselines:
        return []
    metric = plan.get("metric")
    metric_name = metric.get("name") if isinstance(metric, dict) else None
    if any(
        _schema_requests_baseline_comparison(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {}),
            metric_name if isinstance(metric_name, str) and metric_name.strip() else None,
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request baseline comparison evidence"]


def _schema_sota_comparison_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not _plan_requires_sota_comparison_evidence(plan):
        return []
    metric = plan.get("metric")
    metric_name = metric.get("name") if isinstance(metric, dict) else None
    if any(
        _schema_requests_sota_comparison(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {}),
            metric_name if isinstance(metric_name, str) and metric_name.strip() else None,
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request SOTA or prior-work comparison evidence"]


def _plan_requires_sota_comparison_evidence(plan: dict[str, Any]) -> bool:
    text = _normalized_text(plan)
    return any(
        token in text
        for token in (
            "leaderboard",
            "literature result",
            "previous work",
            "prior work",
            "published model",
            "published method",
            "published result",
            "sota",
            "state of the art",
            "state-of-the-art",
        )
    )


def _schema_primary_metric_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    metric = plan.get("metric")
    if not isinstance(metric, dict):
        return []
    metric_name = metric.get("name")
    if not isinstance(metric_name, str) or not metric_name.strip():
        return []
    if any(
        _schema_requests_primary_metric(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {}),
            metric_name,
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return [f"at least one experimental phase schema must request primary metric `{metric_name.strip()}` evidence"]


def _schema_requests_primary_metric(schema: Any, metric_name: str) -> bool:
    return _schema_contains_primary_metric_field(schema, metric_name)


def _schema_contains_primary_metric_field(schema: Any, metric_name: str) -> bool:
    if isinstance(schema, dict):
        for key, value in _schema_child_fields(schema):
            key_text = str(key)
            if _schema_field_matches_metric(key_text, metric_name) and _schema_field_allows_numeric_value(value):
                return True
            if _schema_key_names_non_primary_metric_container(key_text):
                continue
            if _schema_contains_primary_metric_field(value, metric_name):
                return True
        for key in ("items", "additionalProperties"):
            value = schema.get(key)
            if _schema_contains_primary_metric_field(value, metric_name):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_contains_primary_metric_field(item, metric_name) for item in schema)
    return False


def _schema_key_names_non_primary_metric_container(key: str) -> bool:
    return (
        is_baseline_comparison_collection_key(key)
        or is_ablation_evidence_key(key)
        or is_evaluation_protocol_repeated_collection_key(key)
        or is_error_analysis_evidence_key(key)
        or is_robustness_evidence_key(key)
        or is_generalization_evidence_key(key)
        or is_external_generalization_evidence_key(key)
    )


def _schema_field_matches_metric(key: str, metric_name: str) -> bool:
    normalized = _normalize_schema_key(key)
    if any(token in normalized for token in ("baseline", "naive", "control", "reference")):
        return False
    if _schema_field_names_non_primary_metric_value(normalized):
        return False
    return _shared_is_metric_evidence_key(key, metric_name)


def _normalize_schema_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


_NON_PRIMARY_SCHEMA_METRIC_CONTEXT_TOKENS = {
    "min",
    "max",
    "count",
    "n",
    "sample",
    "fold",
}


def _schema_field_names_non_primary_metric_value(normalized_key: str) -> bool:
    parts = [part for part in normalized_key.split("_") if part]
    return (
        any(part in _NON_PRIMARY_SCHEMA_METRIC_CONTEXT_TOKENS for part in parts)
        or _shared_is_metric_support_numeric_key(normalized_key)
    )


def _schema_requests_baseline_comparison(schema: Any, metric_name: str | None = None) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_baseline_comparison_collection_key,
        _BASELINE_COMPARISON_SCHEMA_LABEL_KEYS,
        metric_name,
    )


def _schema_requests_sota_comparison(schema: Any, metric_name: str | None = None) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_sota_comparison_collection_key,
        _SOTA_COMPARISON_SCHEMA_LABEL_KEYS,
        metric_name,
    )


def _schema_ablation_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_ablation_evidence(plan):
        return []
    if any(
        _schema_requests_ablation_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request ablation, feature importance, or sensitivity evidence"]


def _schema_requests_ablation_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_ablation_evidence_key,
        _ABLATION_SCHEMA_LABEL_KEYS,
    )


def _schema_evaluation_protocol_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_evaluation_protocol_evidence(plan):
        return []
    if any(
        _schema_requests_evaluation_protocol_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return [
        "at least one experimental phase schema must request cross-validation or "
        "multiple-split per-fold/split metric evidence"
    ]


def _schema_requests_evaluation_protocol_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_evaluation_protocol_repeated_collection_key,
        _EVALUATION_PROTOCOL_SCHEMA_LABEL_KEYS,
    )


def _schema_causal_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_causal_evidence(plan):
        return []
    if any(
        _schema_requests_causal_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request causal design or identification evidence"]


def _schema_requests_causal_evidence(schema: Any) -> bool:
    return _schema_contains_causal_design_field(schema)


def _schema_contains_causal_design_field(schema: Any) -> bool:
    if isinstance(schema, dict):
        for key, value in schema.items():
            if is_causal_design_evidence_key(str(key)) and _schema_field_allows_causal_design_value(value):
                return True
            if _schema_contains_causal_design_field(value):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_contains_causal_design_field(item) for item in schema)
    return False


def _schema_field_allows_causal_design_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    if isinstance(schema_type, str):
        return schema_type in {"array", "object", "string"}
    if isinstance(schema_type, list):
        return any(item in {"array", "object", "string"} for item in schema_type if isinstance(item, str))
    return False


def _schema_robustness_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_robustness_evidence(plan):
        return []
    if any(
        _schema_requests_robustness_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request robustness or stability evidence"]


def _schema_requests_robustness_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_robustness_evidence_key,
        _ROBUSTNESS_SCHEMA_LABEL_KEYS,
    ) or _schema_contains_labeled_metric_collection_field(
        schema,
        is_evaluation_protocol_repeated_collection_key,
        _ROBUSTNESS_SCHEMA_LABEL_KEYS,
    )


def _schema_generalization_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_generalization_evidence(plan):
        return []
    schema_checker = (
        _schema_requests_external_generalization_evidence
        if plan_requires_external_generalization_evidence(plan)
        else _schema_requests_generalization_evidence
    )
    if any(
        schema_checker(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request held-out, external, or OOD generalization evidence"]


def _schema_requests_generalization_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_generalization_evidence_key,
        _GENERALIZATION_SCHEMA_LABEL_KEYS,
    ) or _schema_contains_field(
        schema,
        lambda key: _normalize_schema_key(key) in {"split_id", "split_protocol", "train_test_split", "holdout_split", "heldout_split"},
    )


def _schema_requests_external_generalization_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_external_generalization_evidence_key,
        _GENERALIZATION_SCHEMA_LABEL_KEYS,
    )


def _schema_contains_field(schema: Any, predicate: Any) -> bool:
    if isinstance(schema, dict):
        return any(
            predicate(str(key)) or _schema_contains_field(value, predicate)
            for key, value in schema.items()
        )
    if isinstance(schema, list):
        return any(_schema_contains_field(item, predicate) for item in schema)
    return False


def _schema_contains_collection_field(schema: Any, predicate: Any) -> bool:
    if isinstance(schema, dict):
        for key, value in schema.items():
            if predicate(str(key)) and _schema_field_allows_collection_value(value):
                return True
            if _schema_contains_collection_field(value, predicate):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_contains_collection_field(item, predicate) for item in schema)
    return False


def _schema_contains_labeled_metric_collection_field(
    schema: Any,
    predicate: Any,
    label_keys: set[str],
    metric_name: str | None = None,
) -> bool:
    if isinstance(schema, dict):
        for key, value in schema.items():
            if (
                predicate(str(key))
                and _schema_field_allows_collection_value(value)
                and _schema_requests_labeled_metric_item(value, label_keys, metric_name)
            ):
                return True
            if _schema_contains_labeled_metric_collection_field(value, predicate, label_keys, metric_name):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_contains_labeled_metric_collection_field(item, predicate, label_keys, metric_name) for item in schema)
    return False


def _schema_requests_labeled_metric_item(
    schema: Any,
    label_keys: set[str],
    metric_name: str | None = None,
) -> bool:
    return _schema_has_label_field(schema, label_keys) and _schema_has_metric_measurement_field(schema, metric_name)


def _schema_has_label_field(schema: Any, label_keys: set[str]) -> bool:
    if isinstance(schema, dict):
        for key, value in _schema_child_fields(schema):
            normalized = _normalize_schema_key(key)
            if normalized in label_keys and _schema_field_allows_label_value(value):
                return True
            if _schema_has_label_field(value, label_keys):
                return True
        for key in ("items", "additionalProperties"):
            value = schema.get(key)
            if _schema_has_label_field(value, label_keys):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_has_label_field(item, label_keys) for item in schema)
    return False


def _schema_has_metric_measurement_field(schema: Any, metric_name: str | None = None) -> bool:
    if isinstance(schema, dict):
        for key, value in _schema_child_fields(schema):
            normalized = _normalize_schema_key(key)
            field_matches = (
                _schema_field_matches_named_metric(key, metric_name)
                if metric_name
                else _schema_measurement_field_key(normalized)
            )
            if field_matches and _schema_field_allows_numeric_value(value):
                return True
            if _schema_has_metric_measurement_field(value, metric_name):
                return True
        for key in ("items", "additionalProperties"):
            value = schema.get(key)
            if _schema_has_metric_measurement_field(value, metric_name):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_has_metric_measurement_field(item, metric_name) for item in schema)
    return False


def _schema_field_matches_named_metric(key: Any, metric_name: str) -> bool:
    normalized = _normalize_schema_key(key)
    if _schema_field_names_non_primary_metric_value(normalized):
        return False
    return _shared_is_metric_evidence_key(key, metric_name)


def _schema_child_fields(schema: dict[str, Any]) -> list[tuple[str, Any]]:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return [(str(key), value) for key, value in properties.items()]
    return [
        (str(key), value)
        for key, value in schema.items()
        if key not in _SCHEMA_META_KEYS
    ]


def _schema_field_allows_label_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    if isinstance(schema_type, str):
        return schema_type in {"string", "integer", "number"}
    if isinstance(schema_type, list):
        return any(item in {"string", "integer", "number"} for item in schema_type if isinstance(item, str))
    return False


def _schema_field_allows_numeric_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    if isinstance(schema_type, str):
        return schema_type in {"number", "integer"}
    if isinstance(schema_type, list):
        return any(item in {"number", "integer"} for item in schema_type if isinstance(item, str))
    return False


def _schema_measurement_field_key(normalized: str) -> bool:
    if (
        normalized in _SCHEMA_NON_MEASUREMENT_KEYS
        or normalized.endswith(("_id", "_ids", "_index", "_indices"))
        or normalized.endswith("_count")
        or normalized.startswith(("n_", "num_"))
    ):
        return False
    parts = set(normalized.split("_"))
    return any(
        not _schema_key_token_has_metadata_suffix(normalized, token)
        and (token in parts or token in normalized)
        for token in _SCHEMA_MEASUREMENT_TOKENS
    )


def _schema_field_allows_collection_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    if isinstance(schema_type, str):
        return schema_type in {"array", "object"}
    if isinstance(schema_type, list):
        return any(item in {"array", "object"} for item in schema_type if isinstance(item, str))
    return False


_SCHEMA_META_KEYS = {
    "$id",
    "$schema",
    "additionalProperties",
    "description",
    "enum",
    "items",
    "properties",
    "required",
    "title",
    "type",
}
_SCHEMA_NEGATION_PREFIX_TOKENS = {"no", "non", "not", "without"}
_NON_NEGATING_NON_COMPOUNDS = {"ml", "parametric"}
_BASELINE_COMPARISON_SCHEMA_LABEL_KEYS = {
    "baseline",
    "citation",
    "id",
    "method",
    "model",
    "name",
    "paper",
    "reference",
    "source",
    "work",
}
_SOTA_COMPARISON_SCHEMA_LABEL_KEYS = {
    "citation",
    "id",
    "method",
    "model",
    "name",
    "paper",
    "prior_work",
    "reference",
    "source",
    "study",
    "title",
    "work",
}
_ABLATION_SCHEMA_LABEL_KEYS = {
    "ablation",
    "component",
    "feature",
    "id",
    "masked_feature",
    "name",
    "parameter",
    "removed_component",
    "removed_feature",
    "variable",
}
_ERROR_ANALYSIS_SCHEMA_LABEL_KEYS = {
    "bucket",
    "case",
    "case_id",
    "class",
    "failure_type",
    "group",
    "label",
    "residual_bucket",
    "segment",
    "slice",
    "subgroup",
}
_FAIRNESS_SCHEMA_LABEL_KEYS = {
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
_ROBUSTNESS_SCHEMA_LABEL_KEYS = {
    "condition",
    "fold",
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
_EVALUATION_PROTOCOL_SCHEMA_LABEL_KEYS = {
    "fold",
    "fold_id",
    "repeat",
    "repeat_id",
    "run",
    "run_id",
    "seed",
    "seed_id",
    "split",
    "split_id",
    "trial",
    "trial_id",
}
_GENERALIZATION_SCHEMA_LABEL_KEYS = {
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
_SCHEMA_NON_MEASUREMENT_KEYS = {
    "alpha",
    "ci",
    "ci95",
    "confidence_interval",
    "fold",
    "fold_count",
    "n",
    "n_samples",
    "n_splits",
    "n_trials",
    "num_samples",
    "num_splits",
    "num_trials",
    "p_value",
    "pvalue",
    "random_seed",
    "random_state",
    "sample_count",
    "seed",
    "split_count",
    "std",
    "trial_count",
}
_STATISTICAL_SUPPORT_SCHEMA_TOKENS = (
    "n",
    "samples",
    "n_samples",
    "sample_count",
    "sample_size",
    "num_samples",
    "n_trials",
    "trial_count",
    "num_trials",
    "replicates",
    "repeats",
    "bootstrap_samples",
    "fold_count",
    "cv_fold_count",
    "cv_folds",
    "n_folds",
    "n_splits",
    "split_count",
    "num_folds",
    "num_splits",
)
_SCHEMA_METADATA_SUFFIX_TOKENS = {
    "description",
    "label",
    "method",
    "methods",
    "name",
    "notes",
    "rationale",
    "source",
    "type",
}
_SCHEMA_MEASUREMENT_TOKENS = {
    "acc",
    "accuracy",
    "auc",
    "auroc",
    "error",
    "f1",
    "gap",
    "loss",
    "mae",
    "metric",
    "mse",
    "parity",
    "precision",
    "rate",
    "ratio",
    "recall",
    "rmse",
    "score",
    "value",
}


def _schema_error_analysis_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_error_analysis_evidence(plan):
        return []
    if any(
        _schema_requests_error_analysis_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request error analysis evidence"]


def _schema_requests_error_analysis_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_error_analysis_evidence_key,
        _ERROR_ANALYSIS_SCHEMA_LABEL_KEYS,
    ) or _schema_contains_confusion_matrix_field(
        schema
    ) or _schema_contains_typed_token_field(
        schema,
        CALIBRATION_ERROR_EVIDENCE_TOKENS,
        _schema_field_allows_numeric_or_numeric_collection_value,
    )


def _schema_fairness_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_fairness_evidence(plan):
        return []
    if any(
        _schema_requests_fairness_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return ["at least one experimental phase schema must request fairness or bias-audit evidence"]


def _schema_requests_fairness_evidence(schema: Any) -> bool:
    return _schema_contains_labeled_metric_collection_field(
        schema,
        is_fairness_evidence_key,
        _FAIRNESS_SCHEMA_LABEL_KEYS,
    ) or _schema_contains_typed_token_field(
        schema,
        FAIRNESS_SCALAR_EVIDENCE_TOKENS,
        _schema_field_allows_numeric_or_numeric_collection_value,
    )


def _schema_efficiency_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not plan_requires_efficiency_evidence(plan):
        return []
    has_efficiency_schema = any(
        _schema_requests_efficiency_evidence(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    )
    if not has_efficiency_schema:
        return ["at least one experimental phase schema must request efficiency or resource evidence"]
    if not plan_requires_efficiency_benchmark_context(plan):
        return []
    has_context_schema = any(
        _schema_requests_efficiency_benchmark_context(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    )
    if has_context_schema:
        return []
    return ["at least one experimental phase schema must request efficiency benchmark context"]


def _schema_requests_efficiency_evidence(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        EFFICIENCY_EVIDENCE_TOKENS,
        _schema_field_allows_numeric_or_numeric_collection_value,
    )


def _schema_requests_efficiency_benchmark_context(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        EFFICIENCY_BENCHMARK_CONTEXT_TOKENS,
        _schema_field_allows_scalar_or_collection_value,
    ) or _schema_contains_field(schema, is_efficiency_benchmark_context_key)


def _schema_contains_confusion_matrix_field(schema: Any) -> bool:
    if isinstance(schema, dict):
        for key, value in schema.items():
            if _normalize_schema_key(key) == "confusion_matrix" and _schema_field_allows_collection_value(value):
                return True
            if _schema_contains_confusion_matrix_field(value):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_contains_confusion_matrix_field(item) for item in schema)
    return False


def _schema_requests_statistics(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        STATISTICS_EVIDENCE_TOKENS,
        _schema_field_allows_numeric_or_numeric_collection_value,
    )


def _schema_requests_statistical_inference(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        (*UNCERTAINTY_EVIDENCE_TOKENS, *STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS),
        _schema_field_allows_numeric_or_numeric_collection_value,
    )


def _schema_leakage_issues(phases: list[dict[str, Any]]) -> list[str]:
    if any(
        _schema_requests_leakage_audit(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return [
        "at least one experimental phase schema must request scoped leakage audit evidence"
    ]


def _schema_requests_leakage_audit(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        SPECIFIC_LEAKAGE_AUDIT_TOKENS,
        _schema_field_allows_leakage_audit_value,
    )


def _schema_goal_achievement_issues(plan: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    if not _has_success_criteria(plan):
        return []
    if any(
        _schema_requests_goal_achievement(
            phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        )
        for phase in phases
        if isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
    ):
        return []
    return [
        "at least one experimental phase schema must request target_achieved, "
        "goal_achieved, or success_criteria_met evidence"
    ]


def _has_success_criteria(plan: dict[str, Any]) -> bool:
    return _success_criteria_issue(plan) is None


def _schema_requests_goal_achievement(schema: Any) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        GOAL_ACHIEVEMENT_EVIDENCE_TOKENS,
        _schema_field_allows_goal_achievement_value,
    )


def _schema_reproducibility_issues(phases: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for phase in phases:
        if not isinstance(phase, dict) or phase.get("type") not in ("script", "optimize"):
            continue
        phase_id = phase.get("id", "?")
        schema = phase.get("expected_outputs", {}).get("report", {}).get("schema", {})
        if not _schema_requests_reproducibility(schema):
            issues.append(
                f"{phase_id} expected output schema must request reproducibility metadata "
                "such as seed, dataset fingerprint/source, split protocol, environment, and code provenance"
            )
    return issues


def _schema_requests_reproducibility(schema: Any) -> bool:
    has_seed = _schema_contains_reproducibility_field(schema, REPRODUCIBILITY_SEED_TOKENS)
    has_data_trace = _schema_contains_reproducibility_field(schema, REPRODUCIBILITY_DATA_SOURCE_TOKENS)
    has_split_trace = _schema_contains_reproducibility_field(schema, REPRODUCIBILITY_SPLIT_TOKENS)
    has_env = _schema_contains_reproducibility_field(schema, REPRODUCIBILITY_ENV_TOKENS)
    has_code_path = _schema_contains_reproducibility_field(schema, REPRODUCIBILITY_CODE_PATH_TOKENS)
    has_code_hash = _schema_contains_reproducibility_field(schema, REPRODUCIBILITY_CODE_HASH_TOKENS)
    has_code_trace = has_code_path and has_code_hash
    return has_seed and has_data_trace and has_split_trace and has_env and has_code_trace


def _schema_contains_reproducibility_field(schema: Any, tokens: tuple[str, ...]) -> bool:
    return _schema_contains_typed_token_field(
        schema,
        tokens,
        _schema_field_allows_reproducibility_value,
    )


def _schema_contains_typed_token_field(schema: Any, tokens: tuple[str, ...], value_checker: Any) -> bool:
    if isinstance(schema, dict):
        for key, value in _schema_child_fields(schema):
            if _schema_key_matches_any_token(str(key), tokens) and value_checker(value):
                return True
            if _schema_contains_typed_token_field(value, tokens, value_checker):
                return True
        for key in ("items", "additionalProperties"):
            value = schema.get(key)
            if _schema_contains_typed_token_field(value, tokens, value_checker):
                return True
        return False
    if isinstance(schema, list):
        return any(_schema_contains_typed_token_field(item, tokens, value_checker) for item in schema)
    return False


def _schema_key_matches_any_token(key: str, tokens: tuple[str, ...]) -> bool:
    normalized = _normalize_schema_key(key)
    return any(_schema_key_matches_token(normalized, token) for token in tokens)


def _schema_key_matches_token(normalized_key: str, token: str) -> bool:
    normalized_token = _normalize_schema_key(token)
    if _schema_key_token_has_negation_prefix(normalized_key, normalized_token):
        return False
    if _schema_key_token_has_metadata_suffix(normalized_key, normalized_token):
        return False
    return (
        normalized_key == normalized_token
        or normalized_key.startswith(f"{normalized_token}_")
        or (
            normalized_key.startswith(normalized_token)
            and len(normalized_key) > len(normalized_token)
            and normalized_key[len(normalized_token)].isdigit()
        )
        or normalized_key.endswith(f"_{normalized_token}")
        or f"_{normalized_token}_" in normalized_key
    )


def _schema_key_token_has_negation_prefix(normalized_key: str, normalized_token: str) -> bool:
    for match in re.finditer(rf"(?:^|_){re.escape(normalized_token)}(?=_|$|\d)", normalized_key):
        prefix = normalized_key[:match.start()].strip("_")
        if prefix and _schema_key_prefix_has_negation(prefix.split("_")):
            return True
    return False


def _schema_key_prefix_has_negation(prefix_parts: list[str]) -> bool:
    index = 0
    while index < len(prefix_parts):
        part = prefix_parts[index]
        if part not in _SCHEMA_NEGATION_PREFIX_TOKENS:
            index += 1
            continue
        if part == "non" and index + 1 < len(prefix_parts) and prefix_parts[index + 1] in _NON_NEGATING_NON_COMPOUNDS:
            index += 2
            continue
        return True
    return False


def _schema_key_token_has_metadata_suffix(normalized_key: str, normalized_token: str) -> bool:
    for match in re.finditer(rf"(?:^|_){re.escape(normalized_token)}(?=_|$|\d)", normalized_key):
        tail = normalized_key[match.end():].strip("_")
        tail = tail.lstrip("0123456789_")
        if tail and any(part in _SCHEMA_METADATA_SUFFIX_TOKENS for part in tail.split("_")):
            return True
    return False


def _schema_field_allows_numeric_or_numeric_collection_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    if _schema_field_allows_numeric_value(value):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    if isinstance(schema_type, str) and schema_type == "array":
        return _schema_field_allows_numeric_value(value.get("items", {}))
    if isinstance(schema_type, list) and "array" in schema_type:
        return _schema_field_allows_numeric_value(value.get("items", {}))
    return False


def _schema_field_allows_scalar_or_collection_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    allowed = {"array", "integer", "number", "object", "string"}
    if isinstance(schema_type, str):
        return schema_type in allowed
    if isinstance(schema_type, list):
        return any(item in allowed for item in schema_type if isinstance(item, str))
    return False


def _schema_field_allows_goal_achievement_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    allowed = {"boolean", "integer", "number", "string"}
    if isinstance(schema_type, str):
        return schema_type in allowed
    if isinstance(schema_type, list):
        return any(item in allowed for item in schema_type if isinstance(item, str))
    return False


def _schema_field_allows_leakage_audit_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    allowed = {"boolean", "integer", "number", "string", "array", "object"}
    if isinstance(schema_type, str):
        return schema_type in allowed
    if isinstance(schema_type, list):
        return any(item in allowed for item in schema_type if isinstance(item, str))
    return False


def _schema_field_allows_reproducibility_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    schema_type = value.get("type")
    if schema_type is None:
        return True
    allowed = {"integer", "number", "string", "array", "object"}
    if isinstance(schema_type, str):
        return schema_type in allowed
    if isinstance(schema_type, list):
        return any(item in allowed for item in schema_type if isinstance(item, str))
    return False


def next_pending_phase(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first executable pending phase."""
    phases = pending_phases(plan)
    return phases[0] if phases else None


def update_phase_status(
    project_dir: Path, iteration: int, phase_id: str, status: str
) -> None:
    """Update a phase's status in the plan file."""
    path = plan_path(project_dir, iteration)
    data = json.loads(path.read_text())
    phases = data.get("phases", [])
    if not isinstance(phases, list):
        raise PlanError("Research plan must have 'phases' list")
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        if phase.get("id") == phase_id:
            phase["status"] = status
            break
    else:
        raise PlanError(f"Phase not found in research plan: {phase_id}")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
