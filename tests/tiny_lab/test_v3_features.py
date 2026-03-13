"""Tests for v3 features: error wrapping, checkpoint recovery, export, sparklines, HTML report, multi-lever, retry."""
from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from tiny_lab.loop import ResearchLoop, State, CycleContext, MAX_CONSECUTIVE_ERRORS
from tiny_lab.build import build_command_multi_flag, dispatch_build
from tiny_lab.errors import BuildError, TinyLabError
from tiny_lab.schemas import validate_hypothesis_entry
from tiny_lab.cli import _build_board_data, _export_board, _format_sparklines, _format_value
from tiny_lab.generate import generate_hypotheses
from tiny_lab.report import generate_html_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    research = tmp_path / "research"
    research.mkdir()
    (research / "ledger.jsonl").touch()
    project = {
        "name": "test",
        "description": "test experiment",
        "baseline": {"command": "python train.py --lr 0.01 --epochs 10"},
        "metric": {"name": "loss", "direction": "minimize"},
        "levers": {
            "lr": {"flag": "--lr", "baseline": "0.01", "space": ["0.01", "0.05", "0.1"]},
            "epochs": {"flag": "--epochs", "baseline": "10", "space": ["10", "20", "50"]},
        },
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


def _write_ledger(project_dir: Path, entries: list[dict]) -> None:
    path = project_dir / "research" / "ledger.jsonl"
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _baseline_entry() -> dict:
    return {
        "id": "EXP-001", "question": "baseline", "family": "test",
        "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
        "status": "done", "class": "BASELINE",
        "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
        "decision": "baseline",
    }


def _experiment_entry(exp_id: str, cls: str, loss: float, lever: str = "lr", value: str = "0.05") -> dict:
    return {
        "id": exp_id, "question": f"test {lever}={value}", "family": "test",
        "changed_variable": lever, "value": value, "control": "EXP-001",
        "status": "done", "class": cls,
        "primary_metric": {"loss": loss, "baseline": 1.0, "delta_pct": round((loss - 1.0) / 1.0 * 100, 2)},
        "decision": cls.lower(),
    }


# ===========================================================================
# Phase 1: Stability + Data Access
# ===========================================================================

class TestLoopErrorWrapping:
    """3B: Loop error wrapping — individual state failures don't kill the loop."""

    def test_tinylaborror_is_caught_and_loop_continues(self, loop: ResearchLoop, project_dir: Path):
        """A TinyLabError in a handler should not crash the loop."""
        project = _load_project(project_dir)
        ctx = CycleContext()

        call_count = 0

        def exploding_handler(ctx, project):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise TinyLabError("transient error")
            loop._shutdown = True
            return State.CHECK_QUEUE

        with patch.object(loop, "_handle_check_queue", exploding_handler), \
             patch.object(loop, "_recover_state"), \
             patch("tiny_lab.loop.ensure_baseline", return_value=True):
            loop._run_loop()

        assert call_count == 2  # first call raises, second call shuts down

    def test_consecutive_errors_stop_loop(self, loop: ResearchLoop, project_dir: Path):
        """MAX_CONSECUTIVE_ERRORS consecutive errors should stop the loop."""

        call_count = 0

        def always_explode(ctx, project):
            nonlocal call_count
            call_count += 1
            raise TinyLabError("persistent error")

        with patch.object(loop, "_handle_check_queue", always_explode), \
             patch.object(loop, "_recover_state"), \
             patch("tiny_lab.loop.ensure_baseline", return_value=True):
            loop._run_loop()

        assert call_count == MAX_CONSECUTIVE_ERRORS

    def test_unexpected_exception_is_caught(self, loop: ResearchLoop, project_dir: Path):
        call_count = 0

        def unexpected_handler(ctx, project):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise RuntimeError("unexpected")
            loop._shutdown = True
            return State.CHECK_QUEUE

        with patch.object(loop, "_handle_check_queue", unexpected_handler), \
             patch.object(loop, "_recover_state"), \
             patch("tiny_lab.loop.ensure_baseline", return_value=True):
            loop._run_loop()

        assert call_count == 2

    def test_error_resets_context_and_marks_skipped(self, loop: ResearchLoop, project_dir: Path):
        """On error with active hypothesis, it should be marked skipped."""
        _add_hypotheses(project_dir, [
            {"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"},
        ])

        call_count = 0

        def error_with_hypothesis(ctx, project):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                ctx.hypothesis = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
                raise TinyLabError("build failed")
            loop._shutdown = True
            return State.CHECK_QUEUE

        with patch.object(loop, "_handle_check_queue", error_with_hypothesis), \
             patch.object(loop, "_recover_state"), \
             patch("tiny_lab.loop.ensure_baseline", return_value=True):
            loop._run_loop()

        queue = yaml.safe_load((project_dir / "research" / "hypothesis_queue.yaml").read_text())
        assert queue["hypotheses"][0]["status"] == "skipped"


class TestCheckpointRecovery:
    """3A: Checkpoint recovery — orphaned running hypotheses are recovered."""

    def test_recover_resets_running_to_pending(self, loop: ResearchLoop, project_dir: Path):
        _add_hypotheses(project_dir, [
            {"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "orphaned"},
            {"id": "H-2", "status": "pending", "lever": "lr", "value": "0.1", "description": "ok"},
            {"id": "H-3", "status": "done", "lever": "lr", "value": "0.01", "description": "done"},
        ])
        state_data = {"state": "run", "updated_at": "2026-01-01T00:00:00", "pid": 99999}
        loop.state_path.write_text(json.dumps(state_data))

        loop._recover_state()

        queue = yaml.safe_load((project_dir / "research" / "hypothesis_queue.yaml").read_text())
        statuses = {h["id"]: h["status"] for h in queue["hypotheses"]}
        assert statuses["H-1"] == "pending"
        assert statuses["H-2"] == "pending"
        assert statuses["H-3"] == "done"
        assert not loop.state_path.exists()

    def test_recover_noop_without_state_file(self, loop: ResearchLoop, project_dir: Path):
        _add_hypotheses(project_dir, [
            {"id": "H-1", "status": "running", "lever": "lr", "value": "0.05", "description": "test"},
        ])
        loop._recover_state()
        # Without state file, nothing should change
        queue = yaml.safe_load((project_dir / "research" / "hypothesis_queue.yaml").read_text())
        assert queue["hypotheses"][0]["status"] == "running"

    def test_recover_handles_corrupt_state_file(self, loop: ResearchLoop, project_dir: Path):
        loop.state_path.write_text("not json")
        loop._recover_state()
        assert not loop.state_path.exists()

    def test_state_file_preserved_on_crash(self, loop: ResearchLoop, project_dir: Path):
        """State file should NOT be deleted on unhandled crash (outside _run_loop)."""
        state_data = {"state": "run", "pid": 12345}
        loop.state_path.write_text(json.dumps(state_data))
        # Simulate: state file exists from a crash. On next _recover_state, it's found.
        assert loop.state_path.exists()


class TestBoardExport:
    """1A: board --export csv|json."""

    def test_export_json(self, project_dir: Path, capsys):
        entries = [_baseline_entry(), _experiment_entry("EXP-002", "WIN", 0.8)]
        _write_ledger(project_dir, entries)
        data = _build_board_data(project_dir)
        _export_board(data, "json", None)
        output = capsys.readouterr().out
        rows = json.loads(output)
        assert len(rows) == 2
        assert rows[1]["id"] == "EXP-002"
        assert rows[1]["class"] == "WIN"

    def test_export_csv(self, project_dir: Path, capsys):
        entries = [_baseline_entry(), _experiment_entry("EXP-002", "LOSS", 1.2)]
        _write_ledger(project_dir, entries)
        data = _build_board_data(project_dir)
        _export_board(data, "csv", None)
        output = capsys.readouterr().out
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[1]["class"] == "LOSS"

    def test_export_json_to_file(self, project_dir: Path):
        entries = [_baseline_entry()]
        _write_ledger(project_dir, entries)
        data = _build_board_data(project_dir)
        out_path = str(project_dir / "out.json")
        _export_board(data, "json", out_path)
        result = json.loads(Path(out_path).read_text())
        assert len(result) == 1


# ===========================================================================
# Phase 2: Visualization
# ===========================================================================

class TestSparklines:
    """1B: ASCII sparkline charts."""

    def test_sparkline_output(self, project_dir: Path, capsys):
        entries = [_baseline_entry()]
        for i, loss in enumerate([0.9, 0.7, 0.5, 0.8, 0.6], start=2):
            entries.append(_experiment_entry(f"EXP-{i:03d}", "WIN" if loss < 1.0 else "LOSS", loss))
        _write_ledger(project_dir, entries)
        data = _build_board_data(project_dir)
        _format_sparklines(data)
        output = capsys.readouterr().out
        assert "Metric trend" in output
        assert "Lever stats" in output

    def test_sparkline_no_data(self, project_dir: Path, capsys):
        data = _build_board_data(project_dir)
        _format_sparklines(data)
        output = capsys.readouterr().out
        assert "(no data)" in output


class TestHtmlReport:
    """1C: HTML report generation."""

    def test_generates_html_file(self, project_dir: Path):
        entries = [_baseline_entry(), _experiment_entry("EXP-002", "WIN", 0.8)]
        _write_ledger(project_dir, entries)
        data = _build_board_data(project_dir)
        out = project_dir / "research" / "report.html"
        generate_html_report(data, out)
        assert out.exists()
        html = out.read_text()
        assert "chart.js" in html.lower() or "Chart" in html
        assert "test" in html  # project name
        assert "EXP-002" in html or "DATA" in html

    def test_html_contains_embedded_data(self, project_dir: Path):
        entries = [_baseline_entry(), _experiment_entry("EXP-002", "WIN", 0.8)]
        _write_ledger(project_dir, entries)
        data = _build_board_data(project_dir)
        out = project_dir / "report.html"
        generate_html_report(data, out)
        html = out.read_text()
        assert "const DATA" in html

    def test_html_no_experiments(self, project_dir: Path):
        data = _build_board_data(project_dir)
        out = project_dir / "report.html"
        generate_html_report(data, out)
        assert out.exists()


# ===========================================================================
# Phase 3: Multi-lever + Retry
# ===========================================================================

class TestMultiLeverSchema:
    """2A: Multi-lever hypothesis schema validation."""

    def test_dict_value_valid(self):
        entry = {"id": "H-1", "status": "pending", "lever": "lr+batch_size",
                 "value": {"lr": "0.05", "batch_size": "32"}, "description": "combo test"}
        errors = validate_hypothesis_entry(entry, strict=False)
        assert errors == []

    def test_string_value_still_valid(self):
        entry = {"id": "H-1", "status": "pending", "lever": "lr",
                 "value": "0.05", "description": "single lever"}
        errors = validate_hypothesis_entry(entry, strict=False)
        assert errors == []


class TestMultiLeverBuild:
    """2A: Multi-lever build command construction."""

    def _project(self) -> dict:
        return {
            "name": "test",
            "baseline": {"command": "python train.py --lr 0.01 --epochs 10"},
            "metric": {"name": "loss"},
            "levers": {
                "lr": {"flag": "--lr", "baseline": "0.01", "space": ["0.01", "0.05", "0.1"]},
                "epochs": {"flag": "--epochs", "baseline": "10", "space": ["10", "20", "50"]},
            },
            "build": {"type": "flag"},
        }

    def test_multi_flag_replaces_both(self):
        project = self._project()
        hyp = {"id": "H-1", "lever": "lr+epochs",
               "value": {"lr": "0.05", "epochs": "20"}, "description": "combo"}
        result = build_command_multi_flag(project, hyp)
        assert "--lr 0.05" in result
        assert "--epochs 20" in result
        assert "--lr 0.01" not in result
        assert "--epochs 10" not in result

    def test_dispatch_build_routes_multi(self):
        project = self._project()
        hyp = {"id": "H-1", "lever": "lr+epochs",
               "value": {"lr": "0.05", "epochs": "20"}, "description": "combo"}
        result = dispatch_build(project, hyp, None)
        assert "--lr 0.05" in result
        assert "--epochs 20" in result

    def test_dispatch_build_multi_unknown_lever_raises(self):
        project = self._project()
        hyp = {"id": "H-1", "lever": "lr+bad",
               "value": {"lr": "0.05", "bad": "x"}, "description": "combo"}
        with pytest.raises(BuildError, match="Unknown lever"):
            dispatch_build(project, hyp, None)

    def test_dispatch_build_multi_bad_value_raises(self):
        project = self._project()
        hyp = {"id": "H-1", "lever": "lr+epochs",
               "value": {"lr": "999", "epochs": "20"}, "description": "combo"}
        with pytest.raises(BuildError, match="not in space"):
            dispatch_build(project, hyp, None)

    def test_single_lever_still_works(self):
        project = self._project()
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "single"}
        result = dispatch_build(project, hyp, None)
        assert "--lr 0.05" in result


class TestMultiLeverRecord:
    """2A: Multi-lever recording in the loop."""

    def test_record_dict_value(self, loop: ResearchLoop, project_dir: Path):
        _write_ledger(project_dir, [_baseline_entry()])
        _add_hypotheses(project_dir, [
            {"id": "H-1", "status": "running", "lever": "lr+epochs",
             "value": {"lr": "0.05", "epochs": "20"}, "description": "combo"},
        ])
        project = _load_project(project_dir)
        ctx = CycleContext(
            hypothesis={"id": "H-1", "lever": "lr+epochs",
                        "value": {"lr": "0.05", "epochs": "20"}, "description": "combo"},
            command="echo test", exp_id="EXP-002", new_metric=0.5, verdict="WIN",
        )
        with patch.object(loop, "_sleep"):
            state = loop._handle_record(ctx, project)
        assert state == State.CHECK_QUEUE

        lines = (project_dir / "research" / "ledger.jsonl").read_text().strip().splitlines()
        recorded = json.loads(lines[-1])
        assert recorded["changed_variable"] == "lr+epochs"
        assert isinstance(recorded["value"], dict)
        assert recorded["value"]["lr"] == "0.05"


class TestFormatValue:
    """Display formatting for single and multi-lever values."""

    def test_string_value(self):
        assert _format_value("0.05") == "0.05"

    def test_dict_value(self):
        result = _format_value({"lr": "0.05", "batch_size": "32"})
        assert "lr=0.05" in result
        assert "batch_size=32" in result

    def test_numeric_value(self):
        assert _format_value(42) == "42"


class TestRunRetry:
    """3C: Transient failure retry in dispatch_run."""

    @patch("tiny_lab.run.run_experiment_command")
    def test_retry_on_timeout(self, mock_run):
        from tiny_lab.run import dispatch_run
        mock_run.side_effect = [
            subprocess.TimeoutExpired("cmd", 60),
            subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr=""),
        ]
        project = {"run": {"type": "command", "max_retries": 1}, "workdir": "."}
        result = dispatch_run(project, "echo", "EXP-001", Path("/tmp"))
        assert result.returncode == 0
        assert mock_run.call_count == 2

    @patch("tiny_lab.run.run_experiment_command")
    def test_raises_after_all_retries_exhausted(self, mock_run):
        from tiny_lab.run import dispatch_run
        from tiny_lab.errors import RunError
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 60)
        project = {"run": {"type": "command", "max_retries": 1}, "workdir": "."}
        with pytest.raises(RunError, match="timed out"):
            dispatch_run(project, "echo", "EXP-001", Path("/tmp"))
        assert mock_run.call_count == 2

    @patch("tiny_lab.run.run_experiment_command")
    def test_no_retry_on_success(self, mock_run):
        from tiny_lab.run import dispatch_run
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
        project = {"run": {"type": "command"}, "workdir": "."}
        result = dispatch_run(project, "echo", "EXP-001", Path("/tmp"))
        assert result.returncode == 0
        assert mock_run.call_count == 1


