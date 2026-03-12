"""Tests for baseline measurement."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tiny_lab.baseline import ensure_baseline


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "ledger.jsonl").touch()
    return tmp_path


def _project(metric_name: str = "loss", eval_type: str = "stdout_json") -> dict:
    return {
        "name": "test",
        "baseline": {"command": "echo '{\"loss\": 1.0}'"},
        "metric": {"name": metric_name},
        "levers": {"lr": {"space": [0.01]}},
        "evaluate": {"type": eval_type},
    }


class TestEnsureBaseline:
    def test_skips_if_baseline_exists(self, project_dir: Path):
        # Write a BASELINE entry to the ledger
        entry = {
            "id": "EXP-001", "question": "Baseline measurement", "family": "test",
            "changed_variable": "baseline", "value": "baseline", "control": "EXP-001",
            "status": "done", "class": "BASELINE",
            "primary_metric": {"loss": 1.0, "baseline": 1.0, "delta_pct": 0.0},
            "decision": "baseline",
        }
        (project_dir / "research" / "ledger.jsonl").write_text(json.dumps(entry) + "\n")
        assert ensure_baseline(_project(), project_dir) is True

    def test_returns_false_without_baseline_command(self, project_dir: Path):
        project = _project()
        project["baseline"] = {}
        assert ensure_baseline(project, project_dir) is False

    @patch("tiny_lab.baseline.dispatch_run")
    def test_records_baseline_on_success(self, mock_run, project_dir: Path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 1.5}\n', stderr=""
        )
        assert ensure_baseline(_project(), project_dir) is True

        # Verify it was written to ledger
        lines = (project_dir / "research" / "ledger.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["class"] == "BASELINE"
        assert entry["primary_metric"]["loss"] == 1.5

    @patch("tiny_lab.baseline.dispatch_run")
    def test_returns_false_on_run_failure(self, mock_run, project_dir: Path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=1, stdout="", stderr="error"
        )
        assert ensure_baseline(_project(), project_dir) is False

    @patch("tiny_lab.baseline.dispatch_run")
    def test_returns_false_on_timeout(self, mock_run, project_dir: Path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=60)
        assert ensure_baseline(_project(), project_dir) is False

    @patch("tiny_lab.baseline.dispatch_run")
    def test_returns_false_when_metric_not_in_output(self, mock_run, project_dir: Path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"accuracy": 0.9}\n', stderr=""
        )
        assert ensure_baseline(_project(), project_dir) is False

    @patch("tiny_lab.baseline.dispatch_run")
    def test_returns_false_for_llm_eval_type(self, mock_run, project_dir: Path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 1.0}\n', stderr=""
        )
        assert ensure_baseline(_project(eval_type="llm"), project_dir) is False
