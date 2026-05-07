"""Claim verification helpers for final research papers."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import (
    baseline_comparison_items as _baseline_comparison_items,
    baseline_comparison_names as _baseline_comparison_names,
    baseline_names_match as _baseline_names_match,
    comparison_names_match as _comparison_names_match,
    evaluation_protocol_repeated_metric_counts as _evaluation_protocol_repeated_metric_counts,
    evaluation_protocol_repetition_counts as _evaluation_protocol_repetition_counts,
    has_causal_evidence as _has_causal_evidence,
    has_efficiency_evidence as _has_efficiency_evidence,
    has_external_generalization_evidence as _has_external_generalization_evidence,
    has_fairness_evidence as _has_fairness_evidence,
    has_generalization_evidence as _has_generalization_evidence,
    has_robustness_evidence as _has_robustness_evidence,
    has_sample_or_repetition_support_evidence as _has_sample_or_repetition_support_evidence,
    has_split_protocol_evidence as _has_split_protocol_evidence,
    has_substantive_ablation_evidence as _has_substantive_ablation_evidence,
    has_substantive_error_analysis_evidence as _has_substantive_error_analysis_evidence,
    has_uncertainty_evidence as _has_uncertainty_evidence,
    contains_metric_support_numeric_token as _shared_contains_metric_support_numeric_token,
    is_ablation_evidence_key as _is_ablation_evidence_key,
    is_error_analysis_evidence_key as _is_error_analysis_evidence_key,
    is_evaluation_protocol_count_key as _is_protocol_count_key,
    is_evaluation_protocol_repeated_collection_key as _is_protocol_repeated_results_key,
    is_goal_achievement_evidence_key as _shared_is_goal_achievement_evidence_key,
    is_leakage_indicator_evidence_key as _shared_is_leakage_indicator_key,
    is_leakage_resolution_evidence_key as _shared_is_leakage_resolution_key,
    is_metric_evidence_key as _shared_is_metric_evidence_key,
    is_metric_support_numeric_key as _shared_is_metric_support_numeric_key,
    is_robustness_evidence_key as _is_robustness_evidence_key,
    is_specific_leakage_audit_key as _is_specific_leakage_check_key,
    canonical_metric_name as _shared_canonical_metric_name,
    plan_metric_target as _shared_plan_metric_target,
    reproducibility_bundle_missing_groups as _reproducibility_bundle_missing_groups,
    sota_comparison_items as _sota_comparison_items,
    sota_comparison_names as _sota_comparison_names,
)
from .paths import (
    RESEARCH_RESULT_JSON_PATH_RE,
    RESEARCH_RESULT_PNG_PATH_RE,
    iteration_number_from_dir_name,
    research_plan_files,
    research_result_json_files,
    safe_research_result_json_paths_in_text,
)
from .provenance import audit_code_provenance


@dataclass
class ClaimIssue:
    """A paper claim that could not be traced to raw results."""

    value: float | None
    sentence: str
    reason: str


@dataclass
class ResultNumber:
    """A numeric value and the JSON key path it came from."""

    value: float
    key_path: str


_NUMBER_PATTERN = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:e[+-]?\d+)?%?"
_NUMBER_RE = re.compile(rf"(?<![\w.]){_NUMBER_PATTERN}", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<!et al\.)(?<=[.!?])\s+|\n+")
_METRIC_HINTS = (
    "accuracy", "acc", "mae", "rmse", "mse", "loss", "auc", "auroc", "f1",
    "precision", "recall", "error", "score", "metric", "baseline", "improvement",
    "mean", "std", "ci", "confidence", "p-value", "p value", "r2", "r^2",
    "uncertainty", "standard deviation", "standard error", "confidence interval",
    "variance",
    "target", "goal", "success criteria", "leakage", "data leak", "target leakage",
    "temporal leakage", "preprocessing leakage", "train/test overlap",
    "duplicate overlap", "cross-validation", "cross validation", "cv", "fold", "split",
    "held-out", "holdout", "test set", "test split", "train/test split",
    "state-of-the-art", "state of the art", "sota", "prior work", "previous work",
    "statistically significant", "significant difference", "significant effect",
    "non-significant", "nonsignificant", "insignificant",
    "ablation", "feature importance", "permutation importance", "sensitivity",
    "shap", "error analysis", "failure case", "failure cases", "residual",
    "slice", "subgroup", "misclassification", "confusion matrix", "calibration",
    "calibrated", "ece", "brier score",
    "fairness", "bias audit", "demographic parity", "equalized odds",
    "equal opportunity", "disparate impact", "protected group", "protected attribute",
    "group fairness", "subgroup fairness", "unbiased",
    "efficiency", "efficient", "latency", "throughput", "runtime", "run time",
    "inference time", "training time", "wall clock", "memory", "model size",
    "parameter count", "flops", "compute cost", "gpu hours", "faster", "slower",
    "reproducibility", "reproducible", "reproduce", "seed",
    "dataset fingerprint", "environment", "code provenance", "script hash",
    "causal", "causality", "causation", "causal effect", "causal impact",
    "caused", "causes",
    "robust", "robustness", "generalize", "generalizes", "generalization",
    "stable", "stability", "consistent across", "unseen data", "external validation",
    "external cohort", "external test set", "independent cohort", "independent validation",
    "validation cohort",
    "out-of-distribution", "ood",
)
_RESULT_PATH_RE = RESEARCH_RESULT_JSON_PATH_RE
_RESULT_FIGURE_PATH_RE = RESEARCH_RESULT_PNG_PATH_RE
_SIGNIFICANCE_RE = re.compile(
    r"\b(statistically\s+significant|significant\s+(?:improvement|difference|gain|reduction|increase|decrease|effect))\b",
    re.IGNORECASE,
)
_NEGATED_SIGNIFICANCE_RE = re.compile(
    r"\b(?:no|not|never|failed\s+to|fails\s+to|did\s+not|does\s+not|without)\b.{0,40}"
    r"\b(?:statistically\s+significant|significant\s+"
    r"(?:improvement|difference|gain|reduction|increase|decrease|effect))\b"
    r"|\b(?:non[- ]significant|insignificant)\b",
    re.IGNORECASE,
)
_UNCERTAINTY_CLAIM_RE = re.compile(
    r"\b(?:uncertainty|standard[- ]deviation|standard[- ]error|"
    r"confidence[- ]interval|credible[- ]interval|error[- ]bar|"
    r"variance|dispersion)\b",
    re.IGNORECASE,
)
_UNCERTAINTY_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|did\s+not|does\s+not|"
    r"was\s+not|were\s+not|not\s+estimated|not\s+computed|not\s+reported)\b.{0,80}"
    r"\b(?:uncertainty|standard[- ]deviation|standard[- ]error|"
    r"confidence[- ]interval|credible[- ]interval|error[- ]bar|"
    r"variance|dispersion)\b"
    r"|\b(?:uncertainty|standard[- ]deviation|standard[- ]error|"
    r"confidence[- ]interval|credible[- ]interval|error[- ]bar|"
    r"variance|dispersion)\b.{0,80}"
    r"\b(?:missing|lacking|future[- ]work|limitation|limitations|"
    r"not\s+estimated|not\s+computed|not\s+reported)\b",
    re.IGNORECASE,
)
_CI_ZERO_EXCLUSION_RE = re.compile(
    r"\b(?:ci|ci95|confidence[- ]interval|credible[- ]interval)\b.{0,80}"
    r"\b(?:excludes?|excluding|does\s+not\s+include|did\s+not\s+include|"
    r"doesn't\s+include|does\s+not\s+cross|doesn't\s+cross|above|below)\s+zero\b",
    re.IGNORECASE,
)
_CI_ZERO_CROSSING_RE = re.compile(
    r"\b(?:ci|ci95|confidence[- ]interval|credible[- ]interval)\b.{0,80}"
    r"\b(?:crosses|crossing|includes?|including|overlaps?|overlapping|contains?|containing)\s+zero\b",
    re.IGNORECASE,
)
_CAUSAL_CLAIM_RE = re.compile(
    r"\b(?:cause(?:s|d)?|causal(?:ly)?|causality|causation)\b"
    r"|\bcausal\s+(?:effect|impact|relationship|mechanism|inference)\b",
    re.IGNORECASE,
)
_CAUSAL_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|cannot|can\s+not|could\s+not|"
    r"does\s+not|did\s+not|do\s+not|was\s+not|were\s+not|"
    r"not\s+designed\s+to|not\s+intended\s+to)\b.{0,96}"
    r"\b(?:causal(?:ly)?|causality|causation|cause(?:s|d)?|causal\s+effect|causal\s+impact)\b"
    r"|\bcorrelation\s+(?:is\s+)?not\s+causation\b",
    re.IGNORECASE,
)
_ROBUSTNESS_CLAIM_RE = re.compile(
    r"\b(?:robust|robustness)\b"
    r"|\b(?:stable|stability|consistent)\b.{0,80}"
    r"\b(?:across|over|between)\b.{0,48}"
    r"\b(?:seeds?|runs?|folds?|splits?|datasets?|cohorts?)\b",
    re.IGNORECASE,
)
_GENERALIZATION_CLAIM_RE = re.compile(
    r"\bgeneraliz(?:e|es|ed|ation)\b"
    r"|\b(?:unseen|new|external|independent|out[- ]of[- ]distribution|ood)\s+"
    r"(?:data|dataset|set|cohort)\b",
    re.IGNORECASE,
)
_EXTERNAL_GENERALIZATION_CLAIM_RE = re.compile(
    r"\b(?:external|independent|cross[- ]dataset|out[- ]of[- ]distribution|ood)\s+"
    r"(?:validation|test|data|dataset|set|cohort|evaluation)\b"
    r"|\bvalidation\s+cohort\b"
    r"|\b(?:generaliz(?:e|es|ed|ation)).{0,80}"
    r"\b(?:external|independent|cross[- ]dataset|out[- ]of[- ]distribution|ood)\b",
    re.IGNORECASE,
)
_ROBUSTNESS_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|cannot|can\s+not|could\s+not|"
    r"does\s+not|did\s+not|do\s+not|was\s+not|were\s+not|"
    r"not\s+designed\s+to|not\s+intended\s+to)\b.{0,96}"
    r"\b(?:robust|robustness|generaliz(?:e|es|ed|ation)|stable|stability|consistent|external|ood|out[- ]of[- ]distribution)\b"
    r"|\b(?:robust|robustness|generaliz(?:e|es|ed|ation)|stable|stability|consistent|external|ood|out[- ]of[- ]distribution)\b.{0,96}"
    r"\b(?:not\s+evaluated|not\s+tested|not\s+measured|not\s+assessed|missing|future[- ]work|limitation|limitations)\b",
    re.IGNORECASE,
)
_EVALUATION_PROTOCOL_RE = re.compile(
    r"\b(?:cross[- ]?validation|cv|k[- ]?fold|folds?|multiple[- ]split|repeated[- ]split)\b",
    re.IGNORECASE,
)
_SPLIT_PROTOCOL_CLAIM_RE = re.compile(
    r"\b(?:held[- ]out|holdout)\s+(?:test\s+)?(?:set|split|partition)\b"
    r"|\b(?:test|validation|evaluation)\s+(?:set|split|partition)\b"
    r"|\b(?:train\s*/\s*test|train-test|train\s+test)\s+split\b"
    r"|\bevaluated\s+on\s+(?:a\s+)?(?:held[- ]out|holdout|test)\s+(?:set|split|partition)\b",
    re.IGNORECASE,
)
_SPLIT_PROTOCOL_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|did\s+not|does\s+not|"
    r"was\s+not|were\s+not|not\s+used|not\s+available)\b.{0,80}"
    r"\b(?:held[- ]out|holdout|test|validation|evaluation|train\s*/\s*test|train-test)"
    r"\s+(?:set|split|partition)\b"
    r"|\b(?:held[- ]out|holdout|test|validation|evaluation|train\s*/\s*test|train-test)"
    r"\s+(?:set|split|partition)\b.{0,80}"
    r"\b(?:missing|lacking|future[- ]work|limitation|limitations|"
    r"not\s+used|not\s+available)\b",
    re.IGNORECASE,
)
_SAMPLE_SIZE_CLAIM_PATTERNS = (
    re.compile(
        rf"\b(?:n|n_samples|num_samples|sample_count|sample_size)\s*"
        rf"(?:=|:)\s*(?P<count>{_NUMBER_PATTERN})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bsample\s+size\s*(?:=|:|of|is|was|were)\s*"
        rf"(?P<count>{_NUMBER_PATTERN})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<count>{_NUMBER_PATTERN})\s+"
        r"(?:samples?|observations?|participants?|examples?|instances?|cases?|rows?)\b",
        re.IGNORECASE,
    ),
)
_REPETITION_COUNT_CLAIM_PATTERNS = (
    re.compile(
        rf"\b(?:n_trials|num_trials|trial_count|n_runs|num_runs|run_count|"
        rf"n_seeds|num_seeds|seed_count|repeat_count|replicate_count)\s*"
        rf"(?:=|:)\s*(?P<count>{_NUMBER_PATTERN})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<count>{_NUMBER_PATTERN})\s+"
        r"(?:random\s+)?(?:seeds?|runs?|trials?|replicates?|repetitions?|repeats?)\b",
        re.IGNORECASE,
    ),
)
_SPLIT_RATIO_CLAIM_PATTERNS = (
    re.compile(
        rf"\b(?P<train>\d{{1,3}}(?:\.\d+)?)\s*/\s*"
        rf"(?P<test>\d{{1,3}}(?:\.\d+)?)\s*"
        r"(?:train[-/ ]?test\s+)?(?:split|holdout|held[- ]out|partition)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:split|holdout|held[- ]out|train[-/ ]?test)\s+"
        rf"(?:ratio|split)?\s*(?:=|:|of|was|is)?\s*"
        rf"(?P<train>\d{{1,3}}(?:\.\d+)?)\s*/\s*"
        rf"(?P<test>\d{{1,3}}(?:\.\d+)?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<train>\d{{1,3}}(?:\.\d+)?)%\s+"
        r"(?:train|training)\b.{0,40}\b"
        rf"(?P<test>\d{{1,3}}(?:\.\d+)?)%\s+"
        r"(?:test|validation|holdout|held[- ]out)\b",
        re.IGNORECASE,
    ),
)
_SPLIT_TEST_PERCENT_CLAIM_PATTERNS = (
    re.compile(
        rf"\b(?P<test>\d{{1,3}}(?:\.\d+)?)%\s+"
        r"(?:(?:held[- ]out|holdout)\s+)?(?:test|validation)?\s*"
        r"(?:set|split|partition)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:held[- ]out|holdout)\s+)?(?:test|validation)?\s*"
        r"(?:set|split|partition)\s+"
        rf"(?:of|was|is|=|:)\s*(?P<test>\d{{1,3}}(?:\.\d+)?)%\b",
        re.IGNORECASE,
    ),
)
_ABLATION_CLAIM_RE = re.compile(
    r"\b(?:ablation|feature[- ]importance|permutation[- ]importance|"
    r"sensitivity[- ]analysis|shap(?:\s+values?|\s+importance)?)\b",
    re.IGNORECASE,
)
_ERROR_ANALYSIS_CLAIM_RE = re.compile(
    r"\b(?:error[- ]analysis|failure[- ]cases?|residual[- ]analysis|"
    r"slice[- ]analysis|subgroup[- ]analysis|misclassification|"
    r"confusion[- ]matrix|calibrat(?:ed|ion)|calibration[- ]errors?|"
    r"expected[- ]calibration[- ]error|ece|brier[- ]score)\b",
    re.IGNORECASE,
)
_FAIRNESS_CLAIM_RE = re.compile(
    r"\b(?:fairness|bias[- ]audit|model[- ]bias|demographic[- ]parity|"
    r"equalized[- ]odds|equal[- ]opportunity|disparate[- ]impact|"
    r"protected[- ](?:group|attribute)s?|group[- ]fairness|"
    r"subgroup[- ]fairness|unbiased(?:\s+across\s+(?:groups?|subgroups?|demographics?))?|"
    r"fair\s+across\s+(?:groups?|subgroups?|demographics?))\b",
    re.IGNORECASE,
)
_FAIRNESS_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|did\s+not|does\s+not|"
    r"was\s+not|were\s+not|not\s+performed|not\s+run|not\s+evaluated)\b.{0,80}"
    r"\b(?:fairness|bias[- ]audit|demographic[- ]parity|equalized[- ]odds|"
    r"equal[- ]opportunity|disparate[- ]impact|protected[- ](?:group|attribute)s?)\b"
    r"|\b(?:fairness|bias[- ]audit|demographic[- ]parity|equalized[- ]odds|"
    r"equal[- ]opportunity|disparate[- ]impact|protected[- ](?:group|attribute)s?)\b.{0,80}"
    r"\b(?:not\s+performed|not\s+run|not\s+evaluated|was\s+not|were\s+not|"
    r"missing|lacking|future[- ]work|limitation|limitations)\b",
    re.IGNORECASE,
)
_EFFICIENCY_CLAIM_RE = re.compile(
    r"\b(?:efficien(?:t|cy)|latency|throughput|runtime|run[- ]time|"
    r"inference[- ]time|training[- ]time|wall[- ]clock|memory(?:[- ]usage)?|"
    r"model[- ]size|parameter[- ]count|n[- ]parameters|flops|macs|"
    r"compute[- ]cost|gpu[- ]hours|faster|slower|speed(?:up)?)\b",
    re.IGNORECASE,
)
_EFFICIENCY_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|did\s+not|does\s+not|"
    r"was\s+not|were\s+not|not\s+measured|not\s+reported|not\s+profiled)\b.{0,80}"
    r"\b(?:efficien(?:t|cy)|latency|throughput|runtime|run[- ]time|"
    r"inference[- ]time|training[- ]time|memory|model[- ]size|"
    r"parameter[- ]count|flops|compute[- ]cost|gpu[- ]hours)\b"
    r"|\b(?:efficien(?:t|cy)|latency|throughput|runtime|run[- ]time|"
    r"inference[- ]time|training[- ]time|memory|model[- ]size|"
    r"parameter[- ]count|flops|compute[- ]cost|gpu[- ]hours)\b.{0,80}"
    r"\b(?:not\s+measured|not\s+reported|not\s+profiled|missing|lacking|"
    r"future[- ]work|limitation|limitations)\b",
    re.IGNORECASE,
)
_REPRODUCIBILITY_CLAIM_RE = re.compile(
    r"\b(?:reproducibility|reproducible|reproduce|reproduced|reproducing|"
    r"replicable|replicate|replicated|repeatable|"
    r"reproducibility[- ]metadata)\b",
    re.IGNORECASE,
)
_REPRODUCIBILITY_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|did\s+not|does\s+not|"
    r"was\s+not|were\s+not|cannot|could\s+not|not\s+fully)\b.{0,80}"
    r"\b(?:reproducibility|reproducible|reproduce|reproduced|reproducing|"
    r"replicable|replicate|replicated|repeatable|"
    r"reproducibility[- ]metadata)\b"
    r"|\b(?:reproducibility|reproducible|reproduce|reproduced|reproducing|"
    r"replicable|replicate|replicated|repeatable|"
    r"reproducibility[- ]metadata)\b.{0,80}"
    r"\b(?:missing|lacking|future[- ]work|limitation|limitations|"
    r"incomplete|not\s+complete|not\s+fully)\b",
    re.IGNORECASE,
)
_EVIDENCE_FAMILY_ABSENCE_RE = re.compile(
    r"\b(?:no|not|never|without|missing|lack(?:s|ed|ing)?|"
    r"future[- ]work|limitation|limitations|did\s+not|does\s+not|"
    r"was\s+not|were\s+not|not\s+performed|not\s+run)\b.{0,80}"
    r"\b(?:ablation|feature[- ]importance|permutation[- ]importance|"
    r"sensitivity[- ]analysis|shap|error[- ]analysis|failure[- ]cases?|"
    r"residual[- ]analysis|slice[- ]analysis|subgroup[- ]analysis|"
    r"misclassification|confusion[- ]matrix|calibrat(?:ed|ion)|"
    r"calibration[- ]errors?|expected[- ]calibration[- ]error|ece|"
    r"brier[- ]score)\b"
    r"|\b(?:ablation|feature[- ]importance|permutation[- ]importance|"
    r"sensitivity[- ]analysis|shap|error[- ]analysis|failure[- ]cases?|"
    r"residual[- ]analysis|slice[- ]analysis|subgroup[- ]analysis|"
    r"misclassification|confusion[- ]matrix|calibrat(?:ed|ion)|"
    r"calibration[- ]errors?|expected[- ]calibration[- ]error|ece|"
    r"brier[- ]score)\b.{0,80}"
    r"\b(?:not\s+performed|not\s+run|was\s+not|were\s+not|missing|"
    r"lacking|future[- ]work|limitation|limitations)\b",
    re.IGNORECASE,
)
_EVIDENCE_FAMILY_META_SENTENCE_RE = re.compile(
    r"\b(?:abstract|method|methods?|results?|discussion|limitations?|paper|study|section)"
    r"(?:\s+section)?\s+(?:describes|documents|reports|summarizes|mentions|discusses)\b"
    r"|\b(?:it|this\s+(?:paper|study)|the\s+(?:paper|study)|paper|study)\s+"
    r"(?:describes|documents|reports|summarizes|mentions|discusses)\b"
    r"|\b(?:describes|documents|reports|summarizes|mentions|discusses)\s+"
    r"(?:the\s+)?(?:abstract|method|methods?|results?|discussion|limitations?|paper|study|section)\b",
    re.IGNORECASE,
)


def verify_paper_numeric_claims(project_dir: Path, tolerance: float = 5e-3) -> list[ClaimIssue]:
    """Check result-backed claims in final_paper.md against results JSONs.

    The verifier is deliberately scoped to metric-like sentences to avoid
    blocking on citation years, section numbering, or dataset prose. It
    catches the most damaging failure modes: a final paper reporting a metric
    value, significance result, target outcome, or leakage outcome that cannot
    be traced to the result artifact cited in the same sentence.
    """
    paper_path = project_dir / "research" / "final_paper.md"
    if not paper_path.exists():
        return []

    result_payloads_by_path = _collect_result_payloads_by_path(project_dir)
    if not result_payloads_by_path:
        return []
    plan_metric_targets_by_iteration = _collect_plan_metric_targets_by_iteration(project_dir)
    result_values_by_path = {
        path: _walk_numbers(data)
        for path, data in result_payloads_by_path.items()
    }

    issues: list[ClaimIssue] = []
    for sentence in _metric_sentences(paper_path.read_text()):
        cited_paths = _result_json_paths_in_sentence(sentence)
        has_claim_number = False
        for match in _NUMBER_RE.finditer(sentence):
            raw = match.group(0)
            value = _parse_number(raw)
            if value is None or _looks_like_noise(value, raw):
                continue
            has_claim_number = True
            if _evaluation_protocol_hint_for_number(sentence, match.start(), match.end()):
                continue
            if _sample_size_hint_for_number(sentence, match.start(), match.end()):
                continue
            if _repetition_count_hint_for_number(sentence, match.start(), match.end()):
                continue
            if _split_ratio_hint_for_number(sentence, match.start(), match.end()):
                continue
            if _confidence_level_context_for_number(sentence, match.start(), match.end(), raw):
                continue
            metric_hint = _claim_hint_for_number(sentence, match.start(), match.end(), raw)
            if not cited_paths:
                issues.append(ClaimIssue(
                    value=value,
                    sentence=" ".join(sentence.split())[:240],
                    reason="metric sentence does not cite a concrete research/iter_*/results/*.json artifact path",
                ))
                continue
            cited_values = _values_for_cited_paths(cited_paths, result_values_by_path)
            if not cited_values:
                issues.append(ClaimIssue(
                    value=value,
                    sentence=" ".join(sentence.split())[:240],
                    reason="cited artifact path is missing or has no numeric values",
                ))
                continue
            support_stat_kind = _support_stat_kind_for_number(sentence, match.start(), match.end())
            if not _matches_result_value(
                value,
                cited_values,
                tolerance,
                metric_hint,
                allow_support_stat=support_stat_kind is not None,
                support_stat_only=support_stat_kind is not None,
                support_stat_kind=support_stat_kind,
            ):
                plan_target_status = _plan_target_number_status(
                    value,
                    sentence,
                    match.start(),
                    match.end(),
                    cited_paths,
                    plan_metric_targets_by_iteration,
                    metric_hint,
                    tolerance,
                )
                if plan_target_status == "matched":
                    continue
                issues.append(ClaimIssue(
                    value=value,
                    sentence=" ".join(sentence.split())[:240],
                    reason=(
                        "number does not match the plan target for the cited iteration"
                        if plan_target_status == "mismatch"
                        else _claim_mismatch_reason(metric_hint)
                    ),
                ))
        significance_issue = _significance_claim_issue(
            sentence,
            cited_paths,
            result_values_by_path,
            result_payloads_by_path,
        )
        if significance_issue:
            issues.append(significance_issue)
        ci_zero_issue = _ci_zero_relationship_claim_issue(
            sentence,
            cited_paths,
            result_values_by_path,
            result_payloads_by_path,
        )
        if ci_zero_issue:
            issues.append(ci_zero_issue)
        uncertainty_issue = _uncertainty_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if uncertainty_issue:
            issues.append(uncertainty_issue)
        protocol_issue = _evaluation_protocol_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if protocol_issue:
            issues.append(protocol_issue)
        sample_size_issue = _sample_size_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if sample_size_issue:
            issues.append(sample_size_issue)
        repetition_count_issue = _repetition_count_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if repetition_count_issue:
            issues.append(repetition_count_issue)
        split_ratio_issue = _split_ratio_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if split_ratio_issue:
            issues.append(split_ratio_issue)
        causal_issue = _causal_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if causal_issue:
            issues.append(causal_issue)
        robustness_issue = _robustness_or_generalization_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if robustness_issue:
            issues.append(robustness_issue)
        if not (has_claim_number and not cited_paths):
            split_protocol_issue = _split_protocol_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
            )
            if split_protocol_issue:
                issues.append(split_protocol_issue)
            evidence_family_issue = _evidence_family_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
            )
            if evidence_family_issue:
                issues.append(evidence_family_issue)
            reproducibility_issue = _reproducibility_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
                project_dir,
            )
            if reproducibility_issue:
                issues.append(reproducibility_issue)
        direction_issue = _directional_improvement_issue(sentence)
        if direction_issue:
            issues.append(direction_issue)
        superiority_issue = None
        if (
            not direction_issue
            and not (has_claim_number and not cited_paths)
            and not _has_explicit_directional_comparison(sentence)
        ):
            superiority_issue = _baseline_superiority_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
            )
            if superiority_issue:
                issues.append(superiority_issue)
        baseline_non_superiority_issue = _baseline_non_superiority_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if baseline_non_superiority_issue:
            issues.append(baseline_non_superiority_issue)
        if not superiority_issue and not baseline_non_superiority_issue:
            baseline_name_issue = _baseline_name_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
            )
            if baseline_name_issue:
                issues.append(baseline_name_issue)
        sota_issue = _sota_superiority_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if sota_issue:
            issues.append(sota_issue)
        sota_non_superiority_issue = _sota_non_superiority_claim_issue(
            sentence,
            cited_paths,
            result_payloads_by_path,
        )
        if sota_non_superiority_issue:
            issues.append(sota_non_superiority_issue)
        if not sota_issue and not sota_non_superiority_issue:
            sota_name_issue = _sota_name_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
            )
            if sota_name_issue:
                issues.append(sota_name_issue)
        if not (has_claim_number and not cited_paths):
            target_issue = _target_achievement_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
                plan_metric_targets_by_iteration,
            )
            if target_issue:
                issues.append(target_issue)
            target_non_achievement_issue = _target_non_achievement_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
                plan_metric_targets_by_iteration,
            )
            if target_non_achievement_issue:
                issues.append(target_non_achievement_issue)
        if not (has_claim_number and not cited_paths):
            leakage_issue = _leakage_claim_issue(
                sentence,
                cited_paths,
                result_payloads_by_path,
            )
            if leakage_issue:
                issues.append(leakage_issue)
    return issues


def _metric_sentences(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    return [
        s
        for s in sentences
        if (
            _has_metric_hint(s)
            or _sample_size_claim_numbers(s)
            or _repetition_count_claim_numbers(s)
            or _split_ratio_claim_pairs(s)
        )
    ]


def _has_metric_hint(sentence: str) -> bool:
    lower = sentence.lower()
    return any(_metric_hint_matches_sentence(lower, hint) for hint in _METRIC_HINTS)


def _metric_hint_matches_sentence(lower_sentence: str, hint: str) -> bool:
    pattern = re.escape(hint.lower()).replace(r"\ ", r"[- ]+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lower_sentence) is not None


def _claim_mismatch_reason(metric_hint: str | None) -> str:
    if metric_hint:
        return (
            f"number does not match a {metric_hint}-like key/value in the cited "
            "research/iter_*/results/*.json artifact"
        )
    return "number does not match any value in the cited research/iter_*/results/*.json artifact"


def format_claim_issue(issue: ClaimIssue) -> str:
    """Render a claim issue for CLI and engine messages."""
    prefix = f"{issue.value:g}: " if issue.value is not None else ""
    return f"{prefix}{issue.sentence} ({issue.reason})"


def _significance_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_values_by_path: dict[str, list[ResultNumber]],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    is_negated = _has_negated_significance_claim(sentence)
    if not _SIGNIFICANCE_RE.search(sentence) and not is_negated:
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="significance claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_values = _values_for_cited_paths(cited_paths, result_values_by_path)
    if not cited_values:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no statistical evidence",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    requires_comparison = _requires_comparison_stat_evidence(sentence)
    if is_negated:
        if not _has_non_significant_statistical_evidence(
            cited_values,
            requires_comparison=requires_comparison,
        ):
            return ClaimIssue(
                value=None,
                sentence=normalized,
                reason=(
                    "non-significance claim requires p-value above alpha or confidence "
                    "interval crossing zero in the cited result artifact"
                ),
            )
        if not any(_has_sample_or_repetition_support_evidence(payload) for payload in cited_payloads):
            return ClaimIssue(
                value=None,
                sentence=normalized,
                reason=(
                    "non-significance claim requires sample/repetition support "
                    "such as n_samples, n_trials, or fold_count in the cited result artifact"
                ),
            )
        return None
    if not _has_statistical_evidence(
        cited_values,
        requires_comparison=requires_comparison,
    ):
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="significance claim requires p-value, confidence interval, or CI evidence in the cited result artifact",
        )
    if not any(_has_sample_or_repetition_support_evidence(payload) for payload in cited_payloads):
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=(
                "significance claim requires sample/repetition support "
                "such as n_samples, n_trials, or fold_count in the cited result artifact"
            ),
        )
    return None


def _uncertainty_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_uncertainty_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths and _EVIDENCE_FAMILY_META_SENTENCE_RE.search(sentence):
        return None
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="uncertainty claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no uncertainty evidence",
        )
    if any(_has_uncertainty_evidence(payload) for payload in cited_payloads):
        if any(_has_sample_or_repetition_support_evidence(payload) for payload in cited_payloads):
            return None
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=(
                "uncertainty claim requires sample/repetition support "
                "such as n_samples, n_trials, or fold_count in the cited result artifact"
            ),
        )
    return ClaimIssue(
        value=None,
        sentence=normalized,
        reason=(
            "uncertainty claim requires std, standard_error, variance, "
            "confidence interval, or CI evidence in the cited result artifact"
        ),
    )


def _ci_zero_relationship_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_values_by_path: dict[str, list[ResultNumber]],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    claim_type = _ci_zero_relationship_claim_type(sentence)
    if claim_type is None:
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="confidence-interval zero relationship claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_values = _values_for_cited_paths(cited_paths, result_values_by_path)
    if not cited_values:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="confidence-interval zero relationship claim requires comparison confidence interval evidence in the cited result artifact",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if claim_type == "excludes_zero":
        if not _has_nonzero_confidence_interval(cited_values):
            return ClaimIssue(
                value=None,
                sentence=normalized,
                reason="confidence-interval zero-exclusion claim requires a comparison confidence interval excluding zero in the cited result artifact",
            )
    elif not _has_zero_crossing_confidence_interval(cited_values):
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="confidence-interval zero-crossing claim requires a comparison confidence interval crossing zero in the cited result artifact",
        )
    if not any(_has_sample_or_repetition_support_evidence(payload) for payload in cited_payloads):
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=(
                "confidence-interval zero relationship claim requires sample/repetition support "
                "such as n_samples, n_trials, or fold_count in the cited result artifact"
            ),
        )
    return None


def _ci_zero_relationship_claim_type(sentence: str) -> str | None:
    if _CI_ZERO_EXCLUSION_RE.search(sentence):
        return "excludes_zero"
    if _CI_ZERO_CROSSING_RE.search(sentence):
        return "crosses_zero"
    return None


def _has_uncertainty_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if _UNCERTAINTY_ABSENCE_RE.search(lower):
        return False
    return _UNCERTAINTY_CLAIM_RE.search(lower) is not None


def _claim_key_matches_without_metadata_suffix(key: str, token: str) -> bool:
    normalized_key = _normalize_claim_key_path(key)
    normalized_token = _normalize_claim_key_path(token)
    key_parts = [part for part in normalized_key.split("_") if part]
    token_parts = [part for part in normalized_token.split("_") if part]
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    for start in range(0, len(key_parts) - len(token_parts) + 1):
        if not _claim_key_parts_match_token(key_parts[start:start + len(token_parts)], token_parts):
            continue
        if _claim_prefix_has_negation(key_parts[:start], _CLAIM_NEGATION_PREFIX_TOKENS):
            continue
        tail = key_parts[start + len(token_parts):]
        if tail and any(part in _CLAIM_METADATA_SUFFIX_TOKENS for part in tail):
            continue
        return True
    return False


def _normalize_claim_key_path(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _claim_key_parts_match_token(key_parts: list[str], token_parts: list[str]) -> bool:
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


_CLAIM_METADATA_SUFFIX_TOKENS = {
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


_CLAIM_NEGATION_PREFIX_TOKENS = {"no", "non", "not", "without"}
_NON_NEGATING_NON_COMPOUNDS = {"ml", "parametric"}


def _claim_key_has_metadata_suffix(key: str) -> bool:
    parts = [part for part in _normalize_claim_key_path(key).split("_") if part]
    return bool(parts and parts[-1] in _CLAIM_METADATA_SUFFIX_TOKENS)


def _causal_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_causal_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="causal claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no causal evidence",
        )
    if any(_has_causal_evidence(payload) for payload in cited_payloads):
        return None
    return ClaimIssue(
        value=None,
        sentence=normalized,
        reason=(
            "causal claim requires causal design or identification evidence "
            "such as randomized_assignment, causal_identification, "
            "counterfactual, instrumental_variable, or difference_in_differences "
            "in the cited result artifact"
        ),
    )


def _has_causal_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if _CAUSAL_ABSENCE_RE.search(lower):
        return False
    return _CAUSAL_CLAIM_RE.search(lower) is not None


def _robustness_or_generalization_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    claim_kind = _robustness_or_generalization_claim_kind(sentence)
    if claim_kind is None:
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=f"{claim_kind} claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=f"cited artifact path is missing or has no {claim_kind} evidence",
        )
    if claim_kind == "robustness":
        if any(_has_robustness_evidence(payload) for payload in cited_payloads):
            return None
        reason = (
            "robustness claim requires repeated-run, repeated-split, seed, "
            "or robustness evidence such as per_fold_metrics, repeated_seed_results, "
            "seed_sensitivity, robustness_checks, or stress_test_results in the cited result artifact"
        )
    elif claim_kind == "external generalization":
        if any(_has_external_generalization_evidence(payload) for payload in cited_payloads):
            return None
        reason = (
            "external generalization claim requires external validation, "
            "cross-dataset, or out-of-distribution metric evidence in the cited result artifact"
        )
    else:
        if any(_has_generalization_evidence(payload) for payload in cited_payloads):
            return None
        reason = (
            "generalization claim requires held-out, split-protocol, external validation, "
            "or out-of-distribution evidence in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _robustness_or_generalization_claim_kind(sentence: str) -> str | None:
    lower = sentence.lower()
    if _ROBUSTNESS_ABSENCE_RE.search(lower):
        return None
    if _ROBUSTNESS_CLAIM_RE.search(lower):
        return "robustness"
    if _EXTERNAL_GENERALIZATION_CLAIM_RE.search(lower):
        return "external generalization"
    if _GENERALIZATION_CLAIM_RE.search(lower):
        return "generalization"
    return None


def _evaluation_protocol_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _EVALUATION_PROTOCOL_RE.search(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="evaluation protocol claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no evaluation protocol evidence",
        )
    claimed_count = _evaluation_protocol_claim_count(sentence)
    evidence_counts = [
        count
        for payload in cited_payloads
        for count in _evaluation_protocol_repetition_counts(payload)
    ]
    repeated_metric_counts = [
        count
        for payload in cited_payloads
        for count in _evaluation_protocol_repeated_metric_counts(payload)
    ]
    if claimed_count is not None:
        if not evidence_counts:
            return ClaimIssue(
                value=float(claimed_count),
                sentence=normalized,
                reason="evaluation protocol claim requires fold_count, split_count, or per-fold/split evidence in the cited result artifact",
            )
        if claimed_count not in evidence_counts:
            return ClaimIssue(
                value=float(claimed_count),
                sentence=normalized,
                reason="evaluation protocol claim count does not match fold/split evidence in the cited result artifact",
            )
        if not repeated_metric_counts or max(repeated_metric_counts) < 2:
            return ClaimIssue(
                value=float(claimed_count),
                sentence=normalized,
                reason="evaluation protocol claim requires per-fold/split metric evidence in the cited result artifact",
            )
        if claimed_count not in repeated_metric_counts:
            return ClaimIssue(
                value=float(claimed_count),
                sentence=normalized,
                reason="evaluation protocol claim count must be materialized by per-fold/split metric evidence in the cited result artifact",
            )
        return None
    if not evidence_counts:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="evaluation protocol claim requires fold_count, split_count, or per-fold/split evidence in the cited result artifact",
        )
    if not repeated_metric_counts or max(repeated_metric_counts) < 2:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="evaluation protocol claim requires per-fold/split metric evidence in the cited result artifact",
        )
    return None


def _split_protocol_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_split_protocol_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths and _EVIDENCE_FAMILY_META_SENTENCE_RE.search(sentence):
        return None
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="split protocol claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no split protocol evidence",
        )
    if any(_has_split_protocol_evidence(payload) for payload in cited_payloads):
        return None
    return ClaimIssue(
        value=None,
        sentence=normalized,
        reason=(
            "split protocol claim requires split_id, split_protocol, "
            "train_test_split, holdout_split, heldout_split, cv_split, "
            "fold evidence, or evaluation split evidence in the cited result artifact"
        ),
    )


def _has_split_protocol_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if _SPLIT_PROTOCOL_ABSENCE_RE.search(lower):
        return False
    return _SPLIT_PROTOCOL_CLAIM_RE.search(lower) is not None


def _sample_size_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    claimed_counts = _sample_size_claim_numbers(sentence)
    if not claimed_counts:
        return None
    normalized = " ".join(sentence.split())[:240]
    first_claimed_count = claimed_counts[0]
    if not _is_positive_integer_count(first_claimed_count):
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason="sample-size claim count must be a positive integer",
        )
    if not cited_paths:
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason="sample-size claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason="cited artifact path is missing or has no sample-size evidence",
        )
    evidence_counts = [
        count
        for payload in cited_payloads
        for count in _sample_size_evidence_counts(payload)
    ]
    if not evidence_counts:
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason=(
                "sample-size claim requires n_samples, sample_count, sample_size, "
                "or row-count evidence in the cited result artifact"
            ),
        )
    for claimed_count in claimed_counts:
        if claimed_count not in evidence_counts:
            return ClaimIssue(
                value=claimed_count,
                sentence=normalized,
                reason="sample-size claim count does not match sample-size evidence in the cited result artifact",
            )
    return None


def _repetition_count_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    claimed_counts = _repetition_count_claim_numbers(sentence)
    if not claimed_counts:
        return None
    normalized = " ".join(sentence.split())[:240]
    first_claimed_count = claimed_counts[0]
    if not _is_positive_integer_count(first_claimed_count):
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason="repetition-count claim count must be a positive integer",
        )
    if not cited_paths:
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason="repetition-count claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason="cited artifact path is missing or has no repetition-count evidence",
        )
    evidence_counts = [
        count
        for payload in cited_payloads
        for count in _repetition_count_evidence_counts(payload)
    ]
    if not evidence_counts:
        return ClaimIssue(
            value=first_claimed_count,
            sentence=normalized,
            reason=(
                "repetition-count claim requires n_trials, trial_count, "
                "repeat_count, run_count, seed_count, or repeated measurement "
                "evidence in the cited result artifact"
            ),
        )
    for claimed_count in claimed_counts:
        if claimed_count not in evidence_counts:
            return ClaimIssue(
                value=claimed_count,
                sentence=normalized,
                reason="repetition-count claim does not match repetition evidence in the cited result artifact",
            )
    return None


def _split_ratio_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    claimed_pairs = _split_ratio_claim_pairs(sentence)
    if not claimed_pairs:
        return None
    normalized = " ".join(sentence.split())[:240]
    first_train, first_test = claimed_pairs[0]
    if not _valid_split_ratio_pair(first_train, first_test):
        return ClaimIssue(
            value=first_test,
            sentence=normalized,
            reason="split-ratio claim must use positive train/test percentages summing to 100",
        )
    if not cited_paths:
        return ClaimIssue(
            value=first_test,
            sentence=normalized,
            reason="split-ratio claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=first_test,
            sentence=normalized,
            reason="cited artifact path is missing or has no split-ratio evidence",
        )
    evidence_pairs = [
        pair
        for payload in cited_payloads
        for pair in _split_ratio_evidence_pairs(payload)
    ]
    if not evidence_pairs:
        return ClaimIssue(
            value=first_test,
            sentence=normalized,
            reason=(
                "split-ratio claim requires split_protocol, train_test_split, "
                "train/test fraction, or train/test row-count evidence in the cited result artifact"
            ),
        )
    for claimed_pair in claimed_pairs:
        if not any(_split_ratio_pairs_match(claimed_pair, evidence_pair) for evidence_pair in evidence_pairs):
            return ClaimIssue(
                value=claimed_pair[1],
                sentence=normalized,
                reason="split-ratio claim does not match split evidence in the cited result artifact",
            )
    return None


def _evidence_family_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    family = _evidence_family_claim(sentence)
    if family is None:
        return None
    label, checker, evidence_name = family
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths and _EVIDENCE_FAMILY_META_SENTENCE_RE.search(sentence):
        return None
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=f"{label} claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=f"cited artifact path is missing or has no {evidence_name} evidence",
        )
    if any(checker(payload) for payload in cited_payloads):
        specific_issue = _specific_evidence_identifier_issue(
            sentence,
            cited_payloads,
            label,
        )
        if specific_issue:
            return specific_issue
        return None
    return ClaimIssue(
        value=None,
        sentence=normalized,
        reason=f"{label} claim requires substantive {evidence_name} evidence in the cited result artifact",
    )


def _specific_evidence_identifier_issue(
    sentence: str,
    cited_payloads: list[Any],
    label: str,
) -> ClaimIssue | None:
    if label == "ablation/feature-importance":
        key_predicate = _is_ablation_evidence_key
    elif label == "error-analysis":
        key_predicate = _is_error_analysis_evidence_key
    else:
        return None
    identifiers = _claimed_specific_identifiers(sentence)
    if not identifiers:
        return None
    missing = [
        identifier
        for identifier in identifiers
        if not any(_evidence_contains_identifier(payload, identifier, key_predicate) for payload in cited_payloads)
    ]
    if not missing:
        return None
    return ClaimIssue(
        value=None,
        sentence=" ".join(sentence.split())[:240],
        reason=f"{label} claim names evidence item(s) not present in the cited result artifact: {missing}",
    )


def _claimed_specific_identifiers(sentence: str) -> list[str]:
    without_paths = _RESULT_FIGURE_PATH_RE.sub(" ", _RESULT_PATH_RE.sub(" ", sentence))
    raw_identifiers: list[str] = []
    raw_identifiers.extend(
        match.group(1)
        for match in re.finditer(r"`([^`]+)`", without_paths)
    )
    raw_identifiers.extend(
        match.group(1)
        for match in re.finditer(r"['\"]([^'\"]+)['\"]", without_paths)
    )
    raw_identifiers.extend(
        match.group(0)
        for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", without_paths)
    )
    identifiers = [
        normalized
        for raw in raw_identifiers
        if (normalized := _normalize_claim_identifier(raw))
        and normalized not in _GENERIC_EVIDENCE_IDENTIFIERS
    ]
    return list(dict.fromkeys(identifiers))


def _evidence_contains_identifier(payload: Any, identifier: str, key_predicate: Any) -> bool:
    for key, value in _walk_named_values_with_containers(payload):
        normalized_key = _normalize_evidence_key(key)
        if not key_predicate(normalized_key):
            continue
        if identifier in _normalize_claim_identifier(json.dumps(value, sort_keys=True)):
            return True
    return False


def _normalize_claim_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


_GENERIC_EVIDENCE_IDENTIFIERS = {
    "feature_importance",
    "feature_importances",
    "permutation_importance",
    "sensitivity_analysis",
    "sensitivity_results",
    "ablation_results",
    "ablation_study",
    "error_analysis",
    "error_slices",
    "slice_metrics",
    "subgroup_metrics",
    "residual_analysis",
    "failure_cases",
    "worst_case_errors",
    "misclassification_examples",
}


def _evidence_family_claim(sentence: str) -> tuple[str, Any, str] | None:
    lower = sentence.lower()
    if _EVIDENCE_FAMILY_ABSENCE_RE.search(lower):
        return None
    if _ABLATION_CLAIM_RE.search(lower):
        return (
            "ablation/feature-importance",
            _has_substantive_ablation_evidence,
            "ablation, feature-importance, or sensitivity",
        )
    if _ERROR_ANALYSIS_CLAIM_RE.search(lower):
        return (
            "error-analysis",
            _has_substantive_error_analysis_evidence,
            "error-analysis",
        )
    if _FAIRNESS_CLAIM_RE.search(lower) and not _FAIRNESS_ABSENCE_RE.search(lower):
        return (
            "fairness/bias-audit",
            _has_fairness_evidence,
            "fairness or bias-audit",
        )
    if _EFFICIENCY_CLAIM_RE.search(lower) and not _EFFICIENCY_ABSENCE_RE.search(lower):
        return (
            "efficiency/resource",
            _has_efficiency_evidence,
            "efficiency or resource",
        )
    return None


def _reproducibility_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
    project_dir: Path,
) -> ClaimIssue | None:
    if not _has_reproducibility_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths and _EVIDENCE_FAMILY_META_SENTENCE_RE.search(sentence):
        return None
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="reproducibility claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no reproducibility evidence",
        )
    missing_by_payload = [
        _reproducibility_bundle_missing_groups(payload)
        for payload in cited_payloads
    ]
    complete_payloads = [
        (path, payload)
        for path in cited_paths
        if path in result_payloads_by_path
        and not _reproducibility_bundle_missing_groups(result_payloads_by_path[path])
        for payload in [result_payloads_by_path[path]]
    ]
    provenance_issues: list[str] = []
    for path, payload in complete_payloads:
        iteration = _iteration_from_result_path(path)
        if iteration is None:
            provenance_issues.append(f"{path}: could not infer iteration for code provenance")
            continue
        payload_provenance_issues = audit_code_provenance(project_dir, iteration, payload)
        if not payload_provenance_issues:
            return None
        provenance_issues.extend(f"{path}: {issue}" for issue in payload_provenance_issues)
    if complete_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason=(
                "reproducibility claim requires valid code provenance with script/code "
                f"path and matching hash in the cited result artifact; {provenance_issues[:3]}"
            ),
        )
    missing = sorted(set().union(*(set(groups) for groups in missing_by_payload)))
    return ClaimIssue(
        value=None,
        sentence=normalized,
        reason=(
            "reproducibility claim requires seed, data source/fingerprint, "
            "split/protocol, environment, and code provenance evidence in the cited "
            f"result artifact; missing {missing}"
        ),
    )


def _has_reproducibility_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if _REPRODUCIBILITY_ABSENCE_RE.search(lower):
        return False
    return _REPRODUCIBILITY_CLAIM_RE.search(lower) is not None


def _has_statistical_evidence(
    result_values: list[ResultNumber],
    *,
    requires_comparison: bool,
) -> bool:
    return _has_significant_p_value(
        result_values,
        requires_comparison=requires_comparison,
    ) or _has_nonzero_confidence_interval(result_values)


def _has_non_significant_statistical_evidence(
    result_values: list[ResultNumber],
    *,
    requires_comparison: bool,
) -> bool:
    return _has_non_significant_p_value(
        result_values,
        requires_comparison=requires_comparison,
    ) or _has_zero_crossing_confidence_interval(result_values)


def _has_significant_p_value(
    result_values: list[ResultNumber],
    *,
    requires_comparison: bool,
) -> bool:
    for value in result_values:
        key = value.key_path.lower()
        if not _is_p_value_key(key):
            continue
        if not _p_value_key_matches_claim(key, result_values, requires_comparison=requires_comparison):
            continue
        alpha = _alpha_for_key(key, result_values)
        if 0 <= value.value <= alpha:
            return True
    return False


def _has_non_significant_p_value(
    result_values: list[ResultNumber],
    *,
    requires_comparison: bool,
) -> bool:
    for value in result_values:
        key = value.key_path.lower()
        if not _is_p_value_key(key):
            continue
        if not _p_value_key_matches_claim(key, result_values, requires_comparison=requires_comparison):
            continue
        alpha = _alpha_for_key(key, result_values)
        if alpha < value.value <= 1:
            return True
    return False


def _p_value_key_matches_claim(
    key: str,
    result_values: list[ResultNumber],
    *,
    requires_comparison: bool,
) -> bool:
    if not requires_comparison:
        return True
    if _is_comparison_stat_key(key):
        return True
    return _is_generic_p_value_key(key) and _has_single_p_value(result_values)


def _is_generic_p_value_key(key: str) -> bool:
    leaf = key.split(".")[-1].split("[", 1)[0]
    return leaf in {"p_value", "pvalue"}


def _has_single_p_value(result_values: list[ResultNumber]) -> bool:
    return sum(1 for value in result_values if _is_p_value_key(value.key_path.lower())) == 1


def _is_p_value_key(key: str) -> bool:
    return (
        _claim_key_matches_without_metadata_suffix(key, "p_value")
        or _claim_key_matches_without_metadata_suffix(key, "pvalue")
    )


def _alpha_for_key(key: str, result_values: list[ResultNumber], default: float = 0.05) -> float:
    key_scope = _key_scope_parts(key)
    candidates: list[tuple[int, float]] = []
    for value in result_values:
        alpha_key = value.key_path.lower()
        if not _is_alpha_key(alpha_key) or not 0 < value.value < 1:
            continue
        alpha_scope = _key_scope_parts(alpha_key)
        if _is_scope_prefix(alpha_scope, key_scope):
            candidates.append((len(alpha_scope), value.value))
    if not candidates:
        return default
    return max(candidates, key=lambda item: item[0])[1]


def _is_alpha_key(key: str) -> bool:
    leaf = key.rsplit(".", 1)[-1].split("[", 1)[0]
    return leaf in {"alpha", "significance_level"}


def _key_scope_parts(key: str) -> tuple[str, ...]:
    if "." not in key:
        return ()
    return tuple(part for part in key.rsplit(".", 1)[0].split(".") if part)


def _is_scope_prefix(candidate: tuple[str, ...], scope: tuple[str, ...]) -> bool:
    return len(candidate) <= len(scope) and scope[:len(candidate)] == candidate


def _requires_comparison_stat_evidence(sentence: str) -> bool:
    lower = sentence.lower()
    return any(token in lower for token in _COMPARISON_CLAIM_TOKENS)


def _has_negated_significance_claim(sentence: str) -> bool:
    return _NEGATED_SIGNIFICANCE_RE.search(sentence) is not None


def _has_nonzero_confidence_interval(result_values: list[ResultNumber]) -> bool:
    return any(low > 0 or high < 0 for low, high in _comparison_confidence_interval_bounds(result_values))


def _has_zero_crossing_confidence_interval(result_values: list[ResultNumber]) -> bool:
    return any(low <= 0 <= high for low, high in _comparison_confidence_interval_bounds(result_values))


def _comparison_confidence_interval_bounds(result_values: list[ResultNumber]) -> list[tuple[float, float]]:
    grouped: dict[str, list[ResultNumber]] = {}
    for value in result_values:
        key = value.key_path.lower()
        if not _is_confidence_interval_key(key):
            continue
        if not _is_comparison_stat_key(key):
            continue
        if (
            not _is_lower_interval_bound_key(key)
            and not _is_upper_interval_bound_key(key)
            and _trailing_index(key) is None
        ):
            continue
        base_key = _confidence_interval_group_key(key)
        grouped.setdefault(base_key, []).append(value)
    bounds: list[tuple[float, float]] = []
    for values in grouped.values():
        interval = _ordered_interval_bounds(values)
        if interval is None:
            continue
        low, high = interval
        if math.isfinite(low) and math.isfinite(high) and low <= high:
            bounds.append(interval)
    return bounds


def _ordered_interval_bounds(values: list[ResultNumber]) -> tuple[float, float] | None:
    if len(values) != 2:
        return None
    lower_values = [value.value for value in values if _is_lower_interval_bound_key(value.key_path.lower())]
    upper_values = [value.value for value in values if _is_upper_interval_bound_key(value.key_path.lower())]
    if lower_values and upper_values:
        return lower_values[0], upper_values[0]
    indexed = [(_trailing_index(value.key_path), value.value) for value in values]
    if all(index is not None for index, _ in indexed):
        by_index = {index: value for index, value in indexed if index is not None}
        if set(by_index) == {0, 1}:
            return by_index[0], by_index[1]
    return None


def _is_lower_interval_bound_key(key: str) -> bool:
    leaf = key.rsplit(".", 1)[-1]
    return leaf in {"lower", "low", "lo", "lower_bound", "ci_lower"}


def _is_upper_interval_bound_key(key: str) -> bool:
    leaf = key.rsplit(".", 1)[-1]
    return leaf in {"upper", "high", "hi", "upper_bound", "ci_upper"}


def _trailing_index(key: str) -> int | None:
    match = re.search(r"\[(\d+)\]$", key)
    return int(match.group(1)) if match else None


def _confidence_interval_group_key(key: str) -> str:
    key = re.sub(r"\[\d+\]$", "", key)
    return re.sub(r"\.(?:lower|low|lo|lower_bound|ci_lower|upper|high|hi|upper_bound|ci_upper)$", "", key)


def _is_comparison_stat_key(key: str) -> bool:
    return any(_comparison_evidence_key_matches(key, token) for token in _COMPARISON_STAT_TOKENS)


def _is_confidence_interval_key(key: str) -> bool:
    return any(
        _claim_key_matches_without_metadata_suffix(key, token)
        for token in ("ci", "ci95", "confidence", "confidence_interval")
    )


_COMPARISON_STAT_TOKENS = (
    "comparison",
    "pairwise",
    "improvement",
    "delta",
    "difference",
    "diff",
    "effect",
    "gain",
    "reduction",
    "vs_baseline",
    "over_baseline",
)
_COMPARISON_CLAIM_TOKENS = (
    "baseline",
    "improvement",
    "difference",
    "gain",
    "reduction",
    "increase",
    "decrease",
    "effect",
)


def _directional_improvement_issue(sentence: str) -> ClaimIssue | None:
    lower = sentence.lower()
    if not any(token in lower for token in _IMPROVEMENT_CLAIM_TOKENS):
        return None
    for match in _FROM_TO_RE.finditer(sentence):
        old_value = _parse_number(match.group("old"))
        new_value = _parse_number(match.group("new"))
        if old_value is None or new_value is None:
            continue
        metric = _from_to_metric_hint(sentence, match)
        direction = _metric_direction(metric)
        if direction is None:
            continue
        improved = new_value < old_value if direction == "lower" else new_value > old_value
        if not improved:
            return ClaimIssue(
                value=new_value,
                sentence=" ".join(sentence.split())[:240],
                reason=(
                    f"improvement direction contradicts {metric} metric direction; "
                    f"expected a {direction} value than the baseline"
                ),
            )
    return _baseline_comparison_direction_issue(sentence)


def _baseline_comparison_direction_issue(sentence: str) -> ClaimIssue | None:
    for match in _MODEL_VS_BASELINE_RE.finditer(sentence):
        issue = _comparison_direction_issue(
            sentence,
            match,
            model_group="model",
            baseline_group="baseline",
        )
        if issue:
            return issue
    for match in _BASELINE_VS_MODEL_RE.finditer(sentence):
        issue = _comparison_direction_issue(
            sentence,
            match,
            model_group="model",
            baseline_group="baseline",
        )
        if issue:
            return issue
    return None


def _has_explicit_directional_comparison(sentence: str) -> bool:
    return (
        _FROM_TO_RE.search(sentence) is not None
        or _MODEL_VS_BASELINE_RE.search(sentence) is not None
        or _BASELINE_VS_MODEL_RE.search(sentence) is not None
    )


def _comparison_direction_issue(
    sentence: str,
    match: re.Match[str],
    *,
    model_group: str,
    baseline_group: str,
) -> ClaimIssue | None:
    model_value = _parse_number(match.group(model_group))
    baseline_value = _parse_number(match.group(baseline_group))
    if model_value is None or baseline_value is None:
        return None
    metric = _comparison_metric_hint(sentence, match)
    direction = _metric_direction(metric)
    if direction is None:
        return None
    improved = model_value < baseline_value if direction == "lower" else model_value > baseline_value
    if improved:
        return None
    return ClaimIssue(
        value=model_value,
        sentence=" ".join(sentence.split())[:240],
        reason=(
            f"improvement direction contradicts {metric} metric direction; "
            f"expected a {direction} value than the baseline"
        ),
    )


def _baseline_superiority_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_positive_baseline_superiority_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="baseline superiority claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no baseline superiority evidence",
        )
    claimed_names = _claimed_baseline_names(sentence)
    if claimed_names:
        name_issue = _baseline_name_claim_issue(sentence, cited_paths, result_payloads_by_path)
        if name_issue:
            return name_issue
        named_status = _named_baseline_superiority_evidence_status(cited_payloads, claimed_names)
        if named_status == "positive":
            return None
        if named_status in {"negative", "conflict", "flag_negative"}:
            reason = "baseline superiority claim contradicts named baseline comparison evidence"
        else:
            reason = "baseline superiority claim requires named baseline metric or item-specific positive comparison evidence"
        return ClaimIssue(value=None, sentence=normalized, reason=reason)
    status = _baseline_superiority_evidence_status(cited_payloads)
    if status == "positive":
        return None
    if status in {"negative", "conflict", "flag_negative"}:
        reason = "baseline superiority claim contradicts explicit result artifact flags"
    else:
        reason = (
            "baseline superiority claim requires same-metric baseline comparison "
            "or positive improvement evidence in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _baseline_non_superiority_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_negative_baseline_superiority_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="baseline non-superiority claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no baseline non-superiority evidence",
        )
    claimed_names = _claimed_baseline_names(sentence)
    if claimed_names:
        name_issue = _baseline_name_claim_issue(sentence, cited_paths, result_payloads_by_path)
        if name_issue:
            return name_issue
        named_status = _named_baseline_superiority_evidence_status(cited_payloads, claimed_names)
        if named_status == "negative":
            return None
        if named_status in {"positive", "conflict", "flag_positive"}:
            reason = "baseline non-superiority claim contradicts named baseline comparison evidence"
        else:
            reason = "baseline non-superiority claim requires named baseline metric or item-specific non-superiority evidence"
        return ClaimIssue(value=None, sentence=normalized, reason=reason)
    status = _baseline_superiority_evidence_status(cited_payloads)
    if status == "negative":
        return None
    if status in {"positive", "conflict", "flag_positive"}:
        reason = "baseline non-superiority claim contradicts explicit result artifact flags"
    else:
        reason = (
            "baseline non-superiority claim requires non-positive improvement evidence "
            "or same-metric baseline comparison "
            "evidence in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _baseline_name_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_baseline_name_claim_context(sentence):
        return None
    claimed_names = _claimed_baseline_names(sentence)
    if not claimed_names:
        return None
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return None
    evidence_names = [
        name
        for payload in cited_payloads
        for name in _baseline_comparison_names(payload)
    ]
    missing = [
        name
        for name in claimed_names
        if not any(_baseline_names_match(name, evidence_name) for evidence_name in evidence_names)
    ]
    if not missing:
        return None
    return ClaimIssue(
        value=None,
        sentence=" ".join(sentence.split())[:240],
        reason=f"baseline claim names baseline(s) not present in the cited result artifact: {missing}",
    )


def _has_baseline_name_claim_context(sentence: str) -> bool:
    lower = sentence.lower()
    return "baseline" in lower and (
        _BASELINE_SUPERIORITY_RE.search(lower) is not None
        or _NEGATED_BASELINE_SUPERIORITY_RE.search(lower) is not None
    )


def _claimed_baseline_names(sentence: str) -> list[str]:
    without_paths = _RESULT_FIGURE_PATH_RE.sub(" ", _RESULT_PATH_RE.sub(" ", sentence))
    raw_names: list[str] = []
    for match in re.finditer(r"`([^`]+)`|['\"]([^'\"]+)['\"]", without_paths):
        raw = match.group(1) or match.group(2)
        window = without_paths[max(0, match.start() - 48):match.end() + 48].lower()
        if "baseline" in window:
            raw_names.append(raw)
    raw_names.extend(
        match.group("name")
        for match in _BASELINE_NAME_BEFORE_RE.finditer(without_paths)
    )
    for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", without_paths):
        window = without_paths[max(0, match.start() - 48):match.end() + 48].lower()
        if "baseline" in window:
            raw_names.append(match.group(0))
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_names:
        name = _clean_claimed_baseline_name(raw)
        if not name:
            continue
        key = _normalize_claim_identifier(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _clean_claimed_baseline_name(raw: str) -> str | None:
    tokens = [token for token in re.split(r"\s+", raw.strip(" \t\n\r`'\".,;:()[]{}")) if token]
    while tokens and tokens[0].lower() in _BASELINE_NAME_LEADING_STOPWORDS:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in _BASELINE_NAME_LEADING_STOPWORDS:
        tokens.pop()
    if not tokens:
        return None
    if any(token.lower() in _BASELINE_NAME_REJECT_WORDS for token in tokens):
        return None
    normalized = _normalize_claim_identifier(" ".join(tokens))
    if normalized in _GENERIC_BASELINE_NAME_IDENTIFIERS:
        return None
    if all(token.lower() in _GENERIC_BASELINE_NAME_WORDS for token in tokens):
        return None
    return " ".join(tokens)


def _sota_superiority_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_positive_sota_superiority_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="SOTA/prior-work superiority claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no SOTA/prior-work comparison evidence",
        )
    claimed_names = _claimed_sota_names(sentence)
    if claimed_names:
        name_issue = _sota_name_claim_issue(sentence, cited_paths, result_payloads_by_path)
        if name_issue:
            return name_issue
        named_status = _named_sota_superiority_evidence_status(cited_payloads, claimed_names)
        if named_status == "positive":
            return None
        if named_status in {"negative", "conflict", "flag_negative"}:
            reason = "SOTA/prior-work superiority claim contradicts named comparison evidence"
        else:
            reason = "SOTA/prior-work superiority claim requires named comparison metric or item-specific positive comparison evidence"
        return ClaimIssue(value=None, sentence=normalized, reason=reason)
    status = _sota_superiority_evidence_status(cited_payloads)
    if status == "positive":
        return None
    if status in {"negative", "conflict", "flag_negative"}:
        reason = "SOTA/prior-work superiority claim contradicts explicit result artifact flags"
    else:
        reason = (
            "SOTA/prior-work superiority claim requires same-metric prior-work "
            "comparison evidence in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _sota_non_superiority_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_negative_sota_superiority_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="SOTA/prior-work non-superiority claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no SOTA/prior-work non-superiority evidence",
        )
    claimed_names = _claimed_sota_names(sentence)
    if claimed_names:
        name_issue = _sota_name_claim_issue(sentence, cited_paths, result_payloads_by_path)
        if name_issue:
            return name_issue
        named_status = _named_sota_superiority_evidence_status(cited_payloads, claimed_names)
        if named_status == "negative":
            return None
        if named_status in {"positive", "conflict", "flag_positive"}:
            reason = "SOTA/prior-work non-superiority claim contradicts named comparison evidence"
        else:
            reason = "SOTA/prior-work non-superiority claim requires named comparison metric or item-specific non-superiority evidence"
        return ClaimIssue(value=None, sentence=normalized, reason=reason)
    status = _sota_superiority_evidence_status(cited_payloads)
    if status == "negative":
        return None
    if status in {"positive", "conflict", "flag_positive"}:
        reason = "SOTA/prior-work non-superiority claim contradicts explicit result artifact flags"
    else:
        reason = (
            "SOTA/prior-work non-superiority claim requires same-metric prior-work "
            "comparison evidence in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _sota_name_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    if not _has_sota_name_claim_context(sentence):
        return None
    claimed_names = _claimed_sota_names(sentence)
    if not claimed_names:
        return None
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return None
    evidence_names = [
        name
        for payload in cited_payloads
        for name in _sota_comparison_names(payload)
    ]
    missing = [
        name
        for name in claimed_names
        if not any(_comparison_names_match(name, evidence_name) for evidence_name in evidence_names)
    ]
    if not missing:
        return None
    return ClaimIssue(
        value=None,
        sentence=" ".join(sentence.split())[:240],
        reason=f"SOTA/prior-work claim names comparison item(s) not present in the cited result artifact: {missing}",
    )


def _has_sota_name_claim_context(sentence: str) -> bool:
    return _has_positive_sota_superiority_claim(sentence) or _has_negative_sota_superiority_claim(sentence)


def _claimed_sota_names(sentence: str) -> list[str]:
    without_paths = _RESULT_FIGURE_PATH_RE.sub(" ", _RESULT_PATH_RE.sub(" ", sentence))
    raw_names: list[str] = []
    for match in re.finditer(r"`([^`]+)`|['\"]([^'\"]+)['\"]", without_paths):
        raw = match.group(1) or match.group(2)
        window = without_paths[max(0, match.start() - 56):match.end() + 56].lower()
        if _has_sota_name_window_token(window):
            raw_names.append(raw)
    raw_names.extend(
        match.group("name")
        for match in _SOTA_NAME_BEFORE_RE.finditer(without_paths)
    )
    for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", without_paths):
        window = without_paths[max(0, match.start() - 56):match.end() + 56].lower()
        if _has_sota_name_window_token(window):
            raw_names.append(match.group(0))
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_names:
        name = _clean_claimed_sota_name(raw)
        if not name:
            continue
        key = _normalize_claim_identifier(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _has_sota_name_window_token(window: str) -> bool:
    return any(
        token in window
        for token in (
            "prior work",
            "previous work",
            "published",
            "leaderboard",
            "state-of-the-art",
            "state of the art",
            "sota",
        )
    )


def _clean_claimed_sota_name(raw: str) -> str | None:
    tokens = [token for token in re.split(r"\s+", raw.strip(" \t\n\r`'\".,;:()[]{}")) if token]
    while tokens and tokens[0].lower() in _SOTA_NAME_LEADING_STOPWORDS:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in _SOTA_NAME_LEADING_STOPWORDS:
        tokens.pop()
    if not tokens:
        return None
    if any(token.lower().rstrip(".") in _SOTA_NAME_REJECT_WORDS for token in tokens):
        return None
    normalized = _normalize_claim_identifier(" ".join(tokens))
    if normalized in _GENERIC_SOTA_NAME_IDENTIFIERS:
        return None
    if all(token.lower().rstrip(".") in _GENERIC_SOTA_NAME_WORDS for token in tokens):
        return None
    return " ".join(tokens)


def _target_achievement_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
    plan_metric_targets_by_iteration: dict[int, tuple[str, str, float]],
) -> ClaimIssue | None:
    if not _has_positive_target_achievement_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="target achievement claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [
        (path, result_payloads_by_path[path])
        for path in cited_paths
        if path in result_payloads_by_path
    ]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no target achievement evidence",
        )
    status = _target_achievement_evidence_status(
        cited_payloads,
        plan_metric_targets_by_iteration,
    )
    if status == "positive":
        return None
    if status == "negative":
        reason = "target achievement claim contradicts explicit result artifact flags"
    elif status == "missing_metric":
        reason = "target achievement claim requires the plan target metric value in the cited result artifact"
    else:
        reason = "target achievement claim requires target_achieved, goal_achieved, or success_criteria_met evidence in the cited result artifact"
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _target_non_achievement_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
    plan_metric_targets_by_iteration: dict[int, tuple[str, str, float]],
) -> ClaimIssue | None:
    if not _has_negative_target_achievement_claim(sentence):
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="target non-achievement claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [
        (path, result_payloads_by_path[path])
        for path in cited_paths
        if path in result_payloads_by_path
    ]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no target non-achievement evidence",
        )
    status = _target_achievement_evidence_status(
        cited_payloads,
        plan_metric_targets_by_iteration,
    )
    if status == "negative":
        return None
    if status == "positive":
        reason = "target non-achievement claim contradicts explicit result artifact flags"
    elif status == "missing_metric":
        reason = "target non-achievement claim requires the plan target metric value in the cited result artifact"
    else:
        reason = (
            "target non-achievement claim requires target_achieved=false, "
            "goal_achieved=false, success_criteria_met=false, or plan-target metric "
            "evidence in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _leakage_claim_issue(
    sentence: str,
    cited_paths: list[str],
    result_payloads_by_path: dict[str, Any],
) -> ClaimIssue | None:
    claim_kind = _leakage_claim_kind(sentence)
    if claim_kind is None:
        return None
    normalized = " ".join(sentence.split())[:240]
    if not cited_paths:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="leakage claim does not cite a concrete research/iter_*/results/*.json artifact path",
        )
    cited_payloads = [result_payloads_by_path[path] for path in cited_paths if path in result_payloads_by_path]
    if not cited_payloads:
        return ClaimIssue(
            value=None,
            sentence=normalized,
            reason="cited artifact path is missing or has no leakage evidence",
        )
    status = _leakage_evidence_status(cited_payloads, claim_kind)
    if status == "positive":
        return None
    if status == "negative":
        reason = "leakage claim contradicts explicit result artifact flags"
    elif claim_kind == "resolved":
        reason = (
            "leakage resolution claim requires leakage_resolved, leakage_mitigated, "
            "leakage_fixed, or no_leakage_after_fix evidence in the cited result artifact"
        )
    elif claim_kind == "problem":
        reason = (
            "leakage presence claim requires leakage_found=true, leakage_detected=true, "
            "or positive overlap/leakage evidence such as train_test_overlap, "
            "duplicate_overlap, group_overlap, target_leakage, temporal_leakage, "
            "preprocessing_leakage, or group_leakage in the cited result artifact"
        )
    else:
        reason = (
            "leakage absence claim requires leakage_found=false, leakage_detected=false, "
            "or overlap/leakage evidence plus scope evidence such as train_test_overlap, "
            "duplicate_overlap, group_overlap, target_leakage, temporal_leakage, "
            "preprocessing_leakage, or group_leakage in the cited result artifact"
        )
    return ClaimIssue(value=None, sentence=normalized, reason=reason)


def _leakage_claim_kind(sentence: str) -> str | None:
    lower = sentence.lower()
    if _LEAKAGE_RESOLUTION_CLAIM_RE.search(lower):
        return "resolved"
    if _NO_LEAKAGE_RE.search(lower):
        return "clean"
    if _POSITIVE_LEAKAGE_CLAIM_RE.search(lower):
        return "problem"
    return None


def _leakage_evidence_status(payloads: list[Any], kind: str) -> str:
    found_clean_indicator = False
    found_problem_indicator = False
    found_clean_scope_indicator = False
    found_resolution_positive = False
    found_resolution_negative = False
    for payload in payloads:
        for key, value in _walk_named_values_with_containers(payload):
            normalized = _normalize_evidence_key(key)
            if _is_leakage_indicator_key(normalized):
                indicator_value = _leakage_indicator_value(value)
                if indicator_value == "clean":
                    found_clean_indicator = True
                    if _is_specific_leakage_check_key(normalized):
                        found_clean_scope_indicator = True
                elif indicator_value == "problem":
                    found_problem_indicator = True
            if _is_leakage_resolution_key(normalized):
                resolution_value = _leakage_resolution_value(value)
                if resolution_value is True:
                    found_resolution_positive = True
                elif resolution_value is False:
                    found_resolution_negative = True
    if kind == "clean":
        if found_problem_indicator:
            return "negative"
        if found_clean_indicator and found_clean_scope_indicator:
            return "positive"
        return "missing"
    if kind == "problem":
        if found_problem_indicator:
            return "positive"
        if found_clean_indicator:
            return "negative"
        return "missing"
    if found_resolution_negative:
        return "negative"
    if found_resolution_positive:
        return "positive"
    if found_problem_indicator:
        return "negative"
    return "missing"


def _is_leakage_indicator_key(key: str) -> bool:
    return _shared_is_leakage_indicator_key(key)


def _is_leakage_resolution_key(key: str) -> bool:
    return _shared_is_leakage_resolution_key(key)


def _leakage_indicator_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "problem" if value else "clean"
    if isinstance(value, list):
        return "problem" if value else "clean"
    if isinstance(value, (int, float)):
        if value > 0:
            return "problem"
        if value == 0:
            return "clean"
        return None
    if isinstance(value, str):
        text = _normalize_evidence_text(value)
        if text in _CLEAN_LEAKAGE_VALUES:
            return "clean"
        if text in _PROBLEM_LEAKAGE_VALUES:
            return "problem"
        if any(token in text for token in ("not_detected", "not_found", "no_leakage", "clean")):
            return "clean"
        if any(token in text for token in ("detected", "found", "present", "leakage", "overlap")):
            return "problem"
    return None


def _leakage_resolution_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value > 0:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        text = _normalize_evidence_text(value)
        if text in _POSITIVE_LEAKAGE_RESOLUTION_VALUES:
            return True
        if text in _NEGATIVE_LEAKAGE_RESOLUTION_VALUES:
            return False
        if any(token in text for token in ("not_resolved", "unresolved", "not_fixed", "not_mitigated")):
            return False
        if any(token in text for token in ("resolved", "mitigated", "fixed", "clean", "no_leakage")):
            return True
    return None


def _normalize_evidence_key(key: str) -> str:
    return key.lower().replace("-", "_").replace("/", "_").replace(" ", "_")


def _normalize_evidence_text(value: str) -> str:
    return re.sub(r"[\s\-/]+", "_", value.strip().lower())


def _walk_named_values_with_containers(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = []
    if prefix and isinstance(value, list):
        values.append((prefix, value))
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            values.extend(_walk_named_values_with_containers(item, child_prefix))
        return values
    if isinstance(value, list):
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            values.extend(_walk_named_values_with_containers(item, child_prefix))
        return values
    if prefix:
        values.append((prefix, value))
    return values


def _has_positive_target_achievement_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if _NEGATED_TARGET_ACHIEVEMENT_RE.search(lower):
        return False
    return _TARGET_ACHIEVEMENT_RE.search(lower) is not None


def _has_negative_target_achievement_claim(sentence: str) -> bool:
    lower = sentence.lower()
    return _NEGATED_TARGET_ACHIEVEMENT_RE.search(lower) is not None


def _target_achievement_evidence_status(
    payloads: list[tuple[str, Any]],
    plan_metric_targets_by_iteration: dict[int, tuple[str, str, float]],
) -> str:
    found_positive = False
    found_negative = False
    found_missing_metric = False
    for path, payload in payloads:
        for key, value in _walk_named_values(payload):
            if not _is_target_achievement_flag_key(key.lower()):
                continue
            flag_value = _truth_value(value)
            if flag_value is True:
                found_positive = True
            if flag_value is False:
                found_negative = True
        iteration = _iteration_from_result_path(path)
        target = plan_metric_targets_by_iteration.get(iteration) if iteration is not None else None
        if target is not None:
            metric_status = _plan_target_metric_status(payload, target)
            if metric_status == "negative":
                found_negative = True
            elif metric_status == "missing":
                found_missing_metric = True
    if found_negative:
        return "negative"
    if found_missing_metric:
        return "missing_metric"
    if found_positive:
        return "positive"
    return "missing"


def _has_positive_baseline_superiority_claim(sentence: str) -> bool:
    if _is_interrogative_claim_sentence(sentence):
        return False
    lower = sentence.lower()
    if _is_research_question_or_objective_sentence(lower):
        return False
    if _NEGATED_BASELINE_SUPERIORITY_RE.search(lower):
        return False
    return _BASELINE_SUPERIORITY_RE.search(lower) is not None


def _has_negative_baseline_superiority_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if _has_negated_significance_claim(sentence):
        return False
    return "baseline" in lower and _NEGATED_BASELINE_SUPERIORITY_RE.search(lower) is not None


def _has_positive_sota_superiority_claim(sentence: str) -> bool:
    if _is_interrogative_claim_sentence(sentence):
        return False
    lower = sentence.lower()
    if _is_research_question_or_objective_sentence(lower):
        return False
    if _NEGATED_SOTA_SUPERIORITY_RE.search(lower):
        return False
    return _SOTA_SUPERIORITY_RE.search(lower) is not None


def _is_interrogative_claim_sentence(sentence: str) -> bool:
    stripped = re.sub(r"^\s*#{1,6}\s*", "", sentence.strip())
    question_index = stripped.find("?")
    if question_index < 0:
        return False
    question = stripped[:question_index].strip().lower()
    return re.match(
        r"^(?:does|do|did|can|could|will|would|is|are|was|were|which|what|when|whether|why|how)\b",
        question,
    ) is not None


def _is_research_question_or_objective_sentence(lower_sentence: str) -> bool:
    return (
        "whether" in lower_sentence
        and any(
            token in lower_sentence
            for token in (
                "objective",
                "goal",
                "aim",
                "question",
                "hypothesis",
                "compare",
                "test",
                "evaluate",
                "assess",
                "investigate",
            )
        )
    )


def _has_negative_sota_superiority_claim(sentence: str) -> bool:
    lower = sentence.lower()
    if re.search(r"\b(?:do|does|did)\s+not\s+claim\b", lower):
        return False
    if not _NEGATED_SOTA_SUPERIORITY_RE.search(lower):
        return False
    return any(
        token in lower
        for token in (
            "leaderboard",
            "prior work",
            "previous work",
            "published",
            "sota",
            "state-of-the-art",
            "state of the art",
        )
    )


def _named_baseline_superiority_evidence_status(payloads: list[Any], claimed_names: list[str]) -> str:
    return _named_comparison_superiority_evidence_status(
        payloads,
        claimed_names,
        _baseline_comparison_items,
        _baseline_names_match,
        _is_superiority_flag_key,
    )


def _named_sota_superiority_evidence_status(payloads: list[Any], claimed_names: list[str]) -> str:
    return _named_comparison_superiority_evidence_status(
        payloads,
        claimed_names,
        _sota_comparison_items,
        _comparison_names_match,
        _is_sota_superiority_flag_key,
    )


def _named_comparison_superiority_evidence_status(
    payloads: list[Any],
    claimed_names: list[str],
    comparison_items: Any,
    names_match: Any,
    flag_predicate: Any,
) -> str:
    statuses: list[str] = []
    for payload in payloads:
        matched_items = [
            item
            for name, item in comparison_items(payload)
            if any(names_match(claimed_name, name) for claimed_name in claimed_names)
        ]
        for item in matched_items:
            statuses.append(_comparison_item_superiority_status(payload, item, flag_predicate))
    return _combine_comparison_status(statuses)


def _comparison_item_superiority_status(payload: Any, item: Any, flag_predicate: Any) -> str:
    flag_statuses: list[str] = []
    substantive_statuses: list[str] = []
    for key, value in _walk_named_values(item):
        normalized = key.lower()
        if flag_predicate(normalized):
            flag_value = _truth_value(value)
            if flag_value is not None:
                flag_statuses.append("positive" if flag_value else "negative")
        if _is_positive_improvement_key(normalized):
            numeric = _numeric_value(value)
            if numeric is not None:
                if _is_statistical_or_uncertainty_key(normalized):
                    continue
                substantive_statuses.append("positive" if numeric > 0 else "negative")
    numeric_status = _named_comparison_numeric_status(payload, item)
    if numeric_status != "missing":
        substantive_statuses.append(numeric_status)
    return _comparison_status_with_flags(substantive_statuses, flag_statuses)


def _named_comparison_numeric_status(payload: Any, item: Any) -> str:
    for metric in _SPECIFIC_METRIC_HINTS:
        canonical = _canonical_metric_hint(metric)
        direction = _metric_direction(canonical)
        if direction is None:
            continue
        model_values = _model_metric_values(payload, canonical)
        comparison_values = _comparison_item_metric_values(item, canonical)
        if not model_values or not comparison_values:
            continue
        model_best = min(model_values) if direction == "lower" else max(model_values)
        comparison_best = min(comparison_values) if direction == "lower" else max(comparison_values)
        improved = model_best < comparison_best if direction == "lower" else model_best > comparison_best
        return "positive" if improved else "negative"
    return "missing"


def _model_metric_values(payload: Any, metric: str) -> list[float]:
    return [
        float(value)
        for key, value in _walk_named_values(payload)
        if _numeric_value(value) is not None
        and _key_mentions_metric(key.lower(), metric)
        and not _key_mentions_baseline(key.lower())
        and not _key_mentions_external_sota(key.lower())
        and not _is_metric_support_stat_key(key.lower())
        and not _is_derived_comparison_metric_key(key.lower())
    ]


def _comparison_item_metric_values(item: Any, metric: str) -> list[float]:
    return [
        float(value)
        for key, value in _walk_named_values(item)
        if _numeric_value(value) is not None
        and _key_mentions_metric(key.lower(), metric)
        and not _is_metric_support_stat_key(key.lower())
        and not _is_derived_comparison_metric_key(key.lower())
    ]


def _sota_superiority_evidence_status(payloads: list[Any]) -> str:
    statuses: list[str] = []
    for payload in payloads:
        flag_statuses: list[str] = []
        for key, value in _walk_named_values(payload):
            normalized = key.lower()
            if _is_sota_superiority_flag_key(normalized):
                flag_value = _truth_value(value)
                if flag_value is not None:
                    flag_statuses.append("positive" if flag_value else "negative")
        numeric_status = _numeric_sota_superiority_status(payload)
        substantive_statuses = [] if numeric_status == "missing" else [numeric_status]
        statuses.append(_comparison_status_with_flags(substantive_statuses, flag_statuses))
    return _combine_comparison_status(statuses)


def _numeric_sota_superiority_status(payload: Any) -> str:
    values = [
        (key.lower(), value)
        for key, value in _walk_named_values(payload)
        if _numeric_value(value) is not None
    ]
    for metric in _SPECIFIC_METRIC_HINTS:
        canonical = _canonical_metric_hint(metric)
        direction = _metric_direction(canonical)
        if direction is None:
            continue
        model_values = [
            float(value)
            for key, value in values
            if _key_mentions_metric(key, canonical)
            and not _key_mentions_external_sota(key)
            and not _key_mentions_baseline(key)
            and not _is_metric_support_stat_key(key)
            and not _is_derived_comparison_metric_key(key)
        ]
        sota_values = [
            float(value)
            for key, value in values
            if _key_mentions_metric(key, canonical)
            and _key_mentions_external_sota(key)
            and not _is_metric_support_stat_key(key)
            and not _is_derived_comparison_metric_key(key)
        ]
        if not model_values or not sota_values:
            continue
        model_best = min(model_values) if direction == "lower" else max(model_values)
        sota_best = min(sota_values) if direction == "lower" else max(sota_values)
        improved = model_best < sota_best if direction == "lower" else model_best > sota_best
        return "positive" if improved else "negative"
    return "missing"


def _baseline_superiority_evidence_status(payloads: list[Any]) -> str:
    statuses: list[str] = []
    for payload in payloads:
        flag_statuses: list[str] = []
        substantive_statuses: list[str] = []
        for key, value in _walk_named_values(payload):
            normalized = key.lower()
            if _is_superiority_flag_key(normalized):
                flag_value = _truth_value(value)
                if flag_value is not None:
                    flag_statuses.append("positive" if flag_value else "negative")
            if _is_positive_improvement_key(normalized):
                numeric = _numeric_value(value)
                if numeric is not None:
                    if _is_statistical_or_uncertainty_key(normalized):
                        continue
                    substantive_statuses.append("positive" if numeric > 0 else "negative")
        numeric_status = _numeric_baseline_superiority_status(payload)
        if numeric_status != "missing":
            substantive_statuses.append(numeric_status)
        statuses.append(_comparison_status_with_flags(substantive_statuses, flag_statuses))
    return _combine_comparison_status(statuses)


def _comparison_status_with_flags(
    substantive_statuses: list[str],
    flag_statuses: list[str],
) -> str:
    substantive_status = _combine_comparison_status(substantive_statuses)
    flag_status = _combine_flag_status(flag_statuses)
    if flag_status == "conflict":
        return "conflict"
    if substantive_status == "missing":
        if flag_status == "positive":
            return "flag_positive"
        if flag_status == "negative":
            return "flag_negative"
        return "missing"
    if flag_status != "missing" and flag_status != substantive_status:
        return "conflict"
    return substantive_status


def _combine_comparison_status(statuses: list[str]) -> str:
    concrete = [status for status in statuses if status != "missing"]
    if not concrete:
        return "missing"
    if "conflict" in concrete:
        return "conflict"
    has_positive = "positive" in concrete
    has_negative = "negative" in concrete
    has_flag_positive = "flag_positive" in concrete
    has_flag_negative = "flag_negative" in concrete
    if has_positive and (has_negative or has_flag_negative):
        return "conflict"
    if has_negative and (has_positive or has_flag_positive):
        return "conflict"
    if has_positive:
        return "positive"
    if has_negative:
        return "negative"
    if has_flag_positive and has_flag_negative:
        return "conflict"
    if has_flag_positive:
        return "flag_positive"
    if has_flag_negative:
        return "flag_negative"
    return "missing"


def _combine_flag_status(statuses: list[str]) -> str:
    concrete = [status for status in statuses if status != "missing"]
    if not concrete:
        return "missing"
    if "positive" in concrete and "negative" in concrete:
        return "conflict"
    if "positive" in concrete:
        return "positive"
    if "negative" in concrete:
        return "negative"
    return "missing"


def _numeric_baseline_superiority_status(payload: Any) -> str:
    values = [
        (key.lower(), value)
        for key, value in _walk_named_values(payload)
        if _numeric_value(value) is not None
    ]
    for metric in _SPECIFIC_METRIC_HINTS:
        canonical = _canonical_metric_hint(metric)
        direction = _metric_direction(canonical)
        if direction is None:
            continue
        model_values = [
            float(value)
            for key, value in values
            if _key_mentions_metric(key, canonical) and not _key_mentions_baseline(key)
            and not _is_metric_support_stat_key(key)
            and not _is_derived_comparison_metric_key(key)
        ]
        baseline_values = [
            float(value)
            for key, value in values
            if _key_mentions_metric(key, canonical) and _key_mentions_baseline(key)
            and not _is_metric_support_stat_key(key)
            and not _is_derived_comparison_metric_key(key)
        ]
        if not model_values or not baseline_values:
            continue
        model_best = min(model_values) if direction == "lower" else max(model_values)
        baseline_best = min(baseline_values) if direction == "lower" else max(baseline_values)
        improved = model_best < baseline_best if direction == "lower" else model_best > baseline_best
        return "positive" if improved else "negative"
    return "missing"


def _key_mentions_metric(key: str, metric: str) -> bool:
    return _shared_is_metric_evidence_key(key, metric)


def _key_mentions_baseline(key: str) -> bool:
    return any(
        _comparison_evidence_key_matches(key, token)
        for token in (
            "baseline",
            "baseline_method",
            "baseline_model",
            "naive",
            "control",
            "reference_model",
        )
    )


def _key_mentions_external_sota(key: str) -> bool:
    return any(
        _comparison_evidence_key_matches(key, token)
        for token in (
            "sota",
            "sota_model",
            "state_of_the_art",
            "state-of-the-art",
            "state_of_the_art_model",
            "prior_work",
            "prior_work_method",
            "prior_work_model",
            "previous_work",
            "previous_work_method",
            "previous_work_model",
            "published",
            "published_method",
            "published_model",
            "literature",
            "leaderboard",
            "leaderboard_model",
        )
    )


def _is_superiority_flag_key(key: str) -> bool:
    return any(
        _comparison_evidence_key_matches(key, token)
        for token in ("beats_baseline", "beats_naive", "beats_ma", "outperforms_baseline")
    )


def _is_sota_superiority_flag_key(key: str) -> bool:
    return any(
        _comparison_evidence_key_matches(key, token)
        for token in (
            "beats_sota",
            "outperforms_sota",
            "beats_prior_work",
            "outperforms_prior_work",
            "beats_previous_work",
            "outperforms_previous_work",
            "beats_state_of_the_art",
            "outperforms_state_of_the_art",
        )
    )


def _is_target_achievement_flag_key(key: str) -> bool:
    return _shared_is_goal_achievement_evidence_key(key)


def _evaluation_protocol_claim_count(sentence: str) -> int | None:
    match = re.search(
        r"\b(\d+)\s*[- ]?\s*(?:fold|folds|split|splits|repeat|repeats)\b",
        sentence.lower(),
    )
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _sample_size_claim_numbers(sentence: str) -> list[float]:
    counts: list[float] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in _SAMPLE_SIZE_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            raw = match.group("count")
            if raw.endswith("%"):
                continue
            value = _parse_number(raw)
            if value is None or not math.isfinite(value):
                continue
            span = match.span("count")
            if span in seen_spans:
                continue
            seen_spans.add(span)
            counts.append(value)
    return counts


def _sample_size_hint_for_number(sentence: str, number_start: int, number_end: int) -> bool:
    for pattern in _SAMPLE_SIZE_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            count_start, count_end = match.span("count")
            if count_start <= number_start and number_end <= count_end:
                return True
    return False


def _repetition_count_claim_numbers(sentence: str) -> list[float]:
    counts: list[float] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in _REPETITION_COUNT_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            raw = match.group("count")
            if raw.endswith("%"):
                continue
            value = _parse_number(raw)
            if value is None or not math.isfinite(value):
                continue
            span = match.span("count")
            if span in seen_spans:
                continue
            seen_spans.add(span)
            counts.append(value)
    return counts


def _repetition_count_hint_for_number(sentence: str, number_start: int, number_end: int) -> bool:
    for pattern in _REPETITION_COUNT_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            count_start, count_end = match.span("count")
            if count_start <= number_start and number_end <= count_end:
                return True
    return False


def _split_ratio_claim_pairs(sentence: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in _SPLIT_RATIO_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            pair = _split_ratio_pair_from_match(match)
            if pair is None:
                continue
            span = match.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            pairs.append(pair)
    for pattern in _SPLIT_TEST_PERCENT_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            test = _parse_number(match.group("test"))
            if test is None or not math.isfinite(test):
                continue
            pair = (100.0 - test, test)
            span = match.span("test")
            if span in seen_spans:
                continue
            seen_spans.add(span)
            pairs.append(pair)
    return pairs


def _split_ratio_pair_from_match(match: re.Match[str]) -> tuple[float, float] | None:
    train = _parse_number(match.group("train"))
    test = _parse_number(match.group("test"))
    if train is None or test is None or not math.isfinite(train) or not math.isfinite(test):
        return None
    return train, test


def _split_ratio_hint_for_number(sentence: str, number_start: int, number_end: int) -> bool:
    for pattern in _SPLIT_RATIO_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            for group in ("train", "test"):
                start, end = match.span(group)
                if start <= number_start and number_end <= _claim_number_group_end(sentence, end):
                    return True
    for pattern in _SPLIT_TEST_PERCENT_CLAIM_PATTERNS:
        for match in pattern.finditer(sentence):
            start, end = match.span("test")
            if start <= number_start and number_end <= _claim_number_group_end(sentence, end):
                return True
    return False


def _claim_number_group_end(sentence: str, group_end: int) -> int:
    if group_end < len(sentence) and sentence[group_end] == "%":
        return group_end + 1
    return group_end


def _sample_size_evidence_counts(payload: Any) -> list[float]:
    return [
        number.value
        for number in _walk_numbers(payload)
        if _is_sample_size_evidence_key(number.key_path) and _is_positive_integer_count(number.value)
    ]


def _repetition_count_evidence_counts(payload: Any) -> list[float]:
    declared_counts = [
        number.value
        for number in _walk_numbers(payload)
        if _is_repetition_count_evidence_key(number.key_path) and _is_positive_integer_count(number.value)
    ]
    materialized_counts = [
        count
        for key, value in _walk_named_values_with_containers(payload)
        if _is_robustness_evidence_key(key)
        for count in _repeated_measurement_counts(value)
    ]
    return declared_counts + materialized_counts


def _split_ratio_evidence_pairs(payload: Any) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for key, value in _walk_named_values_with_containers(payload):
        if isinstance(value, str) and _is_split_ratio_text_evidence_key(key):
            pairs.extend(_split_ratio_claim_pairs(value))
    pairs.extend(_split_ratio_numeric_evidence_pairs(payload))
    return [pair for pair in pairs if _valid_split_ratio_pair(*pair)]


def _split_ratio_numeric_evidence_pairs(payload: Any) -> list[tuple[float, float]]:
    train_values: list[float] = []
    test_values: list[float] = []
    for number in _walk_numbers(payload):
        if not math.isfinite(number.value) or number.value <= 0:
            continue
        leaf = _normalize_claim_key_path(_sample_size_leaf_key(number.key_path))
        if _split_ratio_train_key(leaf):
            train_values.append(number.value)
        elif _split_ratio_test_key(leaf):
            test_values.append(number.value)

    pairs: list[tuple[float, float]] = []
    for train in train_values:
        for test in test_values:
            pair = _coerce_split_ratio_pair(train, test)
            if pair is not None:
                pairs.append(pair)
    return pairs


def _is_split_ratio_text_evidence_key(key: str) -> bool:
    leaf = _normalize_claim_key_path(_sample_size_leaf_key(key))
    return any(_sample_size_key_matches(leaf, token) for token in _SPLIT_RATIO_TEXT_EVIDENCE_KEY_TOKENS)


def _split_ratio_train_key(leaf: str) -> bool:
    return any(_sample_size_key_matches(leaf, token) for token in _SPLIT_RATIO_TRAIN_EVIDENCE_KEY_TOKENS)


def _split_ratio_test_key(leaf: str) -> bool:
    return any(_sample_size_key_matches(leaf, token) for token in _SPLIT_RATIO_TEST_EVIDENCE_KEY_TOKENS)


def _coerce_split_ratio_pair(train: float, test: float) -> tuple[float, float] | None:
    total = train + test
    if total <= 0:
        return None
    if 0 < train <= 1 and 0 < test <= 1 and math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        return train * 100.0, test * 100.0
    if 0 < train < 100 and 0 < test < 100 and math.isclose(total, 100.0, rel_tol=1e-6, abs_tol=1e-6):
        return train, test
    return train / total * 100.0, test / total * 100.0


def _valid_split_ratio_pair(train: float, test: float) -> bool:
    return (
        math.isfinite(train)
        and math.isfinite(test)
        and train > 0
        and test > 0
        and math.isclose(train + test, 100.0, rel_tol=1e-6, abs_tol=1e-6)
    )


def _split_ratio_pairs_match(claimed: tuple[float, float], evidence: tuple[float, float]) -> bool:
    return math.isclose(claimed[0], evidence[0], abs_tol=0.25) and math.isclose(claimed[1], evidence[1], abs_tol=0.25)


def _is_sample_size_evidence_key(key: str) -> bool:
    normalized_leaf = _normalize_claim_key_path(_sample_size_leaf_key(key))
    if not normalized_leaf or _claim_key_has_metadata_suffix(normalized_leaf):
        return False
    return any(_sample_size_key_matches(normalized_leaf, token) for token in _SAMPLE_SIZE_EVIDENCE_KEY_TOKENS)


def _is_repetition_count_evidence_key(key: str) -> bool:
    if "[" in str(key):
        return False
    normalized_leaf = _normalize_claim_key_path(_sample_size_leaf_key(key))
    if not normalized_leaf or _claim_key_has_metadata_suffix(normalized_leaf):
        return False
    return any(_sample_size_key_matches(normalized_leaf, token) for token in _REPETITION_COUNT_EVIDENCE_KEY_TOKENS)


def _sample_size_leaf_key(key: str) -> str:
    leaf = str(key).split(".")[-1]
    return re.sub(r"\[\d+\]", "", leaf)


def _sample_size_key_matches(normalized_key: str, token: str) -> bool:
    key_parts = [part for part in normalized_key.split("_") if part]
    token_parts = [part for part in _normalize_claim_key_path(token).split("_") if part]
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    start = len(key_parts) - len(token_parts)
    if not _claim_key_parts_match_token(key_parts[start:], token_parts):
        return False
    return not _claim_prefix_has_negation(key_parts[:start], _CLAIM_NEGATION_PREFIX_TOKENS)


def _is_positive_integer_count(value: float) -> bool:
    return math.isfinite(value) and value > 0 and value.is_integer()


def _repeated_measurement_counts(value: Any) -> list[float]:
    if isinstance(value, list):
        count = sum(1 for item in value if _has_substantive_repeated_measurement(item))
        return [float(count)] if count > 0 else []
    if isinstance(value, dict):
        count = sum(1 for item in value.values() if _has_substantive_repeated_measurement(item))
        return [float(count)] if count > 0 else []
    return []


def _has_substantive_repeated_measurement(value: Any) -> bool:
    return any(
        _is_substantive_result_number_key(number.key_path)
        for number in _walk_numbers(value)
    )


_SAMPLE_SIZE_EVIDENCE_KEY_TOKENS = (
    "n",
    "n_samples",
    "num_samples",
    "samples",
    "sample_count",
    "sample_size",
    "n_observations",
    "num_observations",
    "observations",
    "observation_count",
    "n_participants",
    "num_participants",
    "participants",
    "participant_count",
    "n_examples",
    "num_examples",
    "examples",
    "example_count",
    "n_instances",
    "num_instances",
    "instances",
    "instance_count",
    "n_cases",
    "num_cases",
    "cases",
    "case_count",
    "n_rows",
    "num_rows",
    "rows",
    "row_count",
    "train_rows",
    "test_rows",
    "validation_rows",
    "evaluation_rows",
)


_REPETITION_COUNT_EVIDENCE_KEY_TOKENS = (
    "n_trials",
    "num_trials",
    "trial_count",
    "n_runs",
    "num_runs",
    "run_count",
    "n_seeds",
    "num_seeds",
    "seed_count",
    "n_repeats",
    "num_repeats",
    "repeat_count",
    "repeats",
    "n_replicates",
    "num_replicates",
    "replicate_count",
    "replicates",
    "benchmark_repeats",
    "measurement_runs",
)


_SPLIT_RATIO_TEXT_EVIDENCE_KEY_TOKENS = (
    "split_protocol",
    "train_test_split",
    "holdout_split",
    "heldout_split",
    "split_ratio",
    "split_description",
)


_SPLIT_RATIO_TRAIN_EVIDENCE_KEY_TOKENS = (
    "train_fraction",
    "training_fraction",
    "train_percent",
    "training_percent",
    "train_percentage",
    "training_percentage",
    "train_size",
    "training_size",
    "train_rows",
    "training_rows",
    "train_count",
    "training_count",
)


_SPLIT_RATIO_TEST_EVIDENCE_KEY_TOKENS = (
    "test_fraction",
    "validation_fraction",
    "holdout_fraction",
    "heldout_fraction",
    "test_percent",
    "validation_percent",
    "holdout_percent",
    "heldout_percent",
    "test_percentage",
    "validation_percentage",
    "holdout_percentage",
    "heldout_percentage",
    "test_size",
    "validation_size",
    "holdout_size",
    "heldout_size",
    "test_rows",
    "validation_rows",
    "holdout_rows",
    "heldout_rows",
    "test_count",
    "validation_count",
    "holdout_count",
    "heldout_count",
)


def _collect_plan_metric_targets_by_iteration(project_dir: Path) -> dict[int, tuple[str, str, float]]:
    targets: dict[int, tuple[str, str, float]] = {}
    for plan_path in research_plan_files(project_dir):
        iteration = iteration_number_from_dir_name(plan_path.parent.name)
        if iteration is None:
            continue
        try:
            data = json.loads(plan_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        target = _plan_metric_target(data)
        if target is not None:
            targets[iteration] = target
    return targets


def _plan_metric_target(plan: dict[str, Any]) -> tuple[str, str, float] | None:
    target = _shared_plan_metric_target(plan)
    if target is None:
        return None
    metric_name, direction, target_value = target
    return _canonical_metric_hint(metric_name), direction, target_value


def _iteration_from_result_path(path: str) -> int | None:
    match = re.search(r"research/iter_(\d+)/results/", path)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _plan_target_metric_status(payload: Any, target: tuple[str, str, float]) -> str:
    metric_name, direction, target_value = target
    values = [
        float(value)
        for key, value in _walk_named_values(payload)
        if _numeric_value(value) is not None
        and _key_mentions_metric(key.lower(), metric_name)
        and not _key_mentions_baseline(key.lower())
        and not _key_mentions_target_metadata(key.lower())
        and not _is_metric_support_stat_key(key.lower())
    ]
    if not values:
        return "missing"
    best = min(values) if direction == "minimize" else max(values)
    if direction == "minimize":
        return "positive" if best <= target_value else "negative"
    return "positive" if best >= target_value else "negative"


def _plan_target_number_status(
    value: float,
    sentence: str,
    number_start: int,
    number_end: int,
    cited_paths: list[str],
    plan_metric_targets_by_iteration: dict[int, tuple[str, str, float]],
    metric_hint: str | None,
    tolerance: float,
) -> str | None:
    if not _number_is_target_threshold(sentence, number_start, number_end):
        return None
    targets: list[tuple[str, str, float]] = []
    for path in cited_paths:
        iteration = _iteration_from_result_path(path)
        if iteration is None:
            continue
        target = plan_metric_targets_by_iteration.get(iteration)
        if target is None:
            continue
        if metric_hint is not None and target[0] != metric_hint:
            continue
        targets.append(target)
    if not targets:
        return None
    candidates = _numeric_claim_candidates(value)
    if any(
        abs(candidate - target_value) <= max(tolerance, abs(target_value) * 1e-6)
        for _, _, target_value in targets
        for candidate in candidates
    ):
        return "matched"
    return "mismatch"


def _number_is_target_threshold(sentence: str, number_start: int, number_end: int) -> bool:
    before = sentence[max(0, number_start - 64):number_start].lower()
    after = sentence[number_end:number_end + 24].lower()
    nearby = before + after
    if not any(token in nearby for token in ("target", "threshold", "goal", "success criteria")):
        return False
    short_before = sentence[max(0, number_start - 16):number_start].lower()
    return (
        any(op in short_before for op in ("<=", ">=", "<", ">", "="))
        or re.search(r"\b(?:target|threshold|goal)\s*(?:of|:|=|was|is)\b", before) is not None
    )


def _key_mentions_target_metadata(key: str) -> bool:
    return any(token in key for token in ("target", "threshold", "goal", "criteria"))


def _is_derived_comparison_metric_key(key: str) -> bool:
    return any(
        _comparison_evidence_key_matches(key, token)
        for token in (
            "delta",
            "difference",
            "diff",
            "effect",
            "gain",
            "improvement",
            "reduction",
        )
    ) or _shared_is_metric_support_numeric_key(key)


def _is_metric_support_stat_key(key: str) -> bool:
    return _shared_is_metric_support_numeric_key(key)


def _is_statistical_or_uncertainty_key(key: str) -> bool:
    return _shared_contains_metric_support_numeric_token(key)


def _is_positive_improvement_key(key: str) -> bool:
    return any(_positive_improvement_key_matches(key, token) for token in _POSITIVE_IMPROVEMENT_EVIDENCE_TOKENS)


def _positive_improvement_key_matches(key: str, token: str) -> bool:
    normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    normalized_token = re.sub(r"[^a-z0-9]+", "_", str(token).lower()).strip("_")
    key_parts = [part for part in normalized_key.split("_") if part]
    token_parts = [part for part in normalized_token.split("_") if part]
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    for start in range(0, len(key_parts) - len(token_parts) + 1):
        if key_parts[start:start + len(token_parts)] != token_parts:
            continue
        if _claim_prefix_has_negation(key_parts[:start], _COMPARISON_NEGATION_PREFIX_TOKENS):
            continue
        tail = key_parts[start + len(token_parts):]
        if tail and any(part in _COMPARISON_METADATA_SUFFIX_TOKENS for part in tail):
            continue
        return True
    return False


def _comparison_evidence_key_matches(key: str, token: str) -> bool:
    normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    normalized_token = re.sub(r"[^a-z0-9]+", "_", str(token).lower()).strip("_")
    key_parts = [part for part in normalized_key.split("_") if part]
    token_parts = [part for part in normalized_token.split("_") if part]
    if not key_parts or not token_parts or len(token_parts) > len(key_parts):
        return False
    for start in range(0, len(key_parts) - len(token_parts) + 1):
        if key_parts[start:start + len(token_parts)] != token_parts:
            continue
        if _claim_prefix_has_negation(key_parts[:start], _COMPARISON_NEGATION_PREFIX_TOKENS):
            continue
        tail = key_parts[start + len(token_parts):]
        if tail and tail[0] in _COMPARISON_METADATA_SUFFIX_TOKENS:
            continue
        return True
    return False


def _claim_prefix_has_negation(prefix_parts: list[str], negation_prefixes: set[str]) -> bool:
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


def _truth_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "pass", "passed", "met"):
            return True
        if text in ("false", "no", "fail", "failed", "not met", "not_met"):
            return False
    return None


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


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


_BASELINE_SUPERIORITY_RE = re.compile(
    r"\b(outperform(?:s|ed)?|beat(?:s|ing)?|better\s+than|superior\s+to)\b.{0,80}\bbaseline\b"
    r"|\bimprov(?:es|ed|ement)?\b.{0,24}\b(?:over|on|upon|the)\b.{0,48}\bbaseline\b"
    r"|\b(?:gain|reduction|increase|decrease|effect|difference)\b.{0,24}\b(?:over|vs\.?|versus|against)\b.{0,48}\bbaseline\b",
    re.IGNORECASE,
)
_BASELINE_NAME_BEFORE_RE = re.compile(
    r"\b(?:the|a|an|vs\.?|versus|against|than|over|to|from)\s+"
    r"(?P<name>[A-Za-z][A-Za-z0-9.+/_-]*(?:\s+[A-Za-z][A-Za-z0-9.+/_-]*){0,3})\s+baseline\b",
    re.IGNORECASE,
)
_BASELINE_NAME_LEADING_STOPWORDS = {
    "a",
    "an",
    "the",
    "our",
    "their",
    "this",
    "that",
}
_GENERIC_BASELINE_NAME_WORDS = {
    "average",
    "baseline",
    "best",
    "chosen",
    "competitive",
    "current",
    "default",
    "external",
    "main",
    "model",
    "primary",
    "prior",
    "proposed",
    "published",
    "reported",
    "same",
    "simple",
    "single",
    "strong",
}
_BASELINE_NAME_REJECT_WORDS = {
    "beat",
    "beats",
    "beating",
    "better",
    "compared",
    "difference",
    "effect",
    "gain",
    "improve",
    "improved",
    "improvement",
    "improves",
    "outperform",
    "outperformed",
    "outperforms",
    "reduction",
    "superior",
    "than",
    "versus",
}
_GENERIC_BASELINE_NAME_IDENTIFIERS = {
    "baseline",
    "best",
    "best_baseline",
    "baseline_model",
    "baseline_method",
    "main_baseline",
    "our_baseline",
    "proposed_baseline",
    "simple_baseline",
    "strong_baseline",
}
_NEGATED_BASELINE_SUPERIORITY_RE = re.compile(
    r"\b(?:no|not|never|failed\s+to|fails\s+to|did\s+not|does\s+not|without)\b.{0,32}"
    r"\b(?:outperform|beat|better|superior|improv)",
    re.IGNORECASE,
)
_SOTA_SUPERIORITY_RE = re.compile(
    r"\b(?:state[- ]of[- ]the[- ]art|sota)\b.{0,96}"
    r"\b(?:performance|result|score|accuracy|mae|rmse|mse|auc|auroc|f1|precision|recall|r2|outperform|beat|better|superior|improv)"
    r"|\b(?:outperform(?:s|ed)?|beat(?:s|ing)?|better\s+than|superior\s+to)\b.{0,80}"
    r"\b(?:prior\s+work|previous\s+work|published\s+(?:model|method|result)|state[- ]of[- ]the[- ]art|sota)\b"
    r"|\b(?:best[- ]performing|best\s+performance)\b.{0,80}"
    r"\b(?:prior\s+work|previous\s+work|published|leaderboard|state[- ]of[- ]the[- ]art|sota)\b",
    re.IGNORECASE,
)
_SOTA_NAME_BEFORE_RE = re.compile(
    r"\b(?:outperform(?:s|ed)?|beat(?:s|ing)?|better\s+than|superior\s+to|"
    r"vs\.?|versus|against|than|over|from)\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z][A-Za-z0-9.+/_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.+/_-]*){0,5})\s+"
    r"(?:prior\s+work|previous\s+work|published\s+(?:model|method|result)|leaderboard)\b",
    re.IGNORECASE,
)
_SOTA_NAME_LEADING_STOPWORDS = {
    "a",
    "an",
    "the",
    "our",
    "their",
    "this",
    "that",
}
_GENERIC_SOTA_NAME_WORDS = {
    "art",
    "best",
    "current",
    "external",
    "leaderboard",
    "literature",
    "method",
    "model",
    "of",
    "performance",
    "previous",
    "prior",
    "published",
    "reported",
    "result",
    "same",
    "sota",
    "state",
    "work",
}
_SOTA_NAME_REJECT_WORDS = {
    "achieve",
    "achieved",
    "achieves",
    "beat",
    "beats",
    "beating",
    "best",
    "better",
    "compared",
    "difference",
    "effect",
    "gain",
    "improve",
    "improved",
    "improvement",
    "improves",
    "outperform",
    "outperformed",
    "outperforms",
    "reduction",
    "superior",
    "than",
    "versus",
}
_GENERIC_SOTA_NAME_IDENTIFIERS = {
    "best_prior_work",
    "current_sota",
    "leaderboard",
    "literature",
    "previous_work",
    "prior_work",
    "published_model",
    "published_result",
    "sota",
    "state_of_the_art",
}
_NEGATED_SOTA_SUPERIORITY_RE = re.compile(
    r"\b(?:no|not|never|failed\s+to|fails\s+to|did\s+not|does\s+not|without)\b.{0,40}"
    r"\b(?:outperform|beat|better|superior|state[- ]of[- ]the[- ]art|sota|best[- ]performing)",
    re.IGNORECASE,
)
_TARGET_ACHIEVEMENT_RE = re.compile(
    r"\b(?:target|goal|success\s+criteria)\b.{0,48}\b(?:achieved|met|satisfied|reached)\b"
    r"|\b(?:achieved|met|satisfied|reached)\b.{0,48}\b(?:target|goal|success\s+criteria)\b",
    re.IGNORECASE,
)
_NEGATED_TARGET_ACHIEVEMENT_RE = re.compile(
    r"\b(?:no|not|never|failed\s+to|fails\s+to|did\s+not|does\s+not|without)\b.{0,40}"
    r"\b(?:achieve|meet|met|satisfy|satisfied|reach|reached)\b.{0,48}"
    r"\b(?:target|goal|success\s+criteria)\b",
    re.IGNORECASE,
)
_NO_LEAKAGE_RE = re.compile(
    r"\bno\s+(?:(?:data|target|temporal|preprocessing|group|duplicate)\s+)?leakage\b"
    r"|\bno\s+(?:train\s*/\s*test|train-test|duplicate|group)\s+overlap\b"
    r"|\b(?:(?:data|target|temporal|preprocessing|group|duplicate)\s+)?leakage\s+(?:was\s+|is\s+)?not\s+detected\b"
    r"|\b(?:(?:data|target|temporal|preprocessing|group|duplicate)\s+)?leakage\s+(?:was\s+|is\s+)?not\s+found\b"
    r"|\bleakage\s+audit\s+(?:passed|was\s+clean|is\s+clean)\b",
    re.IGNORECASE,
)
_LEAKAGE_RESOLUTION_CLAIM_RE = re.compile(
    r"\b(?:(?:data|target|temporal|preprocessing|group|duplicate)\s+)?leakage\s+(?:issue\s+)?"
    r"(?:was\s+|is\s+)?(?:resolved|mitigated|fixed)\b"
    r"|\b(?:resolved|mitigated|fixed)\s+(?:the\s+)?"
    r"(?:(?:data|target|temporal|preprocessing|group|duplicate)\s+)?leakage\b"
    r"|\bno\s+(?:data\s+)?leakage\s+after\s+(?:mitigation|fix|fixing|repair|remediation)\b",
    re.IGNORECASE,
)
_POSITIVE_LEAKAGE_CLAIM_RE = re.compile(
    r"\b(?:(?:data|target|temporal|preprocessing|group|duplicate)\s+)?leakage\s+"
    r"(?:was\s+|is\s+)?(?:detected|found|present|identified|observed)\b"
    r"|\bdata\s+leak\s+(?:was\s+|is\s+)?"
    r"(?:detected|found|present|identified|observed)\b"
    r"|\b(?:detected|found|identified|observed)\s+(?:data\s+)?(?:leakage|leak)\b"
    r"|\b(?:train\s*/\s*test|train-test|duplicate|group)\s+overlap\s+"
    r"(?:was\s+|is\s+)?(?:detected|found|present|identified|observed)\b"
    r"|\b(?:detected|found|identified|observed)\s+"
    r"(?:train\s*/\s*test|train-test|duplicate|group)\s+overlap\b"
    r"|\bleakage\s+audit\s+"
    r"(?:failed|fails|(?:did|does)\s+not\s+pass|found\s+issues|detected\s+issues)\b",
    re.IGNORECASE,
)
_CLEAN_LEAKAGE_VALUES = (
    "false",
    "no",
    "none",
    "0",
    "absent",
    "clean",
    "clear",
    "pass",
    "passed",
    "not_detected",
    "not_found",
    "none_detected",
    "none_found",
    "no_leakage",
    "no_leakage_detected",
    "no_overlap",
    "no_overlap_detected",
)
_PROBLEM_LEAKAGE_VALUES = (
    "true",
    "yes",
    "1",
    "present",
    "detected",
    "found",
    "leakage_detected",
    "leakage_found",
    "overlap_detected",
)
_POSITIVE_LEAKAGE_RESOLUTION_VALUES = (
    "true",
    "yes",
    "1",
    "pass",
    "passed",
    "clean",
    "resolved",
    "mitigated",
    "fixed",
    "no_leakage",
)
_NEGATIVE_LEAKAGE_RESOLUTION_VALUES = (
    "false",
    "no",
    "0",
    "fail",
    "failed",
    "unresolved",
    "not_resolved",
    "not_fixed",
    "not_mitigated",
)
_POSITIVE_IMPROVEMENT_EVIDENCE_TOKENS = (
    "improvement",
    "relative_gain",
    "relative_reduction",
    "gain",
    "reduction",
)
_COMPARISON_NEGATION_PREFIX_TOKENS = {"failed", "fails", "no", "non", "not", "without"}
_COMPARISON_METADATA_SUFFIX_TOKENS = {
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


_IMPROVEMENT_CLAIM_TOKENS = (
    "improv",
    "better",
    "outperform",
    "gain",
    "reduction",
    "reduced",
    "lower",
    "higher",
)

_METRIC_TOKEN_RE = r"accuracy|acc|mae|rmse|mse|loss|auc|auroc|f1|precision|recall|error|score|r2|r\^2"
_FROM_TO_RE = re.compile(
    rf"from\s+(?:(?P<metric1>{_METRIC_TOKEN_RE})\s*(?:=|of|is)?\s*)?"
    rf"(?P<old>{_NUMBER_PATTERN})\s+"
    rf"(?:to|→)\s+(?:(?P<metric2>{_METRIC_TOKEN_RE})\s*(?:=|of|is)?\s*)?"
    rf"(?P<new>{_NUMBER_PATTERN})",
    re.IGNORECASE,
)
_COMPARISON_CONNECTOR_RE = r"(?:vs\.?|versus|compared\s+(?:with|to)|against)"
_MODEL_VS_BASELINE_RE = re.compile(
    rf"(?:(?P<metric1>{_METRIC_TOKEN_RE})\s*(?:=|of|is)?\s*)?"
    rf"(?P<model>{_NUMBER_PATTERN})\s+{_COMPARISON_CONNECTOR_RE}\s+"
    rf"(?:the\s+)?baseline\b\s*:?\s*"
    rf"(?:(?P<metric2>{_METRIC_TOKEN_RE})\s*(?:=|of|is)?\s*)?"
    rf"(?P<baseline>{_NUMBER_PATTERN})",
    re.IGNORECASE,
)
_BASELINE_VS_MODEL_RE = re.compile(
    rf"\bbaseline\b\s*:?\s*"
    rf"(?:(?P<metric1>{_METRIC_TOKEN_RE})\s*(?:=|of|is)?\s*)?"
    rf"(?P<baseline>{_NUMBER_PATTERN})\s+{_COMPARISON_CONNECTOR_RE}\s+"
    rf"(?:(?:the\s+)?(?:(?:proposed|final|refined|our)\s+)?(?:model|method)\s+|ours\s+)?"
    rf"(?:(?P<metric2>{_METRIC_TOKEN_RE})\s*(?:=|of|is)?\s*)?"
    rf"(?P<model>{_NUMBER_PATTERN})",
    re.IGNORECASE,
)


def _from_to_metric_hint(sentence: str, match: re.Match[str]) -> str | None:
    metric = match.group("metric2") or match.group("metric1")
    if metric:
        return _canonical_metric_hint(metric.lower())
    return _metric_hint_for_number(sentence, match.start("old"))


def _comparison_metric_hint(sentence: str, match: re.Match[str]) -> str | None:
    metric = match.group("metric2") or match.group("metric1")
    if metric:
        return _canonical_metric_hint(metric.lower())
    return _metric_hint_for_number(sentence, match.start("model"))


def _metric_direction(metric: str | None) -> str | None:
    if metric in {"mae", "rmse", "mse", "loss", "error"}:
        return "lower"
    if metric in {"accuracy", "auc", "f1", "precision", "recall", "r2", "score"}:
        return "higher"
    return None


def _collect_result_payloads_by_path(project_dir: Path) -> dict[str, Any]:
    payloads_by_path: dict[str, Any] = {}
    for path in research_result_json_files(project_dir):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        payloads_by_path[path.relative_to(project_dir).as_posix()] = data
    return payloads_by_path


def _result_json_paths_in_sentence(sentence: str) -> list[str]:
    return safe_research_result_json_paths_in_text(sentence)


def _values_for_cited_paths(cited_paths: list[str], values_by_path: dict[str, list[ResultNumber]]) -> list[ResultNumber]:
    values: list[ResultNumber] = []
    for cited_path in cited_paths:
        values.extend(values_by_path.get(cited_path, []))
    return values


def _walk_numbers(value: Any, key_path: str = "") -> list[ResultNumber]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [ResultNumber(float(value), key_path)]
    if isinstance(value, dict):
        out: list[ResultNumber] = []
        for key, item in value.items():
            child_path = f"{key_path}.{key}" if key_path else str(key)
            out.extend(_walk_numbers(item, child_path))
        return out
    if isinstance(value, list):
        out: list[ResultNumber] = []
        for index, item in enumerate(value):
            child_path = f"{key_path}[{index}]" if key_path else f"[{index}]"
            out.extend(_walk_numbers(item, child_path))
        return out
    return []


def _parse_number(raw: str) -> float | None:
    try:
        if raw.endswith("%"):
            return float(raw[:-1].replace(",", ""))
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _looks_like_noise(value: float, raw: str) -> bool:
    if raw.endswith("%"):
        return False
    if value.is_integer() and 1900 <= value <= 2100:
        return True
    return False


_SPECIFIC_METRIC_HINTS = (
    "accuracy", "acc", "mae", "rmse", "mse", "loss", "auc", "auroc", "f1",
    "precision", "recall", "score", "r2", "r^2",
)


def _claim_hint_for_number(sentence: str, number_start: int, number_end: int, raw: str) -> str | None:
    protocol_hint = _evaluation_protocol_hint_for_number(sentence, number_start, number_end)
    if protocol_hint:
        return protocol_hint
    comparison_hint = _comparison_hint_for_number(sentence, number_start, number_end, raw)
    if comparison_hint:
        return comparison_hint
    return _metric_hint_for_number(sentence, number_start)


def _evaluation_protocol_hint_for_number(sentence: str, number_start: int, number_end: int) -> str | None:
    window = sentence[max(0, number_start - 24):number_end + 32].lower()
    if re.search(r"\b\d+\s*[- ]?\s*(?:fold|folds|split|splits|repeat|repeats)\b", window):
        return "evaluation_protocol"
    return None


def _comparison_hint_for_number(sentence: str, number_start: int, number_end: int, raw: str) -> str | None:
    if not raw.endswith("%"):
        return None
    lower = sentence.lower()
    before = lower[max(0, number_start - 24):number_start]
    after = lower[number_end:number_end + 32]
    window = before + raw.lower() + after
    if any(token in after for token in _COMPARISON_AFTER_TOKENS):
        return "improvement"
    if any(token in before for token in ("relative", "delta", "improvement", "reduction", "gain")):
        return "improvement"
    if "over baseline" in window or "vs baseline" in window:
        return "improvement"
    return None


_COMPARISON_AFTER_TOKENS = (
    " improvement",
    " gain",
    " reduction",
    " decrease",
    " increase",
    " better",
    " lower",
    " higher",
    " over baseline",
    " vs baseline",
)


def _metric_hint_for_number(sentence: str, number_start: int) -> str | None:
    before = sentence[max(0, number_start - 48):number_start].lower()
    matches: list[tuple[int, str]] = []
    for hint in _SPECIFIC_METRIC_HINTS:
        idx = before.rfind(hint)
        if idx >= 0:
            matches.append((idx, hint))
    if not matches:
        return None
    _, hint = max(matches, key=lambda item: item[0])
    return _canonical_metric_hint(hint)


def _canonical_metric_hint(hint: str) -> str:
    return _shared_canonical_metric_name(hint)


def _matches_result_value(
    value: float,
    result_values: list[ResultNumber],
    tolerance: float,
    metric_hint: str | None = None,
    *,
    allow_support_stat: bool = False,
    support_stat_only: bool = False,
    support_stat_kind: str | None = None,
) -> bool:
    candidates = _numeric_claim_candidates(value)
    return any(
        (
            _evidence_matches_metric(
                rv,
                metric_hint,
                allow_support_stat=allow_support_stat,
                support_stat_only=support_stat_only,
                support_stat_kind=support_stat_kind,
            )
            or _generic_support_stat_has_sibling_metric(
                rv,
                result_values,
                metric_hint,
                support_stat_only=support_stat_only,
                support_stat_kind=support_stat_kind,
            )
        )
        and abs(candidate - rv.value) <= max(tolerance, abs(rv.value) * 1e-6)
        for candidate in candidates
        for rv in result_values
    )


def _generic_support_stat_has_sibling_metric(
    evidence: ResultNumber,
    result_values: list[ResultNumber],
    metric_hint: str | None,
    *,
    support_stat_only: bool,
    support_stat_kind: str | None,
) -> bool:
    if not support_stat_only or metric_hint is None:
        return False
    key = evidence.key_path.lower()
    if not _is_metric_support_stat_key(key):
        return False
    if support_stat_kind and not _support_stat_key_matches_kind(key, support_stat_kind):
        return False
    parent_key = _result_number_parent_key(key)
    if parent_key is None:
        return False
    return any(
        _result_number_parent_key(other.key_path.lower()) == parent_key
        and not _is_metric_support_stat_key(other.key_path.lower())
        and _key_mentions_metric(other.key_path.lower(), metric_hint)
        for other in result_values
    )


def _result_number_parent_key(key: str) -> str | None:
    if "." not in key:
        return None
    return key.rsplit(".", 1)[0]


def _numeric_claim_candidates(value: float) -> list[float]:
    candidates = [value]
    if 0 <= value <= 100:
        candidates.append(value / 100.0)
    return candidates


def _evidence_matches_metric(
    evidence: ResultNumber,
    metric_hint: str | None,
    *,
    allow_support_stat: bool = False,
    support_stat_only: bool = False,
    support_stat_kind: str | None = None,
) -> bool:
    key = evidence.key_path.lower()
    if metric_hint == "evaluation_protocol":
        normalized = _normalize_evidence_key(key)
        return _is_protocol_count_key(normalized) or _is_protocol_repeated_results_key(normalized)
    if support_stat_only and not _is_metric_support_stat_key(key):
        return False
    if support_stat_only and support_stat_kind and not _support_stat_key_matches_kind(key, support_stat_kind):
        return False
    if _is_metric_support_stat_key(key):
        if not allow_support_stat:
            return False
    elif not _is_substantive_result_number_key(key):
        return False
    if metric_hint is None:
        return True
    if metric_hint == "score":
        return _key_mentions_metric(key, metric_hint) and _is_substantive_result_number_key(key)
    if metric_hint == "improvement":
        return (
            any(_comparison_evidence_key_matches(key, token) for token in _IMPROVEMENT_EVIDENCE_TOKENS)
            and not _is_statistical_or_uncertainty_key(key)
        )
    return _key_mentions_metric(key, metric_hint)


def _is_substantive_result_number_key(key: str) -> bool:
    normalized = _normalize_evidence_key(key)
    if _is_metric_support_stat_key(normalized):
        return False
    if _claim_key_has_metadata_suffix(normalized):
        return False
    metadata_tokens = (
        "batch_size",
        "duration",
        "duration_seconds",
        "epoch",
        "epochs",
        "fold",
        "fold_count",
        "iteration",
        "iterations",
        "n",
        "n_samples",
        "n_trials",
        "num_samples",
        "num_trials",
        "random_seed",
        "replicate",
        "replicate_count",
        "replicates",
        "repeat",
        "repeat_count",
        "repeats",
        "run_id",
        "sample_count",
        "sample_size",
        "seed",
        "split",
        "split_count",
        "step",
        "test_rows",
        "timestamp",
        "train_rows",
        "trial",
        "trial_count",
        "trial_id",
    )
    return not any(
        normalized == token
        or normalized.endswith(f"_{token}")
        or f"_{token}_" in normalized
        for token in metadata_tokens
    )


def _support_stat_context_for_number(sentence: str, number_start: int, number_end: int) -> bool:
    return _support_stat_kind_for_number(sentence, number_start, number_end) is not None


def _support_stat_kind_for_number(sentence: str, number_start: int, number_end: int) -> str | None:
    before = sentence[max(0, number_start - 64):number_start].lower()
    after = sentence[number_end:number_end + 32].lower()
    if re.search(r"(?:\u00b1|\+/-|\+\s*/\s*-)\s*$", before):
        return "dispersion"
    if re.search(r"\bp\s*[=<>]\s*$|\bp[- ]?value\s*[=<>:]?\s*$", before):
        return "p_value"
    contexts = list(_SUPPORT_STAT_CONTEXT_RE.finditer(before))
    if contexts:
        context = contexts[-1]
        if _support_stat_context_reaches_number(before[context.end():]):
            return _support_stat_kind_from_text(context.group(0))
    context = _SUPPORT_STAT_AFTER_RE.match(after)
    if context:
        return _support_stat_kind_from_text(context.group(0))
    return None


def _support_stat_context_reaches_number(text_between_context_and_number: str) -> bool:
    between = text_between_context_and_number.strip()
    if not between:
        return True
    if "]" in between or ")" in between:
        return False
    between_without_linking_words = re.sub(
        r"\b(?:is|was|were|are|of|at|about|approximately|approx)\b",
        lambda match: "",
        between.lower(),
    )
    between_without_linking_words = re.sub(
        r"\b(?:lower|upper|low|high|bound|bounds|endpoint|endpoints)\b",
        "",
        between_without_linking_words,
    )
    if re.search(r"[a-z]", between_without_linking_words):
        return False
    if re.search(_NUMBER_RE, between_without_linking_words):
        return "[" in between and "]" not in between
    return True


def _support_stat_kind_from_text(text: str) -> str | None:
    normalized = text.lower()
    if re.search(r"\b(?:p[- ]?value|q[- ]?value)\b", normalized):
        return "p_value"
    if re.search(r"\b(?:confidence[- ]interval|credible[- ]interval|ci|ci95)\b", normalized):
        return "interval"
    if re.search(r"\b(?:std|stdev|standard[- ]deviation|standard[- ]error|stderr|sem|variance)\b", normalized):
        return "dispersion"
    return None


def _support_stat_key_matches_kind(key: str, kind: str) -> bool:
    normalized = _normalize_evidence_key(key)
    if kind == "p_value":
        return any(_claim_key_matches_without_metadata_suffix(normalized, token) for token in ("p_value", "pvalue", "q_value", "qvalue"))
    if kind == "interval":
        return any(
            _claim_key_matches_without_metadata_suffix(normalized, token)
            for token in ("ci", "ci95", "confidence", "confidence_interval", "credible_interval")
        )
    if kind == "dispersion":
        return any(
            _claim_key_matches_without_metadata_suffix(normalized, token)
            for token in (
                "std",
                "stdev",
                "standard_deviation",
                "standard_error",
                "stderr",
                "sem",
                "se",
                "variance",
            )
        )
    return True


def _confidence_level_context_for_number(sentence: str, number_start: int, number_end: int, raw: str) -> bool:
    if not raw.endswith("%"):
        return False
    value = _parse_number(raw)
    if value is None or value <= 50 or value >= 100:
        return False
    before = sentence[max(0, number_start - 16):number_start].lower()
    after = sentence[number_end:number_end + 32].lower()
    if re.search(r"\b(?:ci|confidence[- ]?level)\s*$", before):
        return True
    return _CONFIDENCE_LEVEL_AFTER_RE.match(after) is not None


_SUPPORT_STAT_CONTEXT_RE = re.compile(
    r"\b(?:std|stdev|standard[- ]deviation|standard[- ]error|stderr|sem|"
    r"variance|confidence[- ]interval|credible[- ]interval|ci|ci95|"
    r"p[- ]?value|q[- ]?value)\b",
    re.IGNORECASE,
)
_SUPPORT_STAT_AFTER_RE = re.compile(
    r"\s*(?:std|stdev|standard[- ]deviation|standard[- ]error|stderr|sem|"
    r"variance|confidence[- ]interval|credible[- ]interval|ci|ci95|"
    r"p[- ]?value|q[- ]?value)\b",
    re.IGNORECASE,
)
_CONFIDENCE_LEVEL_AFTER_RE = re.compile(
    r"\s*(?:confidence[- ]interval|credible[- ]interval|ci)\b",
    re.IGNORECASE,
)


_IMPROVEMENT_EVIDENCE_TOKENS = (
    "improvement",
    "delta_vs_baseline",
    "relative_gain",
    "relative_reduction",
    "reduction",
    "gain",
    "beats_baseline",
)