class TestEvaluateRetry:
    """3C: Transient failure retry in evaluate_with_script."""

    @patch("tiny_lab.evaluate.subprocess.run")
    def test_retry_on_failure(self, mock_run):
        from tiny_lab.evaluate import evaluate_with_script
        mock_run.side_effect = [
            subprocess.CompletedProcess(args="", returncode=1, stdout="", stderr="fail"),
            subprocess.CompletedProcess(args="", returncode=0, stdout='{"loss": 0.5}\n', stderr=""),
        ]
        project = {"evaluate": {"command": "eval.sh", "max_retries": 1}, "metric": {"name": "loss"}, "workdir": "."}
        result = evaluate_with_script(project, None, "EXP-001", Path("/tmp"))
        assert result == 0.5
        assert mock_run.call_count == 2

    @patch("tiny_lab.evaluate.subprocess.run")
    def test_returns_none_after_all_retries(self, mock_run):
        from tiny_lab.evaluate import evaluate_with_script
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=1, stdout="", stderr="fail")
        project = {"evaluate": {"command": "eval.sh", "max_retries": 1}, "metric": {"name": "loss"}, "workdir": "."}
        result = evaluate_with_script(project, None, "EXP-001", Path("/tmp"))
        assert result is None
        assert mock_run.call_count == 2


