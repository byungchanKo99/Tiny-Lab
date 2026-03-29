"""Tests for workflow.json parser and validator."""
from __future__ import annotations

from pathlib import Path

import pytest
import json

from tiny_lab.errors import WorkflowError
from tiny_lab.workflow import load_workflow, validate_workflow, Workflow, StateSpec


@pytest.fixture()
def tmp_workflow(tmp_path: Path):
    """Helper to write a workflow YAML and return path."""
    def _write(data: dict) -> Path:
        path = tmp_path / "workflow.json"
        path.write_text(json.dumps(data, indent=2))
        return path
    return _write


class TestLoadWorkflow:
    def test_minimal_valid(self, tmp_workflow):
        path = tmp_workflow({
            "states": [
                {"id": "A", "type": "ai_session", "next": "DONE"},
            ],
        })
        wf = load_workflow(path)
        assert wf.first_state() == "A"
        assert wf.state_ids() == ["A"]

    def test_missing_file(self, tmp_path):
        with pytest.raises(WorkflowError, match="not found"):
            load_workflow(tmp_path / "nope.json")

    def test_no_states(self, tmp_workflow):
        path = tmp_workflow({"autonomy": {"mode": "autonomous"}})
        with pytest.raises(WorkflowError, match="states"):
            load_workflow(path)

    def test_full_preset(self):
        """ml-experiment preset loads without error."""
        path = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "ml-experiment.json"
        if path.exists():
            wf = load_workflow(path)
            assert len(wf.states) > 10
            assert wf.autonomy.mode == "autonomous"

    def test_autonomy_defaults(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{"id": "A", "type": "ai_session", "next": "DONE"}],
        })
        wf = load_workflow(path)
        assert wf.autonomy.mode == "autonomous"
        assert wf.autonomy.max_iterations == 5

    def test_autonomy_override(self, tmp_workflow):
        path = tmp_workflow({
            "autonomy": {"mode": "supervised", "max_iterations": 10},
            "states": [{"id": "A", "type": "ai_session", "next": "DONE"}],
        })
        wf = load_workflow(path)
        assert wf.autonomy.mode == "supervised"
        assert wf.autonomy.max_iterations == 10

    def test_intervention_defaults(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{"id": "A", "type": "ai_session", "next": "DONE"}],
        })
        wf = load_workflow(path)
        assert wf.intervention.timeout_seconds == 3600

    def test_completion_parsing(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{
                "id": "A", "type": "ai_session", "next": "DONE",
                "completion": {
                    "artifact": "research/{iter}/.out.json",
                    "required_fields": ["x", "y"],
                },
            }],
        })
        wf = load_workflow(path)
        comp = wf.get_state("A").completion
        assert comp is not None
        assert comp.artifact == "research/{iter}/.out.json"
        assert comp.required_fields == ["x", "y"]

    def test_error_spec_parsing(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{
                "id": "A", "type": "ai_session", "next": "DONE",
                "error": {"max_retries": 3, "retry_to": "B", "on_exhaust": "stop"},
            }],
        })
        wf = load_workflow(path)
        err = wf.get_state("A").error
        assert err is not None
        assert err.max_retries == 3
        assert err.retry_to == "B"
        assert err.on_exhaust == "stop"

    def test_condition_parsing(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{
                "id": "A", "type": "process",
                "condition": {"source": "reflect.json", "field": "decision"},
                "next": {"done": "DONE", "retry": "A"},
            }],
        })
        wf = load_workflow(path)
        cond = wf.get_state("A").condition
        assert cond is not None
        assert cond.source == "reflect.json"
        assert cond.field == "decision"


class TestValidateWorkflow:
    def test_duplicate_ids(self, tmp_workflow):
        path = tmp_workflow({
            "states": [
                {"id": "A", "type": "ai_session", "next": "DONE"},
                {"id": "A", "type": "process", "next": "DONE"},
            ],
        })
        with pytest.raises(WorkflowError, match="Duplicate"):
            load_workflow(path)

    def test_invalid_type(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{"id": "A", "type": "invalid", "next": "DONE"}],
        })
        with pytest.raises(WorkflowError, match="invalid type"):
            load_workflow(path)

    def test_ai_session_dict_next_rejected(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{
                "id": "A", "type": "ai_session",
                "next": {"a": "B", "b": "C"},
            }],
        })
        with pytest.raises(WorkflowError, match="single"):
            load_workflow(path)

    def test_dict_next_without_condition(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{
                "id": "A", "type": "process",
                "next": {"a": "DONE"},
            }],
        })
        with pytest.raises(WorkflowError, match="condition"):
            load_workflow(path)

    def test_next_target_not_found(self, tmp_workflow):
        path = tmp_workflow({
            "states": [
                {"id": "A", "type": "ai_session", "next": "NONEXISTENT"},
            ],
        })
        with pytest.raises(WorkflowError, match="does not exist"):
            load_workflow(path)

    def test_valid_chain(self, tmp_workflow):
        path = tmp_workflow({
            "states": [
                {"id": "A", "type": "ai_session", "next": "B"},
                {"id": "B", "type": "ai_session", "next": "DONE"},
            ],
        })
        wf = load_workflow(path)
        assert wf.state_ids() == ["A", "B"]


class TestWorkflowGetState:
    def test_get_existing(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{"id": "A", "type": "ai_session", "next": "DONE"}],
        })
        wf = load_workflow(path)
        assert wf.get_state("A").id == "A"

    def test_get_unknown_raises(self, tmp_workflow):
        path = tmp_workflow({
            "states": [{"id": "A", "type": "ai_session", "next": "DONE"}],
        })
        wf = load_workflow(path)
        with pytest.raises(WorkflowError, match="Unknown state"):
            wf.get_state("NOPE")
