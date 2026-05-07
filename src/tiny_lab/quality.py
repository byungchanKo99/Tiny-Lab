"""Reusable research quality audit helpers."""
from __future__ import annotations

import json
from functools import lru_cache
import re
from pathlib import Path
from typing import Any, Iterable

from .evidence import (
    ABLATION_EVIDENCE_TOKENS,
    BASELINE_COMPARISON_EVIDENCE_TOKENS,
    CAUSAL_EVIDENCE_TOKENS,
    EFFICIENCY_EVIDENCE_TOKENS,
    ERROR_ANALYSIS_EVIDENCE_TOKENS,
    EXTERNAL_GENERALIZATION_EVIDENCE_TOKENS,
    EVALUATION_PROTOCOL_EVIDENCE_TOKENS,
    FAIRNESS_EVIDENCE_TOKENS,
    GENERALIZATION_EVIDENCE_TOKENS,
    GOAL_ACHIEVEMENT_EVIDENCE_TOKENS,
    LEAKAGE_AUDIT_EVIDENCE_TOKENS,
    REPRODUCIBILITY_CODE_TOKENS,
    REPRODUCIBILITY_DATA_TOKENS,
    REPRODUCIBILITY_ENV_TOKENS,
    REPRODUCIBILITY_SEED_TOKENS,
    ROBUSTNESS_EVIDENCE_TOKENS,
    SOTA_COMPARISON_EVIDENCE_TOKENS,
    STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS,
    STATISTICS_EVIDENCE_TOKENS,
    baseline_comparison_entries as _shared_baseline_comparison_entries,
    baseline_comparison_items as _shared_baseline_comparison_items,
    baseline_names_match as _shared_baseline_names_match,
    evaluation_protocol_evidence_values as _evaluation_protocol_evidence_values,
    evaluation_protocol_repeated_metric_counts as _evaluation_protocol_repeated_metric_counts,
    evaluation_protocol_repetition_counts as _evaluation_protocol_repetition_counts,
    has_causal_evidence as _shared_has_causal_evidence,
    has_efficiency_benchmark_context as _shared_has_efficiency_benchmark_context,
    has_efficiency_evidence as _shared_has_efficiency_evidence,
    has_evidence_token_value as _shared_has_evidence_token_value,
    has_external_generalization_evidence as _shared_has_external_generalization_evidence,
    has_fairness_evidence as _shared_has_fairness_evidence,
    has_explicit_generalization_evidence as _shared_has_explicit_generalization_evidence,
    has_explicit_robustness_evidence as _shared_has_explicit_robustness_evidence,
    has_generalization_evidence as _shared_has_generalization_evidence,
    has_robustness_evidence as _shared_has_robustness_evidence,
    has_statistical_significance_evidence as _shared_has_statistical_significance_evidence,
    has_substantive_leakage_audit_evidence as _shared_has_substantive_leakage_audit_evidence,
    has_substantive_ablation_evidence as _shared_has_substantive_ablation_evidence,
    has_substantive_error_analysis_evidence as _shared_has_substantive_error_analysis_evidence,
    has_uncertainty_evidence as _shared_has_uncertainty_evidence,
    is_ablation_evidence_key as _is_ablation_evidence_key,
    is_baseline_comparison_evidence_key as _shared_is_baseline_comparison_evidence_key,
    is_causal_evidence_key as _shared_is_causal_evidence_key,
    is_efficiency_evidence_key as _shared_is_efficiency_evidence_key,
    is_efficiency_profile_evidence_key as _shared_is_efficiency_profile_evidence_key,
    is_error_analysis_evidence_key as _is_error_analysis_evidence_key,
    is_evaluation_protocol_evidence_key as _shared_is_evaluation_protocol_evidence_key,
    is_external_generalization_evidence_key as _shared_is_external_generalization_evidence_key,
    is_fairness_evidence_key as _shared_is_fairness_evidence_key,
    is_generalization_evidence_key as _shared_is_generalization_evidence_key,
    is_evaluation_protocol_count_key as _is_protocol_count_key,
    is_goal_achievement_evidence_key as _shared_is_goal_achievement_evidence_key,
    is_leakage_audit_evidence_key as _shared_is_leakage_audit_evidence_key,
    is_leakage_indicator_evidence_key as _shared_is_leakage_indicator_key,
    is_leakage_resolution_evidence_key as _shared_is_leakage_resolution_key,
    is_metric_evidence_key as _shared_is_metric_evidence_key,
    is_metric_support_numeric_key as _shared_is_metric_support_numeric_key,
    is_reproducibility_code_path_key as _shared_is_reproducibility_code_path_key,
    is_reproducibility_evidence_key as _shared_is_reproducibility_evidence_key,
    is_robustness_evidence_key as _shared_is_robustness_evidence_key,
    is_sota_comparison_evidence_key as _shared_is_sota_comparison_evidence_key,
    is_statistics_evidence_key as _shared_is_statistics_evidence_key,
    metric_aliases as _shared_metric_aliases,
    plan_requires_ablation_evidence,
    plan_requires_causal_evidence,
    plan_requires_efficiency_evidence,
    plan_requires_efficiency_benchmark_context,
    plan_requires_error_analysis_evidence,
    plan_requires_external_generalization_evidence,
    plan_requires_evaluation_protocol_evidence,
    plan_requires_fairness_evidence,
    plan_requires_generalization_evidence,
    plan_requires_robustness_evidence,
    plan_metric_target as _shared_plan_metric_target,
    reproducibility_bundle_missing_groups as _shared_reproducibility_bundle_missing_groups,
    sota_comparison_entries as _shared_sota_comparison_entries,
)
from .paths import (
    is_safe_research_result_artifact_path,
    research_result_json_files,
    research_result_json_paths_in_text,
    research_result_png_files,
    research_result_png_paths_in_text,
    resolve_research_results_path,
)
from .provenance import audit_code_provenance
from .result_schema import (
    _allows_zero_absent_split_count,
    schema_expected_fields,
    schema_fields_to_validate,
    validate_finite_numeric_values,
    validate_phase_identity,
    validate_result_object,
    validate_schema_types,
    validate_substantive_result_values,
)
from .review import evaluation_feedback_artifact_paths, evaluation_feedback_unsafe_artifact_paths
from .visualizations import is_valid_png_artifact, phase_visualization_issues


FINAL_PAPER_MIN_CHARS = 500
FINAL_PAPER_REQUIRED_SECTION_GROUPS = {
    "abstract": ("abstract",),
    "method": ("method", "methodology", "search strategy"),
    "results_or_analysis": ("result", "finding", "analysis", "taxonomy"),
    "limitations": ("limitation", "threats to validity"),
}
FINAL_PAPER_RELATED_WORK_TERMS = ("related work", "references", "literature", "prior work")
FINAL_PAPER_NOVELTY_CLAIM_TERMS = (
    "state-of-the-art",
    "state of the art",
    "sota",
    "novel",
    "first to",
    "first method",
    "first approach",
    "beat prior work",
    "beats prior work",
    "beating prior work",
    "better than prior work",
    "outperforms prior work",
    "superior to prior work",
    "beat previous work",
    "beats previous work",
    "beating previous work",
    "better than previous work",
    "outperforms previous work",
    "superior to previous work",
    "outperforms published model",
    "outperforms published method",
    "outperforms published result",
    "beats published model",
    "beats published method",
    "beats published result",
    "better than published model",
    "better than published method",
    "better than published result",
)
FINAL_PAPER_NOVELTY_CLAIM_RES = tuple(
    re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", re.IGNORECASE)
    for term in FINAL_PAPER_NOVELTY_CLAIM_TERMS
)
FINAL_PAPER_SOTA_SUPERIORITY_RE = re.compile(
    r"\b(?:state[- ]of[- ]the[- ]art|sota)\b.{0,96}"
    r"\b(?:performance|result|score|accuracy|mae|rmse|mse|auc|auroc|f1|precision|recall|r2|outperform|beat|better|superior|improv)"
    r"|\b(?:outperform(?:s|ed|ing)?|beat(?:s|ing)?|better\s+than|superior\s+to)\b.{0,80}"
    r"\b(?:prior\s+work|previous\s+work|published\s+(?:models?|methods?|results?)|state[- ]of[- ]the[- ]art|sota)\b"
    r"|\b(?:best[- ]performing|best\s+performance)\b.{0,80}"
    r"\b(?:prior\s+work|previous\s+work|published|leaderboard|state[- ]of[- ]the[- ]art|sota)\b",
    re.IGNORECASE,
)
FINAL_PAPER_NEGATED_NOVELTY_SOTA_RES = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:no|without)\b[^.!?;]{0,96}"
        r"\b(?:novelty|novel|sota|state[- ]of[- ]the[- ]art)\b[^.!?;]{0,64}"
        r"\bclaim(?:s|ed|ing)?\b(?:\s+(?:are|is|were|was|made|presented|asserted))*",
        r"\b(?:no|without)\b[^.!?;]{0,64}\bclaim(?:s|ed|ing)?\b[^.!?;]{0,96}"
        r"\b(?:novelty|novel|sota|state[- ]of[- ]the[- ]art)\b",
        r"\b(?:do|does|did|is|are|was|were)\s+not\s+"
        r"(?:make|claim|assert|present)\b[^.!?;]{0,96}"
        r"\b(?:novelty|novel|sota|state[- ]of[- ]the[- ]art)\b(?:\s+claim(?:s|ed|ing)?)?",
        r"\bnot\s+(?:a\s+|an\s+)?novel\b",
        r"\bnot\s+(?:sota|state[- ]of[- ]the[- ]art)\b",
    )
)
_CLEAN_LEAKAGE_TEXT_VALUES = {
    "0",
    "clean",
    "false",
    "no",
    "no leakage",
    "none",
    "not detected",
    "not found",
    "not_found",
}


def render_final_paper_contract() -> str:
    """Return the shared final-paper contract for prompts and runner docs."""
    section_rows = "\n".join(
        f"- `{name}`: " + ", ".join(f"`{term}`" for term in alternatives)
        for name, alternatives in FINAL_PAPER_REQUIRED_SECTION_GROUPS.items()
    )
    related_terms = ", ".join(f"`{term}`" for term in FINAL_PAPER_RELATED_WORK_TERMS)
    novelty_terms = ", ".join(f"`{term}`" for term in FINAL_PAPER_NOVELTY_CLAIM_TERMS)
    return f"""## Final Paper Contract (SSOT)

This section is generated from `tiny_lab.quality`; update that module instead of copying final-paper rules into prompts.

1. `research/final_paper.md` must be at least {FINAL_PAPER_MIN_CHARS} non-whitespace characters.
2. It must include Markdown section headings with these signals:
{section_rows}
3. If reference artifacts exist, the paper must include a Markdown heading for related work or references, using language such as {related_terms}, and cite every reference-bearing `research/iter_*/*.json` artifact using the concrete project-relative path.
4. Novelty or SOTA claims such as {novelty_terms} require reference artifacts with passing `*.ref_verification.json` sidecars.
5. The paper must cite every `research/iter_*/results/*.json` artifact at least once using the concrete project-relative path, and cited JSONs must be valid non-empty result artifacts.
6. The paper must cite every generated `research/iter_*/results/*.png` figure artifact at least once using the concrete project-relative path, and cited PNGs must be valid non-empty image artifacts.
7. Cited `research/iter_*/results/*` paths must be syntactically safe project-relative paths with no `.` or `..` path segments.
8. Metric, sample-size, repetition-count, split-ratio, statistical, baseline-superiority, and SOTA/prior-work superiority claims must cite the relevant result artifact in the same sentence so claim verification can trace them.
9. Sample-size claims such as `n=120`, `120 samples`, or `sample size of 120` must match `n_samples`, `sample_count`, `sample_size`, or row-count evidence in the cited result artifact.
10. Repetition-count claims such as `5 trials`, `3 random seeds`, or `2 runs` must match `n_trials`, `trial_count`, `repeat_count`, `run_count`, `seed_count`, or materialized repeated-measurement evidence in the cited result artifact.
11. Split-ratio claims such as `80/20 holdout` or `20% held-out test set` must match `split_protocol`, `train_test_split`, train/test fractions, or train/test row-count evidence in the cited result artifact.
12. If result artifacts include baseline comparison, SOTA/prior-work comparison, ablation/feature-importance, evaluation protocol, statistical uncertainty (std/CI/variance; support counts alone do not trigger this family), statistical significance (p-values or comparison confidence intervals), causal design, robustness/stability, generalization, external/OOD generalization, error analysis, fairness/bias audit, efficiency/resource evidence, leakage audit, target achievement, or reproducibility evidence, the paper must discuss that evidence family in a sentence that cites a result artifact containing the evidence.
"""


