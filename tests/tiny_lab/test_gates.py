"""Tests for shared completion gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tiny_lab.gates import (
    audit_final_artifacts,
    audit_iteration_completion,
    audit_research_completion,
    completion_artifact_quality_issue,
    completion_quality_issue,
    planned_iterations,
)
from tiny_lab.review import REQUIRED_SCORE_KEYS, RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA

PNG_SIGNATURE = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _evaluation(
    verdict: str = "ACCEPT",
    score: int = 8,
    result_artifact: str = "research/iter_1/results/phase_0.json",
) -> dict:
    evaluation = {
        "verdict": verdict,
        "scores": {
            "academic_rigor": score,
            "experimental_sufficiency": score,
            "novelty": score,
            "narrative_coherence": score,
            "goal_achievement": score,
        },
        "total": score * 5,
    }
    if verdict == "ACCEPT":
        evaluation["feedback"] = _complete_feedback(score, result_artifact=result_artifact)
    return evaluation


def _complete_feedback(
    score: int = 8,
    result_artifact: str = "research/iter_1/results/phase_0.json",
) -> list[dict]:
    return [
        {
            "criterion": criterion,
            "score": score,
            "recommendation": (
                f"Maintain artifact-backed evidence for {criterion.replace('_', ' ')} "
                f"using {_feedback_artifact_for(criterion, result_artifact)}."
            ),
        }
        for criterion in REQUIRED_SCORE_KEYS
    ]


def _feedback_artifact_for(criterion: str, result_artifact: str) -> str:
    if criterion in RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA:
        return result_artifact
    return "research/final_paper.md"


def _write_complete_final_paper(project_dir: Path, sentence: str = "") -> None:
    (project_dir / "research").mkdir(parents=True, exist_ok=True)
    default_result = project_dir / "research" / "iter_1" / "results" / "phase_0.json"
    default_uncertainty_sentence = ""
    if not sentence and default_result.exists():
        try:
            result_data = json.loads(default_result.read_text())
        except (OSError, json.JSONDecodeError):
            result_data = {}
        if isinstance(result_data, dict) and "mae_std" in result_data:
            default_uncertainty_sentence = (
                "The statistical uncertainty is reported in research/iter_1/results/phase_0.json. "
            )
    (project_dir / "research" / "final_paper.md").write_text(
        "# Final Paper\n\n"
        "## Abstract\n"
        "This paper summarizes a rigorous automated ML study. "
        f"{sentence}\n\n"
        "## Method\n"
        "The method describes split protocol, baselines, reproducibility metadata, "
        "leakage audit, feature importance, target achievement, and evaluation procedure.\n\n"
        "## Results\n"
        f"{default_uncertainty_sentence}"
        "The results discuss repeated splits, feature importance, target achievement, leakage audit, "
        "and failure cases.\n\n"
        "## Limitations\n"
        "The limitations document data quality, evaluation constraints, distribution shift, and implementation assumptions. "
        "Additional text pads the fixture so it resembles a complete paper rather than a stub. "
        * 3
    )


def _complete_result_discussion(path: str = "research/iter_1/results/phase_0.json") -> str:
    return (
        f"The result artifact {path} documents the baseline comparison, feature importance, "
        "statistical uncertainty, cross-validation fold evaluation protocol, error analysis, "
        "leakage audit, target achievement, and reproducibility metadata."
    )


def _write_complete_plan_and_result(
    project_dir: Path,
    *,
    iteration: int = 1,
    report_name: str = "phase_0",
    mae_mean: float = 0.42,
    include_target_flag: bool = True,
) -> None:
    idir = project_dir / "research" / f"iter_{iteration}"
    pdir = idir / "phases"
    rdir = idir / "results"
    pdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(exist_ok=True)
    script = pdir / "phase_0.py"
    script.write_text("print('phase complete')\n")
    script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()

    schema_properties = {
        "mae_mean": {"type": "number"},
        "mae_std": {"type": "number"},
        "baseline_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "baseline": {"type": "string"},
                    "mae_mean": {"type": "number"},
                },
            },
        },
        "improvement_over_baseline": {"type": "number"},
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
        "fold_count": {"type": "integer"},
        "per_fold_metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fold": {"type": "integer"},
                    "mae_mean": {"type": "number"},
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
        "leakage_found": {"type": "boolean"},
        "train_test_overlap": {"type": "integer"},
        "target_achieved": {"type": "boolean"},
        "random_seed": {"type": "integer"},
        "dataset_fingerprint": {"type": "string"},
        "split_id": {"type": "string"},
        "python_version": {"type": "string"},
        "script_path": {"type": "string"},
        "script_sha256": {"type": "string"},
    }
    required = [key for key in schema_properties if key != "target_achieved"]
    (idir / "research_plan.json").write_text(json.dumps({
        "name": "complete rigorous fixture",
        "metric": {"name": "mae", "direction": "minimize"},
        "success_criteria": "Beat baselines by at least 10% MAE with documented validity checks.",
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
            "why": "Compare baselines under leakage-safe splits.",
            "type": "script",
            "depends_on": [],
            "methodology": (
                "Run held-out split, seasonal naive, linear regression, ablation, "
                "cross-validation fold residual error analysis, and leakage audit."
            ),
            "expected_outputs": {
                "report": {
                    "path": f"research/iter_{iteration}/results/{report_name}.json",
                    "schema": {
                        "required": required,
                        "properties": schema_properties,
                    },
                }
            },
            "visualization": ["phase_0_error.png"],
            "status": "done",
        }],
    }))

    data = {
        "mae_mean": mae_mean,
        "mae_std": 0.03,
        "baseline_results": [
            {"name": "seasonal naive", "mae_mean": 0.58},
            {"name": "linear regression", "mae_mean": 0.49},
        ],
        "improvement_over_baseline": round(0.49 - mae_mean, 10),
        "feature_importance": [{"feature": "lag_1", "importance": 0.72}],
        "fold_count": 2,
        "per_fold_metrics": [
            {"fold": 0, "mae_mean": 0.43},
            {"fold": 1, "mae_mean": 0.41},
        ],
        "error_analysis": [{"slice": "peak_load", "mae_mean": 0.55}],
        "leakage_found": False,
        "train_test_overlap": 0,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": f"research/iter_{iteration}/phases/phase_0.py",
        "script_sha256": script_sha,
    }
    if include_target_flag:
        data["target_achieved"] = True
    (rdir / f"{report_name}.json").write_text(json.dumps(data))
    (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)


def test_plan_gate_rejects_weak_experimental_plan(tmp_path: Path):
    plan = {
        "name": "weak",
        "metric": {"name": "mae"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "depends_on": [],
            "status": "pending",
            "methodology": "train one model",
            "expected_outputs": {"report": {"path": "research/iter_1/results/phase_0.json", "schema": {"mae": {}}}},
            "visualization": ["phase_0_loss.png"],
        }],
    }

    issue = completion_quality_issue(tmp_path, "PLAN", plan, 1)

    assert issue is not None
    assert "research plan quality issues" in issue


def test_plan_gate_rejects_empty_phase_list(tmp_path: Path):
    issue = completion_quality_issue(tmp_path, "PLAN", {"name": "empty", "phases": []}, 1)

    assert issue is not None
    assert "plan must define at least one phase" in issue


def test_plan_gate_rejects_report_path_for_wrong_iteration(tmp_path: Path):
    plan = {
        "name": "wrong iteration path",
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
            "type": "script",
            "depends_on": [],
            "status": "pending",
            "why": "Compare baselines under leakage-safe splits.",
            "methodology": "Run held-out split, seasonal naive, linear regression, ablation, CV fold residual error analysis.",
            "expected_outputs": {
                "report": {
                    "path": "research/iter_2/results/phase_0.json",
                    "schema": {
                        "mae_mean": {},
                        "mae_std": {},
                        "fold_count": {},
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
            "visualization": ["phase_0_results.png"],
        }],
    }

    issue = completion_quality_issue(tmp_path, "PLAN", plan, 1)

    assert issue is not None
    assert "expected_outputs.report.path must be under research/iter_1/results/" in issue


def test_idea_refine_gate_requires_response_to_revise_actions(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": ["Rerun the baseline comparison with leakage-safe splits."],
    }))
    artifact = {
        "goal": "Improve the model",
        "inputs": [],
        "outputs": [],
        "metric": {"name": "mae"},
    }

    issue = completion_quality_issue(tmp_path, "IDEA_REFINE", artifact, 1)

    assert issue is not None
    assert "review feedback response issues" in issue


def test_idea_refine_gate_accepts_response_to_revise_actions(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
        "verdict": "REVISE",
        "required_actions": ["Rerun the baseline comparison with leakage-safe splits."],
    }))
    artifact = {
        "goal": "Improve the model",
        "inputs": [],
        "outputs": [],
        "metric": {"name": "mae"},
        "review_response": {
            "addressed_required_actions": [{
                "action": "Rerun the baseline comparison with leakage-safe splits.",
                "how_addressed": "Rerun baseline comparison after validating leakage-safe train/test splits.",
            }]
        },
    }

    assert completion_quality_issue(tmp_path, "IDEA_REFINE", artifact, 1) is None


def test_review_gate_rejects_inconsistent_evaluation(tmp_path: Path):
    evaluation = _evaluation(verdict="ACCEPT", score=7)

    issue = completion_quality_issue(tmp_path, "REVIEW", evaluation, 1)

    assert issue is not None
    assert "evaluation consistency issues" in issue


def test_review_gate_rejects_unsupported_claim_from_wrong_cited_file(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    _write_complete_plan_and_result(tmp_path, report_name="winner", mae_mean=0.31)
    (rdir / "baseline.json").write_text(json.dumps({"mae_mean": 0.42}))
    _write_complete_final_paper(
        tmp_path,
        "The model reports MAE = 0.31 (research/iter_1/results/baseline.json). "
        f"{_complete_result_discussion('research/iter_1/results/winner.json')} "
        "The primary error figure is research/iter_1/results/phase_0_error.png.",
    )

    issue = completion_quality_issue(
        tmp_path,
        "REVIEW",
        _evaluation(result_artifact="research/iter_1/results/winner.json"),
        1,
    )

    assert issue is not None
    assert "unsupported research claims" in issue


def test_review_gate_rejects_unsupported_target_achievement_claim(tmp_path: Path):
    _write_complete_plan_and_result(tmp_path, include_target_flag=False)
    result_path = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
    result_data = json.loads(result_path.read_text())
    result_data["success_criteria_met"] = "unknown"
    result_path.write_text(json.dumps(result_data))
    _write_complete_final_paper(
        tmp_path,
        "The final target was achieved (research/iter_1/results/phase_0.json). "
        f"{_complete_result_discussion()} "
        "The primary error figure is research/iter_1/results/phase_0_error.png.",
    )

    issue = completion_quality_issue(tmp_path, "REVIEW", _evaluation(), 1)

    assert issue is not None
    assert "evaluation consistency issues" in issue
    assert "evaluation.feedback cites invalid result JSON research artifacts" in issue


def test_review_gate_rejects_accept_when_target_flag_is_false(tmp_path: Path):
    _write_complete_plan_and_result(tmp_path)
    result_path = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
    result_data = json.loads(result_path.read_text())
    result_data["target_achieved"] = False
    result_path.write_text(json.dumps(result_data))
    _write_complete_final_paper(
        tmp_path,
        f"{_complete_result_discussion()} "
        "The primary error figure is research/iter_1/results/phase_0_error.png.",
    )
    evaluation = _evaluation()
    evaluation["summary"] = "The target achieved criterion was met."

    issue = completion_quality_issue(tmp_path, "REVIEW", evaluation, 1)

    assert issue is not None
    assert "contradicts result flags" in issue


def test_final_artifact_audit_reports_missing_paper_when_evaluation_exists(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "evaluation.json").write_text(json.dumps(_evaluation()))

    audit = audit_final_artifacts(tmp_path)

    assert audit.evaluation_exists is True
    assert audit.final_paper_exists is False
    assert audit.missing_final_paper_issue == "final_paper.md not found but evaluation.json exists"


def test_story_tell_artifact_gate_rejects_weak_final_paper(tmp_path: Path):
    final_paper = tmp_path / "research" / "final_paper.md"
    final_paper.parent.mkdir(parents=True)
    final_paper.write_text("# Paper\n\nToo short.")

    issue = completion_artifact_quality_issue(tmp_path, "STORY_TELL", final_paper, 1)

    assert issue is not None
    assert "final paper issues" in issue
    assert "too short" in issue


def test_iteration_completion_audit_reports_missing_plan(tmp_path: Path):
    (tmp_path / "research" / "iter_1").mkdir(parents=True)

    audit = audit_iteration_completion(tmp_path, 1)

    assert audit.plan_exists is False
    assert audit.issues() == ["research_plan.json is missing"]


def test_review_gate_rejects_accept_with_missing_plan(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    _write_complete_final_paper(tmp_path, _complete_result_discussion())

    issue = completion_quality_issue(tmp_path, "REVIEW", _evaluation(), 1)

    assert issue is not None
    assert "incomplete research artifacts" in issue
    assert "research_plan.json is missing" in issue


def test_research_completion_audit_includes_current_iteration_when_previous_plan_exists(tmp_path: Path):
    _write_complete_plan_and_result(tmp_path, iteration=1)

    issues = audit_research_completion(tmp_path, 2)

    assert any(issue == "iter_2: research_plan.json is missing" for issue in issues)


def test_planned_iterations_ignores_non_numeric_iteration_dirs(tmp_path: Path):
    (tmp_path / "research" / "iter_1").mkdir(parents=True)
    (tmp_path / "research" / "iter_x").mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / "research_plan.json").write_text("{}")
    (tmp_path / "research" / "iter_x" / "research_plan.json").write_text("{}")

    assert planned_iterations(tmp_path) == [1]


def test_iteration_completion_audit_reports_unreadable_plan(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / "research_plan.json").write_text("{not valid json")

    audit = audit_iteration_completion(tmp_path, 1)

    assert audit.plan_exists is True
    assert audit.load_issue is not None
    assert "could not audit plan" in audit.load_issue


def test_review_gate_rejects_accept_with_unreadable_plan(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    rdir = idir / "results"
    rdir.mkdir(parents=True)
    (idir / "research_plan.json").write_text("{not valid json")
    (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
    _write_complete_final_paper(tmp_path, _complete_result_discussion())

    issue = completion_quality_issue(tmp_path, "REVIEW", _evaluation(), 1)

    assert issue is not None
    assert "incomplete research artifacts" in issue
    assert "could not audit plan" in issue
