"""Tests for professor review validation."""
from __future__ import annotations

import json

from tiny_lab.review import (
    RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA,
    render_evaluation_contract,
    validate_evaluation_consistency,
    validate_review_feedback_response,
)


def _complete_feedback(score: int = 8) -> list[dict]:
    return [
        {
            "criterion": criterion,
            "score": score,
            "recommendation": (
                f"Maintain artifact-backed evidence for {criterion.replace('_', ' ')} "
                f"using {_feedback_artifact_for(criterion)}."
            ),
        }
        for criterion in (
            "academic_rigor",
            "experimental_sufficiency",
            "novelty",
            "narrative_coherence",
            "goal_achievement",
        )
    ]


def _feedback_artifact_for(criterion: str) -> str:
    if criterion in RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA:
        return "research/iter_1/results/phase_0.json"
    return "research/final_paper.md"


def test_accepts_consistent_accept_verdict():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": _complete_feedback(8),
    }

    assert validate_evaluation_consistency(evaluation) == []


def test_rejects_accept_without_feedback():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "ACCEPT evaluation must include feedback covering every score criterion" in issues


def test_rejects_accept_feedback_without_artifact_citation():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": [{
            "criterion": criterion,
            "score": 8,
            "recommendation": f"Maintain artifact-backed evidence for {criterion}.",
        } for criterion in (
            "academic_rigor",
            "experimental_sufficiency",
            "novelty",
            "narrative_coherence",
            "goal_achievement",
        )],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert any("must cite a concrete project-relative research artifact path" in issue for issue in issues)


def test_rejects_accept_result_grounded_feedback_without_result_artifact_citation():
    feedback = _complete_feedback(8)
    feedback[1]["recommendation"] = (
        "Maintain artifact-backed evidence for experimental sufficiency "
        "using research/final_paper.md."
    )
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": feedback,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert any(
        "experimental_sufficiency" in issue
        and "research/iter_*/results/*.json" in issue
        for issue in issues
    )


def test_rejects_accept_feedback_with_path_traversal_artifact_citation():
    feedback = _complete_feedback(8)
    feedback[0]["recommendation"] = (
        "Maintain artifact-backed evidence for academic rigor using "
        "research/iter_1/results/../../evaluation.json."
    )
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": feedback,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert any("must cite a concrete project-relative research artifact path" in issue for issue in issues)


def test_rejects_result_grounded_feedback_with_path_traversal_result_citation():
    feedback = _complete_feedback(8)
    feedback[1]["recommendation"] = (
        "Maintain artifact-backed evidence for experimental sufficiency using "
        "research/iter_1/results/../../evaluation.json."
    )
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": feedback,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert any(
        "experimental_sufficiency" in issue
        and "research/iter_*/results/*.json" in issue
        for issue in issues
    )


def test_rejects_total_mismatch():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
    }
    evaluation["total"] = 39

    issues = validate_evaluation_consistency(evaluation)

    assert "does not equal score sum" in issues[0]


def test_rejects_missing_total():
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

    issues = validate_evaluation_consistency(evaluation)

    assert "evaluation.total is required" in issues


def test_rejects_verdict_threshold_mismatch():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "expected REVISE" in issues[0]


def test_rejects_accept_with_low_required_criterion_score():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 10,
            "experimental_sufficiency": 10,
            "novelty": 10,
            "narrative_coherence": 10,
            "goal_achievement": 1,
        },
        "total": 41,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "ACCEPT evaluation requires every criterion score >= 7" in issues[0]


def test_rejects_accept_with_required_actions():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "required_actions": ["Rerun the baseline comparison with leakage-safe splits."],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "ACCEPT evaluation must not include required_actions" in issues[0]


def test_rejects_accept_with_structured_required_actions():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "required_actions": [{
            "action": "Rerun the baseline comparison with leakage-safe splits.",
            "target": "baseline comparison",
        }],
        "feedback": _complete_feedback(8),
    }

    issues = validate_evaluation_consistency(evaluation)

    assert any("ACCEPT evaluation must not include required_actions" in issue for issue in issues)