def audit_final_paper(project_dir: Path, iteration: int | None = None) -> list[str]:
    """Check that the final paper exists and has minimal scholarly structure."""
    path = project_dir / "research" / "final_paper.md"
    if not path.exists():
        return ["final_paper.md is missing"]
    try:
        text = path.read_text()
    except OSError as e:
        return [f"could not read final_paper.md: {e}"]
    if len(text.strip()) < FINAL_PAPER_MIN_CHARS:
        return ["final_paper.md is too short to be a complete paper"]
    lower = text.lower()
    headings = _markdown_headings(text)
    missing = [
        name for name, alternatives in FINAL_PAPER_REQUIRED_SECTION_GROUPS.items()
        if not any(_heading_has_term(heading, term) for heading in headings for term in alternatives)
    ]
    if missing:
        return [f"final_paper.md missing expected sections: {missing}"]
    has_reference_artifacts = _has_reference_artifacts(project_dir, iteration)
    if has_reference_artifacts and not _has_related_work_heading(headings):
        return ["final_paper.md must include a related work or references section when reference artifacts exist"]
    if _has_novelty_or_sota_claim(lower) and not has_reference_artifacts:
        return ["final_paper.md novelty or SOTA claims require reference artifacts"]
    if _has_novelty_or_sota_claim(lower):
        reference_issues = _reference_verification_issues(project_dir, iteration)
        if reference_issues:
            return [
                "final_paper.md novelty or SOTA claims require reference artifacts "
                "with passing verification sidecars: "
                + "; ".join(reference_issues[:3])
            ]
    unsafe_results = _unsafe_cited_result_artifacts(text)
    if unsafe_results:
        return [f"final_paper.md cites unsafe research result artifact paths: {unsafe_results}"]
    unsafe_figures = _unsafe_cited_visualization_artifacts(text)
    if unsafe_figures:
        return [f"final_paper.md cites unsafe research figure artifact paths: {unsafe_figures}"]
    nonexistent_results = _nonexistent_cited_result_artifacts(project_dir, text)
    if nonexistent_results:
        return [f"final_paper.md cites missing research result artifacts: {nonexistent_results}"]
    nonexistent_figures = _nonexistent_cited_visualization_artifacts(project_dir, text)
    if nonexistent_figures:
        return [f"final_paper.md cites missing research figure artifacts: {nonexistent_figures}"]
    out_of_scope_results = _out_of_scope_cited_result_artifacts(text, iteration)
    if out_of_scope_results:
        return [f"final_paper.md cites out-of-scope research result artifacts: {out_of_scope_results}"]
    out_of_scope_figures = _out_of_scope_cited_visualization_artifacts(text, iteration)
    if out_of_scope_figures:
        return [f"final_paper.md cites out-of-scope research figure artifacts: {out_of_scope_figures}"]
    invalid_results = _invalid_cited_result_artifacts(project_dir, text, iteration)
    if invalid_results:
        return [f"final_paper.md cites invalid research result artifacts: {invalid_results}"]
    non_substantive_results = _non_substantive_cited_result_artifacts(project_dir, text, iteration)
    if non_substantive_results:
        return [f"final_paper.md cites non-substantive research result artifacts: {non_substantive_results}"]
    invalid_figures = _invalid_cited_visualization_artifacts(project_dir, text)
    if invalid_figures:
        return [f"final_paper.md cites invalid research figure artifacts: {invalid_figures}"]
    uncited_references = _uncited_reference_artifacts(project_dir, text, iteration)
    if uncited_references:
        return [f"final_paper.md must cite every reference artifact; missing: {uncited_references}"]
    uncited_results = _uncited_result_artifacts(project_dir, text, iteration)
    if uncited_results:
        return [f"final_paper.md must cite every research result artifact; missing: {uncited_results}"]
    uncited_figures = _uncited_visualization_artifacts(project_dir, text, iteration)
    if uncited_figures:
        return [f"final_paper.md must cite every research figure artifact; missing: {uncited_figures}"]
    discussion_issues = _final_paper_evidence_discussion_issues(project_dir, lower, iteration)
    if discussion_issues:
        return discussion_issues
    return []


def _unsafe_cited_result_artifacts(text: str) -> list[str]:
    return [
        path
        for path in sorted(set(research_result_json_paths_in_text(text)))
        if not is_safe_research_result_artifact_path(path, ".json")
    ]


def _unsafe_cited_visualization_artifacts(text: str) -> list[str]:
    return [
        path
        for path in sorted(set(research_result_png_paths_in_text(text)))
        if not is_safe_research_result_artifact_path(path, ".png")
    ]


def _nonexistent_cited_result_artifacts(project_dir: Path, text: str) -> list[str]:
    return [
        path
        for path in sorted(set(research_result_json_paths_in_text(text)))
        if not (project_dir / path).is_file()
    ]


def _nonexistent_cited_visualization_artifacts(project_dir: Path, text: str) -> list[str]:
    return [
        path
        for path in sorted(set(research_result_png_paths_in_text(text)))
        if not (project_dir / path).is_file()
    ]


def _cited_result_json_paths(text: str, iteration: int | None = None) -> list[str]:
    paths = sorted(set(research_result_json_paths_in_text(text)))
    if iteration is None:
        return paths
    prefix = f"research/iter_{iteration}/results/"
    return [path for path in paths if path.startswith(prefix)]


def _out_of_scope_cited_result_artifacts(text: str, iteration: int | None = None) -> list[str]:
    if iteration is None:
        return []
    prefix = f"research/iter_{iteration}/results/"
    return [
        path
        for path in sorted(set(research_result_json_paths_in_text(text)))
        if not path.startswith(prefix)
    ]


def _out_of_scope_cited_visualization_artifacts(text: str, iteration: int | None = None) -> list[str]:
    if iteration is None:
        return []
    prefix = f"research/iter_{iteration}/results/"
    return [
        path
        for path in sorted(set(research_result_png_paths_in_text(text)))
        if not path.startswith(prefix)
    ]


def _invalid_cited_result_artifacts(project_dir: Path, text: str, iteration: int | None = None) -> list[str]:
    return [
        _result_artifact_validation_summary(path, project_dir / path)
        for path in _cited_result_json_paths(text, iteration)
        if (project_dir / path).is_file() and not _is_valid_result_artifact(project_dir / path)
    ]


def _non_substantive_cited_result_artifacts(project_dir: Path, text: str, iteration: int | None = None) -> list[str]:
    return [
        path
        for path in _cited_result_json_paths(text, iteration)
        if (project_dir / path).is_file()
        and _is_valid_json_artifact(project_dir / path)
        and not _is_substantive_json_result_artifact(project_dir / path)
    ]


def _invalid_cited_visualization_artifacts(project_dir: Path, text: str) -> list[str]:
    return [
        path
        for path in sorted(set(research_result_png_paths_in_text(text)))
        if (project_dir / path).is_file() and not is_valid_png_artifact(project_dir / path)
    ]


def _uncited_result_artifacts(project_dir: Path, text: str, iteration: int | None = None) -> list[str]:
    result_paths = [
        path.relative_to(project_dir).as_posix()
        for path in research_result_json_files(project_dir, iteration=iteration)
        if is_citable_result_artifact(path)
    ]
    if not result_paths:
        return []
    cited = set(research_result_json_paths_in_text(text))
    return [path for path in result_paths if path not in cited]


def _uncited_visualization_artifacts(project_dir: Path, text: str, iteration: int | None = None) -> list[str]:
    figure_paths = [
        path.relative_to(project_dir).as_posix()
        for path in research_result_png_files(project_dir, iteration=iteration)
    ]
    if not figure_paths:
        return []
    cited = set(research_result_png_paths_in_text(text))
    return [path for path in figure_paths if path not in cited]


def _uncited_reference_artifacts(project_dir: Path, text: str, iteration: int | None = None) -> list[str]:
    from .refs import discover_artifacts

    reference_paths = [
        path.relative_to(project_dir).as_posix()
        for path in discover_artifacts(project_dir, iteration=iteration)
    ]
    return [path for path in reference_paths if path not in text]


def _has_reference_artifacts(project_dir: Path, iteration: int | None = None) -> bool:
    from .refs import discover_artifacts

    return bool(discover_artifacts(project_dir, iteration=iteration))


def _reference_verification_issues(project_dir: Path, iteration: int | None = None) -> list[str]:
    from .refs import audit_reference_sidecars

    return audit_reference_sidecars(project_dir, iteration=iteration, require_identity_verified=True)


def _has_related_work_heading(headings: list[str]) -> bool:
    return any(
        _heading_has_term(heading, term)
        for heading in headings
        for term in FINAL_PAPER_RELATED_WORK_TERMS
    )