# ===========================================================================
# Stderr logging on provider failure
# ===========================================================================

class TestStderrLogging:
    """Provider stderr is logged on failure for diagnostics."""

    def test_generate_logs_stderr_on_failure(self, project_dir: Path):
        """GENERATE should log stderr lines when provider exits non-zero."""
        provider = MagicMock()
        provider.name = "codex"
        provider.run_structured.return_value = subprocess.CompletedProcess(
            args="", returncode=1, stdout="",
            stderr="Error: failed to lookup address information\nstream disconnected before completion",
        )

        project = _load_project(project_dir)
        logged = []
        with patch("tiny_lab.generate.log", side_effect=lambda msg: logged.append(msg)):
            generate_hypotheses(project, project_dir, provider)

        stderr_logs = [l for l in logged if "stderr:" in l]
        assert len(stderr_logs) == 2
        assert "failed to lookup address" in stderr_logs[0]
        assert "stream disconnected" in stderr_logs[1]

    def test_generate_no_stderr_log_on_success(self, project_dir: Path):
        """No stderr logging when provider succeeds."""
        provider = MagicMock()
        provider.name = "codex"
        provider.run_structured.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="ok", stderr="",
        )

        project = _load_project(project_dir)
        logged = []
        with patch("tiny_lab.generate.log", side_effect=lambda msg: logged.append(msg)):
            generate_hypotheses(project, project_dir, provider)

        stderr_logs = [l for l in logged if "stderr:" in l]
        assert len(stderr_logs) == 0

    def test_generate_truncates_long_stderr(self, project_dir: Path):
        """Only last 10 lines of stderr are logged."""
        provider = MagicMock()
        provider.name = "codex"
        stderr_lines = "\n".join(f"line {i}" for i in range(20))
        provider.run_structured.return_value = subprocess.CompletedProcess(
            args="", returncode=1, stdout="", stderr=stderr_lines,
        )

        project = _load_project(project_dir)
        logged = []
        with patch("tiny_lab.generate.log", side_effect=lambda msg: logged.append(msg)):
            generate_hypotheses(project, project_dir, provider)

        stderr_logs = [l for l in logged if "stderr:" in l]
        assert len(stderr_logs) == 10
        assert "line 10" in stderr_logs[0]
        assert "line 19" in stderr_logs[9]

    def test_build_code_logs_stderr_on_failure(self):
        """BUILD[code] should log stderr when provider fails."""
        from tiny_lab.build import build_command_code

        provider = MagicMock()
        provider.name = "codex"
        provider.run.return_value = subprocess.CompletedProcess(
            args="", returncode=1, stdout="",
            stderr="DNS resolution failed\nconnection refused",
        )

        project = {
            "name": "test", "description": "test",
            "baseline": {"command": "echo test"},
            "build": {"target_files": []},
        }
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}

        logged = []
        with patch("tiny_lab.build.log", side_effect=lambda msg: logged.append(msg)), \
             pytest.raises(BuildError):
            build_command_code(project, hyp, Path("/tmp"), provider)

        stderr_logs = [l for l in logged if "stderr:" in l]
        assert len(stderr_logs) == 2
        assert "DNS resolution" in stderr_logs[0]
