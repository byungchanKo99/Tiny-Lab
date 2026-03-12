"""Tests for EVALUATE plugins — pure function tests."""
from __future__ import annotations

import subprocess

import pytest

from tiny_lab.evaluate import extract_metric_from_stdout, judge_verdict, evaluate_stdout_json


# ---------------------------------------------------------------------------
# extract_metric_from_stdout
# ---------------------------------------------------------------------------

class TestExtractMetricFromStdout:
    def test_simple_json(self):
        stdout = '{"loss": 0.42}\n'
        assert extract_metric_from_stdout(stdout, "loss") == 0.42

    def test_nested_metric_key(self):
        stdout = '{"metric": {"loss": 0.42}}\n'
        assert extract_metric_from_stdout(stdout, "loss") == 0.42

    def test_nested_in_arbitrary_dict(self):
        stdout = '{"results": {"loss": 0.42}}\n'
        assert extract_metric_from_stdout(stdout, "loss") == 0.42

    def test_last_json_wins(self):
        stdout = '{"loss": 1.0}\n{"loss": 0.5}\n'
        assert extract_metric_from_stdout(stdout, "loss") == 0.5

    def test_non_json_lines_skipped(self):
        stdout = 'Training...\nEpoch 1\n{"loss": 0.3}\n'
        assert extract_metric_from_stdout(stdout, "loss") == 0.3

    def test_missing_metric(self):
        stdout = '{"accuracy": 0.9}\n'
        assert extract_metric_from_stdout(stdout, "loss") is None

    def test_empty_stdout(self):
        assert extract_metric_from_stdout("", "loss") is None

    def test_no_json_at_all(self):
        assert extract_metric_from_stdout("hello world\n", "loss") is None

    def test_malformed_json_skipped(self):
        stdout = '{bad json}\n{"loss": 0.1}\n'
        assert extract_metric_from_stdout(stdout, "loss") == 0.1

    def test_integer_metric(self):
        stdout = '{"score": 85}\n'
        assert extract_metric_from_stdout(stdout, "score") == 85


# ---------------------------------------------------------------------------
# evaluate_stdout_json
# ---------------------------------------------------------------------------

class TestEvaluateStdoutJson:
    def _project(self):
        return {"metric": {"name": "loss"}}

    def test_extracts_from_successful_run(self):
        result = subprocess.CompletedProcess(args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="")
        assert evaluate_stdout_json(self._project(), result) == 0.5

    def test_returns_none_on_nonzero_exit(self):
        result = subprocess.CompletedProcess(args="", returncode=1, stdout='{"loss": 0.5}\n', stderr="")
        assert evaluate_stdout_json(self._project(), result) is None

    def test_returns_none_when_result_is_none(self):
        assert evaluate_stdout_json(self._project(), None) is None


# ---------------------------------------------------------------------------
# judge_verdict
# ---------------------------------------------------------------------------

class TestJudgeVerdict:
    def _project(self, direction="minimize"):
        return {"metric": {"name": "loss", "direction": direction}}

    def test_win_minimize(self):
        assert judge_verdict(self._project("minimize"), 0.5, 1.0) == "WIN"

    def test_loss_minimize(self):
        assert judge_verdict(self._project("minimize"), 1.5, 1.0) == "LOSS"

    def test_win_maximize(self):
        assert judge_verdict(self._project("maximize"), 1.5, 1.0) == "WIN"

    def test_loss_maximize(self):
        assert judge_verdict(self._project("maximize"), 0.5, 1.0) == "LOSS"

    def test_invalid_when_metric_is_none(self):
        assert judge_verdict(self._project(), None, 1.0) == "INVALID"

    def test_inconclusive_when_baseline_is_none(self):
        assert judge_verdict(self._project(), 0.5, None) == "INCONCLUSIVE"

    def test_equal_is_loss_minimize(self):
        assert judge_verdict(self._project("minimize"), 1.0, 1.0) == "LOSS"

    def test_equal_is_loss_maximize(self):
        assert judge_verdict(self._project("maximize"), 1.0, 1.0) == "LOSS"
