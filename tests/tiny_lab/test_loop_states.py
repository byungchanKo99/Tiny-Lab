"""Tests for ResearchLoop state handler methods."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from tiny_lab.events import load_events, reset_event_seq
from tiny_lab.loop import ResearchLoop, State, CycleContext


@pytest.fixture(autouse=True)
def _reset_seq():
    reset_event_seq()
    yield
    reset_event_seq()


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    research = tmp_path / "research"
    research.mkdir()
    (research / "ledger.jsonl").touch()
    project = {
        "name": "test",
        "baseline": {"command": "echo test"},
        "metric": {"name": "loss", "direction": "minimize"},
        "levers": {"lr": {"flag": "--lr", "baseline": "0.01", "space": ["0.01", "0.05"]}},
        "build": {"type": "flag"},
        "run": {"type": "command"},
        "evaluate": {"type": "stdout_json"},
    }
    (research / "project.yaml").write_text(yaml.dump(project))
    (research / "hypothesis_queue.yaml").write_text(yaml.dump({"hypotheses": []}))
    return tmp_path


@pytest.fixture()
def loop(project_dir: Path) -> ResearchLoop:
    with patch("tiny_lab.loop.get_provider") as mock_provider:
        provider = MagicMock()
        provider.name = "mock"
        mock_provider.return_value = provider
        return ResearchLoop(project_dir)


def _add_hypotheses(project_dir: Path, hypotheses: list[dict]) -> None:
    path = project_dir / "research" / "hypothesis_queue.yaml"
    path.write_text(yaml.dump({"hypotheses": hypotheses}))


def _load_project(project_dir: Path) -> dict:
    return yaml.safe_load((project_dir / "research" / "project.yaml").read_text())


class TestCycleContext:
    def test_reset_experiment(self):
        ctx = CycleContext(
            hypothesis={"id": "H-1"}, command="echo", exp_id="EXP-002",
            run_result=MagicMock(), new_metric=0.5, verdict="WIN",
            consecutive_generate_failures=3,
        )
        ctx.reset_experiment()
        assert ctx.hypothesis is None
        assert ctx.command is None
        assert ctx.exp_id is None
        assert ctx.run_result is None
        assert ctx.new_metric is None
        assert ctx.verdict == ""
        # consecutive_generate_failures is NOT reset by reset_experiment
        assert ctx.consecutive_generate_failures == 3


class TestHandleCheckQueue:
    def test_returns_generate_when_empty(self, loop: ResearchLoop, project_dir: Path):
        project = _load_project(project_dir)
        ctx = CycleContext()
        assert loop._handle_check_queue(ctx, project) == State.GENERATE

    def test_returns_select_when_pending(self, loop: ResearchLoop, project_dir: Path):
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "pending", "lever": "lr", "value": "0.05", "description": "test"}])
        project = _load_project(project_dir)
        ctx = CycleContext(consecutive_generate_failures=2)
        state = loop._handle_check_queue(ctx, project)
        assert state == State.SELECT
        assert ctx.consecutive_generate_failures == 0

    def test_circuit_breaker_triggers(self, loop: ResearchLoop, project_dir: Path):
        # Write enough INVALID entries to trigger circuit breaker
        ledger_path = project_dir / "research" / "ledger.jsonl"
        for i in range(5):
            entry = {
                "id": f"EXP-{i+2:03d}", "question": "q", "family": "test",
                "changed_variable": "lr", "value": "0.05", "status": "done",
                "class": "INVALID", "primary_metric": {"loss": None},
                "decision": "invalid",
            }
            with ledger_path.open("a") as f:
                f.write(json.dumps(entry) + "\n")

        project = _load_project(project_dir)
        ctx = CycleContext()
        loop._handle_check_queue(ctx, project)
        assert loop._shutdown is True


class TestHandleSelect:
    def test_selects_first_pending(self, loop: ResearchLoop, project_dir: Path):
        _add_hypotheses(project_dir, [
            {"id": "H-1", "status": "pending", "lever": "lr", "value": "0.05", "description": "first"},
            {"id": "H-2", "status": "pending", "lever": "lr", "value": "0.1", "description": "second"},
        ])
        project = _load_project(project_dir)
        ctx = CycleContext()
        state = loop._handle_select(ctx, project)
        assert state == State.BUILD_COMMAND
        assert ctx.hypothesis["id"] == "H-1"

    def test_returns_check_queue_when_empty(self, loop: ResearchLoop, project_dir: Path):
        project = _load_project(project_dir)
        ctx = CycleContext()
        assert loop._handle_select(ctx, project) == State.CHECK_QUEUE


class TestHandleBuildCommand:
    def test_successful_flag_build(self, loop: ResearchLoop, project_dir: Path):
        project = _load_project(project_dir)
        ctx = CycleContext(hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"})
        state = loop._handle_build_command(ctx, project)
        assert state == State.RUN
        assert ctx.command is not None
        assert "--lr 0.05" in ctx.command
        assert ctx.exp_id is not None

    def test_build_failure_skips(self, loop: ResearchLoop, project_dir: Path):
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "badlever", "value": "x", "description": "test"}])
        project = _load_project(project_dir)
        ctx = CycleContext(hypothesis={"id": "H-1", "lever": "badlever", "value": "x", "description": "test"})
        state = loop._handle_build_command(ctx, project)
        assert state == State.CHECK_QUEUE
        assert ctx.hypothesis is None


class TestHandleRun:
    @patch("tiny_lab.loop.dispatch_run")
    def test_successful_run(self, mock_run, loop: ResearchLoop, project_dir: Path):
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
        project = _load_project(project_dir)
        ctx = CycleContext(command="echo test", exp_id="EXP-002")
        state = loop._handle_run(ctx, project)
        assert state == State.EVALUATE
        assert ctx.run_result is not None
        assert ctx.run_result.returncode == 0

    @patch("tiny_lab.loop.dispatch_run")
    def test_run_failure_continues(self, mock_run, loop: ResearchLoop, project_dir: Path):
        from tiny_lab.errors import RunError
        mock_run.side_effect = RunError("Experiment EXP-002 timed out")
        project = _load_project(project_dir)
        ctx = CycleContext(command="echo test", exp_id="EXP-002")
        state = loop._handle_run(ctx, project)
        assert state == State.EVALUATE
        assert ctx.run_result is None


class TestHandleEvaluate:
    def test_evaluates_and_judges(self, loop: ResearchLoop, project_dir: Path):
        # Write a baseline entry first
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")

        run_result = subprocess.CompletedProcess(args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="")
        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            exp_id="EXP-002", run_result=run_result,
        )
        state = loop._handle_evaluate(ctx, project)
        assert state == State.RECORD
        assert ctx.new_metric == 0.5
        assert ctx.verdict == "WIN"


class TestHandleRecord:
    def test_records_and_resets(self, loop: ResearchLoop, project_dir: Path):
        # Write baseline
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")

        # Add hypothesis to queue
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        # Patch _sleep to avoid delay
        with patch.object(loop, "_sleep"):
            state = loop._handle_record(ctx, project)
        assert state == State.CHECK_QUEUE
        assert ctx.hypothesis is None
        assert ctx.command is None

        # Verify ledger was updated
        lines = (project_dir / "research" / "ledger.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        recorded = json.loads(lines[1])
        assert recorded["id"] == "EXP-002"
        assert recorded["class"] == "WIN"

    def test_record_emits_experiment_done_event(self, loop: ResearchLoop, project_dir: Path):
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        with patch.object(loop, "_sleep"):
            loop._handle_record(ctx, project)

        events = load_events(project_dir)
        event_types = [e["event"] for e in events]
        assert "experiment_done" in event_types

    def test_record_events_include_loop_state(self, loop: ResearchLoop, project_dir: Path):
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        loop._current_state = "record"
        with patch.object(loop, "_sleep"):
            loop._handle_record(ctx, project)

        events = load_events(project_dir)
        for ev in events:
            assert ev["loop_state"] == "record"
            assert ev["source"] == "tiny-lab"
            assert "sequence" in ev

    def test_record_emits_new_best_event(self, loop: ResearchLoop, project_dir: Path):
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        with patch.object(loop, "_sleep"):
            loop._handle_record(ctx, project)

        events = load_events(project_dir)
        new_best_events = [e for e in events if e["event"] == "new_best"]
        assert len(new_best_events) == 1
        assert new_best_events[0]["data"]["exp_id"] == "EXP-002"
        assert new_best_events[0]["data"]["metric_value"] == 0.5


class TestCircuitBreakerWarning:
    def test_warning_event_emitted(self, loop: ResearchLoop, project_dir: Path):
        """Warning emitted when invalid count reaches threshold-1."""
        ledger_path = project_dir / "research" / "ledger.jsonl"
        # Write exactly threshold-1 (4) INVALID entries
        for i in range(4):
            entry = {
                "id": f"EXP-{i+2:03d}", "question": "q", "family": "test",
                "changed_variable": "lr", "value": "0.05", "status": "done",
                "class": "INVALID", "primary_metric": {"loss": None},
                "decision": "invalid",
            }
            with ledger_path.open("a") as f:
                f.write(json.dumps(entry) + "\n")

        result = loop._check_circuit_breaker()
        assert result is False  # not yet at threshold

        events = load_events(project_dir)
        warning_events = [e for e in events if e["event"] == "circuit_breaker_warning"]
        assert len(warning_events) == 1
        assert warning_events[0]["data"]["invalid_count"] == 4


class TestExperimentReports:
    """F5: Auto-generated per-experiment markdown reports."""

    def test_report_written_on_record(self, loop: ResearchLoop, project_dir: Path):
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test lr"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test lr"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        with patch.object(loop, "_sleep"):
            loop._handle_record(ctx, project)

        report_path = project_dir / "research" / "reports" / "EXP-002.md"
        assert report_path.exists()
        content = report_path.read_text()
        assert "# EXP-002" in content
        assert "test lr" in content
        assert "**WIN**" in content
        assert "Lever: lr" in content

    def test_report_failure_does_not_crash(self, loop: ResearchLoop, project_dir: Path):
        """Report write failure should not break the record handler."""
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        with patch.object(loop, "_write_experiment_report", side_effect=OSError("disk full")):
            with patch.object(loop, "_sleep"):
                loop._handle_record(ctx, project)  # should not raise


class TestUntilIdle:
    """Tests for --until-idle mode."""

    @pytest.fixture()
    def idle_loop(self, project_dir: Path) -> ResearchLoop:
        with patch("tiny_lab.loop.get_provider") as mock_provider:
            provider = MagicMock()
            provider.name = "mock"
            mock_provider.return_value = provider
            return ResearchLoop(project_dir, until_idle=True)

    def test_until_idle_stops_when_queue_empty(self, idle_loop: ResearchLoop, project_dir: Path):
        """until_idle=True: empty queue → shutdown instead of GENERATE."""
        project = _load_project(project_dir)
        ctx = CycleContext()
        state = idle_loop._handle_check_queue(ctx, project)
        assert idle_loop._shutdown is True
        assert state == State.CHECK_QUEUE

    def test_until_idle_emits_idle_stop_event(self, idle_loop: ResearchLoop, project_dir: Path):
        """until_idle=True: IDLE_STOP event is emitted when queue exhausted."""
        project = _load_project(project_dir)
        ctx = CycleContext()
        idle_loop._handle_check_queue(ctx, project)

        events = load_events(project_dir)
        idle_events = [e for e in events if e["event"] == "idle_stop"]
        assert len(idle_events) == 1
        assert idle_events[0]["data"]["reason"] == "queue_exhausted"

    def test_until_idle_selects_when_pending(self, idle_loop: ResearchLoop, project_dir: Path):
        """until_idle=True: pending hypotheses → SELECT as normal."""
        _add_hypotheses(project_dir, [
            {"id": "H-1", "status": "pending", "lever": "lr", "value": "0.05", "description": "test"},
        ])
        project = _load_project(project_dir)
        ctx = CycleContext()
        state = idle_loop._handle_check_queue(ctx, project)
        assert state == State.SELECT
        assert idle_loop._shutdown is False

    def test_default_mode_generates_when_empty(self, loop: ResearchLoop, project_dir: Path):
        """until_idle=False (default): empty queue → GENERATE as before."""
        project = _load_project(project_dir)
        ctx = CycleContext()
        state = loop._handle_check_queue(ctx, project)
        assert state == State.GENERATE
        assert loop._shutdown is False
