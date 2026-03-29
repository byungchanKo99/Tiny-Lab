"""Integration tests for the engine."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tiny_lab.engine import Engine
from tiny_lab.handlers.defaults import research_registry
from tiny_lab.state import load_state, save_state, set_state, LoopState
from tiny_lab.paths import workflow_path, iter_dir, results_dir, phases_dir


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


class TestEngineInit:
    def test_creates_iter_1(self, project_dir):
        engine = make_engine(project_dir)
        engine._init()
        assert (iter_dir(project_dir, 1)).exists()
        ls = load_state(project_dir)
        assert ls.state == "DOMAIN_RESEARCH"
        assert ls.current_iteration == 1

    def test_resume_from_existing_state(self, project_dir):
        save_state(project_dir, LoopState(state="PLAN", current_iteration=1))
        (iter_dir(project_dir, 1)).mkdir(parents=True)
        engine = make_engine(project_dir)
        engine._init()
        ls = load_state(project_dir)
        assert ls.state == "PLAN"  # didn't reset

    def test_done_not_resumable(self, project_dir):
        save_state(project_dir, LoopState(state="DONE", resumable=False))
        engine = make_engine(project_dir)
        engine._init()
        # Should return without changing state


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

    def test_mandatory_checkpoint_waits_for_intervention(self, project_dir):
        """Mandatory PLAN_REVIEW waits even in autonomous mode."""
        (iter_dir(project_dir, 1)).mkdir(parents=True)
        save_state(project_dir, LoopState(state="PLAN_REVIEW", current_iteration=1))

        # Pre-write intervention so it doesn't hang
        from tiny_lab.paths import intervention_path
        ipath = intervention_path(project_dir)
        ipath.parent.mkdir(parents=True, exist_ok=True)
        ipath.write_text(json.dumps({"action": "approve"}))

        engine = make_engine(project_dir)
        spec = engine.workflow.get_state("PLAN_REVIEW")
        assert spec.mandatory is True

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


class TestTryAdvance:
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