def _markdown_headings(text: str) -> list[str]:
    return [
        match.group(1).strip().lower()
        for match in re.finditer(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", text)
    ]


def _heading_has_term(heading: str, term: str) -> bool:
    return term in heading


def _has_novelty_or_sota_claim(lower_text: str) -> bool:
    return any(
        _sentence_has_novelty_or_sota_claim(sentence)
        for sentence in _paper_sentences(lower_text)
    )


def _sentence_has_novelty_or_sota_claim(sentence: str) -> bool:
    claim_text = _strip_negated_novelty_sota_language(sentence)
    return (
        any(pattern.search(claim_text) is not None for pattern in FINAL_PAPER_NOVELTY_CLAIM_RES)
        or FINAL_PAPER_SOTA_SUPERIORITY_RE.search(claim_text) is not None
    )


def _strip_negated_novelty_sota_language(sentence: str) -> str:
    stripped = sentence
    for pattern in FINAL_PAPER_NEGATED_NOVELTY_SOTA_RES:
        stripped = pattern.sub(" ", stripped)
    return stripped


FINAL_PAPER_EVIDENCE_DISCUSSION_GROUPS = (
    (
        "baseline comparison",
        BASELINE_COMPARISON_EVIDENCE_TOKENS,
        ("baseline", "comparison", "leaderboard", "improvement"),
    ),
    (
        "SOTA or prior-work comparison",
        SOTA_COMPARISON_EVIDENCE_TOKENS,
        (
            "prior work",
            "previous work",
            "published result",
            "published model",
            "sota",
            "state-of-the-art",
            "state of the art",
            "leaderboard",
        ),
    ),
    (
        "ablation or feature-importance",
        ABLATION_EVIDENCE_TOKENS,
        ("ablation", "feature importance", "permutation importance", "sensitivity", "shap"),
    ),
    (
        "evaluation protocol",
        EVALUATION_PROTOCOL_EVIDENCE_TOKENS,
        ("cross-validation", "cross validation", "fold", "split", "held-out", "holdout"),
    ),
    (
        "statistical uncertainty",
        STATISTICS_EVIDENCE_TOKENS,
        (
            "uncertainty",
            "statistical",
            "confidence interval",
            "confidence",
            "standard deviation",
            "standard error",
            "variance",
            "dispersion",
            "error bar",
        ),
    ),
    (
        "statistical significance",
        STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS,
        (
            "statistical significance",
            "statistically significant",
            "significant",
            "significance",
            "p-value",
            "p value",
            "excludes zero",
            "excluding zero",
            "does not include zero",
            "crosses zero",
            "crossing zero",
            "includes zero",
            "including zero",
            "overlaps zero",
        ),
    ),
    (
        "causal design",
        CAUSAL_EVIDENCE_TOKENS,
        (
            "causal",
            "causal effect",
            "causal identification",
            "counterfactual",
            "treatment",
            "control group",
            "propensity",
            "instrumental variable",
            "difference-in-differences",
            "difference in differences",
            "regression discontinuity",
        ),
    ),
    (
        "robustness or stability",
        ROBUSTNESS_EVIDENCE_TOKENS,
        (
            "robustness",
            "robust",
            "stability",
            "stable",
            "seed sensitivity",
            "stress test",
            "perturbation",
            "sensitivity",
        ),
    ),
    (
        "generalization",
        GENERALIZATION_EVIDENCE_TOKENS,
        (
            "generalization",
            "generalizes",
            "external validation",
            "external dataset",
            "out-of-distribution",
            "out of distribution",
            "ood",
            "held-out",
            "holdout",
            "cross-dataset",
            "cross dataset",
        ),
    ),
    (
        "external/OOD generalization",
        EXTERNAL_GENERALIZATION_EVIDENCE_TOKENS,
        (
            "external validation",
            "external test",
            "external dataset",
            "external cohort",
            "independent validation",
            "independent cohort",
            "validation cohort",
            "out-of-distribution",
            "out of distribution",
            "ood",
            "cross-dataset",
            "cross dataset",
        ),
    ),
    (
        "error analysis",
        ERROR_ANALYSIS_EVIDENCE_TOKENS,
        ("error analysis", "failure case", "failure cases", "residual", "slice", "subgroup", "misclassification", "calibration"),
    ),
    (
        "fairness or bias audit",
        FAIRNESS_EVIDENCE_TOKENS,
        (
            "fairness",
            "bias audit",
            "model bias",
            "demographic parity",
            "equalized odds",
            "equal opportunity",
            "disparate impact",
            "protected group",
            "protected attribute",
            "group fairness",
            "subgroup fairness",
            "unbiased",
        ),
    ),
    (
        "efficiency or resource usage",
        EFFICIENCY_EVIDENCE_TOKENS,
        (
            "efficiency",
            "latency",
            "throughput",
            "runtime",
            "run time",
            "inference time",
            "training time",
            "wall clock",
            "memory",
            "model size",
            "parameter count",
            "flops",
            "compute cost",
            "gpu hours",
        ),
    ),
    (
        "leakage audit",
        LEAKAGE_AUDIT_EVIDENCE_TOKENS,
        ("leakage", "split audit", "train/test overlap", "duplicate overlap"),
    ),
    (
        "target achievement",
        GOAL_ACHIEVEMENT_EVIDENCE_TOKENS,
        ("target", "goal", "success criteria"),
    ),
    (
        "reproducibility",
        (
            *REPRODUCIBILITY_SEED_TOKENS,
            *REPRODUCIBILITY_DATA_TOKENS,
            *REPRODUCIBILITY_ENV_TOKENS,
            *REPRODUCIBILITY_CODE_TOKENS,
        ),
        ("reproducibility", "reproduce", "seed", "dataset fingerprint", "environment", "code provenance", "script hash"),
    ),
)


def _final_paper_evidence_discussion_issues(
    project_dir: Path,
    lower_text: str,
    iteration: int | None = None,
) -> list[str]:
    missing = [
        name
        for name, evidence_tokens, discussion_terms in FINAL_PAPER_EVIDENCE_DISCUSSION_GROUPS
        if (
            evidence_paths := _result_artifact_paths_with_evidence(project_dir, evidence_tokens, iteration)
        )
        and not _paper_discusses_evidence_family(lower_text, discussion_terms, evidence_paths)
    ]
    if not missing:
        return []
    return [f"final_paper.md must discuss result evidence families present in artifacts: {missing}"]


def _paper_discusses_evidence_family(
    lower_text: str,
    discussion_terms: tuple[str, ...],
    evidence_paths: set[str],
) -> bool:
    for sentence in _paper_sentences(lower_text):
        if not any(term in sentence for term in discussion_terms):
            continue
        if any(path in sentence for path in evidence_paths):
            return True
    return False


def _paper_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text) if sentence.strip()]


def _result_artifact_paths_with_evidence(
    project_dir: Path,
    evidence_tokens: tuple[str, ...],
    iteration: int | None = None,
) -> set[str]:
    paths: set[str] = set()
    for path in research_result_json_files(project_dir, iteration=iteration):
        if not is_citable_result_artifact(path):
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if _artifact_has_discussion_evidence(data, evidence_tokens):
            paths.add(path.relative_to(project_dir).as_posix().lower())
    return paths


def _artifact_has_discussion_evidence(data: dict[str, Any], evidence_tokens: tuple[str, ...]) -> bool:
    if evidence_tokens == BASELINE_COMPARISON_EVIDENCE_TOKENS:
        return _has_baseline_discussion_evidence(data)
    if evidence_tokens == SOTA_COMPARISON_EVIDENCE_TOKENS:
        return _has_sota_discussion_evidence(data)
    if evidence_tokens == ABLATION_EVIDENCE_TOKENS:
        return _shared_has_substantive_ablation_evidence(data)
    if evidence_tokens == EVALUATION_PROTOCOL_EVIDENCE_TOKENS:
        return (
            bool(_evaluation_protocol_evidence_values(data))
            and any(count >= 2 for count in _evaluation_protocol_repetition_counts(data))
            and any(count >= 2 for count in _evaluation_protocol_repeated_metric_counts(data))
        )
    if evidence_tokens == STATISTICS_EVIDENCE_TOKENS:
        return _shared_has_uncertainty_evidence(data)
    if evidence_tokens == STATISTICAL_SIGNIFICANCE_EVIDENCE_TOKENS:
        return _shared_has_statistical_significance_evidence(data)
    if evidence_tokens == CAUSAL_EVIDENCE_TOKENS:
        return _shared_has_causal_evidence(data)
    if evidence_tokens == ROBUSTNESS_EVIDENCE_TOKENS:
        return _shared_has_explicit_robustness_evidence(data)
    if evidence_tokens == GENERALIZATION_EVIDENCE_TOKENS:
        return _shared_has_explicit_generalization_evidence(data)
    if evidence_tokens == EXTERNAL_GENERALIZATION_EVIDENCE_TOKENS:
        return _shared_has_external_generalization_evidence(data)
    if evidence_tokens == ERROR_ANALYSIS_EVIDENCE_TOKENS:
        return _shared_has_substantive_error_analysis_evidence(data)
    if evidence_tokens == FAIRNESS_EVIDENCE_TOKENS:
        return _shared_has_fairness_evidence(data)
    if evidence_tokens == EFFICIENCY_EVIDENCE_TOKENS:
        return _shared_has_efficiency_evidence(data)
    if evidence_tokens == LEAKAGE_AUDIT_EVIDENCE_TOKENS:
        return _shared_has_substantive_leakage_audit_evidence(data)
    if evidence_tokens == GOAL_ACHIEVEMENT_EVIDENCE_TOKENS:
        return bool(_goal_achievement_values(data))
    if _is_reproducibility_discussion_token_group(evidence_tokens):
        return (
            not _shared_reproducibility_bundle_missing_groups(data)
            and _has_reproducibility_code_path(data)
        )
    return _shared_has_evidence_token_value(data, evidence_tokens)


def _is_reproducibility_discussion_token_group(evidence_tokens: tuple[str, ...]) -> bool:
    return set(evidence_tokens) == set(
        (
            *REPRODUCIBILITY_SEED_TOKENS,
            *REPRODUCIBILITY_DATA_TOKENS,
            *REPRODUCIBILITY_ENV_TOKENS,
            *REPRODUCIBILITY_CODE_TOKENS,
        )
    )


def _has_baseline_discussion_evidence(data: dict[str, Any]) -> bool:
    return any(
        _shared_is_baseline_comparison_evidence_key(key)
        and _is_substantive_evidence_leaf(value)
        for key, value in _walk_named_values(data)
    )


def _has_sota_discussion_evidence(data: dict[str, Any]) -> bool:
    return any(
        _shared_is_sota_comparison_evidence_key(key)
        and _is_substantive_evidence_leaf(value)
        for key, value in _walk_named_values(data)
    )


def _script_phase_reproducibility_issues(
    phase: dict[str, Any],
    phase_id: str,
    data: dict[str, Any],
) -> list[str]:
    if phase.get("type") not in ("script", "optimize"):
        return []
    missing = _shared_reproducibility_bundle_missing_groups(data)
    if not _has_reproducibility_code_path(data):
        missing.append("code path")
    if not missing:
        return []
    return [f"{phase_id} reproducibility metadata missing groups: {sorted(set(missing))}"]


def _script_phase_statistics_issues(
    plan: dict[str, Any],
    phase: dict[str, Any],
    phase_id: str,
    data: dict[str, Any],
) -> list[str]:
    if phase.get("type") not in ("script", "optimize") or not _plan_looks_experimental(plan):
        return []
    if _has_statistical_numeric_evidence(data):
        return []
    return [
        f"{phase_id} experimental script result must include statistical evidence "
        "such as std, CI, sample counts, fold counts, or p-values; "
        "support counts alone do not satisfy the statistical inference requirement"
    ]


def audit_phase_result_artifact_contract(
    plan: dict[str, Any],
    phase: dict[str, Any],
    phase_id: str,
    data: dict[str, Any],
) -> list[str]:
    """Audit one phase result's executable-artifact contract.

    Shared by live `PHASE_EVALUATE` and final iteration audits so a phase
    cannot pass the engine with metadata that the final audit later rejects.
    """
    issues: list[str] = []
    issues.extend(_script_phase_reproducibility_issues(phase, phase_id, data))
    issues.extend(_script_phase_statistics_issues(plan, phase, phase_id, data))
    issues.extend(_optimize_phase_trace_issues(plan, phase, phase_id, data))
    return issues


def _audit_missing_statistical_inference_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not _plan_looks_experimental(plan) or not result_payloads:
        return []
    if any(
        _shared_has_uncertainty_evidence(data)
        or _shared_has_statistical_significance_evidence(data)
        for _, data in result_payloads
    ):
        return []
    return [
        "experimental results must include statistical uncertainty or significance "
        "evidence such as std, CI, variance, p_value, or comparison CI"
    ]


def _plan_looks_experimental(plan: dict[str, Any]) -> bool:
    phases = plan.get("phases", [])
    phase_list = phases if isinstance(phases, list) else []
    return bool(plan.get("metric") or plan.get("baselines") or plan.get("experiment_checklist")) or any(
        isinstance(phase, dict) and phase.get("type") in ("script", "optimize")
        for phase in phase_list
    )


def _has_statistical_numeric_evidence(data: dict[str, Any]) -> bool:
    return any(
        _shared_is_statistics_evidence_key(key)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        for key, value in _walk_named_values(data)
    )


def _has_reproducibility_code_path(data: dict[str, Any]) -> bool:
    return any(
        _shared_is_reproducibility_code_path_key(key)
        and not _is_empty(value)
        for key, value in _walk_named_values(data)
    )