def test_rejects_missing_required_score_criteria():
    evaluation = {
        "verdict": "REJECT",
        "scores": {"academic_rigor": 4},
        "total": 4,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "missing required criteria" in issues[0]


def test_rejects_unknown_score_criteria():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
            "extra_credit": 10,
        },
        "total": 50,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "unknown criteria" in issues[0]


def test_rejects_feedback_score_mismatch():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": [{
            "criterion": "experimental_sufficiency",
            "score": 6,
            "issue": "Baselines need attention.",
        }],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert any("does not match scores.experimental_sufficiency" in issue for issue in issues)


def test_rejects_feedback_score_outside_score_range():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": [{
            "criterion": "experimental_sufficiency",
            "score": 12,
            "issue": "Baselines need attention in research/final_paper.md.",
        }],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "evaluation.feedback[0].score must be between 1 and 10" in issues


def test_rejects_feedback_unknown_criterion():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": [{"criterion": "style", "score": 8}],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "evaluation.feedback[0].criterion is unknown: style" in issues
    assert any("must include a substantive issue" in issue for issue in issues)


def test_rejects_feedback_without_substantive_text():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": [{"criterion": "academic_rigor", "score": 8}],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "evaluation.feedback[0] must include a substantive issue, rationale, comment, or recommendation" in issues


def test_accepts_feedback_with_recommendation_text():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": _complete_feedback(8),
    }

    assert validate_evaluation_consistency(evaluation) == []


def test_rejects_feedback_without_all_score_criteria():
    evaluation = {
        "verdict": "ACCEPT",
        "scores": {
            "academic_rigor": 8,
            "experimental_sufficiency": 8,
            "novelty": 8,
            "narrative_coherence": 8,
            "goal_achievement": 8,
        },
        "total": 40,
        "feedback": [{
            "criterion": "academic_rigor",
            "score": 8,
            "recommendation": "Document the leakage audit assumptions in the final paper.",
        }],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "evaluation.feedback must cover every score criterion" in issues[-1]


def test_rejects_revise_without_required_actions():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": [],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "REVISE evaluation must include non-empty required_actions" in issues


def test_accepts_revise_with_actionable_required_actions():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": ["Add a leakage-safe error analysis phase over the held-out split."],
    }

    assert validate_evaluation_consistency(evaluation) == []


def test_accepts_revise_required_action_with_execute_verb():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": [
            "Execute Iteration 2 multi-dataset replication on three small regression datasets "
            "with leakage-safe splits and per-dataset MAE confidence intervals."
        ],
    }

    assert validate_evaluation_consistency(evaluation) == []


def test_accepts_revise_with_structured_actionable_required_actions():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": [{
            "action": "Add a leakage-safe error analysis phase.",
            "target": "held-out split residuals",
            "rationale": "The current result artifact lacks split-level error analysis.",
        }],
    }

    assert validate_evaluation_consistency(evaluation) == []


def test_rejects_vague_required_actions():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": ["Do more work", "Improve the paper"],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "REVISE evaluation must include non-empty required_actions" in issues


def test_rejects_required_actions_without_specific_research_detail():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": ["Run experiment"],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "REVISE evaluation must include non-empty required_actions" in issues


def test_rejects_required_action_with_only_generic_research_targets():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": ["Run baseline experiment."],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "REVISE evaluation must include non-empty required_actions" in issues


