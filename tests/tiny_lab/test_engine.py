"""Integration tests for the engine."""
from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from tiny_lab.engine import Engine
from tiny_lab.handlers.defaults import research_registry
from tiny_lab.state import load_state, save_state, set_state, LoopState
from tiny_lab.paths import workflow_path, iter_dir, results_dir, phases_dir, iterations_path
from tiny_lab.review import REQUIRED_SCORE_KEYS, RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA

PNG_SIGNATURE = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Set up a minimal project with ml-experiment preset."""
    rd = tmp_path / "research"
    rd.mkdir()
    (tmp_path / "shared").mkdir()

    preset = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "ml-experiment.json"
    shutil.copy2(preset, rd / ".workflow.json")

    return tmp_path


def make_engine(project_dir: Path) -> Engine:
    return Engine(project_dir, research_registry())


def complete_review_feedback(score: int = 8) -> list[dict]:
    return [
        {
            "criterion": criterion,
            "score": score,
            "recommendation": (
                f"Maintain artifact-backed evidence for {criterion.replace('_', ' ')} "
                f"using {_feedback_artifact_for(criterion)}."
            ),
        }
        for criterion in REQUIRED_SCORE_KEYS
    ]


def _feedback_artifact_for(criterion: str) -> str:
    if criterion in RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA:
        return "research/iter_1/results/phase_0.json"
    return "research/final_paper.md"


def write_complete_final_paper(project_dir: Path, extra_result_sentence: str = "") -> None:
    default_result = project_dir / "research" / "iter_1" / "results" / "phase_0.json"
    default_uncertainty_sentence = ""
    if not extra_result_sentence and default_result.exists():
        try:
            result_data = json.loads(default_result.read_text())
        except (OSError, json.JSONDecodeError):
            result_data = {}
        if isinstance(result_data, dict) and "mae_std" in result_data:
            default_uncertainty_sentence = (
                "The statistical uncertainty is reported in research/iter_1/results/phase_0.json. "
            )
    text = (
        "# Final Paper\n\n"
        "## Abstract\n"
        "This paper summarizes a rigorous automated ML study with traceable artifacts, "
        "controlled comparisons, and explicit limitations. "
        f"{extra_result_sentence}\n\n"
        "## Related Work\n"
        "Prior work establishes the baseline context for this study.\n\n"
        "## Method\n"
        "The method section describes the data split protocol, baseline comparisons, "
        "modeling assumptions, reproducibility metadata, leakage audit, feature importance, "
        "target achievement, and evaluation procedure. "
        "It is intentionally verbose enough for another researcher to rerun the study. "
        "\n\n## Results\n"
        "The results section reports only artifact-backed findings and avoids unsupported "
        f"claims. {default_uncertainty_sentence}"
        "It discusses repeated splits, feature importance, target achievement, and failure cases in detail. "
        "\n\n## Limitations\n"
        "The limitations section documents data quality, evaluation constraints, possible "
        "distribution shift, and implementation assumptions. "
        "Additional text pads the fixture so it resembles a complete paper rather than a stub. "
        * 3
    )
    (project_dir / "research" / "final_paper.md").write_text(text)


def write_complete_plan_and_result(
    project_dir: Path,
    *,
    iteration: int = 1,
    phase_id: str = "phase_0",
    mae_mean: float = 0.42,
) -> None:
    idir = iter_dir(project_dir, iteration)
    idir.mkdir(parents=True, exist_ok=True)
    pdir = phases_dir(project_dir, iteration)
    pdir.mkdir(exist_ok=True)
    rdir = results_dir(project_dir, iteration)
    rdir.mkdir(exist_ok=True)

    script_path = pdir / f"{phase_id}.py"
    script_path.write_text("print('phase complete')\n")
    script_sha = "sha256:" + hashlib.sha256(script_path.read_bytes()).hexdigest()

    (idir / "research_plan.json").write_text(json.dumps({
        "name": "complete rigorous fixture",
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
            "id": phase_id,
            "why": "Compare baselines under leakage-safe splits.",
            "type": "script",
            "depends_on": [],
            "methodology": (
                "Run held-out split, seasonal naive, linear regression, ablation, "
                "cross-validation fold residual error analysis, and leakage audit."
            ),
            "expected_outputs": {
                "report": {
                    "path": f"research/iter_{iteration}/results/{phase_id}.json",
                    "schema": {
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
                    },
                }
            },
            "visualization": [f"{phase_id}_error.png"],
            "status": "done",
        }],
    }))

    (rdir / f"{phase_id}.json").write_text(json.dumps({
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
        "target_achieved": True,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.11",
        "script_path": f"research/iter_{iteration}/phases/{phase_id}.py",
        "script_sha256": script_sha,
    }))
    (rdir / f"{phase_id}_error.png").write_bytes(PNG_SIGNATURE)


def complete_result_citation(iteration: int = 1, phase_id: str = "phase_0") -> str:
    return (
        f"The primary result artifact research/iter_{iteration}/results/{phase_id}.json documents "
        "the baseline comparison, statistical uncertainty, feature importance, cross-validation fold evaluation protocol, "
        "error analysis, leakage audit, target achievement, and reproducibility metadata, "
        f"and the primary error figure is research/iter_{iteration}/results/{phase_id}_error.png."
    )


class TestEngineInit:
    def test_creates_iter_1(self, project_dir):
        engine = make_engine(project_dir)
        engine._init()
        assert (iter_dir(project_dir, 1)).exists()
        ls = load_state(project_dir)
        assert ls.state == "SHAPE_FULL"
        assert ls.current_iteration == 1

    def test_resume_from_existing_state(self, project_dir):
        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        (iter_dir(project_dir, 1)).mkdir(parents=True)
        engine = make_engine(project_dir)
        engine._init()
        ls = load_state(project_dir)
        assert ls.state == "PLAN"  # didn't reset

    def test_unknown_state_does_not_mark_workflow_done(self, project_dir):
        save_state(project_dir, LoopState(state="MISSING_STATE", current_iteration=1))
        (iter_dir(project_dir, 1)).mkdir(parents=True)
        engine = make_engine(project_dir)

        outcome = engine.step_once()
        ls = load_state(project_dir)

        assert outcome.executed is False
        assert outcome.state_before == "MISSING_STATE"
        assert outcome.state_after == "MISSING_STATE"
        assert "missing from workflow" in outcome.message
        assert ls.state == "MISSING_STATE"

    def test_done_not_resumable(self, project_dir):
        save_state(project_dir, LoopState(state="DONE", resumable=False))
        engine = make_engine(project_dir)
        engine._init()
        # Should return without changing state

    def test_run_returns_false_when_error_stops_loop(self, tmp_path, monkeypatch):
        from tiny_lab.errors import StateError
        from tiny_lab.handlers import HandlerRegistry

        class FailingHandler:
            def execute(self, spec, ls, ctx):
                raise StateError("boom")

        monkeypatch.chdir(tmp_path)
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "autonomy": {"circuit_breaker": {"max_consecutive_failures": 3}},
            "states": [{
                "id": "FAIL",
                "type": "process",
                "error": {"max_retries": 0, "on_exhaust": "stop"},
            }],
        }))
        registry = HandlerRegistry()
        registry.on_type("process", FailingHandler())

        ok = Engine(tmp_path, registry).run()
        ls = load_state(tmp_path)

        assert ok is False
        assert ls.state == "DONE"
        assert ls.consecutive_failures == 1

    def test_run_max_steps_pauses_after_limited_state_count(self, tmp_path, monkeypatch):
        from tiny_lab.handlers import HandlerRegistry, StateResult

        class CountingHandler:
            def __init__(self):
                self.count = 0

            def execute(self, spec, ls, ctx):
                self.count += 1
                return StateResult()

        monkeypatch.chdir(tmp_path)
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [
                {"id": "A", "type": "process", "next": "B"},
                {"id": "B", "type": "process", "next": "DONE"},
            ],
        }))
        handler = CountingHandler()
        registry = HandlerRegistry()
        registry.on_type("process", handler)

        ok = Engine(tmp_path, registry).run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert handler.count == 1
        assert ls.state == "B"

    def test_run_max_iterations_routes_to_story_without_executing_next_iteration_state(self, tmp_path, monkeypatch):
        from tiny_lab.handlers import HandlerRegistry, StateResult

        executed: list[str] = []

        class RecordingHandler:
            def execute(self, spec, ls, ctx):
                executed.append(ls.state)
                return StateResult(transition="DONE")

        monkeypatch.chdir(tmp_path)
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "autonomy": {"max_iterations": 1},
            "states": [
                {"id": "IDEA_REFINE", "type": "process", "next": "DONE"},
                {"id": "STORY_TELL", "type": "process", "next": "DONE"},
            ],
        }))
        save_state(tmp_path, LoopState(state="IDEA_REFINE", current_iteration=2))
        registry = HandlerRegistry()
        registry.on_type("process", RecordingHandler())

        ok = Engine(tmp_path, registry).run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert executed == ["STORY_TELL"]
        assert ls.state == "DONE"

    @pytest.mark.parametrize("current_iteration", [1, 2])
    @pytest.mark.parametrize("verdict,target", [("REVISE", "IDEA_REFINE"), ("REJECT", "SHAPE_FULL")])
    def test_run_max_iterations_stops_after_final_review_without_revision_loop(
        self,
        tmp_path,
        monkeypatch,
        verdict,
        target,
        current_iteration,
    ):
        monkeypatch.chdir(tmp_path)
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "autonomy": {"max_iterations": 1},
            "states": [
                {
                    "id": "REVIEW_DONE",
                    "type": "process",
                    "condition": {"source": "evaluation.json", "field": "verdict"},
                    "next": {"ACCEPT": "DONE", verdict: target},
                },
                {"id": target, "type": "process", "next": "DONE"},
            ],
        }))
        (rd / "evaluation.json").write_text(json.dumps({"verdict": verdict}))
        save_state(
            tmp_path,
            LoopState(state="REVIEW_DONE", current_iteration=current_iteration, session_id="review-session"),
        )

        ok = Engine(tmp_path, research_registry()).run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert ls.state == "DONE"
        assert ls.resumable is False
        assert ls.session_id is None

    def test_ai_session_uses_workflow_state_timeout(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        seen: dict[str, float] = {}

        class RecordingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                seen["timeout"] = kwargs["timeout"]
                (tmp_path / "research" / "constraints.json").write_text(json.dumps({
                    "objective": "Compare tabular regressors.",
                    "goal": {"success_criteria": "Report repeated-split MAE."},
                    "invariants": ["No leakage."],
                }))
                return BackendResult(exit_code=0, stdout="{}", stderr="", session_id="session")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", RecordingBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "timeout_seconds": 7,
                "completion": {"artifact": "research/constraints.json"},
                "next": "DONE",
            }],
        }))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry).run(max_steps=1)

        assert ok is True
        assert seen["timeout"] == 7.0

    def test_ai_session_timeout_override_takes_precedence(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        seen: dict[str, float] = {}

        class RecordingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                seen["timeout"] = kwargs["timeout"]
                (tmp_path / "research" / "constraints.json").write_text(json.dumps({
                    "objective": "Compare tabular regressors.",
                    "goal": {"success_criteria": "Report repeated-split MAE."},
                    "invariants": ["No leakage."],
                }))
                return BackendResult(exit_code=0, stdout="{}", stderr="", session_id="session")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", RecordingBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "timeout_seconds": 7,
                "completion": {"artifact": "research/constraints.json"},
                "next": "DONE",
            }],
        }))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry, backend_timeout_seconds=2).run(max_steps=1)

        assert ok is True
        assert seen["timeout"] == 2.0

    def test_ai_session_advances_existing_completion_before_backend_invocation(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("valid existing artifacts should advance before backend invocation")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / "constraints.json").write_text(json.dumps({
            "objective": "Compare tabular regressors.",
            "goal": {"success_criteria": "Report repeated-split MAE."},
            "invariants": ["No leakage."],
        }))
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "completion": {"artifact": "research/constraints.json"},
                "next": "DONE",
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry).run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert ls.state == "DONE"

    def test_ai_session_advances_existing_phase_script_with_shared_resolver(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("existing phase script should advance before backend invocation")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        write_complete_plan_and_result(project_dir, phase_id="p1")
        save_state(project_dir, LoopState(state="PHASE_CODE", current_iteration=1, current_phase_id="p1"))

        ok = make_engine(project_dir).run(max_steps=1)
        ls = load_state(project_dir)

        assert ok is True
        assert ls.state == "PHASE_RUN"

    def test_phase_code_retry_does_not_auto_advance_stale_script(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult

        called = {"backend": False}

        class RecordingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                called["backend"] = True
                return BackendResult(exit_code=0, stdout="{}", stderr="", session_id=None)

        monkeypatch.setitem(base._REGISTRY, "claude", RecordingBackend())
        write_complete_plan_and_result(project_dir, phase_id="p1")
        save_state(
            project_dir,
            LoopState(
                state="PHASE_CODE",
                current_iteration=1,
                current_phase_id="p1",
                phase_retries=1,
            ),
        )

        ok = make_engine(project_dir).run(max_steps=1)
        ls = load_state(project_dir)

        assert ok is True
        assert called["backend"] is True
        assert ls.state == "PHASE_RUN"

    def test_ai_session_repairs_existing_invalid_completion_before_backend_invocation(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult

        write_complete_plan_and_result(project_dir)
        (project_dir / "research" / "final_paper.md").write_text("too short")
        save_state(project_dir, LoopState(state="STORY_TELL", current_iteration=1))

        calls = {"count": 0}

        class RecordingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                calls["count"] += 1
                if calls["count"] > 1:
                    raise AssertionError("repair should advance before the main backend invocation")
                write_complete_final_paper(project_dir, complete_result_citation())
                return BackendResult(exit_code=0, stdout="", stderr="", session_id=None)

        monkeypatch.setitem(base._REGISTRY, "claude", RecordingBackend())

        ok = make_engine(project_dir).run(max_steps=1)
        ls = load_state(project_dir)

        assert ok is True
        assert ls.state == "REVIEW"
        assert calls["count"] == 1

    def test_paper_draft_writes_deterministic_artifact_before_backend_invocation(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("artifact-backed paper draft should not need backend")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        write_complete_plan_and_result(project_dir)
        save_state(project_dir, LoopState(state="PAPER_DRAFT", current_iteration=1))

        ok = make_engine(project_dir).run(max_steps=1)
        ls = load_state(project_dir)
        draft = project_dir / "research" / "iter_1" / "paper_draft.md"

        assert ok is True
        assert ls.state == "REFLECT"
        assert "research/iter_1/results/phase_0.json" in draft.read_text()

    def test_reflect_writes_deterministic_seed_until_max_iteration(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("artifact-backed reflection should not need backend")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        write_complete_plan_and_result(project_dir)
        (project_dir / "research" / "iter_1" / "paper_draft.md").write_text("draft")
        save_state(project_dir, LoopState(state="REFLECT", current_iteration=1))
        engine = make_engine(project_dir)
        engine.workflow.autonomy.max_iterations = 2

        ok = engine.run(max_steps=1)
        ls = load_state(project_dir)
        reflect = json.loads((project_dir / "research" / "iter_1" / "reflect.json").read_text())

        assert ok is True
        assert ls.state == "SHAPE_SEED"
        assert reflect["decision"] == "idea_mutation"
        assert len(reflect["idea_portfolio"]) >= 3
        assert reflect["selected_direction"]["direction"] == reflect["future_iteration_seeds"][0]["direction"]
        assert reflect["future_iteration_seeds"][0]["status"] == "promote_next"

    def test_reflect_writes_done_when_max_iteration_reached(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("artifact-backed reflection should not need backend")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        write_complete_plan_and_result(project_dir, iteration=2)
        (project_dir / "research" / "iter_2" / "paper_draft.md").write_text("draft")
        save_state(project_dir, LoopState(state="REFLECT", current_iteration=2))
        engine = make_engine(project_dir)
        engine.workflow.autonomy.max_iterations = 2

        ok = engine.run(max_steps=1)
        reflect = json.loads((project_dir / "research" / "iter_2" / "reflect.json").read_text())

        assert ok is True
        assert reflect["decision"] == "done"
        assert reflect["future_iteration_seeds"] == []

    def test_story_tell_and_review_can_close_from_deterministic_audits(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base
        from tiny_lab.gates import audit_final_artifacts

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("audited final artifacts should not need backend")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        write_complete_plan_and_result(project_dir)
        save_state(project_dir, LoopState(state="STORY_TELL", current_iteration=1))

        engine = make_engine(project_dir)
        ok = engine.run(max_steps=2)
        ls = load_state(project_dir)
        evaluation = json.loads((project_dir / "research" / "evaluation.json").read_text())

        assert ok is True
        assert ls.state == "REVIEW_DONE"
        assert evaluation["verdict"] == "ACCEPT"
        assert audit_final_artifacts(project_dir, evaluation=evaluation, reference_iterations=(1,)).paper_issues == ()

    def test_ai_session_writes_reference_verification_sidecar_before_advancing(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        class ReferenceWritingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                idir = tmp_path / "research" / "iter_1"
                idir.mkdir(parents=True, exist_ok=True)
                (idir / ".domain_research.json").write_text(json.dumps({
                    "domain_type": "tabular_regression",
                    "sota_models": ["RandomForestRegressor"],
                    "references": [{
                        "title": "Random Forests",
                        "doi": "10.1023/A:1010933404324",
                    }],
                }))
                return BackendResult(exit_code=0, stdout="{}", stderr="", session_id="session")

        calls: list[Path] = []

        def fake_verify_file(path):
            calls.append(path)
            return SimpleNamespace(total=1)

        def fake_write_verification(path, result):
            out = path.parent / (path.stem + ".ref_verification.json")
            out.write_text(json.dumps({
                "source_file": path.relative_to(tmp_path).as_posix(),
                "summary": {"total": result.total, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
                "refs": [],
            }))
            return out

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", ReferenceWritingBackend())
        monkeypatch.setattr("tiny_lab.refs.verify_file", fake_verify_file)
        monkeypatch.setattr("tiny_lab.refs.write_verification", fake_write_verification)
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "DOMAIN_RESEARCH",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/iter_1/.domain_research.json",
                    "required_fields": ["domain_type", "sota_models", "references"],
                },
                "next": "DONE",
            }],
        }))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry).run(max_steps=1)

        assert ok is True
        assert calls == [tmp_path / "research" / "iter_1" / ".domain_research.json"]
        assert (tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json").exists()

    def test_backend_unavailable_stops_without_consuming_retries(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        class UnavailableBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                return BackendResult(
                    exit_code=1,
                    stdout=json.dumps({
                        "is_error": True,
                        "result": "Not logged in · Please run /login",
                        "session_id": "error-session",
                    }),
                    stderr="",
                    session_id="error-session",
                )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", UnavailableBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "completion": {"artifact": "research/constraints.json"},
                "error": {"max_retries": 5, "on_exhaust": "stop"},
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry).run()
        ls = load_state(tmp_path)

        assert ok is False
        assert ls.state == "SHAPE_FULL"
        assert ls.consecutive_failures == 0
        assert ls.phase_retries == 0
        assert ls.session_id is None

    def test_backend_usage_limit_stops_without_marking_done(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        class UsageLimitedBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                return BackendResult(
                    exit_code=1,
                    stdout=json.dumps({
                        "is_error": True,
                        "result": "You're out of extra usage · resets 2:40am (Asia/Seoul)",
                    }),
                    stderr="",
                    session_id=None,
                )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", UsageLimitedBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "HYPOTHESIS_UPDATE",
                "type": "ai_session",
                "completion": {"artifact": "research/iter_1/phases/.hypothesis_log.json"},
                "error": {"max_retries": 3, "on_exhaust": "stop"},
            }],
        }))
        save_state(tmp_path, LoopState(state="HYPOTHESIS_UPDATE", current_iteration=1, phase_retries=2))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry).run()
        ls = load_state(tmp_path)

        assert ok is False
        assert ls.state == "HYPOTHESIS_UPDATE"
        assert ls.consecutive_failures == 0
        assert ls.phase_retries == 2

    def test_ai_session_retries_timeout_with_accelerated_prompt(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        prompts: list[str] = []

        class TimeoutThenWritingBackend:
            name = "codex"

            def invoke(self, prompt, *args, **kwargs):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return BackendResult(
                        exit_code=124,
                        stdout="",
                        stderr="Backend command timed out after 2s: codex",
                        session_id=None,
                    )
                (tmp_path / "research" / "constraints.json").write_text(json.dumps({
                    "objective": "Compare tabular regressors.",
                    "goal": {"success_criteria": "Report repeated-split MAE."},
                    "invariants": ["No leakage."],
                }))
                return BackendResult(exit_code=0, stdout="", stderr="", session_id=None)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "codex", TimeoutThenWritingBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "completion": {"artifact": "research/constraints.json"},
                "next": "DONE",
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry, engine="codex", backend_timeout_seconds=2).run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert ls.state == "DONE"
        assert len(prompts) == 2
        assert "Accelerated retry instructions" in prompts[1]
        assert "Think faster" in prompts[1]

    def test_ai_session_retries_missing_artifact_with_accelerated_prompt(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        prompts: list[str] = []

        class EmptyThenWritingBackend:
            name = "claude"

            def invoke(self, prompt, *args, **kwargs):
                prompts.append(prompt)
                if len(prompts) == 2:
                    (tmp_path / "research" / "constraints.json").write_text(json.dumps({
                        "objective": "Compare tabular regressors.",
                        "goal": {"success_criteria": "Report repeated-split MAE."},
                        "invariants": ["No leakage."],
                    }))
                return BackendResult(exit_code=0, stdout="", stderr="", session_id=None)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", EmptyThenWritingBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "completion": {"artifact": "research/constraints.json"},
                "next": "DONE",
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry).run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert ls.state == "DONE"
        assert len(prompts) == 2
        assert "artifact file not found" in prompts[1]
        assert "Think faster" in prompts[1]

    def test_ai_session_uses_accelerated_prompt_after_logged_previous_timeout(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        prompts: list[str] = []

        class WritingBackend:
            name = "codex"

            def invoke(self, prompt, *args, **kwargs):
                prompts.append(prompt)
                (tmp_path / "research" / "constraints.json").write_text(json.dumps({
                    "objective": "Compare tabular regressors.",
                    "goal": {"success_criteria": "Report repeated-split MAE."},
                    "invariants": ["No leakage."],
                }))
                return BackendResult(exit_code=0, stdout="", stderr="", session_id=None)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "codex", WritingBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / "loop.log").write_text(
            "2026-05-05 11:45:07 ENGINE: entering SHAPE_FULL (type=ai_session, iter=1)\n"
            "2026-05-05 12:00:14 ENGINE: codex session finished (exit=124)\n"
            "2026-05-05 12:00:14 ENGINE: backend error: Backend command timed out after 900s: codex\n"
            "2026-05-05 12:00:14 ENGINE: backend unavailable in SHAPE_FULL: codex backend is unavailable\n"
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "completion": {"artifact": "research/constraints.json"},
                "next": "DONE",
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        ok = Engine(tmp_path, registry, engine="codex").run(max_steps=1)
        ls = load_state(tmp_path)

        assert ok is True
        assert ls.state == "DONE"
        assert len(prompts) == 1
        assert "Accelerated retry instructions" in prompts[0]
        assert "previous backend failure" in (rd / "loop.log").read_text()

    def test_logged_previous_backend_failure_does_not_leak_across_states(self, tmp_path):
        from tiny_lab.handlers.ai_session import _logged_previous_backend_failure_reason

        rd = tmp_path / "research"
        rd.mkdir()
        (rd / "loop.log").write_text(
            "2026-05-05 11:34:51 ENGINE: entering PHASE_CODE (type=ai_session, iter=1)\n"
            "2026-05-05 11:34:52 ENGINE: advanced PHASE_CODE → PHASE_RUN\n"
            "2026-05-05 11:45:07 ENGINE: entering HYPOTHESIS_UPDATE (type=ai_session, iter=1)\n"
            "2026-05-05 12:00:14 ENGINE: backend error: Backend command timed out after 900s: codex\n"
            "2026-05-05 12:00:14 ENGINE: backend unavailable in HYPOTHESIS_UPDATE: codex backend is unavailable\n"
            "2026-05-05 12:11:56 ENGINE: entering PHASE_CODE (type=ai_session, iter=1)\n"
        )

        assert _logged_previous_backend_failure_reason(tmp_path, "PHASE_CODE") == ""

    def test_step_once_reports_backend_unavailable_as_failed_outcome(self, tmp_path, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers import HandlerRegistry
        from tiny_lab.handlers.ai_session import AiSessionHandler

        class UnavailableBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                return BackendResult(
                    exit_code=1,
                    stdout=json.dumps({
                        "is_error": True,
                        "result": "Not logged in · Please run /login",
                    }),
                    stderr="",
                    session_id=None,
                )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(base._REGISTRY, "claude", UnavailableBackend())
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "completion": {"artifact": "research/constraints.json"},
                "error": {"max_retries": 5, "on_exhaust": "stop"},
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("ai_session", AiSessionHandler())

        outcome = Engine(tmp_path, registry).step_once(run_ai=True)
        ls = load_state(tmp_path)

        assert outcome.executed is False
        assert outcome.state_before == "SHAPE_FULL"
        assert outcome.state_after == "SHAPE_FULL"
        assert "backend is unavailable" in outcome.message
        assert ls.consecutive_failures == 0

    def test_step_once_reports_retry_exhaustion_as_failed_outcome(self, tmp_path, monkeypatch):
        from tiny_lab.errors import StateError
        from tiny_lab.handlers import HandlerRegistry

        class FailingHandler:
            def execute(self, spec, ls, ctx):
                raise StateError("boom")

        monkeypatch.chdir(tmp_path)
        rd = tmp_path / "research"
        rd.mkdir()
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "FAIL",
                "type": "process",
                "error": {"max_retries": 0, "on_exhaust": "stop"},
            }],
        }))
        save_state(tmp_path, LoopState(state="FAIL", current_iteration=1))
        registry = HandlerRegistry()
        registry.on_type("process", FailingHandler())

        outcome = Engine(tmp_path, registry).step_once()
        ls = load_state(tmp_path)

        assert outcome.executed is False
        assert outcome.state_before == "FAIL"
        assert outcome.state_after == "DONE"
        assert outcome.message == "FAIL failed: boom"
        assert ls.consecutive_failures == 1


class TestCheckpointAutonomous:
    def test_auto_approves_in_autonomous_mode(self, project_dir):
        """Non-mandatory CHECKPOINT auto-approves in autonomous mode."""
        save_state(project_dir, LoopState(state="CHECKPOINT", current_iteration=1))
        (iter_dir(project_dir, 1)).mkdir(parents=True)
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("CHECKPOINT")
        ls = load_state(project_dir)

        from tiny_lab.handlers.checkpoint import CheckpointHandler
        handler = CheckpointHandler()
        result = handler.execute(spec, ls, engine.ctx)

        assert result.transition == "PHASE_SELECT"

    def test_checkpoint_reads_intervention(self, project_dir):
        """CHECKPOINT reads intervention file and transitions accordingly."""
        (iter_dir(project_dir, 1)).mkdir(parents=True)
        save_state(project_dir, LoopState(state="CHECKPOINT", current_iteration=1))

        # Pre-write intervention so it doesn't hang
        from tiny_lab.paths import intervention_path
        ipath = intervention_path(project_dir)
        ipath.parent.mkdir(parents=True, exist_ok=True)
        ipath.write_text(json.dumps({"action": "approve"}))

        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("CHECKPOINT")

        ls = load_state(project_dir)
        from tiny_lab.handlers.checkpoint import CheckpointHandler
        handler = CheckpointHandler()
        result = handler.execute(spec, ls, engine.ctx)

        assert result.transition == "PHASE_SELECT"


class TestPhaseSelect:
    def test_selects_pending_phase(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        phases_dir(project_dir, 1).mkdir(exist_ok=True)
        results_dir(project_dir, 1).mkdir(exist_ok=True)

        plan = {
            "name": "test",
            "phases": [
                {"id": "phase_0", "status": "pending", "name": "prep", "depends_on": [], "type": "script"},
            ],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_SELECT", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_SELECT")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseSelectHandler
        handler = PhaseSelectHandler()
        result = handler.execute(spec, ls, engine.ctx)

        assert result.state_overrides.get("current_phase_id") == "phase_0"

    def test_no_pending_phases(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        phases_dir(project_dir, 1).mkdir(exist_ok=True)
        results_dir(project_dir, 1).mkdir(exist_ok=True)

        plan = {
            "name": "test",
            "phases": [{"id": "phase_0", "status": "done", "depends_on": []}],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_SELECT", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_SELECT")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseSelectHandler
        handler = PhaseSelectHandler()
        result = handler.execute(spec, ls, engine.ctx)

        assert result.state_overrides.get("current_phase_id") is None


class TestPhaseRunScript:
    def test_runs_script(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)

        script = pdir / "phase_0_test.py"
        script.write_text(
            'import json, os\n'
            'from pathlib import Path\n'
            'rdir = Path(os.environ["TINYLAB_RESULTS_DIR"])\n'
            'rdir.mkdir(parents=True, exist_ok=True)\n'
            '(rdir / "phase_0.json").write_text(json.dumps({"result": 42}))\n'
        )

        plan = {
            "name": "test",
            "phases": [{"id": "phase_0", "status": "running", "name": "test", "depends_on": [], "type": "script"}],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        handler.execute(spec, ls, engine.ctx)

        assert (rdir / "phase_0.json").exists()
        data = json.loads((rdir / "phase_0.json").read_text())
        assert data["result"] == 42
        assert data["script_path"] == "research/iter_1/phases/phase_0_test.py"
        expected_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
        assert data["script_sha256"] == expected_sha

    def test_rejects_unknown_phase_type(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        script = pdir / "phase_0_test.py"
        script.write_text("raise SystemExit('should not run')\n")
        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "name": "bad",
                "depends_on": [],
                "type": "notebook",
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        with pytest.raises(StateError, match="Unknown phase type"):
            handler.execute(spec, ls, engine.ctx)

    def test_runs_script_stamps_nested_schema_provenance(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)

        script = pdir / "phase_0_nested.py"
        script.write_text(
            'import json, os\n'
            'from pathlib import Path\n'
            'rdir = Path(os.environ["TINYLAB_RESULTS_DIR"])\n'
            'rdir.mkdir(parents=True, exist_ok=True)\n'
            '(rdir / "phase_0.json").write_text(json.dumps({"result": 42, "run_metadata": {}}))\n'
        )

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "name": "nested",
                "depends_on": [],
                "type": "script",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "result": {"type": "number"},
                            "run_metadata": {
                                "type": "object",
                                "properties": {
                                    "script_path": {"type": "string"},
                                    "script_sha256": {"type": "string"},
                                },
                            },
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        handler.execute(spec, ls, engine.ctx)

        data = json.loads((rdir / "phase_0.json").read_text())
        expected_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
        assert data["run_metadata"]["script_path"] == "research/iter_1/phases/phase_0_nested.py"
        assert data["run_metadata"]["script_sha256"] == expected_sha
        assert "script_path" not in data
        assert "script_sha256" not in data

    def test_runs_unique_python_script_ignoring_non_python_artifacts(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)

        (pdir / "phase_0_notes.txt").write_text("not executable\n")
        script = pdir / "phase_0_train.py"
        script.write_text(
            'import json, os\n'
            'from pathlib import Path\n'
            'rdir = Path(os.environ["TINYLAB_RESULTS_DIR"])\n'
            '(rdir / "phase_0.json").write_text(json.dumps({"result": 42}))\n'
        )
        plan = {
            "name": "test",
            "phases": [{"id": "phase_0", "status": "running", "name": "test", "depends_on": [], "type": "script"}],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        handler.execute(spec, ls, engine.ctx)

        data = json.loads((rdir / "phase_0.json").read_text())
        assert data["script_path"] == "research/iter_1/phases/phase_0_train.py"

    def test_rejects_ambiguous_phase_scripts(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        (pdir / "phase_0_train.py").write_text("print('train')\n")
        (pdir / "phase_0_eval.py").write_text("print('eval')\n")
        plan = {
            "name": "test",
            "phases": [{"id": "phase_0", "status": "running", "name": "test", "depends_on": [], "type": "script"}],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        with pytest.raises(StateError, match="Multiple Python scripts found"):
            handler.execute(spec, ls, engine.ctx)

    def test_does_not_match_phase_id_as_substring(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        (pdir / "phase_10_train.py").write_text("print('wrong phase')\n")
        plan = {
            "name": "test",
            "phases": [{"id": "phase_1", "status": "running", "name": "test", "depends_on": [], "type": "script"}],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_1"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        with pytest.raises(StateError, match="No Python script found for phase phase_1"):
            handler.execute(spec, ls, engine.ctx)

    def test_runs_script_stamps_schema_provenance_fields(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)

        script = pdir / "phase_0_test.py"
        script.write_text(
            'import json, os\n'
            'from pathlib import Path\n'
            'rdir = Path(os.environ["TINYLAB_RESULTS_DIR"])\n'
            '(rdir / "phase_0.json").write_text(json.dumps({"result": 42}))\n'
        )

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "name": "test",
                "depends_on": [],
                "type": "script",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "result": {"type": "integer"},
                            "code_path": {"type": "string"},
                            "code_hash": {"type": "string"},
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        handler.execute(spec, ls, engine.ctx)

        data = json.loads((rdir / "phase_0.json").read_text())
        expected_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
        assert data["code_path"] == "research/iter_1/phases/phase_0_test.py"
        assert data["code_hash"] == expected_sha

    @patch("tiny_lab.optimize.run_optimize")
    def test_optimize_phase_stamps_script_provenance(self, mock_run_optimize, project_dir):
        mock_run_optimize.return_value = SimpleNamespace(
            best_value=0.3,
            best_params={"lr": 0.01},
            n_trials=1,
            total_seconds=0.1,
            all_trials=[{"value": 0.3}],
        )
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)

        script = pdir / "phase_0_optimize.py"
        script.write_text("print('optimizer target')\n")

        plan = {
            "name": "test",
            "metric": {"name": "loss", "direction": "minimize"},
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "name": "optimize",
                "depends_on": [],
                "type": "optimize",
                "optimize": {},
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_RUN", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_RUN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseRunHandler
        handler = PhaseRunHandler()
        handler.execute(spec, ls, engine.ctx)

        data = json.loads((rdir / "phase_0.json").read_text())
        expected_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
        assert data["script_path"] == "research/iter_1/phases/phase_0_optimize.py"
        assert data["script_sha256"] == expected_sha
        assert data["optimization_metric"] == "loss"
        assert data["optimization_direction"] == "minimize"
        assert data["selection_criterion"] == "minimize loss"
        assert data["optimization_config"] == {}


class TestPhaseEvaluate:
    def test_validates_schema(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"gravity_removed": True, "rows_after": 100}))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": f"research/iter_1/results/phase_0.json",
                        "schema": {"gravity_removed": {"type": "boolean"}, "rows_after": {"type": "integer"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        handler.execute(spec, ls, engine.ctx)  # should not raise

    def test_rejects_mismatched_result_phase_id(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "phase_id": "phase_1",
            "score": 0.9,
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "phase_id": {"type": "string"},
                            "score": {"type": "number"},
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report phase identity errors"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_baseline_consistency_errors_during_phase_evaluate(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "phase_id": "phase_0",
            "rmse": 20.0,
            "baseline_results": [{"baseline": "mean", "rmse": 10.0}],
            "comparison_table": [{
                "model": "candidate",
                "rmse": 20.0,
                "beats_baseline": True,
                "delta_vs_baseline": 5.0,
            }],
        }))

        plan = {
            "name": "test",
            "metric": {"name": "rmse", "direction": "minimize"},
            "baselines": [{"name": "mean", "type": "non-ml"}],
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report consistency errors"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_missing_executable_artifact_contract_during_phase_evaluate(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "phase_id": "phase_0",
            "mae_mean": 0.42,
            "mae_std": 0.03,
            "fold_count": 5,
        }))

        plan = {
            "name": "test",
            "metric": {"name": "mae", "direction": "minimize"},
            "phases": [{
                "id": "phase_0",
                "type": "script",
                "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "phase_id": {"type": "string"},
                            "mae_mean": {"type": "number"},
                            "mae_std": {"type": "number"},
                            "fold_count": {"type": "integer"},
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report artifact contract errors"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_present_optional_substantive_schema_field(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "mae_mean": 0.42,
            "p_value": 1.2,
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "required": ["mae_mean"],
                            "properties": {
                                "mae_mean": {"type": "number"},
                                "p_value": {"type": "number"},
                            },
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="p_value p-value must be between 0 and 1"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_extra_invalid_substantive_field_not_declared_in_schema(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "mae_mean": 0.42,
            "p_value": 1.2,
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {"type": "number"},
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="p_value p-value must be between 0 and 1"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_unsafe_report_path(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "../escape.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        from tiny_lab.errors import StateError
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Unsafe report path"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_report_path_from_other_iteration(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_2/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="research/iter_1/results"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_non_object_report_json(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps([{"score": 0.9}]))
        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "expected_outputs": {
                    "report": {"path": "research/iter_1/results/phase_0.json"}
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="report is not a JSON object"):
            handler.execute(spec, ls, engine.ctx)

    def test_validates_explicit_visualization_files(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
        (rdir / "phase_0_error_distribution.png").write_bytes(PNG_SIGNATURE)

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "visualization": ["phase_0_error_distribution.png"],
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        handler.execute(spec, ls, engine.ctx)  # should not raise

    def test_validates_structured_visualization_path(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
        (rdir / "phase_0_data_profile.png").write_bytes(PNG_SIGNATURE)

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "visualization": {
                    "path": "research/iter_1/results/phase_0_data_profile.png",
                    "description": "Feature and target distributions.",
                },
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        handler.execute(spec, ls, engine.ctx)  # should not raise

    def test_validates_nested_structured_visualization_filenames(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
        (rdir / "baseline_comparison_bar.png").write_bytes(PNG_SIGNATURE)
        (rdir / "residual_histogram.png").write_bytes(PNG_SIGNATURE)

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "running",
                "visualization": {
                    "plots": [
                        {"filename": "research/iter_1/results/baseline_comparison_bar.png"},
                        {"filename": "research/iter_1/results/residual_histogram.png"},
                    ]
                },
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        handler.execute(spec, ls, engine.ctx)

    def test_rejects_missing_visualization_files(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "visualization": ["phase_0_error_distribution.png"],
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Missing visualization files"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_empty_visualization_files(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
        (rdir / "phase_0_error_distribution.png").write_bytes(b"")

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "visualization": ["phase_0_error_distribution.png"],
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="empty visualizations"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_invalid_png_visualization_files(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": 0.9}))
        (rdir / "phase_0_error_distribution.png").write_bytes(b"not a png")

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "visualization": ["phase_0_error_distribution.png"],
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="invalid PNG visualizations"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_schema_type_mismatch(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"score": "0.9"}))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report schema type errors"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_nested_non_finite_numbers(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "score": 0.9,
            "baseline_results": [{"mae_mean": float("nan")}],
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"score": {"type": "number"}},
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="non-finite numeric value"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_mismatched_code_provenance_hash(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        pdir = phases_dir(project_dir, 1)
        rdir = results_dir(project_dir, 1)
        pdir.mkdir(exist_ok=True)
        rdir.mkdir(exist_ok=True)
        script = pdir / "phase_0.py"
        script.write_text("print('actual')\n")
        (rdir / "phase_0.json").write_text(json.dumps({
            "score": 0.9,
            "script_path": "research/iter_1/phases/phase_0.py",
            "script_sha256": "sha256:wrong",
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "score": {"type": "number"},
                            "script_path": {"type": "string"},
                            "script_sha256": {"type": "string"},
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report code provenance errors"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_empty_reproducibility_metadata(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "mae_mean": 0.42,
            "mae_std": 0.03,
            "random_seed": 7,
            "dataset_fingerprint": "",
            "split_id": "fold_0",
            "python_version": "3.11",
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {"type": "number"},
                            "mae_std": {"type": "number"},
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                        },
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report substantive value errors"):
            handler.execute(spec, ls, engine.ctx)

    def test_rejects_invalid_substantive_values_without_schema(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({
            "mae_mean": 0.42,
            "p_value": 1.2,
        }))

        plan = {
            "name": "test",
            "phases": [{
                "id": "phase_0", "status": "running",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                    }
                },
            }],
        }
        (idir / "research_plan.json").write_text(json.dumps(plan))

        save_state(project_dir, LoopState(state="PHASE_EVALUATE", current_iteration=1, current_phase_id="phase_0"))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_EVALUATE")
        ls = load_state(project_dir)

        from tiny_lab.errors import StateError
        from tiny_lab.handlers.phase import PhaseEvaluateHandler
        handler = PhaseEvaluateHandler()
        with pytest.raises(StateError, match="Report substantive value errors"):
            handler.execute(spec, ls, engine.ctx)


class TestTryAdvance:
    def test_story_tell_quality_gate_uses_latest_planned_iteration_for_max_iter_tail(
        self,
        project_dir,
    ):
        from tiny_lab.gates import completion_artifact_quality_issue

        write_complete_plan_and_result(project_dir)
        write_complete_final_paper(project_dir, complete_result_citation())
        iter_dir(project_dir, 2).mkdir(parents=True)
        (iter_dir(project_dir, 2) / ".domain_research.json").write_text(
            json.dumps({"references": ["Unfinished follow-up reference"]})
        )

        issue = completion_artifact_quality_issue(
            project_dir,
            "STORY_TELL",
            project_dir / "research" / "final_paper.md",
            iteration=2,
        )

        assert issue is None

    def test_try_fix_json_ignores_markdown_completion_artifacts(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.handlers.ai_session import _try_fix_json
        from tiny_lab.runner_contract import RunnerStateContract

        (project_dir / "research" / "final_paper.md").write_text("# Paper\n\nNot JSON.")
        contract = RunnerStateContract(
            state="STORY_TELL",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/story_tell.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/final_paper.md",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/final_paper.md",
            completion_required_fields=(),
            condition=None,
            next="REVIEW",
        )

        def fail_run(*args, **kwargs):
            raise AssertionError("markdown artifacts must not use JSON repair")

        monkeypatch.setattr("tiny_lab.handlers.ai_session.subprocess.run", fail_run)

        ok = _try_fix_json(
            contract,
            LoopState(state="STORY_TELL", current_iteration=1),
            make_engine(project_dir).ctx,
        )

        assert ok is False

    def test_story_tell_artifact_fix_prompt_repairs_markdown_with_quality_gate(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers.ai_session import _try_fix_artifact
        from tiny_lab.runner_contract import RunnerStateContract

        captured: dict[str, str] = {}
        write_complete_plan_and_result(project_dir)
        (project_dir / "research" / "final_paper.md").write_text("too short")
        contract = RunnerStateContract(
            state="STORY_TELL",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/story_tell.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/final_paper.md",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/final_paper.md",
            completion_required_fields=(),
            condition=None,
            next="REVIEW",
        )

        class RecordingBackend:
            name = "claude"

            def invoke(self, prompt, *args, **kwargs):
                captured["prompt"] = prompt
                captured["timeout"] = kwargs["timeout"]
                write_complete_final_paper(project_dir, complete_result_citation())
                return BackendResult(exit_code=0, stdout="", stderr="", session_id=None)

        monkeypatch.setitem(base._REGISTRY, "claude", RecordingBackend())

        ok = _try_fix_artifact(
            contract,
            LoopState(state="STORY_TELL", current_iteration=1),
            make_engine(project_dir).ctx,
            "paper issue",
        )

        assert ok is True
        assert "Final Paper Contract" in captured["prompt"]
        assert "Final Paper Evidence Ledger" in captured["prompt"]
        assert "research/iter_1/results/phase_0.json" in captured["prompt"]
        assert "Baseline comparison evidence is recorded" in captured["prompt"]
        assert "tiny-lab audit --strict --iter 1" in captured["prompt"]
        assert "Fix the JSON file" not in captured["prompt"]
        assert captured["timeout"] == 600.0

    def test_story_tell_traceable_fallback_runs_before_expensive_completion_resolver(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.handlers.ai_session import _try_fix_artifact
        from tiny_lab.runner_contract import RunnerStateContract

        write_complete_plan_and_result(project_dir)
        (project_dir / "research" / "final_paper.md").write_text(
            "# Paper\n\n"
            "## Abstract\nA complete summary of the study.\n\n"
            "## Method\nA detailed account of the experimental setup.\n\n"
            "## Results\nThis stale paper cites research/iter_1/results/invalid.json.\n\n"
            "## Limitations\nA detailed account of threats to validity. " * 20
        )

        def fail_completion_resolver(*args, **kwargs):
            raise AssertionError("fallback should run before quality-backed completion matching")

        monkeypatch.setattr(
            "tiny_lab.handlers.ai_session._completion_artifact_matches",
            fail_completion_resolver,
        )

        contract = RunnerStateContract(
            state="STORY_TELL",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/story_tell.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/final_paper.md",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/final_paper.md",
            completion_required_fields=(),
            condition=None,
            next="REVIEW",
        )

        ok = _try_fix_artifact(
            contract,
            LoopState(state="STORY_TELL", current_iteration=1),
            make_engine(project_dir).ctx,
            "final_paper.md cites invalid research result artifacts",
        )

        assert ok is True
        text = (project_dir / "research" / "final_paper.md").read_text()
        assert "research/iter_1/results/phase_0.json" in text
        assert "research/iter_1/results/invalid.json" not in text

    def test_deterministic_review_uses_final_artifact_iteration_scope(self, project_dir):
        from tiny_lab.final_paper import write_traceable_final_paper
        from tiny_lab.handlers.ai_session import _try_write_deterministic_review

        old_iter = iter_dir(project_dir, 1)
        old_iter.mkdir(parents=True, exist_ok=True)
        (old_iter / "research_plan.json").write_text(json.dumps({
            "phases": [{
                "id": "old_phase",
                "status": "pending",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/old_phase.json",
                        "schema": {"mae_mean": {"type": "number"}},
                    }
                },
                "visualization": [],
            }],
        }))
        write_complete_plan_and_result(project_dir, iteration=2)
        write_traceable_final_paper(project_dir, 2)

        ok = _try_write_deterministic_review(
            LoopState(state="REVIEW", current_iteration=2),
            make_engine(project_dir).ctx,
        )

        assert ok is True
        evaluation = json.loads((project_dir / "research" / "evaluation.json").read_text())
        assert evaluation["verdict"] == "ACCEPT"

    def test_phase_code_artifact_fix_ignores_scripts_for_other_phases(self, project_dir, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.handlers.ai_session import _try_fix_artifact
        from tiny_lab.runner_contract import RunnerStateContract

        pdir = phases_dir(project_dir, 1)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "phase_0_preprocess.py").write_text("print('old phase')\n")

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("missing active phase script should use normal PHASE_CODE generation")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        contract = RunnerStateContract(
            state="PHASE_CODE",
            iteration=1,
            current_phase_id="phase_1_heuristic_baselines",
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/phase_code.md",
            allowed_tools=("Read", "Write", "Edit", "Bash"),
            allowed_write_globs=("research/{iter}/phases/*.py",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/iter_1/phases/phase_*.py",
            completion_required_fields=(),
            condition=None,
            next="PHASE_RUN",
        )

        ok = _try_fix_artifact(
            contract,
            LoopState(state="PHASE_CODE", current_iteration=1, current_phase_id="phase_1_heuristic_baselines"),
            make_engine(project_dir).ctx,
            "No Python script found for phase phase_1_heuristic_baselines",
        )

        assert ok is False

    def test_plan_artifact_fix_prompt_allows_quality_contract_repairs(self, project_dir):
        from tiny_lab.handlers.ai_session import _artifact_fix_prompt
        from tiny_lab.runner_contract import RunnerStateContract

        contract = RunnerStateContract(
            state="PLAN",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/plan.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/{iter}/research_plan.json",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/iter_1/research_plan.json",
            completion_required_fields=("name", "phases"),
            condition=None,
            next="VALIDATE_PLAN",
        )

        prompt = _artifact_fix_prompt(
            project_dir / "research" / "iter_1" / "research_plan.json",
            contract,
            "research plan quality issues: missing ablation schema",
            project_dir,
        )

        assert "Experimental Plan Quality Contract" in prompt
        assert "You may add, remove, rename, or restructure" in prompt
        assert "Do NOT change the content" not in prompt
        assert "research/iter_1/results/" in prompt

    def test_json_artifact_fix_prompt_allows_missing_field_addition(self, project_dir):
        from tiny_lab.handlers.ai_session import _artifact_fix_prompt
        from tiny_lab.runner_contract import RunnerStateContract

        contract = RunnerStateContract(
            state="VISUALIZE_DATA",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/visualize_data.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/{iter}/.data_viz_manifest.json",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/{iter}/.data_viz_manifest.json",
            completion_required_fields=("generated", "skipped", "researcher_readout", "summary"),
            condition=None,
            next="IDEA_REFINE",
        )

        prompt = _artifact_fix_prompt(
            project_dir / "research" / "iter_1" / ".data_viz_manifest.json",
            contract,
            "missing required fields ['summary']",
            project_dir,
        )

        assert "you may add missing required fields" in prompt
        assert "derive" in prompt
        assert "Do NOT change the content" not in prompt

    def test_plan_quality_fallback_runs_before_backend_artifact_fix(self, project_dir, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.handlers.ai_session import _try_fix_artifact
        from tiny_lab.runner_contract import RunnerStateContract

        class FailingBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                raise AssertionError("deterministic plan fallback should run before backend repair")

        monkeypatch.setitem(base._REGISTRY, "claude", FailingBackend())
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True, exist_ok=True)
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "WAPE plan",
            "metric": {"name": "WAPE", "direction": "minimize", "target": None},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "success_criteria": "All result artifacts report no leakage and every schema field is present.",
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
                "has_fairness_audit": "yes",
                "has_robustness_checks": "yes",
                "has_generalization_check": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Model comparison",
                "why": "Compare prior work, baselines, ablation, robustness, fairness, generalization, error analysis, and leakage audit.",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "Run held-out split, cross-validation, seasonal naive, linear regression, ablation, robustness, fairness, residual error analysis, and leakage audit.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "WAPE": {"type": "number"},
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
                            "fold_count": {"type": "integer"},
                            "train_test_overlap": {"type": "integer"},
                            "target_achieved": {"type": "boolean"},
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                            "script_path": {"type": "string"},
                            "script_sha256": {"type": "string"},
                        },
                    },
                },
                "visualization": ["phase_0.png"],
            }],
        }))
        contract = RunnerStateContract(
            state="PLAN",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/plan.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/{iter}/research_plan.json",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/iter_1/research_plan.json",
            completion_required_fields=("name", "phases"),
            condition=None,
            next="VALIDATE_PLAN",
        )

        ok = _try_fix_artifact(
            contract,
            LoopState(state="PLAN", current_iteration=1),
            make_engine(project_dir).ctx,
            "research plan quality issues: missing schema fields",
        )

        assert ok is True

    def test_story_tell_artifact_fix_timeout_returns_false(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers.ai_session import _try_fix_artifact
        from tiny_lab.runner_contract import RunnerStateContract

        (project_dir / "research" / "final_paper.md").write_text("too short")
        contract = RunnerStateContract(
            state="STORY_TELL",
            iteration=1,
            current_phase_id=None,
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="claude",
            prompt_path="prompts/story_tell.md",
            allowed_tools=("Read", "Write"),
            allowed_write_globs=("research/final_paper.md",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/final_paper.md",
            completion_required_fields=(),
            condition=None,
            next="REVIEW",
        )

        class TimeoutBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                return BackendResult(
                    exit_code=124,
                    stdout="",
                    stderr=f"Backend command timed out after {kwargs['timeout']:g}s: claude",
                    session_id=None,
                )

        monkeypatch.setitem(base._REGISTRY, "claude", TimeoutBackend())

        engine = Engine(project_dir, research_registry(), backend_timeout_seconds=7)
        ok = _try_fix_artifact(
            contract,
            LoopState(state="STORY_TELL", current_iteration=1),
            engine.ctx,
            "paper issue",
        )

        assert ok is False

    def test_artifact_fix_timeout_accepts_valid_artifact_written_before_timeout(
        self,
        project_dir,
        monkeypatch,
    ):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.handlers.ai_session import _try_fix_artifact
        from tiny_lab.runner_contract import RunnerStateContract

        hlog = project_dir / "research" / "iter_1" / "phases" / ".hypothesis_log.json"
        hlog.parent.mkdir(parents=True, exist_ok=True)
        hlog.write_text(json.dumps({
            "iteration": 1,
            "entries": [{
                "phase_id": "p0",
                "ran_at": "2026-05-05T00:00:00Z",
                "incoming_hypothesis": "old",
                "result_interpretation": "old",
                "outgoing_hypothesis": "old",
                "drift_axis": "none",
            }],
        }))

        class TimeoutAfterWritingBackend:
            name = "codex"

            def invoke(self, *args, **kwargs):
                hlog.write_text(json.dumps({
                    "iteration": 1,
                    "entries": [
                        {
                            "phase_id": "p0",
                            "ran_at": "2026-05-05T00:00:00Z",
                            "incoming_hypothesis": "old",
                            "result_interpretation": "old",
                            "outgoing_hypothesis": "old",
                            "drift_axis": "none",
                        },
                        {
                            "phase_id": "p1",
                            "ran_at": "2026-05-05T01:00:00Z",
                            "incoming_hypothesis": "new",
                            "result_interpretation": "new",
                            "outgoing_hypothesis": "new",
                            "drift_axis": "scope",
                        },
                    ],
                }))
                return BackendResult(
                    exit_code=124,
                    stdout="",
                    stderr="Backend command timed out after 120s: codex",
                    session_id=None,
                )

        monkeypatch.setitem(base._REGISTRY, "codex", TimeoutAfterWritingBackend())
        contract = RunnerStateContract(
            state="HYPOTHESIS_UPDATE",
            iteration=1,
            current_phase_id="p1",
            state_type="ai_session",
            action="",
            runner_command=None,
            intended_engine="codex",
            prompt_path="prompts/hypothesis_update.md",
            allowed_tools=("Read", "Write", "Edit"),
            allowed_write_globs=("research/{iter}/phases/.hypothesis_log.json",),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact="research/iter_1/phases/.hypothesis_log.json",
            completion_required_fields=("iteration", "entries"),
            condition=None,
            next="CHECKPOINT",
        )

        ok = _try_fix_artifact(
            contract,
            LoopState(state="HYPOTHESIS_UPDATE", current_iteration=1, current_phase_id="p1"),
            Engine(project_dir, research_registry()).ctx,
            "stale hypothesis log",
        )

        assert ok is True

    def test_artifact_fix_timeout_caps_long_phase_timeout(self, project_dir):
        from tiny_lab.handlers.ai_session import _artifact_fix_timeout_seconds

        engine = Engine(project_dir, research_registry(), backend_timeout_seconds=900)

        assert _artifact_fix_timeout_seconds(engine.ctx, project_dir / "research_plan.json") == 120.0
        assert _artifact_fix_timeout_seconds(engine.ctx, project_dir / "final_paper.md") == 600.0
        assert (
            _artifact_fix_timeout_seconds(
                engine.ctx,
                project_dir / "research_plan.json",
                backend_name="codex",
            )
            == 300.0
        )

    def test_artifact_fix_timeout_honors_short_override(self, project_dir):
        from tiny_lab.handlers.ai_session import _artifact_fix_timeout_seconds

        engine = Engine(project_dir, research_registry(), backend_timeout_seconds=7)

        assert _artifact_fix_timeout_seconds(engine.ctx, project_dir / "research_plan.json") == 7.0

    def test_advances_when_artifact_exists(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / ".domain_research.json").write_text(
            json.dumps({"domain_type": "test", "sota_models": ["a"], "references": ["b"]})
        )

        save_state(project_dir, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DOMAIN_RESEARCH")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        _try_advance(spec, ls, engine.ctx)

        new_ls = load_state(project_dir)
        assert new_ls.state == "DATA_DEEP_DIVE"

    def test_completion_transition_resets_session_for_phase_loop(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / ".plan_validation.json").write_text(json.dumps({
            "verdict": "APPROVE",
            "checks": [],
        }))

        save_state(
            project_dir,
            LoopState(state="VALIDATE_PLAN", current_iteration=1, session_id="planning-session"),
        )
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("VALIDATE_PLAN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is None
        new_ls = load_state(project_dir)
        assert new_ls.state == "PHASE_SELECT"
        assert new_ls.session_id is None

    def test_explore_completion_starts_new_iteration_with_seed(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / ".explore_seed.json").write_text(json.dumps({
            "new_seed": "Try a causal representation learning direction.",
            "rationale": "The current supervised baseline has plateaued.",
        }))

        save_state(
            project_dir,
            LoopState(state="EXPLORE", current_iteration=1, session_id="explore-session"),
        )
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("EXPLORE")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is None
        new_ls = load_state(project_dir)
        assert new_ls.state == "DOMAIN_RESEARCH"
        assert new_ls.current_iteration == 2
        assert new_ls.session_id is None
        assert (iter_dir(project_dir, 2) / ".explore_seed.json").exists()
        seed = json.loads((iter_dir(project_dir, 2) / ".iteration_seed.json").read_text())
        assert seed["source_artifact"] == "research/iter_1/.explore_seed.json"
        assert seed["new_idea"] == "Try a causal representation learning direction."
        iterations = json.loads(iterations_path(project_dir).read_text())
        assert iterations["iterations"][0]["id"] == 1

    def test_does_not_advance_without_artifact(self, project_dir):
        iter_dir(project_dir, 1).mkdir(parents=True)
        save_state(project_dir, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DOMAIN_RESEARCH")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        _try_advance(spec, ls, engine.ctx)

        new_ls = load_state(project_dir)
        assert new_ls.state == "DOMAIN_RESEARCH"

    def test_does_not_advance_with_missing_fields(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / ".domain_research.json").write_text(json.dumps({"domain_type": "test"}))

        save_state(project_dir, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DOMAIN_RESEARCH")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        _try_advance(spec, ls, engine.ctx)

        new_ls = load_state(project_dir)
        assert new_ls.state == "DOMAIN_RESEARCH"

    def test_does_not_advance_with_invalid_json_artifact(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / ".domain_research.json").write_text('{"domain_type": "test"')

        save_state(project_dir, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DOMAIN_RESEARCH")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "invalid JSON" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "DOMAIN_RESEARCH"

    def test_plan_quality_blocks_advance(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "weak",
            "metric": {"name": "mae", "direction": "minimize"},
            "phases": [{
                "id": "phase_0",
                "status": "pending",
                "depends_on": [],
                "type": "script",
                "methodology": "train one model",
                "expected_outputs": {"report": {"path": "research/iter_1/results/phase_0.json", "schema": {"mae": {}}}},
                "visualization": ["phase_0_loss.png"],
            }],
        }))

        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PLAN")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "research plan quality issues" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "PLAN"

    def test_review_accept_blocks_unsupported_numeric_claims(self, project_dir):
        write_complete_plan_and_result(project_dir)
        write_complete_final_paper(
            project_dir,
            "The final model beats the baseline with MAE = 0.31 "
            "(research/iter_1/results/phase_0.json). "
            f"{complete_result_citation()} "
            "The primary error figure is research/iter_1/results/phase_0_error.png.",
        )
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": complete_review_feedback(8),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "unsupported research claims" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"

    def test_review_revise_allows_unsupported_numeric_claims_to_route(self, project_dir):
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(parents=True)
        (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        (project_dir / "research" / "final_paper.md").write_text(
            "The final model beats the baseline with MAE = 0.31 (research/iter_1/results/phase_0.json)."
        )
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "REVISE",
            "scores": {
                "academic_rigor": 7,
                "experimental_sufficiency": 7,
                "novelty": 7,
                "narrative_coherence": 7,
                "goal_achievement": 7,
            },
            "total": 35,
            "required_actions": ["Rerun the final model and correct unsupported MAE claims."],
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is None
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW_DONE"

    def test_review_blocks_inconsistent_evaluation_verdict(self, project_dir):
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 7,
                "experimental_sufficiency": 7,
                "novelty": 7,
                "narrative_coherence": 7,
                "goal_achievement": 7,
            },
            "total": 35,
            "feedback": complete_review_feedback(7),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "evaluation consistency issues" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"

    def test_review_accept_blocks_reference_verification_issues(self, project_dir):
        write_complete_plan_and_result(project_dir)
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True, exist_ok=True)
        (idir / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Imaginary Paper", "doi": "10.9999/missing"}]
        }))
        (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": str(idir / ".domain_research.json"),
            "summary": {"total": 1, "verified": 0, "unverified": 0, "not_found": 1, "error": 0},
            "refs": [],
        }))
        write_complete_final_paper(
            project_dir,
            f"{complete_result_citation()} research/iter_1/.domain_research.json",
        )
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": complete_review_feedback(8),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "reference verification issues" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"

    def test_review_accept_blocks_out_of_scope_previous_iteration_results(self, project_dir):
        write_complete_plan_and_result(project_dir, iteration=1)
        write_complete_plan_and_result(project_dir, iteration=2)
        old_iter = iter_dir(project_dir, 1)
        old_iter.mkdir(parents=True, exist_ok=True)
        (old_iter / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Old Imaginary Paper", "doi": "10.9999/old-missing"}]
        }))
        (old_iter / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": str(old_iter / ".domain_research.json"),
            "summary": {"total": 1, "verified": 0, "unverified": 0, "not_found": 1, "error": 0},
            "refs": [],
        }))
        write_complete_final_paper(
            project_dir,
            f"{complete_result_citation(iteration=1)} {complete_result_citation(iteration=2)} "
            "research/iter_1/.domain_research.json",
        )
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": complete_review_feedback(8),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=2))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "out-of-scope research result artifacts" in problem
        assert "iter_1" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"

    def test_review_accept_blocks_incomplete_phase_outputs(self, project_dir):
        idir = iter_dir(project_dir, 1)
        rdir = results_dir(project_dir, 1)
        idir.mkdir(parents=True, exist_ok=True)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "rigorous",
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
                "name": "Leakage-safe baseline audit",
                "why": "Check split protocol and baseline",
                "type": "script",
                "depends_on": [],
                "methodology": "Run held-out split, seasonal naive, linear regression, ablation, CV fold residual error analysis.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {"type": "number"},
                            "mae_std": {"type": "number"},
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                        },
                    }
                },
                "visualization": ["phase_0_error.png"],
                "status": "done",
            }],
        }))
        write_complete_final_paper(
            project_dir,
            "The incomplete phase result is cited in research/iter_1/results/phase_0.json.",
        )
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": complete_review_feedback(8),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "incomplete research artifacts" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"

    def test_review_accept_blocks_incomplete_phase_outputs_from_previous_iterations(self, project_dir):
        old_iter = iter_dir(project_dir, 1)
        old_results = results_dir(project_dir, 1)
        old_iter.mkdir(parents=True, exist_ok=True)
        old_results.mkdir(exist_ok=True)
        (old_results / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        (old_iter / "research_plan.json").write_text(json.dumps({
            "name": "old rigorous",
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
                "name": "Old model comparison",
                "why": "Compare baseline under CV folds",
                "type": "script",
                "depends_on": [],
                "methodology": "Run held-out split, seasonal naive, linear regression, ablation, CV fold residual error analysis.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {"type": "number"},
                            "mae_std": {"type": "number"},
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                        },
                    }
                },
                "visualization": ["phase_0_error.png"],
                "status": "pending",
            }],
        }))
        write_complete_final_paper(
            project_dir,
            "The incomplete prior result is cited in research/iter_1/results/phase_0.json.",
        )
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": complete_review_feedback(8),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=2))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "incomplete research artifacts" in problem
        assert "iter_1" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"

    def test_review_accept_blocks_missing_final_paper(self, project_dir):
        rdir = results_dir(project_dir, 1)
        rdir.mkdir(parents=True)
        (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": complete_review_feedback(8),
        }))

        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")
        ls = load_state(project_dir)

        from tiny_lab.handlers.ai_session import _try_advance
        problem = _try_advance(spec, ls, engine.ctx)

        assert problem is not None
        assert "final paper issues" in problem
        new_ls = load_state(project_dir)
        assert new_ls.state == "REVIEW"


class TestPromptRendering:
    def test_injects_quality_standard_into_ai_prompts(self, project_dir):
        save_state(project_dir, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DOMAIN_RESEARCH")

        from tiny_lab.handlers.ai_session import _render_prompt
        prompt = _render_prompt(spec, {"iter": "iter_1", "project_dir": str(project_dir)}, engine.ctx)

        assert "## ML Researcher Quality Standard" in prompt
        assert "Traceable claims" in prompt
        assert "Leakage and validity audits" in prompt

    def test_injects_constraints_after_quality_standard(self, project_dir):
        (project_dir / "research" / "constraints.json").write_text(json.dumps({
            "objective": "Build a robust ML forecasting study",
            "goal": {"success_criteria": "Beat seasonal naive by 10% MAE"},
            "invariants": ["No leakage"],
            "exploration_bounds": {"forbidden": ["test-set tuning"]},
        }))
        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PLAN")

        from tiny_lab.handlers.ai_session import _render_prompt
        prompt = _render_prompt(spec, {"iter": "iter_1", "project_dir": str(project_dir)}, engine.ctx)

        quality_idx = prompt.index("## ML Researcher Quality Standard")
        constraints_idx = prompt.index("## Constraints (MUST NOT VIOLATE)")
        assert quality_idx < constraints_idx
        assert "Objective: Build a robust ML forecasting study" in prompt
        assert "- Forbidden: test-set tuning" in prompt

    def test_does_not_inject_invalid_constraints(self, project_dir):
        (project_dir / "research" / "constraints.json").write_text(json.dumps({
            "objective": " ",
            "goal": "reduce error somehow",
            "invariants": [],
        }))
        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PLAN")

        from tiny_lab.handlers.ai_session import _render_prompt
        prompt = _render_prompt(spec, {"iter": "iter_1", "project_dir": str(project_dir)}, engine.ctx)

        assert "## ML Researcher Quality Standard" in prompt
        assert "## Constraints (MUST NOT VIOLATE)" not in prompt

    def test_data_deep_dive_prompt_has_no_data_escape_hatch(self, project_dir):
        save_state(project_dir, LoopState(state="DATA_DEEP_DIVE", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DATA_DEEP_DIVE")

        from tiny_lab.handlers.ai_session import _render_prompt
        prompt = _render_prompt(spec, {"iter": "iter_1", "project_dir": str(project_dir)}, engine.ctx)

        assert "If no local data files are found" in prompt
        assert "do not keep searching" in prompt
        assert '"not_available"' in prompt
        assert "This no-data artifact is a valid output" in prompt

    def test_domain_research_prompt_prefers_explore_seed_when_present(self, project_dir):
        save_state(project_dir, LoopState(state="DOMAIN_RESEARCH", current_iteration=2))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("DOMAIN_RESEARCH")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "research/iter_2/.iteration_seed.json" in prompt
        assert "research/iter_2/.explore_seed.json" in prompt
        assert "active research direction for the current iteration" in prompt
        assert "Run at most two high-value searches" in prompt
        assert "do not stall" in prompt
        assert 'literature_search_status` as "offline_or_unavailable"' in prompt

    def test_idea_refine_prompt_reads_iteration_seed_when_present(self, project_dir):
        save_state(project_dir, LoopState(state="IDEA_REFINE", current_iteration=2))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("IDEA_REFINE")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "research/iter_2/.iteration_seed.json" in prompt
        assert "active seed for the current iteration" in prompt

    def test_phase_code_prompt_uses_shared_phase_script_contract(self, project_dir):
        idir = iter_dir(project_dir, 1)
        idir.mkdir(parents=True)
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "phase prompt contract",
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-Safe Baseline Audit",
                "type": "script",
                "depends_on": [],
                "methodology": "Run a leakage-safe baseline.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {"mae": {"type": "number"}},
                    }
                },
                "status": "pending",
            }],
        }))
        save_state(
            project_dir,
            LoopState(state="PHASE_CODE", current_iteration=1, current_phase_id="phase_0"),
        )
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PHASE_CODE")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "tiny_lab.phase_contract" in prompt
        assert "research/iter_1/phases/phase_0_leakage_safe_baseline_audit.py" in prompt
        assert "current*phase_id" not in prompt
        assert "Do not create additional matching scripts for `phase_0`" in prompt
        assert "uv pip install --python" in prompt
        assert "UV_CACHE_DIR" in prompt
        assert "ensurepip" in prompt
        assert "PIP_CACHE_DIR" in prompt
        assert "No module named pip" in prompt
        assert "If you declare `alpha` or `significance_level`" in prompt

    def test_plan_prompt_uses_shared_evidence_contract(self, project_dir):
        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PLAN")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Experimental Evidence Contract" in prompt
        assert "tiny_lab.evidence" in prompt
        assert "baseline_results" in prompt
        assert "{evidence_contract}" not in prompt

    def test_plan_prompt_uses_shared_plan_quality_contract(self, project_dir):
        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PLAN")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Experimental Plan Quality Contract" in prompt
        assert "tiny_lab.plan" in prompt
        assert "`expected_outputs`" in prompt
        assert '"status": "pending"' in prompt
        assert "PHASE_SELECT will run it" in prompt
        assert "{plan_quality_contract}" not in prompt

    def test_validate_plan_prompt_uses_shared_plan_quality_contract(self, project_dir):
        save_state(project_dir, LoopState(state="VALIDATE_PLAN", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("VALIDATE_PLAN")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Experimental Plan Quality Contract" in prompt
        assert "tiny_lab.plan" in prompt
        assert "Engine-Enforced Plan Quality Contract" in prompt
        assert "{plan_quality_contract}" not in prompt

    def test_validate_plan_writes_deterministic_approval_when_shared_contract_passes(self, project_dir):
        write_complete_plan_and_result(project_dir)
        from tiny_lab.plan import load_plan, repair_plan_quality_issues, validate_plan_quality
        plan = load_plan(project_dir, 1)
        repair_plan_quality_issues(plan, 1)
        (iter_dir(project_dir, 1) / "research_plan.json").write_text(json.dumps(plan))
        assert validate_plan_quality(plan, 1) == []
        save_state(project_dir, LoopState(state="VALIDATE_PLAN", current_iteration=1))
        engine = make_engine(project_dir)

        engine.step_once(run_ai=True)

        validation_path = iter_dir(project_dir, 1) / ".plan_validation.json"
        data = json.loads(validation_path.read_text())
        assert data["verdict"] == "APPROVE"
        assert data["checks"]["shared_plan_quality_contract"] == "pass"
        assert load_state(project_dir).state == "PHASE_SELECT"

    def test_story_tell_prompt_uses_shared_final_paper_contract(self, project_dir):
        write_complete_plan_and_result(project_dir)
        save_state(project_dir, LoopState(state="STORY_TELL", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("STORY_TELL")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Final Paper Contract" in prompt
        assert "tiny_lab.quality" in prompt
        assert "research/iter_*/results/*.json" in prompt
        assert "Sample-size claims" in prompt
        assert "Repetition-count claims" in prompt
        assert "Split-ratio claims" in prompt
        assert "Before writing a sentence with any metric" in prompt
        assert "Do not use a title or heading that states or implies a result claim" in prompt
        assert "tiny-lab audit --strict" in prompt
        assert "Final Paper Evidence Ledger" in prompt
        assert "research/iter_1/results/phase_0.json" in prompt
        assert "research/iter_1/results/phase_0_error.png" in prompt
        assert "Baseline comparison evidence is recorded" in prompt
        assert "same-sentence citations" in prompt
        assert "{final_paper_contract}" not in prompt
        assert "{final_paper_evidence_ledger}" not in prompt

    def test_story_tell_prompt_targets_latest_planned_iteration_when_state_is_max_iter_tail(
        self,
        project_dir,
    ):
        write_complete_plan_and_result(project_dir)
        iter_dir(project_dir, 2).mkdir(parents=True)
        (iter_dir(project_dir, 2) / ".domain_research.json").write_text(
            json.dumps({"references": ["Unfinished follow-up reference"]})
        )
        save_state(project_dir, LoopState(state="STORY_TELL", current_iteration=2))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("STORY_TELL")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        context = _build_context(spec, load_state(project_dir), engine.ctx)
        prompt = _render_prompt(spec, context, engine.ctx)

        assert context["iter"] == "iter_1"
        assert context["iteration"] == 1
        assert context["state_iteration"] == 2
        assert "research/iter_1/results/" in context["project_tree"]
        assert "research/iter_2/results/" not in context["project_tree"]

    def test_story_tell_prompt_evidence_ledger_covers_latest_planned_iteration_at_max_iter_tail(
        self,
        project_dir,
    ):
        write_complete_plan_and_result(project_dir, iteration=1)
        write_complete_plan_and_result(project_dir, iteration=2, mae_mean=0.38)
        save_state(project_dir, LoopState(state="STORY_TELL", current_iteration=3))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("STORY_TELL")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        context = _build_context(spec, load_state(project_dir), engine.ctx)
        prompt = _render_prompt(spec, context, engine.ctx)

        assert context["iter"] == "iter_2"
        assert context["iteration"] == 2
        assert context["state_iteration"] == 3
        assert "completed iterations `iter_2`" in prompt
        assert "research/iter_1/results/phase_0.json" not in prompt
        assert "research/iter_2/results/phase_0.json" in prompt
        assert "research/iter_1/results/phase_0_error.png" not in prompt
        assert "research/iter_2/results/phase_0_error.png" in prompt

    def test_evaluate_matrix_prompt_uses_shared_reference_verification_contract(self, project_dir):
        preset = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "ideate.json"
        shutil.copy2(preset, workflow_path(project_dir))
        save_state(project_dir, LoopState(state="EVALUATE_MATRIX", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("EVALUATE_MATRIX")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Reference Verification Contract" in prompt
        assert "tiny_lab.refs" in prompt
        assert "research/iter_1/.diverge.ref_verification.json" in prompt
        assert "research/iter_1/.lit_scan.ref_verification.json" in prompt
        assert "unverified" in prompt
        assert "not_found" in prompt
        assert "error" in prompt
        assert "{reference_verification_contract}" not in prompt
        assert "research/iter_1/.ref_verification.json" not in prompt
        assert "for each not_found URL" not in prompt

    def test_professor_prompt_uses_shared_evaluation_contract(self, project_dir):
        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Professor Evaluation Contract" in prompt
        assert "tiny_lab.review" in prompt
        assert "required_actions" in prompt
        assert "research/final_paper.md" in prompt
        assert "\"recommendation\"" in prompt
        assert "\"evidence\"" in prompt
        assert "{evaluation_contract}" not in prompt

    def test_review_paper_professor_prompt_uses_shared_evaluation_contract(self, project_dir):
        preset = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "review-paper.json"
        shutil.copy2(preset, workflow_path(project_dir))
        save_state(project_dir, LoopState(state="REVIEW", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("REVIEW")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Professor Evaluation Contract" in prompt
        assert "\"academic_rigor\"" in prompt
        assert "\"experimental_sufficiency\"" in prompt
        assert "\"coverage\"" not in prompt
        assert "\"taxonomy_quality\"" not in prompt
        assert "\"recommendation\"" in prompt
        assert "\"evidence\"" in prompt
        assert "{evaluation_contract}" not in prompt

    def test_revision_prompts_include_previous_review_required_actions(self, project_dir):
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "REVISE",
            "summary": "The paper needs a stronger leakage audit.",
            "required_actions": ["Add a leakage-safe error analysis phase over the held-out split."],
            "weaknesses": ["No split-level leakage evidence."],
            "feedback": [{
                "criterion": "experimental_sufficiency",
                "issue": "Leakage audit is missing",
                "suggestion": "Validate duplicate overlap and preprocessing fit scope",
            }],
        }))
        save_state(project_dir, LoopState(state="IDEA_REFINE", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("IDEA_REFINE")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Previous evaluation feedback" in prompt
        assert "Add a leakage-safe error analysis phase over the held-out split." in prompt
        assert "Leakage audit is missing" in prompt

    def test_reject_restart_prompt_includes_previous_review_required_actions(self, project_dir):
        (project_dir / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "REJECT",
            "summary": "The task framing cannot support the claimed metric.",
            "required_actions": ["Reframe the leakage-safe held-out dataset split and rerun the seasonal naive baseline comparison."],
        }))
        save_state(project_dir, LoopState(state="SHAPE_FULL", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("SHAPE_FULL")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "Previous Review Feedback" in prompt
        assert "Reframe the leakage-safe held-out dataset split and rerun the seasonal naive baseline comparison." in prompt

    def test_shape_full_prompt_is_noninteractive_for_full_auto_run(self, project_dir):
        save_state(project_dir, LoopState(state="SHAPE_FULL", current_iteration=1))
        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("SHAPE_FULL")

        from tiny_lab.handlers.ai_session import _build_context, _render_prompt
        prompt = _render_prompt(spec, _build_context(spec, load_state(project_dir), engine.ctx), engine.ctx)

        assert "tiny-lab run` is a non-interactive full-auto loop" in prompt
        assert "Do NOT ask follow-up questions" in prompt
        assert "Always write the required artifacts" in prompt
        assert "Do NOT ask the user during this state; write the artifacts." in prompt


class TestIterationManagement:
    def test_create_iteration(self, project_dir):
        engine = make_engine(project_dir)
        engine._create_iteration(2)
        assert iter_dir(project_dir, 2).exists()
        assert phases_dir(project_dir, 2).exists()
        assert results_dir(project_dir, 2).exists()

    def test_carry_over(self, project_dir):
        engine = make_engine(project_dir)
        idir1 = iter_dir(project_dir, 1)
        idir1.mkdir(parents=True)
        (idir1 / ".domain_research.json").write_text("domain: test")
        (idir1 / ".data_analysis.json").write_text("data: test")

        engine._create_iteration(2)
        engine._carry_over(1, 2, "IDEA_REFINE")

        idir2 = iter_dir(project_dir, 2)
        assert (idir2 / ".domain_research.json").exists()
        assert (idir2 / ".data_analysis.json").exists()
