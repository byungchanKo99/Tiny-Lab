"""Tests for ResearchLoop state handler methods."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from tiny_lab.errors import OptimizeError
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


    def test_invalid_hypothesis_skipped_with_log(self, loop: ResearchLoop, project_dir: Path):
        """Hypothesis with wrong fields (e.g. changed_variable instead of lever) is skipped."""
        _add_hypotheses(project_dir, [
            {"id": "H-bad", "status": "pending", "changed_variable": "model", "value": "xgb", "description": "test"},
        ])
        project = _load_project(project_dir)
        ctx = CycleContext()
        state = loop._handle_select(ctx, project)
        assert state == State.CHECK_QUEUE  # skipped, not BUILD_COMMAND
        assert ctx.hypothesis is None

        # Verify it was marked as skipped
        queue = yaml.safe_load((project_dir / "research" / "hypothesis_queue.yaml").read_text())
        assert queue["hypotheses"][0]["status"] == "skipped"


class TestHandleBuildCommand:
    def test_successful_flag_build(self, loop: ResearchLoop, project_dir: Path):
        project = _load_project(project_dir)
        ctx = CycleContext(hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"})
        state = loop._handle_build_command(ctx, project)
        assert state == State.OPTIMIZE
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


class TestHandleRunSingle:
    @patch("tiny_lab.loop.dispatch_run")
    def test_successful_run(self, mock_run, loop: ResearchLoop, project_dir: Path):
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
        project = _load_project(project_dir)
        ctx = CycleContext(command="echo test", exp_id="EXP-002")
        state = loop._handle_run_single(ctx, project)
        assert state == State.EVALUATE
        assert ctx.run_result is not None
        assert ctx.run_result.returncode == 0

    @patch("tiny_lab.loop.dispatch_run")
    def test_run_failure_continues(self, mock_run, loop: ResearchLoop, project_dir: Path):
        from tiny_lab.errors import RunError
        mock_run.side_effect = RunError("Experiment EXP-002 timed out")
        project = _load_project(project_dir)
        ctx = CycleContext(command="echo test", exp_id="EXP-002")
        state = loop._handle_run_single(ctx, project)
        assert state == State.EVALUATE
        assert ctx.run_result is None


class TestHandleOptimize:
    def test_no_search_space_falls_back_to_single_run(self, loop: ResearchLoop, project_dir: Path):
        """v1 hypothesis without search_space goes through single RUN."""
        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"},
            command="echo test", exp_id="EXP-002",
        )
        with patch("tiny_lab.loop.dispatch_run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
            state = loop._handle_optimize(ctx, project)
        assert state == State.EVALUATE

    @patch("tiny_lab.optimize.dispatch_optimize")
    def test_with_search_space_runs_optimizer(self, mock_opt, loop: ResearchLoop, project_dir: Path):
        """v2 hypothesis with search_space dispatches to optimizer."""
        from tiny_lab.optimize import OptimizeResult
        mock_opt.return_value = OptimizeResult(
            best_value=0.3, best_params={"lr": 0.05},
            n_trials=5, total_seconds=10.0,
            best_stdout='{"loss": 0.3}\n', best_stderr="",
        )
        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={
                "id": "H-10", "approach": "xgboost", "description": "test",
                "search_space": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            },
            command="echo test", exp_id="EXP-002",
        )
        state = loop._handle_optimize(ctx, project)
        assert state == State.EVALUATE
        assert ctx.optimize_result is not None
        assert ctx.new_metric == 0.3
        assert ctx.run_result is not None

    @patch("tiny_lab.optimize.dispatch_optimize")
    def test_project_level_search_space_triggers_optimizer(self, mock_opt, loop: ResearchLoop, project_dir: Path):
        """v2 hypothesis without search_space uses project-level search_space."""
        from tiny_lab.optimize import OptimizeResult
        mock_opt.return_value = OptimizeResult(
            best_value=0.4, best_params={"lr": 0.01},
            n_trials=3, total_seconds=5.0,
            best_stdout='{"loss": 0.4}\n', best_stderr="",
        )
        # Add search_space to project.yaml
        project = _load_project(project_dir)
        project["search_space"] = {"lr": {"type": "float", "low": 0.001, "high": 0.1}}
        (project_dir / "research" / "project.yaml").write_text(yaml.dump(project))
        project = _load_project(project_dir)

        ctx = CycleContext(
            hypothesis={"id": "H-10", "approach": "xgboost", "description": "test"},
            command="echo test", exp_id="EXP-002",
        )
        state = loop._handle_optimize(ctx, project)
        assert state == State.EVALUATE
        assert ctx.optimize_result is not None
        mock_opt.assert_called_once()

    @patch("tiny_lab.optimize.dispatch_optimize", side_effect=OptimizeError("fail"))
    def test_optimizer_error_falls_back(self, mock_opt, loop: ResearchLoop, project_dir: Path):
        """OptimizeError falls back to single RUN."""
        from tiny_lab.errors import OptimizeError as OE
        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={
                "id": "H-10", "approach": "xgboost", "description": "test",
                "search_space": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            },
            command="echo test", exp_id="EXP-002",
        )
        with patch("tiny_lab.loop.dispatch_run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
            state = loop._handle_optimize(ctx, project)
        assert state == State.EVALUATE


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
        assert recorded["hypothesis_id"] == "H-1"
        assert recorded["config"] == {"lr": "0.05"}
        assert recorded["reasoning"] == ""

    def test_records_hypothesis_reasoning(self, loop: ResearchLoop, project_dir: Path):
        """Ledger entry includes reasoning from hypothesis."""
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{"id": "H-2", "status": "running", "lever": "lr", "value": "0.05",
                                        "description": "lower lr", "reasoning": "LR 0.01 won, try 0.05"}])

        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-2", "lever": "lr", "value": "0.05", "description": "lower lr",
                         "reasoning": "LR 0.01 won, try 0.05"},
            command="echo test", exp_id="EXP-003", new_metric=0.4, verdict="WIN",
        )
        with patch.object(loop, "_sleep"):
            loop._handle_record(ctx, project)

        lines = (project_dir / "research" / "ledger.jsonl").read_text().strip().splitlines()
        recorded = json.loads(lines[-1])
        assert recorded["hypothesis_id"] == "H-2"
        assert recorded["reasoning"] == "LR 0.01 won, try 0.05"
        assert recorded["config"] == {"lr": "0.05"}

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


class TestHandleRecordV2:
    """Tests for v2 (approach-based) hypothesis recording."""

    def test_records_v2_hypothesis_with_optimize_result(self, loop: ResearchLoop, project_dir: Path):
        from tiny_lab.optimize import OptimizeResult
        baseline = {
            "id": "EXP-001", "question": "baseline", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(baseline) + "\n")
        _add_hypotheses(project_dir, [{
            "id": "H-10", "status": "running", "approach": "xgboost",
            "description": "XGBoost stacking",
        }])

        project = _load_project(project_dir)
        opt_result = OptimizeResult(
            best_value=0.3, best_params={"lr": 0.05, "depth": 5},
            n_trials=10, total_seconds=30.0,
        )
        ctx = CycleContext(
            hypothesis={"id": "H-10", "approach": "xgboost", "description": "XGBoost stacking"},
            command="echo test", exp_id="EXP-002", new_metric=0.3, verdict="WIN",
            optimize_result=opt_result,
        )
        with patch.object(loop, "_sleep"):
            state = loop._handle_record(ctx, project)
        assert state == State.CHECK_QUEUE

        lines = (project_dir / "research" / "ledger.jsonl").read_text().strip().splitlines()
        recorded = json.loads(lines[-1])
        assert recorded["changed_variable"] == "xgboost"
        assert recorded["approach"] == "xgboost"
        assert recorded["optimize_result"]["n_trials"] == 10
        assert recorded["optimize_result"]["best_params"] == {"lr": 0.05, "depth": 5}
        assert recorded["config"] == {"lr": 0.05, "depth": 5}


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