def test_rejects_mixed_actionable_and_vague_required_actions():
    evaluation = {
        "verdict": "REVISE",
        "scores": {
            "academic_rigor": 7,
            "experimental_sufficiency": 7,
            "novelty": 7,
            "narrative_coherence": 7,
            "goal_achievement": 7,
        },
        "total": 35,
        "required_actions": [
            "Add a leakage-safe error analysis phase over the held-out split.",
            "Improve the paper",
        ],
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "REVISE evaluation must include non-empty required_actions" in issues


def test_accepts_reject_with_concrete_required_action():
    evaluation = {
        "verdict": "REJECT",
        "scores": {
            "academic_rigor": 6,
            "experimental_sufficiency": 6,
            "novelty": 6,
            "narrative_coherence": 6,
            "goal_achievement": 6,
        },
        "total": 30,
        "required_actions": ["Reframe the leakage-safe held-out dataset split and rerun the seasonal naive baseline comparison."],
    }

    assert validate_evaluation_consistency(evaluation) == []


def test_rejects_reject_without_required_actions():
    evaluation = {
        "verdict": "REJECT",
        "scores": {
            "academic_rigor": 6,
            "experimental_sufficiency": 6,
            "novelty": 6,
            "narrative_coherence": 6,
            "goal_achievement": 6,
        },
        "total": 30,
    }

    issues = validate_evaluation_consistency(evaluation)

    assert "REJECT evaluation must include non-empty required_actions" in issues


def test_evaluation_contract_renders_review_ssot():
    text = render_evaluation_contract()

    assert "Professor Evaluation Contract" in text
    assert "tiny_lab.review" in text
    assert "`academic_rigor`" in text
    assert "ACCEPT" in text
    assert "required_actions" in text
    assert "ACCEPT` evaluations must include `feedback`" in text
    assert "cover every required score criterion" in text


def test_revision_artifact_must_address_previous_required_actions(tmp_path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": ["Add a leakage-safe error analysis phase over the held-out split."],
    }))
    artifact = {
        "goal": "Improve the model",
        "review_response": {
            "addressed_required_actions": [{
                "action": "Add another chart",
                "how_addressed": "Add a chart to the report",
            }]
        },
    }

    issues = validate_review_feedback_response(tmp_path, "IDEA_REFINE", artifact)

    assert "does not address previous required_actions" in issues[0]


def test_revision_artifact_accepts_addressed_required_actions(tmp_path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": ["Add a leakage-safe error analysis phase over the held-out split."],
    }))
    artifact = {
        "goal": "Improve the model",
        "review_response": {
            "addressed_required_actions": [{
                "action": "Add a leakage-safe error analysis phase over the held-out split.",
                "how_addressed": "Add a phase that audits leakage and error analysis on the held-out split.",
                "planned_change": "Add leakage audit and split-level residual diagnostics.",
            }]
        },
    }

    assert validate_review_feedback_response(tmp_path, "IDEA_REFINE", artifact) == []


def test_revision_artifact_accepts_structured_previous_required_actions(tmp_path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": [{
            "action": "Add a leakage-safe error analysis phase.",
            "target": "held-out split residuals",
            "rationale": "Current result artifacts lack split-level error analysis.",
        }],
    }))
    artifact = {
        "goal": "Improve the model",
        "review_response": {
            "addressed_required_actions": [{
                "action": "Add a leakage-safe error analysis phase over the held-out split residuals.",
                "how_addressed": "Add leakage audit and split-level residual diagnostics.",
            }]
        },
    }

    assert validate_review_feedback_response(tmp_path, "IDEA_REFINE", artifact) == []


def test_revision_artifact_accepts_intentionally_deferred_action_with_reason(tmp_path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": ["Add a leakage-safe error analysis phase over the held-out split."],
    }))
    artifact = {
        "goal": "Reframe the study around a dataset without held-out temporal labels.",
        "review_response": {
            "intentionally_deferred": [{
                "action": "Add a leakage-safe error analysis phase over the held-out split.",
                "reason": (
                    "This is no longer applicable because the revised dataset has no held-out "
                    "split labels; the replacement plan validates leakage with grouped CV."
                ),
            }]
        },
    }

    assert validate_review_feedback_response(tmp_path, "IDEA_REFINE", artifact) == []


def test_revision_artifact_rejects_deferred_action_without_substantive_reason(tmp_path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": ["Add a leakage-safe error analysis phase over the held-out split."],
    }))
    artifact = {
        "goal": "Reframe the study",
        "review_response": {
            "intentionally_deferred": [{
                "action": "Add a leakage-safe error analysis phase over the held-out split.",
                "reason": "Later.",
            }]
        },
    }

    issues = validate_review_feedback_response(tmp_path, "IDEA_REFINE", artifact)

    assert "does not address previous required_actions" in issues[0]


def test_reject_restart_artifact_requires_review_response(tmp_path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REJECT",
        "required_actions": ["Reframe the leakage-safe held-out dataset split and rerun the seasonal naive baseline comparison."],
    }))

    issues = validate_review_feedback_response(tmp_path, "SHAPE_FULL", {"objective": "Try again"})

    assert "must include review_response" in issues[0]