def _optimize_phase_trace_issues(
    plan: dict[str, Any],
    phase: dict[str, Any],
    phase_id: str,
    data: dict[str, Any],
) -> list[str]:
    if phase.get("type") != "optimize":
        return []
    metric = plan.get("metric", {})
    metric_name = str(metric.get("name", "metric"))
    direction = str(metric.get("direction", "minimize"))
    issues: list[str] = []
    if data.get("optimization_metric") != metric_name:
        issues.append(f"{phase_id} optimize result must record optimization_metric={metric_name!r}")
    if data.get("optimization_direction") != direction:
        issues.append(f"{phase_id} optimize result must record optimization_direction={direction!r}")
    if not isinstance(data.get("selection_criterion"), str) or not data["selection_criterion"].strip():
        issues.append(f"{phase_id} optimize result must record a non-empty selection_criterion")
    if not isinstance(data.get("optimization_config"), dict):
        issues.append(f"{phase_id} optimize result must record optimization_config")

    all_trials = data.get("all_trials")
    if not isinstance(all_trials, list) or not all_trials:
        issues.append(f"{phase_id} optimize result must include non-empty all_trials")
        return issues

    n_trials = data.get("n_trials")
    if not isinstance(n_trials, int) or isinstance(n_trials, bool) or n_trials <= 0:
        issues.append(f"{phase_id} optimize result must include positive integer n_trials")
    elif n_trials != len(all_trials):
        issues.append(f"{phase_id} n_trials={n_trials} does not match all_trials length {len(all_trials)}")

    complete_values: list[float] = []
    for index, trial in enumerate(all_trials):
        trial_path = f"all_trials[{index}]"
        if not isinstance(trial, dict):
            issues.append(f"{phase_id} {trial_path} must be an object")
            continue
        if not isinstance(trial.get("params"), dict):
            issues.append(f"{phase_id} {trial_path}.params must be an object")
        if not isinstance(trial.get("command"), str) or not trial["command"].strip():
            issues.append(f"{phase_id} {trial_path}.command must be non-empty")
        state = str(trial.get("state", "")).lower()
        if state not in {"complete", "success", "fail", "failed", "timeout", "error"}:
            issues.append(f"{phase_id} {trial_path}.state is unknown: {trial.get('state')!r}")
        value = trial.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            complete_values.append(float(value))
        elif state in {"complete", "success"}:
            issues.append(f"{phase_id} {trial_path}.value must be numeric for completed trials")

    if not complete_values:
        issues.append(f"{phase_id} optimize result must include at least one completed numeric trial")
        return issues

    best_metric = data.get(metric_name)
    if not isinstance(best_metric, (int, float)) or isinstance(best_metric, bool):
        issues.append(f"{phase_id} optimize result must include numeric best `{metric_name}`")
    else:
        expected_best = min(complete_values) if direction == "minimize" else max(complete_values)
        if not _approximately_equal(float(best_metric), expected_best):
            issues.append(
                f"{phase_id} best {metric_name}={float(best_metric):g} does not match "
                f"{direction} all_trials best {expected_best:g}"
            )
    if not isinstance(data.get("best_params"), dict):
        issues.append(f"{phase_id} optimize result must include best_params object")
    return issues


def audit_phase_outputs(project_dir: Path, iteration: int, plan: dict[str, Any]) -> list[str]:
    """Check completed/running phase outputs against plan schemas and plots."""
    issues: list[str] = []
    result_payloads: list[tuple[str, dict[str, Any]]] = []
    script_result_payloads: list[tuple[str, dict[str, Any]]] = []
    for phase in plan.get("phases", []):
        status = phase.get("status")
        phase_id = phase.get("id", "?")
        if status != "done":
            issues.append(f"{phase_id} status is {status!r}, expected 'done'")
            continue
        expected_outputs = phase.get("expected_outputs")
        if not isinstance(expected_outputs, dict):
            issues.append(f"{phase_id} expected_outputs must be an object")
            report = {}
        else:
            report = expected_outputs.get("report")
            if not isinstance(report, dict):
                issues.append(f"{phase_id} expected_outputs.report is required")
                report = {}
        report_path = report.get("path")
        if not report_path:
            issues.append(f"{phase_id} expected_outputs.report.path is required")
        if not report.get("schema"):
            issues.append(f"{phase_id} expected_outputs.report.schema is required")
        if report_path:
            try:
                path = resolve_research_results_path(
                    project_dir,
                    report_path,
                    iteration,
                    "expected_outputs.report.path",
                )
            except ValueError as e:
                issues.append(f"{phase_id} unsafe report path: {e}")
                path = None
            if path is not None and not path.exists():
                issues.append(f"{phase_id} missing report: {report_path}")
            elif path is not None:
                try:
                    data = json.loads(path.read_text())
                    object_error = validate_result_object(data)
                    if object_error:
                        issues.append(f"{phase_id} {object_error}")
                    else:
                        schema = report.get("schema", {})
                        expected: list[str] = []
                        validation_fields: list[str] = []
                        if schema:
                            expected = schema_expected_fields(schema)
                            validation_fields = schema_fields_to_validate(data, schema, expected)
                            missing = [field for field in expected if field not in data]
                            if missing:
                                issues.append(f"{phase_id} report missing fields: {missing}")
                            type_errors = validate_schema_types(data, schema, expected)
                            for err in type_errors:
                                issues.append(f"{phase_id} {err}")
                        substantive_fields = list(dict.fromkeys([
                            *(validation_fields or expected),
                            *data.keys(),
                        ]))
                        value_errors = validate_substantive_result_values(data, substantive_fields)
                        for err in value_errors:
                            issues.append(f"{phase_id} {err}")
                        for err in validate_phase_identity(data, str(phase_id)):
                            issues.append(f"{phase_id} {err}")
                        for err in validate_finite_numeric_values(data):
                            issues.append(f"{phase_id} {err}")
                        provenance_errors = audit_code_provenance(project_dir, iteration, data)
                        for err in provenance_errors:
                            issues.append(f"{phase_id} {err}")
                        for err in audit_phase_result_artifact_contract(plan, phase, str(phase_id), data):
                            issues.append(err)
                        result_payloads.append((str(phase_id), data))
                        if phase.get("type") in ("script", "optimize"):
                            script_result_payloads.append((str(phase_id), data))
                except Exception as e:
                    issues.append(f"{phase_id} invalid report JSON: {e}")

        for err in phase_visualization_issues(project_dir, iteration, phase):
            issues.append(f"{phase_id} {err}")
    issues.extend(_audit_missing_baseline_comparison(plan, result_payloads))
    issues.extend(_audit_missing_sota_comparison(plan, result_payloads))
    issues.extend(_audit_missing_ablation_evidence(plan, result_payloads))
    issues.extend(_audit_missing_evaluation_protocol_evidence(plan, result_payloads))
    issues.extend(_audit_missing_causal_evidence(plan, result_payloads))
    issues.extend(_audit_missing_robustness_evidence(plan, result_payloads))
    issues.extend(_audit_missing_generalization_evidence(plan, result_payloads))
    issues.extend(_audit_missing_error_analysis_evidence(plan, result_payloads))
    issues.extend(_audit_missing_fairness_evidence(plan, result_payloads))
    issues.extend(_audit_missing_efficiency_evidence(plan, result_payloads))
    issues.extend(_audit_missing_statistical_inference_evidence(plan, script_result_payloads))
    issues.extend(_audit_baseline_metric_consistency(plan, result_payloads))
    issues.extend(_audit_missing_target_achievement_evidence(plan, result_payloads))
    issues.extend(_audit_target_flag_metric_consistency(plan, result_payloads))
    issues.extend(_audit_missing_leakage_audit_evidence(plan, result_payloads))
    issues.extend(_audit_unresolved_leakage(result_payloads))
    return issues


def audit_phase_result_consistency(
    plan: dict[str, Any],
    phase_id: str,
    data: dict[str, Any],
) -> list[str]:
    """Audit result-level consistency shared by live phase validation and final audits."""
    result_payloads = [(phase_id, data)]
    issues: list[str] = []
    issues.extend(_audit_baseline_metric_consistency(plan, result_payloads))
    issues.extend(_audit_target_flag_metric_consistency(plan, result_payloads))
    issues.extend(_audit_unresolved_leakage(result_payloads))
    return issues


_REFLECTION_DECISIONS = {"done", "add_phases", "idea_mutation", "domain_pivot"}
_IDEA_SCORE_FIELDS = ("novelty", "feasibility", "expected_information_gain", "risk", "artifact_cost")


def validate_reflection_strategy(data: dict[str, Any], iteration: int) -> list[str]:
    """Validate the researcher-loop strategy fields in reflect.json."""
    decision = str(data.get("decision", "")).strip()
    issues: list[str] = []
    if decision not in _REFLECTION_DECISIONS:
        issues.append(f"reflect decision must be one of {sorted(_REFLECTION_DECISIONS)}, got {decision!r}")
        return issues

    if data.get("drift_warning") is True and decision not in {"idea_mutation", "domain_pivot"}:
        issues.append("reflect drift_warning=true requires decision idea_mutation or domain_pivot")

    seeds = data.get("future_iteration_seeds")
    promoted_seeds = [
        seed
        for seed in (seeds if isinstance(seeds, list) else [])
        if isinstance(seed, dict) and seed.get("status") == "promote_next"
    ]
    if decision == "done":
        if promoted_seeds:
            issues.append("reflect decision done contradicts promote_next future_iteration_seeds")
        return issues

    if not isinstance(data.get("diagnosis"), list) or not data["diagnosis"]:
        issues.append("reflect non-terminal decision requires non-empty diagnosis")
    if not _non_empty_text(data.get("selection_rationale")):
        issues.append("reflect non-terminal decision requires non-empty selection_rationale")
    if decision in {"idea_mutation", "domain_pivot"} and not _non_empty_text(data.get("new_idea")):
        issues.append(f"reflect decision {decision} requires non-empty new_idea")
    if not promoted_seeds:
        issues.append("reflect non-terminal decision requires a promote_next future_iteration_seed")

    portfolio = data.get("idea_portfolio")
    if not isinstance(portfolio, list) or len(portfolio) < 3:
        issues.append("reflect non-terminal decision requires idea_portfolio with at least 3 candidate directions")
        portfolio_items: list[Any] = []
    else:
        portfolio_items = portfolio
        for index, candidate in enumerate(portfolio_items):
            issues.extend(_reflection_candidate_issues(candidate, index))

    selected = data.get("selected_direction")
    if not isinstance(selected, dict):
        issues.append("reflect non-terminal decision requires selected_direction object")
    else:
        for key in ("direction", "reason", "evidence"):
            if not _non_empty_text(selected.get(key)):
                issues.append(f"reflect selected_direction.{key} must be non-empty")
        if not _non_empty_text(selected.get("selection_rule")):
            issues.append("reflect selected_direction.selection_rule must be non-empty")
        if not isinstance(selected.get("score"), (int, float)) or isinstance(selected.get("score"), bool):
            issues.append("reflect selected_direction.score must be numeric")
        selected_direction = str(selected.get("direction", "")).strip()
        candidate_directions = {
            str(candidate.get("direction", "")).strip()
            for candidate in portfolio_items
            if isinstance(candidate, dict)
        }
        promoted_directions = {
            str(seed.get("direction") or seed.get("idea") or "").strip()
            for seed in promoted_seeds
        }
        if selected_direction and candidate_directions and selected_direction not in candidate_directions:
            issues.append("reflect selected_direction.direction must match an idea_portfolio candidate")
        if selected_direction and promoted_directions and selected_direction not in promoted_directions:
            issues.append("reflect selected_direction.direction must match the promote_next future_iteration_seed")

    return issues


