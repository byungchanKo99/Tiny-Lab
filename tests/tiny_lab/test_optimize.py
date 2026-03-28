"""Tests for optimizer inner loop."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from tiny_lab.optimize import inject_flag, _sample_param, _extract_metric, _is_better, run_optimize


class TestInjectFlag:
    def test_replaces_existing(self):
        assert inject_flag("train.py --lr 0.01", "--lr", "0.01", "0.05") == "train.py --lr 0.05"

    def test_appends_when_missing(self):
        assert inject_flag("train.py", "--lr", "0.01", "0.05") == "train.py --lr 0.05"

    def test_preserves_other_flags(self):
        result = inject_flag("train.py --lr 0.01 --epochs 10", "--lr", "0.01", "0.05")
        assert "--lr 0.05" in result
        assert "--epochs 10" in result


class TestSampleParam:
    def test_categorical(self):
        spec = {"type": "categorical", "choices": ["a", "b", "c"]}
        assert _sample_param(spec) in ["a", "b", "c"]

    def test_int(self):
        spec = {"type": "int", "low": 1, "high": 10}
        val = _sample_param(spec)
        assert isinstance(val, int)
        assert 1 <= val <= 10

    def test_float(self):
        spec = {"type": "float", "low": 0.0, "high": 1.0}
        val = _sample_param(spec)
        assert isinstance(val, float)
        assert 0.0 <= val <= 1.0


class TestExtractMetric:
    def test_extracts_from_json(self):
        assert _extract_metric('{"loss": 0.5}\n', "loss") == 0.5

    def test_last_json_line(self):
        stdout = 'progress...\n{"loss": 0.8}\nfinal\n{"loss": 0.3}\n'
        assert _extract_metric(stdout, "loss") == 0.3

    def test_missing_metric(self):
        assert _extract_metric('{"accuracy": 0.9}\n', "loss") is None

    def test_no_json(self):
        assert _extract_metric("no json here\n", "loss") is None


class TestIsBetter:
    def test_minimize(self):
        assert _is_better(0.3, 0.5, "minimize") is True
        assert _is_better(0.7, 0.5, "minimize") is False

    def test_maximize(self):
        assert _is_better(0.7, 0.5, "maximize") is True
        assert _is_better(0.3, 0.5, "maximize") is False

    def test_none_old(self):
        assert _is_better(0.5, None, "minimize") is True


class TestRunOptimize:
    @patch("tiny_lab.optimize.subprocess.run")
    def test_single_approach_no_search_space(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="",
        )
        result = run_optimize(
            base_command="python train.py",
            phase_config={"approaches": {"lstm": {"model": "lstm"}}},
            metric_name="loss",
            direction="minimize",
            project_dir=tmp_path,
            levers={"model": {"flag": "--model", "baseline": "default"}},
        )
        assert result.n_trials == 1
        assert result.best_value == 0.5

    @patch("tiny_lab.optimize.subprocess.run")
    def test_with_search_space(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.3}\n', stderr="",
        )
        result = run_optimize(
            base_command="python train.py",
            phase_config={
                "type": "random",
                "time_budget": 300,
                "n_trials": 3,
                "approaches": {"lstm": {"model": "lstm"}},
                "search_space": {
                    "lstm": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
                },
            },
            metric_name="loss",
            direction="minimize",
            project_dir=tmp_path,
        )
        assert result.n_trials == 3
        assert result.best_value == 0.3
        assert mock_run.call_count == 3

    @patch("tiny_lab.optimize.subprocess.run")
    def test_all_fail(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=1, stdout="", stderr="error",
        )
        result = run_optimize(
            base_command="echo",
            phase_config={
                "n_trials": 2,
                "approaches": {"x": {}},
                "search_space": {"x": {"a": {"type": "int", "low": 1, "high": 5}}},
            },
            metric_name="loss",
            direction="minimize",
            project_dir=tmp_path,
        )
        assert result.best_value is None
        assert result.n_trials == 2
