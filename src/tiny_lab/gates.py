"""Shared completion gates for engine and native hooks."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from .claims import format_claim_issue, verify_paper_numeric_claims
from .plan import load_plan, validate_plan_quality
from .paths import iteration_dirs, plan_path
from .quality import (
    audit_evaluation_result_consistency,
    audit_final_paper,
    audit_phase_outputs,
    validate_reflection_strategy,
)
from .refs import audit_reference_sidecars
from .review import validate_evaluation_consistency, validate_review_feedback_response
from .visualizations import data_visualization_manifest_issues


QUALITY_GATED_STATES = {"PLAN", "VISUALIZE_DATA", "IDEA_REFINE", "SHAPE_FULL", "REFLECT", "REVIEW"}
ARTIFACT_QUALITY_GATED_STATES = {"STORY_TELL"}


@dataclass(frozen=True)
class IterationCompletionAudit:
    """Plan and phase-output audit result for one research iteration."""

    iteration: int
    plan_exists: bool
    plan_issues: tuple[str, ...] = ()
    phase_issues: tuple[str, ...] = ()
    load_issue: str | None = None

    def issues(self) -> list[str]:
        out: list[str] = []
        if not self.plan_exists:
            out.append("research_plan.json is missing")
        if self.load_issue:
            out.append(self.load_issue)
        out.extend(self.plan_issues)
        out.extend(self.phase_issues)
        return out


@dataclass(frozen=True)
class FinalArtifactAudit:
    """Final-paper, claims, references, and evaluation audit result."""

    final_paper_exists: bool
    evaluation_exists: bool
    paper_issues: tuple[str, ...] = ()
    claim_issues: tuple[str, ...] = ()
    reference_issues: tuple[str, ...] = ()
    evaluation_issues: tuple[str, ...] = ()
    missing_final_paper_issue: str | None = None


def requires_completion_quality_artifact(state_id: str) -> bool:
    """Return true when a state artifact must be parsed for quality gates."""
    return state_id in QUALITY_GATED_STATES


def requires_completion_artifact_quality_gate(state_id: str) -> bool:
    """Return true when a non-JSON completion artifact has direct quality gates."""
    return state_id in ARTIFACT_QUALITY_GATED_STATES


def completion_artifact_quality_issue(
    project_dir: Path,
    state_id: str,
    artifact_path: Path,
    iteration: int,
) -> str | None:
    """Return a blocking completion issue for non-JSON completion artifacts."""
    if state_id != "STORY_TELL":
        return None
    if artifact_path.name != "final_paper.md":
        return None

    reference_iterations = final_artifact_reference_iterations(project_dir, iteration)
    final_audit = audit_final_artifacts(project_dir, reference_iterations=reference_iterations)
    if final_audit.paper_issues:
        return "final paper issues: " + "; ".join(final_audit.paper_issues[:5])
    completion_issues = audit_research_completion(
        project_dir,
        max(reference_iterations),
        iterations=reference_iterations,
    )
    if completion_issues:
        return "final paper has incomplete research artifacts: " + "; ".join(completion_issues[:5])
    if final_audit.claim_issues:
        return (
            f"final paper has {len(final_audit.claim_issues)} unsupported research claims; "
            "first issues: "
            + "; ".join(final_audit.claim_issues[:20])
        )
    if final_audit.reference_issues:
        return "final paper has reference verification issues: " + "; ".join(final_audit.reference_issues[:5])
    return None


def completion_quality_issue(
    project_dir: Path,
    state_id: str,
    artifact_data: dict[str, Any],
    iteration: int,
) -> str | None:
    """Return a blocking completion issue for high-value research states.

    This function is the single source of truth for gates that must behave
    identically in the CLI engine and PostToolUse native runner hook.
    """
    if state_id == "PLAN":
        issues = validate_plan_quality(artifact_data, iteration)
        if issues:
            return "research plan quality issues: " + "; ".join(issues)

    if state_id == "VISUALIZE_DATA":
        issues = data_visualization_manifest_issues(project_dir, iteration, artifact_data)
        if issues:
            return "data visualization issues: " + "; ".join(issues)
        return None

    if state_id in {"IDEA_REFINE", "SHAPE_FULL"}:
        issues = validate_review_feedback_response(project_dir, state_id, artifact_data)
        if issues:
            return "review feedback response issues: " + "; ".join(issues)

    if state_id == "REFLECT":
        issues = validate_reflection_strategy(artifact_data, iteration)
        if issues:
            return "reflection strategy issues: " + "; ".join(issues)
        return None

    if state_id != "REVIEW":
        return None

    reference_iterations = final_artifact_reference_iterations(project_dir, iteration)
    final_audit = audit_final_artifacts(
        project_dir,
        evaluation=artifact_data,
        reference_iterations=reference_iterations,
        require_final_paper=str(artifact_data.get("verdict", "")).upper() == "ACCEPT",
    )
    if final_audit.evaluation_issues:
        return "evaluation consistency issues: " + "; ".join(final_audit.evaluation_issues)

    if str(artifact_data.get("verdict", "")).upper() != "ACCEPT":
        return None

    if final_audit.paper_issues:
        return "accepted paper has final paper issues: " + "; ".join(final_audit.paper_issues)

    completion_issues = audit_research_completion(
        project_dir,
        max(reference_iterations),
        iterations=reference_iterations,
    )
    if completion_issues:
        return "accepted paper has incomplete research artifacts: " + "; ".join(completion_issues[:5])

    if final_audit.claim_issues:
        preview = "; ".join(final_audit.claim_issues[:20])
        return f"accepted paper has {len(final_audit.claim_issues)} unsupported research claims: " + preview

    if final_audit.reference_issues:
        return "accepted paper has reference verification issues: " + "; ".join(final_audit.reference_issues[:5])

    return None


def audit_research_completion(
    project_dir: Path,
    iteration: int,
    *,
    iterations: Iterable[int] | None = None,
) -> list[str]:
    """Audit planned iteration completion for the requested scope."""
    iter_nums = sorted(set(iterations) if iterations is not None else {*planned_iterations(project_dir), iteration})
    issues: list[str] = []
    for iter_num in iter_nums:
        audit = audit_iteration_completion(project_dir, iter_num)
        for issue in audit.issues():
            issues.append(f"iter_{iter_num}: {issue}")
    return issues


def final_artifact_reference_iteration(project_dir: Path, iteration: int) -> int:
    """Return the latest planned iteration that the final paper should close."""
    return max(final_artifact_reference_iterations(project_dir, iteration))


def final_artifact_reference_iterations(project_dir: Path, iteration: int) -> tuple[int, ...]:
    """Return the canonical iteration scope for final artifacts."""
    if plan_path(project_dir, iteration).is_file():
        return (iteration,)
    candidates = [iter_num for iter_num in planned_iterations(project_dir) if iter_num <= iteration]
    if candidates:
        return (max(candidates),)
    return (iteration,)


def audit_final_artifacts(
    project_dir: Path,
    *,
    evaluation: dict[str, Any] | None = None,
    reference_iteration: int | None = None,
    reference_iterations: Iterable[int] | None = None,
    require_final_paper: bool = False,
) -> FinalArtifactAudit:
    """Audit final-paper, claim, reference, and evaluation artifacts."""
    final_paper = project_dir / "research" / "final_paper.md"
    eval_file = project_dir / "research" / "evaluation.json"
    evaluation_exists = evaluation is not None or eval_file.exists()
    evaluation_issues: list[str] = []
    iteration_scope = tuple(reference_iterations) if reference_iterations is not None else None
    if evaluation is None and eval_file.exists():
        try:
            loaded = json.loads(eval_file.read_text())
            if isinstance(loaded, dict):
                evaluation = loaded
            else:
                evaluation_issues.append(f"evaluation.json must be a JSON object (got {type(loaded).__name__})")
        except Exception as e:
            evaluation_issues.append(f"could not read evaluation.json: {e}")

    if evaluation is not None:
        evaluation_issues.extend(validate_evaluation_consistency(evaluation))
        evaluation_issues.extend(
            audit_evaluation_result_consistency(project_dir, evaluation, iterations=iteration_scope)
        )

    paper_issues: list[str] = []
    claim_issues: list[str] = []
    missing_final_paper_issue: str | None = None
    if final_paper.exists():
        if iteration_scope is None:
            paper_issues.extend(audit_final_paper(project_dir, iteration=reference_iteration))
        else:
            for iter_num in iteration_scope:
                paper_issues.extend(audit_final_paper(project_dir, iteration=iter_num))
        claim_issues.extend(format_claim_issue(issue) for issue in verify_paper_numeric_claims(project_dir))
    elif require_final_paper:
        paper_issues.append("final_paper.md is missing")
    elif evaluation_exists:
        missing_final_paper_issue = "final_paper.md not found but evaluation.json exists"

    return FinalArtifactAudit(
        final_paper_exists=final_paper.exists(),
        evaluation_exists=evaluation_exists,
        paper_issues=tuple(paper_issues),
        claim_issues=tuple(claim_issues),
        reference_issues=tuple(
            audit_reference_sidecars(project_dir, reference_iteration)
            if iteration_scope is None
            else _audit_reference_sidecars_for_iterations(project_dir, iteration_scope)
        ),
        evaluation_issues=tuple(evaluation_issues),
        missing_final_paper_issue=missing_final_paper_issue,
    )


def _audit_reference_sidecars_for_iterations(project_dir: Path, iterations: Iterable[int]) -> list[str]:
    issues: list[str] = []
    for iter_num in iterations:
        issues.extend(audit_reference_sidecars(project_dir, iter_num))
    return issues


def audit_iteration_completion(project_dir: Path, iteration: int) -> IterationCompletionAudit:
    """Audit one iteration's plan and phase outputs."""
    if not plan_path(project_dir, iteration).exists():
        return IterationCompletionAudit(iteration=iteration, plan_exists=False)
    try:
        plan = load_plan(project_dir, iteration)
    except Exception as e:
        return IterationCompletionAudit(
            iteration=iteration,
            plan_exists=True,
            load_issue=f"could not audit plan: {e}",
        )
    return IterationCompletionAudit(
        iteration=iteration,
        plan_exists=True,
        plan_issues=tuple(validate_plan_quality(plan, iteration)),
        phase_issues=tuple(audit_phase_outputs(project_dir, iteration, plan)),
    )


def planned_iterations(project_dir: Path) -> list[int]:
    """Return iteration numbers with research plans."""
    out: list[int] = []
    for path in iteration_dirs(project_dir):
        if not (path / "research_plan.json").is_file():
            continue
        out.append(int(path.name.removeprefix("iter_")))
    return out