def _reflection_candidate_issues(candidate: Any, index: int) -> list[str]:
    if not isinstance(candidate, dict):
        return [f"reflect idea_portfolio[{index}] must be an object"]
    issues: list[str] = []
    for key in ("direction", "rationale", "evidence"):
        if not _non_empty_text(candidate.get(key)):
            issues.append(f"reflect idea_portfolio[{index}].{key} must be non-empty")
    scores = candidate.get("scores")
    if not isinstance(scores, dict):
        issues.append(f"reflect idea_portfolio[{index}].scores must be an object")
    else:
        for field in _IDEA_SCORE_FIELDS:
            value = scores.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                issues.append(f"reflect idea_portfolio[{index}].scores.{field} must be numeric")
    status = candidate.get("status")
    if status not in {"promote_next", "defer", "discard"}:
        issues.append(f"reflect idea_portfolio[{index}].status must be promote_next, defer, or discard")
    return issues


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def audit_evaluation_result_consistency(
    project_dir: Path,
    evaluation: dict[str, Any],
    *,
    iterations: Iterable[int] | None = None,
) -> list[str]:
    """Check professor scores against explicit result flags."""
    verdict = str(evaluation.get("verdict", "")).upper()
    scores = evaluation.get("scores", {})
    goal_score = scores.get("goal_achievement") if isinstance(scores, dict) else None
    high_goal_score = isinstance(goal_score, (int, float)) and not isinstance(goal_score, bool) and goal_score >= 7

    issues: list[str] = []
    if (verdict == "ACCEPT" or high_goal_score) and _evaluation_claims_goal_success(evaluation):
        false_flags = _explicit_false_goal_flags(project_dir, iterations=iterations)
        if false_flags:
            issues.append(f"evaluation goal achievement contradicts result flags: {false_flags}")

    rigor_score = scores.get("academic_rigor") if isinstance(scores, dict) else None
    sufficiency_score = scores.get("experimental_sufficiency") if isinstance(scores, dict) else None
    high_validity_score = any(
        isinstance(score, (int, float)) and not isinstance(score, bool) and score >= 7
        for score in (rigor_score, sufficiency_score)
    )
    if verdict == "ACCEPT" or high_validity_score:
        unresolved_leakage = _unresolved_leakage_result_fields(project_dir, iterations=iterations)
        if unresolved_leakage:
            issues.append(f"evaluation validity scores contradict unresolved leakage findings: {unresolved_leakage}")
        missing_evidence = _explicit_missing_experimental_evidence_flags(project_dir, iterations=iterations)
        if missing_evidence:
            issues.append(
                "evaluation rigor/sufficiency contradicts explicit missing experimental evidence flags: "
                f"{missing_evidence}"
            )

    feedback_path_issues = _evaluation_feedback_artifact_path_issues(project_dir, evaluation)
    issues.extend(feedback_path_issues)

    return issues


def _evaluation_feedback_artifact_path_issues(project_dir: Path, evaluation: dict[str, Any]) -> list[str]:
    if str(evaluation.get("verdict", "")).upper() != "ACCEPT":
        return []
    unsafe = evaluation_feedback_unsafe_artifact_paths(evaluation)
    cited_paths = [
        path
        for path in evaluation_feedback_artifact_paths(evaluation)
        if path != "research/final_paper.md"
    ]
    missing = [
        path
        for path in cited_paths
        if not (project_dir / path).is_file()
    ]
    invalid_json = [
        path
        for path in cited_paths
        if path.endswith(".json")
        and (project_dir / path).is_file()
        and not _is_valid_json_artifact(project_dir / path)
    ]
    invalid_result_json = [
        _result_artifact_validation_summary(path, project_dir / path)
        for path in cited_paths
        if _is_result_json_artifact_path(path)
        and (project_dir / path).is_file()
        and _is_valid_json_artifact(project_dir / path)
        and _is_substantive_json_result_artifact(project_dir / path)
        and not _is_valid_result_artifact(project_dir / path)
    ]
    non_substantive_json = [
        path
        for path in cited_paths
        if _is_result_json_artifact_path(path)
        and (project_dir / path).is_file()
        and _is_valid_json_artifact(project_dir / path)
        and not _is_substantive_json_result_artifact(project_dir / path)
    ]
    invalid_png = [
        path
        for path in cited_paths
        if path.endswith(".png")
        and (project_dir / path).is_file()
        and not is_valid_png_artifact(project_dir / path)
    ]
    issues: list[str] = []
    if unsafe:
        issues.append(f"evaluation.feedback cites unsafe research artifact paths: {unsafe}")
    if missing:
        issues.append(f"evaluation.feedback cites missing research artifacts: {missing}")
    if invalid_json:
        issues.append(f"evaluation.feedback cites invalid JSON research artifacts: {invalid_json}")
    if invalid_result_json:
        issues.append(f"evaluation.feedback cites invalid result JSON research artifacts: {invalid_result_json}")
    if non_substantive_json:
        issues.append(f"evaluation.feedback cites non-substantive JSON research artifacts: {non_substantive_json}")
    if invalid_png:
        issues.append(f"evaluation.feedback cites invalid PNG research artifacts: {invalid_png}")
    return issues


def _is_result_json_artifact_path(path: str) -> bool:
    return re.fullmatch(r"research/iter_\d+/results/[A-Za-z0-9_./-]+\.json", path) is not None


def _is_valid_json_artifact(path: Path) -> bool:
    try:
        json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return True


def _is_valid_result_artifact(path: Path) -> bool:
    return not _result_artifact_validation_errors(path)


def is_citable_result_artifact(path: Path) -> bool:
    """Return true when a result JSON can be used as final-paper evidence."""
    try:
        stat = path.stat()
    except OSError:
        return False
    return _is_citable_result_artifact_cached(path.as_posix(), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4096)
def _is_citable_result_artifact_cached(path_str: str, _mtime_ns: int, _size: int) -> bool:
    path = Path(path_str)
    return _is_valid_result_artifact(path) and _is_substantive_json_result_artifact(path)


def _result_artifact_validation_summary(display_path: str, path: Path) -> str:
    errors = _result_artifact_validation_errors(path)
    if not errors or not _is_valid_json_artifact(path):
        return display_path
    return f"{display_path}: {errors[:3]}"


def _result_artifact_validation_errors(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ["invalid JSON"]
    object_error = validate_result_object(data)
    if object_error:
        return [object_error]
    errors: list[str] = []
    errors.extend(validate_finite_numeric_values(data))
    errors.extend(validate_substantive_result_values(data, list(data.keys())))
    return errors


def _is_substantive_json_result_artifact(path: Path) -> bool:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or not data:
        return False
    return any(not _is_empty(value) for _, value in _walk_named_values(data))


def _research_result_json_files_for_iterations(
    project_dir: Path,
    iterations: Iterable[int] | None = None,
) -> list[Path]:
    if iterations is None:
        return research_result_json_files(project_dir)
    return [
        path
        for iteration in sorted(set(iterations))
        for path in research_result_json_files(project_dir, iteration=iteration)
    ]


def _explicit_false_goal_flags(project_dir: Path, iterations: Iterable[int] | None = None) -> list[str]:
    flags: list[str] = []
    for path in _research_result_json_files_for_iterations(project_dir, iterations):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        rel = path.relative_to(project_dir).as_posix()
        for key, value in _walk_named_values(data):
            if _is_goal_achievement_flag(key.lower()) and _value_indicates_false(value):
                flags.append(f"{rel}:{key}")
    return flags


def _explicit_negative_comparison_flags(project_dir: Path) -> list[str]:
    flags: list[str] = []
    for path in research_result_json_files(project_dir):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        rel = path.relative_to(project_dir).as_posix()
        for key, value in _walk_named_values(data):
            if _key_value_indicates_negative_comparison(key.lower(), value):
                flags.append(f"{rel}:{key}")
    return flags


def _key_value_indicates_negative_comparison(key: str, value: Any) -> bool:
    if _is_baseline_superiority_flag_key(key) or _is_sota_superiority_flag_key(key):
        return _value_indicates_false(value)
    if _is_baseline_improvement_key(key):
        numeric = _numeric_evaluation_value(value)
        return numeric is not None and numeric <= 0
    return False


def _is_baseline_superiority_flag_key(key: str) -> bool:
    return (
        _shared_is_baseline_comparison_evidence_key(key)
        and _path_key_matches(key, {"beats_baseline", "outperforms_baseline"})
    )


def _is_sota_superiority_flag_key(key: str) -> bool:
    return (
        _shared_is_sota_comparison_evidence_key(key)
        and _path_key_matches(
            key,
            {
                "beats_sota",
                "outperforms_sota",
                "beats_prior_work",
                "outperforms_prior_work",
                "beats_previous_work",
                "outperforms_previous_work",
                "beats_state_of_the_art",
                "outperforms_state_of_the_art",
            },
        )
    )


def _is_baseline_improvement_key(key: str) -> bool:
    return (
        _shared_is_baseline_comparison_evidence_key(key)
        and _path_key_matches(
            key,
            {"improvement_over_baseline", "delta_vs_baseline", "relative_improvement"},
        )
    )


def _numeric_evaluation_value(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _unresolved_leakage_result_fields(project_dir: Path, iterations: Iterable[int] | None = None) -> list[str]:
    unresolved: list[str] = []
    for path in _research_result_json_files_for_iterations(project_dir, iterations):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        rel = path.relative_to(project_dir).as_posix()
        for field in _positive_leakage_fields(data):
            unresolved.append(f"{rel}:{field}")
        if unresolved and _has_leakage_resolution(data):
            unresolved = []
    return unresolved


def _explicit_missing_experimental_evidence_flags(
    project_dir: Path,
    iterations: Iterable[int] | None = None,
) -> list[str]:
    flags: list[str] = []
    for path in _research_result_json_files_for_iterations(project_dir, iterations):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        rel = path.relative_to(project_dir).as_posix()
        for key, value in _walk_named_subtrees(data):
            if _is_experimental_support_evidence_key(key.lower()) and _key_value_indicates_missing_evidence(
                key.lower(),
                value,
            ):
                flags.append(f"{rel}:{key}")
    return flags


def _key_value_indicates_missing_evidence(key: str, value: Any) -> bool:
    normalized_key = _normalize_text(key)
    if "failure cases" in normalized_key:
        return False
    if normalized_key.endswith("prior work results") or normalized_key.endswith("reference results"):
        return False
    if _shared_is_leakage_indicator_key(key) and _value_indicates_clean_leakage_check(value):
        return False
    if _is_baseline_superiority_flag_key(key) or _is_sota_superiority_flag_key(key):
        return False
    if _is_baseline_improvement_key(key) and _numeric_evaluation_value(value) is not None:
        return False
    if isinstance(value, bool) and value is False and not _boolean_false_means_missing_evidence(key):
        return False
    return _value_indicates_missing_evidence(value)


def _evaluation_claims_goal_success(evaluation: dict[str, Any]) -> bool:
    text = _normalize_text({
        key: value
        for key, value in evaluation.items()
        if key in {"summary", "rationale", "decision_rationale", "feedback", "comments"}
    })
    return any(
        phrase in text
        for phrase in (
            "goal achieved",
            "goal was achieved",
            "goal met",
            "success criteria met",
            "target achieved",
            "target was achieved",
            "target met",
            "met the target",
            "achieved the target",
        )
    )


def _boolean_false_means_missing_evidence(key: str) -> bool:
    normalized = _normalize_text(key)
    phrases = {
        "baseline results",
        "sota results",
        "prior work results",
        "reference results",
        "ablation results",
        "cv results",
        "cross validation results",
        "robustness checks",
        "error analysis",
        "fairness by group",
    }
    return any(normalized == phrase or normalized.endswith(f" {phrase}") for phrase in phrases)


def _is_experimental_support_evidence_key(key: str) -> bool:
    return (
        _shared_is_baseline_comparison_evidence_key(key)
        or _shared_is_sota_comparison_evidence_key(key)
        or _shared_is_statistics_evidence_key(key)
        or _is_ablation_evidence_key(key)
        or _shared_is_evaluation_protocol_evidence_key(key)
        or _is_error_analysis_evidence_key(key)
        or _shared_is_causal_evidence_key(key)
        or _shared_is_robustness_evidence_key(key)
        or _shared_is_generalization_evidence_key(key)
        or _shared_is_external_generalization_evidence_key(key)
        or _shared_is_fairness_evidence_key(key)
        or _shared_is_efficiency_evidence_key(key)
        or _shared_is_leakage_audit_evidence_key(key)
        or _shared_is_reproducibility_evidence_key(key)
    )


def _value_indicates_clean_leakage_check(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 0
    if isinstance(value, str):
        return value.strip().lower() in _CLEAN_LEAKAGE_TEXT_VALUES
    return False


def _value_indicates_missing_evidence(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value.strip().lower() in {
            "",
            "false",
            "missing",
            "n/a",
            "na",
            "no",
            "none",
            "not applicable",
            "not collected",
            "not done",
            "not measured",
            "not reported",
            "todo",
            "unknown",
        }
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _is_goal_achievement_flag(key: str) -> bool:
    return _shared_is_goal_achievement_evidence_key(key)


def _value_indicates_false(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 0
    if isinstance(value, str):
        return value.strip().lower() in ("false", "no", "not met", "not_met", "failed", "0")
    return False


def _value_indicates_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "met", "achieved", "passed", "1")
    return False


def _audit_missing_baseline_comparison(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    baselines = plan.get("baselines")
    if not isinstance(baselines, list) or not baselines or not result_payloads:
        return []
    comparison_values = [
        value
        for _, data in result_payloads
        for value in _baseline_comparison_values(data)
    ]
    metric_name = _plan_metric_name(plan)
    baseline_entries = [
        entry
        for _, data in result_payloads
        for entry in _baseline_comparison_entries(data, metric_name)
    ]
    if not comparison_values and not baseline_entries:
        return ["experimental results must include baseline comparison evidence"]
    baseline_names = [name for name, _ in baseline_entries]
    missing = _missing_planned_baselines(baselines, [*comparison_values, *baseline_names])
    if missing:
        return [f"experimental results missing planned baseline comparisons: {missing}"]
    missing_metric = _missing_planned_baseline_metric_values(baselines, baseline_entries)
    if missing_metric:
        return [
            "experimental results missing numeric baseline metric values for planned baselines: "
            f"{missing_metric}"
        ]
    return []


def _has_baseline_comparison_evidence(data: dict[str, Any]) -> bool:
    return bool(_baseline_comparison_values(data))


def _audit_missing_sota_comparison(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not _plan_requires_sota_comparison_evidence(plan) or not result_payloads:
        return []
    metric_name = _plan_metric_name(plan)
    entries = [
        entry
        for _, data in result_payloads
        for entry in _sota_comparison_entries(data, metric_name)
    ]
    if not entries:
        return ["experimental results must include SOTA or prior-work comparison evidence"]
    if not any(has_metric for _, has_metric in entries):
        return [
            "experimental results must include numeric SOTA or prior-work metric values "
            "matching the plan metric"
        ]
    return []


def _plan_requires_sota_comparison_evidence(plan: dict[str, Any]) -> bool:
    baselines = plan.get("baselines")
    if isinstance(baselines, list):
        has_context_only_sota = any(
            _is_context_only_baseline(baseline) and "sota" in _normalize_text(baseline)
            for baseline in baselines
        )
        has_planned_sota = any(
            not _is_context_only_baseline(baseline)
            and any(token in _normalize_text(baseline) for token in ("sota", "state of the art", "prior work"))
            for baseline in baselines
        )
        if has_context_only_sota and not has_planned_sota:
            return False
    text = _normalize_text(plan)
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


def _audit_missing_ablation_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_ablation_evidence(plan) or not result_payloads:
        return []
    if any(_has_substantive_ablation_evidence(data) for _, data in result_payloads):
        return []
    return ["experimental results must include ablation, feature importance, or sensitivity evidence"]


def _audit_missing_evaluation_protocol_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_evaluation_protocol_evidence(plan) or not result_payloads:
        return []
    if any(_evaluation_protocol_evidence_values(data) for _, data in result_payloads):
        repetition_counts = [
            count
            for _, data in result_payloads
            for count in _evaluation_protocol_repetition_counts(data)
        ]
        if not repetition_counts or max(repetition_counts) < 2:
            return [
                "cross-validation or multiple-split evidence must include at least 2 folds/splits"
            ]
        repeated_metric_counts = [
            count
            for _, data in result_payloads
            for count in _evaluation_protocol_repeated_metric_counts(data)
        ]
        if not repeated_metric_counts or max(repeated_metric_counts) < 2:
            return [
                "cross-validation or multiple-split evidence must include per-fold/split metric results"
            ]
        count_issues = _evaluation_protocol_count_consistency_issues(result_payloads)
        if count_issues:
            return count_issues
        return []
    return ["experimental results must include cross-validation or multiple-split evidence"]


def _evaluation_protocol_count_consistency_issues(
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    issues: list[str] = []
    for phase_id, data in result_payloads:
        declared_counts = _declared_evaluation_protocol_counts(data)
        if not declared_counts:
            continue
        repeated_metric_counts = _evaluation_protocol_repeated_metric_counts(data)
        repeat_multipliers = _declared_repeat_multipliers(data)
        for key, count in declared_counts:
            if count < 2 and _allows_zero_absent_split_count(key, data):
                continue
            if count < 2:
                issues.append(f"{phase_id} {key} must declare at least 2 folds/splits")
            elif (
                repeated_metric_counts
                and count not in repeated_metric_counts
                and not _count_matches_repeated_total(key, count, repeated_metric_counts, repeat_multipliers)
            ):
                materialized_counts = sorted(set(repeated_metric_counts))
                issues.append(
                    f"{phase_id} {key}={count} must match materialized "
                    f"per-fold/split metric result count(s) {materialized_counts}"
                )
    return issues


def _declared_evaluation_protocol_counts(data: dict[str, Any]) -> list[tuple[str, int]]:
    counts: list[tuple[str, int]] = []
    for key, value in _walk_named_values(data):
        if not _is_protocol_count_key(key):
            continue
        count = _integer_count_value(value)
        if count is not None:
            counts.append((key, count))
    return counts


def _declared_repeat_multipliers(data: dict[str, Any]) -> list[int]:
    counts: list[int] = []
    for key, value in _walk_named_values(data):
        normalized = _normalize_metric_key(key)
        if normalized not in {"n_repeats", "repeat_count", "num_repeats", "repeats"}:
            continue
        count = _integer_count_value(value)
        if count is not None and count >= 2:
            counts.append(count)
    return counts


def _count_matches_repeated_total(
    key: str,
    count: int,
    repeated_metric_counts: list[int],
    repeat_multipliers: list[int],
) -> bool:
    if not repeat_multipliers:
        return False
    if not _is_per_repeat_split_count_key(key):
        return False
    totals = {count * multiplier for multiplier in repeat_multipliers}
    return any(total in repeated_metric_counts for total in totals)


def _is_per_repeat_split_count_key(key: str) -> bool:
    normalized = _normalize_metric_key(key)
    return normalized in {"n_splits", "n_folds", "cv_folds", "cv_fold_count"}


def _integer_count_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _audit_missing_error_analysis_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_error_analysis_evidence(plan) or not result_payloads:
        return []
    if any(_has_substantive_error_analysis_evidence(data) for _, data in result_payloads):
        return []
    return ["experimental results must include error analysis evidence"]


def _audit_missing_fairness_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_fairness_evidence(plan) or not result_payloads:
        return []
    if any(_shared_has_fairness_evidence(data) for _, data in result_payloads):
        return []
    return ["experimental results must include fairness or bias-audit evidence"]


def _audit_missing_efficiency_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_efficiency_evidence(plan) or not result_payloads:
        return []
    if any(_shared_has_efficiency_evidence(data) for _, data in result_payloads):
        return []
    if (
        plan_requires_efficiency_benchmark_context(plan)
        and any(_has_efficiency_profile_measurement(data) for _, data in result_payloads)
        and not any(_shared_has_efficiency_benchmark_context(data) for _, data in result_payloads)
    ):
        return ["experimental results must include efficiency benchmark context"]
    return ["experimental results must include efficiency or resource evidence"]


def _has_efficiency_profile_measurement(data: dict[str, Any]) -> bool:
    return any(
        _shared_is_efficiency_profile_evidence_key(key)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        for key, value in _walk_named_values(data)
    )


def _audit_missing_causal_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_causal_evidence(plan) or not result_payloads:
        return []
    if any(_shared_has_causal_evidence(data) for _, data in result_payloads):
        return []
    return ["experimental results must include causal design or identification evidence"]


def _audit_missing_robustness_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_robustness_evidence(plan) or not result_payloads:
        return []
    if any(_shared_has_robustness_evidence(data) for _, data in result_payloads):
        return []
    return ["experimental results must include robustness or stability evidence"]


def _audit_missing_generalization_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not plan_requires_generalization_evidence(plan) or not result_payloads:
        return []
    if plan_requires_external_generalization_evidence(plan):
        if any(_shared_has_external_generalization_evidence(data) for _, data in result_payloads):
            return []
        return ["experimental results must include external, cross-dataset, or OOD generalization evidence"]
    if any(_shared_has_generalization_evidence(data) for _, data in result_payloads):
        return []
    return ["experimental results must include held-out, external, or OOD generalization evidence"]


def _audit_missing_leakage_audit_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not _plan_requires_leakage_audit_evidence(plan) or not result_payloads:
        return []
    if any(_shared_has_substantive_leakage_audit_evidence(data) for _, data in result_payloads):
        return []
    return [
        "experimental results must include leakage audit scope evidence such as "
        "train_test_overlap, duplicate_overlap, group_overlap, target_leakage, "
        "temporal_leakage, preprocessing_leakage, or group_leakage"
    ]


def _plan_requires_leakage_audit_evidence(plan: dict[str, Any]) -> bool:
    text = _normalize_text(plan)
    return any(
        token in text
        for token in (
            "leakage",
            "data leak",
            "train/test",
            "train test",
            "duplicate overlap",
            "split_audit",
            "leakage_found",
            "leakage_detected",
            "target_leakage",
            "temporal_leakage",
            "preprocessing_leakage",
            "group_leakage",
            "group_overlap",
        )
    )


def _audit_target_flag_metric_consistency(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if _plan_target_is_improvement_threshold(plan):
        return []
    metric_target = _plan_metric_target(plan)
    if metric_target is None:
        return []
    metric_name, direction, target = metric_target

    issues: list[str] = []
    for phase_id, data in result_payloads:
        issues.extend(
            _target_scope_consistency_issues(
                phase_id,
                data,
                metric_name,
                direction,
                target,
                _primary_metric_value(data, metric_name),
                "",
            )
        )
    return issues


def _audit_missing_target_achievement_evidence(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    if not result_payloads:
        return []
    has_goal_flag = any(_goal_achievement_values(data) for _, data in result_payloads)
    if has_goal_flag:
        return []
    if _plan_has_explicit_success_criteria(plan):
        return [
            "experimental results must include target_achieved, goal_achieved, "
            "or success_criteria_met when plan defines success criteria"
        ]
    metric_target = _plan_metric_target(plan)
    if metric_target is None:
        return []
    metric_name, _, _ = metric_target
    has_primary_metric = any(_contains_primary_metric_value(data, metric_name) for _, data in result_payloads)
    if not has_primary_metric:
        return []
    return [
        "experimental results must include target_achieved, goal_achieved, "
        "or success_criteria_met when plan metric defines a target"
    ]


def _plan_has_explicit_success_criteria(plan: dict[str, Any]) -> bool:
    if _non_empty_success_criteria(plan.get("success_criteria")):
        return True
    goal = plan.get("goal")
    return isinstance(goal, dict) and _non_empty_success_criteria(goal.get("success_criteria"))


def _non_empty_success_criteria(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_non_empty_success_criteria(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return False


def _target_scope_consistency_issues(
    phase_id: str,
    value: Any,
    metric_name: str,
    direction: str,
    target: float,
    inherited_metric_value: float | None,
    prefix: str,
) -> list[str]:
    if isinstance(value, list):
        issues: list[str] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            issues.extend(
                _target_scope_consistency_issues(
                    phase_id,
                    item,
                    metric_name,
                    direction,
                    target,
                    inherited_metric_value,
                    child_prefix,
                )
            )
        return issues
    if not isinstance(value, dict):
        return []

    metric_value = _primary_metric_value(value, metric_name)
    if metric_value is None:
        metric_value = inherited_metric_value
    issues: list[str] = []
    for key, flag in value.items():
        if not _is_goal_achievement_flag(str(key).lower()):
            continue
        path = f"{prefix}.{key}" if prefix else str(key)
        if metric_value is None:
            issues.append(
                f"{phase_id} {path} requires {metric_name} metric value "
                f"to verify target {target:g}"
            )
            continue
        meets_target = _metric_meets_target(metric_value, target, direction)
        if _value_indicates_true(flag) and not meets_target:
            issues.append(
                f"{phase_id} {path}=true contradicts {metric_name}={metric_value:g} "
                f"vs target {target:g} for {direction} metric"
            )
        elif _value_indicates_false(flag) and meets_target:
            issues.append(
                f"{phase_id} {path}=false contradicts {metric_name}={metric_value:g} "
                f"vs target {target:g} for {direction} metric"
            )

    for key, item in value.items():
        if isinstance(item, (dict, list)):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            issues.extend(
                _target_scope_consistency_issues(
                    phase_id,
                    item,
                    metric_name,
                    direction,
                    target,
                    metric_value,
                    child_prefix,
                )
            )
    return issues


def _plan_metric_target(plan: dict[str, Any]) -> tuple[str, str, float] | None:
    return _shared_plan_metric_target(plan)


def _plan_target_is_improvement_threshold(plan: dict[str, Any]) -> bool:
    metric = plan.get("metric")
    if not isinstance(metric, dict):
        return False
    text = _normalize_text({
        "target_interpretation": metric.get("target_interpretation"),
        "definition": metric.get("definition"),
        "success_criteria": plan.get("success_criteria"),
    })
    return bool(
        any(token in text for token in ("delta", "improvement", "reduction"))
        and any(token in text for token in ("target", "threshold", "minimum useful"))
    )


def _plan_metric_name(plan: dict[str, Any]) -> str | None:
    metric = plan.get("metric")
    if not isinstance(metric, dict):
        return None
    metric_name = str(metric.get("name", "")).strip().lower()
    return metric_name or None


def _goal_achievement_values(data: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        (key, value)
        for key, value in _walk_named_values(data)
        if _is_goal_achievement_flag(key.lower())
        and (_value_indicates_true(value) or _value_indicates_false(value))
    ]


def _contains_primary_metric_value(value: Any, metric_name: str) -> bool:
    if isinstance(value, list):
        return any(_contains_primary_metric_value(item, metric_name) for item in value)
    if not isinstance(value, dict):
        return False
    if _primary_metric_value(value, metric_name) is not None:
        return True
    return any(
        _contains_primary_metric_value(item, metric_name)
        for key, item in value.items()
        if isinstance(item, (dict, list))
        and not _is_non_primary_metric_container_key(str(key))
    )


def _is_non_primary_metric_container_key(key: str) -> bool:
    normalized = _normalize_metric_key(key)
    exact = {
        "ablation_results",
        "baseline_metrics",
        "baseline_results",
        "baseline_scores",
        "cross_validation_results",
        "cv_results",
        "error_analysis",
        "error_slices",
        "evaluation_splits",
        "external_validation_results",
        "feature_importance",
        "fold_metrics",
        "generalization_results",
        "multiple_split_results",
        "per_fold_metrics",
        "repeated_seed_results",
        "repeated_split_results",
        "robustness_results",
        "sensitivity_results",
        "split_results",
    }
    return normalized in exact or any(normalized.endswith(f"_{item}") for item in exact)


def _metric_meets_target(model_value: float, target: float, direction: str) -> bool:
    if direction == "minimize":
        return model_value <= target
    return model_value >= target


def _audit_baseline_metric_consistency(
    plan: dict[str, Any],
    result_payloads: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    metric = plan.get("metric")
    if not isinstance(metric, dict):
        return []
    metric_name = str(metric.get("name", "")).strip().lower()
    direction = str(metric.get("direction", "")).strip().lower()
    if not metric_name or direction not in {"minimize", "maximize"}:
        return []

    issues: list[str] = []
    for phase_id, data in result_payloads:
        issues.extend(
            _baseline_scope_consistency_issues(
                phase_id,
                data,
                metric_name,
                direction,
                _primary_metric_value(data, metric_name),
                tuple(_baseline_metric_values(data, metric_name)),
                "",
            )
        )
    return issues


def _baseline_scope_consistency_issues(
    phase_id: str,
    value: Any,
    metric_name: str,
    direction: str,
    inherited_model_value: float | None,
    inherited_baseline_values: tuple[float, ...],
    prefix: str,
) -> list[str]:
    if isinstance(value, list):
        issues: list[str] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            issues.extend(
                _baseline_scope_consistency_issues(
                    phase_id,
                    item,
                    metric_name,
                    direction,
                    inherited_model_value,
                    inherited_baseline_values,
                    child_prefix,
                )
            )
        return issues
    if not isinstance(value, dict):
        return []

    model_value = _primary_metric_value(value, metric_name)
    if model_value is None:
        model_value = inherited_model_value
    baseline_values = (
        tuple(_direct_comparator_metric_values(value, metric_name))
        or tuple(_baseline_metric_values(value, metric_name))
        or inherited_baseline_values
    )
    issues: list[str] = []
    if model_value is not None and baseline_values:
        best_baseline = min(baseline_values) if direction == "minimize" else max(baseline_values)
        model_beats_baseline = _metric_beats(model_value, best_baseline, direction)

        for flag_key, beats in _direct_beats_baseline_flags(value, prefix):
            if beats is True and not model_beats_baseline:
                issues.append(
                    f"{phase_id} {flag_key}=true contradicts {metric_name}={model_value:g} "
                    f"vs best baseline {best_baseline:g} for {direction} metric"
                )
            elif beats is False and model_beats_baseline:
                issues.append(
                    f"{phase_id} {flag_key}=false contradicts {metric_name}={model_value:g} "
                    f"vs best baseline {best_baseline:g} for {direction} metric"
                )

        for improvement_key, improvement in _direct_baseline_improvement_values(value):
            if improvement > 0 and not model_beats_baseline:
                issues.append(
                    f"{phase_id} positive {improvement_key} contradicts {metric_name}={model_value:g} "
                    f"vs best baseline {best_baseline:g} for {direction} metric"
                )
            elif improvement <= 0 and model_beats_baseline:
                issues.append(
                    f"{phase_id} non-positive {improvement_key} contradicts {metric_name}={model_value:g} "
                    f"vs best baseline {best_baseline:g} for {direction} metric"
                )
                continue
            expected_values = _expected_improvement_values(improvement_key, model_value, best_baseline, direction)
            if expected_values and not _improvement_value_matches(improvement, expected_values, improvement_key):
                expected_text = " or ".join(f"{expected:g}" for expected in expected_values)
                issues.append(
                    f"{phase_id} {improvement_key}={improvement:g} does not match "
                    f"{metric_name}={model_value:g} vs best baseline {best_baseline:g}; "
                    f"expected about {expected_text}"
                )

    for key, item in value.items():
        if isinstance(item, (dict, list)):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            issues.extend(
                _baseline_scope_consistency_issues(
                    phase_id,
                    item,
                    metric_name,
                    direction,
                    model_value,
                    baseline_values,
                    child_prefix,
                )
            )
    return issues


def _primary_metric_value(data: dict[str, Any], metric_name: str) -> float | None:
    candidates: list[tuple[int, float]] = []
    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        normalized = _normalize_metric_key(key)
        if not _metric_key_matches(normalized, metric_name):
            continue
        if _is_non_primary_metric_key(normalized):
            continue
        candidates.append((_metric_key_priority(normalized, metric_name), float(value)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _baseline_metric_values(data: dict[str, Any], metric_name: str) -> list[float]:
    values: list[float] = []
    excluded_names = _candidate_baseline_collection_names(data)
    for key, item in data.items():
        if _is_explicit_baseline_collection_key(str(key)):
            values.extend(_explicit_baseline_collection_metric_values(item, metric_name, excluded_names))
    values.extend(_labeled_baseline_metric_values(data, metric_name))

    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        normalized = _normalize_metric_key(key)
        if _shared_is_baseline_comparison_evidence_key(key) and _metric_key_matches(normalized, metric_name):
            values.append(float(value))
    return values


def _explicit_baseline_collection_metric_values(
    value: Any,
    metric_name: str,
    excluded_names: set[str] | None = None,
) -> list[float]:
    if isinstance(value, list):
        values: list[float] = []
        for item in value:
            values.extend(_explicit_baseline_collection_metric_values(item, metric_name, excluded_names))
        return values
    excluded_names = excluded_names or set()
    if (
        not isinstance(value, dict)
        or _is_candidate_baseline_collection_item(value)
        or bool(_baseline_collection_item_names(value) & excluded_names)
    ):
        return []
    metric_value = _primary_metric_value(value, metric_name)
    return [] if metric_value is None else [metric_value]


def _candidate_baseline_collection_names(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key, value in data.items():
        if _is_explicit_baseline_collection_key(str(key)):
            names.update(_candidate_baseline_names_in_value(value))
    names.update(_candidate_method_names_from_comparison_rows(data))
    return names


def _candidate_baseline_names_in_value(value: Any) -> set[str]:
    if isinstance(value, list):
        names: set[str] = set()
        for item in value:
            names.update(_candidate_baseline_names_in_value(item))
        return names
    if not isinstance(value, dict) or not _is_candidate_baseline_collection_item(value):
        return set()
    return _baseline_collection_item_names(value)


def _candidate_method_names_from_comparison_rows(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("method_results", "model_comparison", "comparison_table"):
        names.update(_candidate_method_names_in_value(data.get(key)))
    return names


def _candidate_method_names_in_value(value: Any) -> set[str]:
    if isinstance(value, list):
        names: set[str] = set()
        for item in value:
            names.update(_candidate_method_names_in_value(item))
        return names
    if not isinstance(value, dict) or not _is_candidate_comparison_row(value):
        return set()
    return _method_collection_item_names(value)


def _is_candidate_comparison_row(data: dict[str, Any]) -> bool:
    method_names = _method_collection_item_names(data)
    comparator_names = _comparison_baseline_names(data)
    if not method_names or not comparator_names or method_names & comparator_names:
        return False
    if data.get("beats_baseline") is True:
        return True
    for key in ("delta_vs_baseline", "improvement_over_baseline", "relative_improvement"):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0:
            return True
    return False


def _is_explicit_baseline_collection_key(key: str) -> bool:
    normalized = _normalize_metric_key(key)
    explicit_suffixes = {
        "baseline_results",
        "baseline_metrics",
        "baseline_scores",
    }
    return normalized in explicit_suffixes or any(
        normalized.endswith(f"_{suffix}") for suffix in explicit_suffixes
    )


def _is_candidate_baseline_collection_item(data: dict[str, Any]) -> bool:
    for key in ("baseline_type", "result_type", "role", "kind", "category"):
        value = data.get(key)
        if not isinstance(value, str):
            continue
        normalized = _normalize_metric_key(value)
        if any(token in normalized for token in ("candidate", "proposed", "treatment", "under_test")):
            return True
    return False


def _baseline_collection_item_names(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("baseline", "baseline_name", "method", "model", "name"):
        value = data.get(key)
        if isinstance(value, str):
            normalized = _normalize_metric_key(value)
            if normalized:
                names.add(normalized)
    return names


def _method_collection_item_names(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("method", "model", "name"):
        value = data.get(key)
        if isinstance(value, str):
            normalized = _normalize_metric_key(value)
            if normalized:
                names.add(normalized)
    return names


def _comparison_baseline_names(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("baseline", "baseline_name", "baseline_model", "comparator", "comparator_name"):
        value = data.get(key)
        if isinstance(value, str):
            normalized = _normalize_metric_key(value)
            if normalized:
                names.add(normalized)
    return names


def _direct_comparator_metric_values(data: dict[str, Any], metric_name: str) -> list[float]:
    values: list[float] = []
    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        normalized = _normalize_metric_key(key)
        if not _metric_key_matches(normalized, metric_name):
            continue
        if normalized.startswith(("comparator_", "baseline_")):
            values.append(float(value))
    return values


def _labeled_baseline_metric_values(data: dict[str, Any], metric_name: str) -> list[float]:
    baseline = data.get("baseline") or data.get("baseline_model") or data.get("baseline_name")
    if not isinstance(baseline, str) or not baseline.strip():
        return []
    normalized_baseline = _normalize_metric_key(baseline)
    if not normalized_baseline:
        return []
    values: list[float] = []
    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        normalized_key = _normalize_metric_key(key)
        if not _metric_key_matches(normalized_key, metric_name):
            continue
        if normalized_key == normalized_baseline or normalized_key.startswith(f"{normalized_baseline}_"):
            values.append(float(value))
    return values


def _direct_beats_baseline_flags(data: dict[str, Any], prefix: str) -> list[tuple[str, bool]]:
    flags: list[tuple[str, bool]] = []
    for key, value in data.items():
        key_text = str(key)
        if (
            _shared_is_baseline_comparison_evidence_key(key_text)
            and _path_key_matches(key_text, {"beats_baseline", "outperforms_baseline"})
            and isinstance(value, bool)
        ):
            path = f"{prefix}.{key}" if prefix else str(key)
            flags.append((path, value))
    return flags


def _direct_baseline_improvement_values(data: dict[str, Any]) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    keys = {"improvement_over_baseline", "delta_vs_baseline", "relative_improvement"}
    for key, value in data.items():
        key_text = str(key)
        if (
            _shared_is_baseline_comparison_evidence_key(key_text)
            and _path_key_matches(key_text, keys)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            values.append((_path_key_suffix(key_text, keys), float(value)))
    return values


def _path_key_matches(path: str, accepted: set[str]) -> bool:
    normalized = _normalize_metric_key(path)
    return any(normalized == key or normalized.endswith(f"_{key}") for key in accepted)


def _path_key_suffix(path: str, accepted: set[str]) -> str:
    normalized = _normalize_metric_key(path)
    for key in accepted:
        if normalized == key or normalized.endswith(f"_{key}"):
            return key
    return normalized


def _expected_improvement_values(
    improvement_key: str,
    model_value: float,
    baseline_value: float,
    direction: str,
) -> tuple[float, ...]:
    absolute = baseline_value - model_value if direction == "minimize" else model_value - baseline_value
    if improvement_key == "delta_vs_baseline":
        return (absolute,)
    if baseline_value == 0:
        return (absolute,) if improvement_key == "improvement_over_baseline" else ()
    relative = absolute / abs(baseline_value)
    if improvement_key == "relative_improvement":
        return (relative,)
    if improvement_key == "improvement_over_baseline":
        return (absolute, relative)
    return ()


def _improvement_value_matches(actual: float, expected_values: tuple[float, ...], improvement_key: str) -> bool:
    candidates = [actual]
    if improvement_key in {"relative_improvement", "improvement_over_baseline"}:
        candidates.append(actual / 100.0)
    return any(
        _approximately_equal(candidate, expected)
        for candidate in candidates
        for expected in expected_values
    )


def _approximately_equal(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= max(1e-6, abs(expected) * 0.05)


def _metric_beats(model_value: float, baseline_value: float, direction: str) -> bool:
    if direction == "minimize":
        return model_value < baseline_value
    return model_value > baseline_value


def _normalize_metric_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _metric_key_matches(normalized_key: str, metric_name: str) -> bool:
    return _shared_is_metric_evidence_key(normalized_key, metric_name)


def _metric_key_priority(normalized_key: str, metric_name: str) -> int:
    aliases = _shared_metric_aliases(metric_name)
    if normalized_key in aliases:
        return 0
    if any(normalized_key in {f"{alias}_mean", f"test_{alias}", f"val_{alias}"} for alias in aliases):
        return 1
    if any(
        normalized_key.endswith(f"_{alias}") or normalized_key.endswith(f"_{alias}_mean")
        for alias in aliases
    ):
        return 2
    return 3


_NON_PRIMARY_METRIC_CONTEXT_TOKENS = (
    "baseline",
    "improvement",
    "delta",
    "relative",
    "min",
    "max",
    "count",
    "sample",
    "fold",
)


def _is_non_primary_metric_key(normalized_key: str) -> bool:
    parts = [part for part in normalized_key.split("_") if part]
    return (
        any(part in _NON_PRIMARY_METRIC_CONTEXT_TOKENS for part in parts)
        or _shared_is_metric_support_numeric_key(normalized_key)
    )


def _baseline_comparison_values(data: dict[str, Any]) -> list[Any]:
    return [
        value
        for key, value in _walk_named_values(data)
        if _is_comparison_evidence_key(key.lower()) and _is_substantive_evidence_leaf(value)
    ]


def _baseline_comparison_entries(data: dict[str, Any], metric_name: str | None) -> list[tuple[str, bool]]:
    return _shared_baseline_comparison_entries(data, metric_name)


def _sota_comparison_entries(data: dict[str, Any], metric_name: str | None) -> list[tuple[str, bool]]:
    return _shared_sota_comparison_entries(data, metric_name)


def _primary_metric_values(value: Any, metric_name: str) -> list[float]:
    if isinstance(value, list):
        values: list[float] = []
        for item in value:
            values.extend(_primary_metric_values(item, metric_name))
        return values
    if not isinstance(value, dict):
        return []
    direct_value = _primary_metric_value(value, metric_name)
    values = [direct_value] if direct_value is not None else []
    for item in value.values():
        if isinstance(item, (dict, list)):
            values.extend(_primary_metric_values(item, metric_name))
    return values


def _ablation_evidence_values(data: dict[str, Any]) -> list[Any]:
    return [
        value
        for key, value in _walk_named_values(data)
        if _is_ablation_evidence_key(key.lower()) and _is_substantive_evidence_leaf(value)
    ]


def _has_substantive_ablation_evidence(data: dict[str, Any]) -> bool:
    return _shared_has_substantive_ablation_evidence(data)


def _error_analysis_evidence_values(data: dict[str, Any]) -> list[Any]:
    return [
        value
        for key, value in _walk_named_values(data)
        if _is_error_analysis_evidence_key(key.lower()) and _is_substantive_evidence_leaf(value)
    ]


def _has_substantive_error_analysis_evidence(data: dict[str, Any]) -> bool:
    return _shared_has_substantive_error_analysis_evidence(data)


def _missing_planned_baselines(baselines: list[Any], comparison_values: list[Any]) -> list[str]:
    names = _planned_baseline_names(baselines)
    if not names:
        return []
    evidence_names = [
        str(value)
        for value in comparison_values
        if isinstance(value, str) and value.strip()
    ]
    evidence_text = _normalize_text(comparison_values)
    missing: list[str] = []
    for display_name, aliases in _planned_baseline_alias_groups(baselines):
        if any(_normalize_text(alias) in evidence_text for alias in aliases):
            continue
        if any(
            _shared_baseline_names_match(alias, evidence_name)
            for alias in aliases
            for evidence_name in evidence_names
        ):
            continue
        missing.append(display_name)
    return missing


def _missing_planned_baseline_metric_values(
    baselines: list[Any],
    baseline_entries: list[tuple[str, bool]],
) -> list[str]:
    missing: list[str] = []
    for display_name, aliases in _planned_baseline_alias_groups(baselines):
        if not any(
            has_metric and any(_shared_baseline_names_match(alias, evidence_name) for alias in aliases)
            for evidence_name, has_metric in baseline_entries
        ):
            missing.append(display_name)
    return missing


def _planned_baseline_names(baselines: list[Any]) -> list[str]:
    return [display_name for display_name, _aliases in _planned_baseline_alias_groups(baselines)]


def _planned_baseline_alias_groups(baselines: list[Any]) -> list[tuple[str, tuple[str, ...]]]:
    groups: list[tuple[str, tuple[str, ...]]] = []
    seen_display: set[str] = set()
    for baseline in baselines:
        if _is_context_only_baseline(baseline):
            continue
        aliases: list[str] = []
        if isinstance(baseline, str) and baseline.strip():
            aliases.append(baseline.strip())
        elif isinstance(baseline, dict):
            for key in ("name", "id"):
                value = baseline.get(key)
                if isinstance(value, str) and value.strip():
                    aliases.append(value.strip())
        if not aliases:
            continue
        display_name = aliases[0]
        if display_name in seen_display:
            continue
        seen_display.add(display_name)
        groups.append((display_name, tuple(dict.fromkeys(aliases))))
    return groups


def _is_context_only_baseline(baseline: Any) -> bool:
    if not isinstance(baseline, dict):
        return False
    category = _normalize_text(baseline.get("category", ""))
    phase_ids = baseline.get("phase_ids")
    text = _normalize_text(baseline)
    return (
        "context only" in category
        or "not reproduced" in text
        or "not planned" in text
        or (isinstance(phase_ids, list) and len(phase_ids) == 0 and "sota" in text)
    )


def _normalize_text(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_comparison_evidence_key(key: str) -> bool:
    return _shared_is_baseline_comparison_evidence_key(key)


def _audit_unresolved_leakage(result_payloads: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Flag positive leakage findings unless a later artifact marks them resolved."""
    unresolved: list[str] = []
    for phase_id, data in result_payloads:
        leakage_fields = _positive_leakage_fields(data)
        for field in leakage_fields:
            unresolved.append(f"{phase_id}.{field}")
        if unresolved and _has_leakage_resolution(data):
            unresolved = []
    if unresolved:
        return [f"unresolved leakage findings in results: {unresolved}"]
    return []


def _positive_leakage_fields(data: dict[str, Any]) -> list[str]:
    positives: list[str] = []
    for key, value in _walk_named_values(data):
        normalized = key.lower()
        if _shared_is_leakage_resolution_key(normalized):
            continue
        if _is_leakage_indicator(normalized) and _value_indicates_problem(value):
            positives.append(key)
    return positives


def _has_leakage_resolution(data: dict[str, Any]) -> bool:
    return any(
        _shared_is_leakage_resolution_key(key)
        and _value_indicates_resolution(value)
        for key, value in _walk_named_values(data)
    )


def _is_leakage_indicator(key: str) -> bool:
    return _shared_is_leakage_indicator_key(key)


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


def _value_indicates_problem(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value > 0
    if isinstance(value, str):
        text = value.strip().lower()
        return text not in {"", *_CLEAN_LEAKAGE_TEXT_VALUES}
    return False


def _is_substantive_evidence_leaf(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return not _is_empty(value)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _value_indicates_resolution(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "resolved", "mitigated", "fixed", "clean")
    return False
