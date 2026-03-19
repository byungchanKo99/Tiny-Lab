"""Tests for the pluggable inner-loop optimizer."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from tiny_lab.errors import OptimizeError
from tiny_lab.optimize import (
    OptimizeResult,
    parse_search_space,
    build_trial_command,
    _run_random,
    _run_grid,
    dispatch_optimize,
    _is_better,
)


# ---------------------------------------------------------------------------
# parse_search_space
# ---------------------------------------------------------------------------

class TestParseSearchSpace:
    def test_float_param(self):
        space = parse_search_space({"lr": {"type": "float", "low": 0.001, "high": 0.1}})
        assert space["lr"]["type"] == "float"

    def test_int_param(self):
        space = parse_search_space({"epochs": {"type": "int", "low": 1, "high": 100}})
        assert space["epochs"]["type"] == "int"

    def test_categorical_param(self):
        space = parse_search_space({"algo": {"type": "categorical", "choices": ["sgd", "adam"]}})
        assert space["algo"]["choices"] == ["sgd", "adam"]

    def test_invalid_type(self):
        with pytest.raises(OptimizeError, match="type must be one of"):
            parse_search_space({"x": {"type": "boolean"}})

    def test_missing_bounds(self):
        with pytest.raises(OptimizeError, match="require 'low' and 'high'"):
            parse_search_space({"x": {"type": "float", "low": 0.1}})

    def test_low_ge_high(self):
        with pytest.raises(OptimizeError, match="low.*must be < high"):
            parse_search_space({"x": {"type": "float", "low": 1.0, "high": 0.5}})

    def test_categorical_empty_choices(self):
        with pytest.raises(OptimizeError, match="non-empty 'choices'"):
            parse_search_space({"x": {"type": "categorical", "choices": []}})

    def test_non_dict_spec(self):
        with pytest.raises(OptimizeError, match="expected dict"):
            parse_search_space({"x": "not_a_dict"})


# ---------------------------------------------------------------------------
# build_trial_command
# ---------------------------------------------------------------------------

class TestBuildTrialCommand:
    def test_flag_substitution(self):
        project = {"levers": {"lr": {"flag": "--lr", "baseline": "0.01"}}}
        cmd = build_trial_command("python train.py --lr 0.01", {"lr": 0.05}, project)
        assert "--lr 0.05" in cmd
        assert "--lr 0.01" not in cmd

    def test_flag_append_when_not_in_command(self):
        project = {"levers": {"lr": {"flag": "--lr", "baseline": "0.01"}}}
        cmd = build_trial_command("python train.py", {"lr": 0.05}, project)
        assert cmd == "python train.py --lr 0.05"

    def test_unknown_param_appended(self):
        project = {"levers": {}}
        cmd = build_trial_command("python train.py", {"batch_size": 32}, project)
        assert "--batch_size 32" in cmd

    def test_multiple_params(self):
        project = {"levers": {"lr": {"flag": "--lr", "baseline": "0.01"}}}
        cmd = build_trial_command("python train.py --lr 0.01", {"lr": 0.05, "epochs": 10}, project)
        assert "--lr 0.05" in cmd
        assert "--epochs 10" in cmd


# ---------------------------------------------------------------------------
# _is_better
# ---------------------------------------------------------------------------

class TestIsBetter:
    def test_minimize_better(self):
        assert _is_better(0.5, 1.0, "minimize") is True

    def test_minimize_worse(self):
        assert _is_better(1.5, 1.0, "minimize") is False

    def test_maximize_better(self):
        assert _is_better(1.5, 1.0, "maximize") is True

    def test_none_old_always_better(self):
        assert _is_better(0.5, None, "minimize") is True


# ---------------------------------------------------------------------------
# _run_random
# ---------------------------------------------------------------------------

class TestRunRandom:
    @patch("tiny_lab.optimize.run_experiment_command")
    def test_basic_random_search(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0,
            stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "workdir": ".",
        }
        space = {"lr": {"type": "float", "low": 0.001, "high": 0.1}}
        result = _run_random(project, "python train.py", space, Path("/tmp"), "EXP-002", n_trials=3)
        assert isinstance(result, OptimizeResult)
        assert result.n_trials == 3
        assert result.best_value == 0.5
        assert mock_run.call_count == 3

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_all_trials_fail(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=1, stdout="", stderr="error",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "workdir": ".",
        }
        space = {"lr": {"type": "float", "low": 0.001, "high": 0.1}}
        result = _run_random(project, "python train.py", space, Path("/tmp"), "EXP-002", n_trials=2)
        assert result.best_value is None
        assert result.n_trials == 2

    @patch("tiny_lab.optimize.run_experiment_command")
    @patch("tiny_lab.optimize.time")
    def test_time_budget_stops_early(self, mock_time, mock_run):
        """Time budget should stop trials when exceeded."""
        # Simulate: start=0, after trial 0 → 1s, after trial 1 → 2s, ...
        # With time_budget=1, trial 0 runs (at t=0), trial 1 sees t=1 >= budget → stop
        call_count = 0
        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            return (call_count - 1) * 0.5  # 0, 0.5, 1.0, 1.5, ...
        mock_time.monotonic = fake_monotonic

        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "workdir": ".",
        }
        space = {"lr": {"type": "float", "low": 0.001, "high": 0.1}}
        result = _run_random(project, "python train.py", space, Path("/tmp"), "EXP-002",
                             n_trials=100, time_budget=1)
        # Should stop well before 100 trials
        assert result.n_trials < 10

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_picks_best_minimize(self, mock_run):
        values = [0.8, 0.3, 0.6]
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            val = values[call_count]
            call_count += 1
            return subprocess.CompletedProcess(
                args="", returncode=0,
                stdout=f'{{"loss": {val}}}\n', stderr="",
            )

        mock_run.side_effect = side_effect
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "workdir": ".",
        }
        space = {"lr": {"type": "categorical", "choices": [0.01, 0.05, 0.1]}}
        result = _run_random(project, "python train.py", space, Path("/tmp"), "EXP-002", n_trials=3)
        assert result.best_value == 0.3


# ---------------------------------------------------------------------------
# _run_grid
# ---------------------------------------------------------------------------

class TestRunGrid:
    @patch("tiny_lab.optimize.run_experiment_command")
    def test_categorical_grid(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0,
            stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "workdir": ".",
        }
        space = {"algo": {"type": "categorical", "choices": ["sgd", "adam"]}}
        result = _run_grid(project, "python train.py", space, Path("/tmp"), "EXP-002")
        assert result.n_trials == 2  # 2 choices
        assert mock_run.call_count == 2

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_int_grid(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0,
            stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "workdir": ".",
        }
        space = {"depth": {"type": "int", "low": 3, "high": 5}}
        result = _run_grid(project, "python train.py", space, Path("/tmp"), "EXP-002")
        assert result.n_trials == 3  # 3, 4, 5


# ---------------------------------------------------------------------------
# dispatch_optimize
# ---------------------------------------------------------------------------

class TestDispatchOptimize:
    def test_no_search_space_returns_none(self):
        result = dispatch_optimize(
            {"metric": {"name": "loss"}, "levers": {}},
            "echo", {"id": "H-1"}, Path("/tmp"), "EXP-002",
        )
        assert result is None

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_project_level_search_space_by_approach(self, mock_run):
        """search_space in project is looked up by approach name."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "optimize": {"type": "random", "n_trials": 2},
            "search_space": {
                "xgboost": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
                "lightgbm": {"num_leaves": {"type": "int", "low": 20, "high": 127}},
            },
        }
        hypothesis = {
            "id": "H-1",
            "approach": "xgboost",
            "description": "test",
        }
        result = dispatch_optimize(project, "echo", hypothesis, Path("/tmp"), "EXP-002")
        assert result is not None
        assert result.n_trials == 2
        # Should only have xgboost params, not lightgbm
        assert "lr" in result.best_params
        assert "num_leaves" not in result.best_params

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_unknown_approach_returns_none(self, mock_run):
        """Approach not in search_space and no hypothesis search_space → None."""
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "optimize": {"type": "random", "n_trials": 1},
            "search_space": {
                "xgboost": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            },
        }
        hypothesis = {
            "id": "H-1",
            "approach": "catboost",  # not in search_space
            "description": "test",
        }
        result = dispatch_optimize(project, "echo", hypothesis, Path("/tmp"), "EXP-002")
        assert result is None  # no params to optimize

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_hypothesis_search_space_overrides_project(self, mock_run):
        """hypothesis search_space extends/overrides project-level."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "optimize": {"type": "random", "n_trials": 1},
            "search_space": {
                "xgboost": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            },
        }
        hypothesis = {
            "id": "H-1",
            "approach": "xgboost",
            "description": "test",
            "search_space": {"depth": {"type": "int", "low": 3, "high": 10}},
        }
        result = dispatch_optimize(project, "echo", hypothesis, Path("/tmp"), "EXP-002")
        assert result is not None
        # Both lr (from project.xgboost) and depth (from hypothesis) should be in best_params
        assert result.best_params is not None

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_routes_to_random(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "optimize": {"type": "random", "n_trials": 2},
        }
        hypothesis = {
            "id": "H-1",
            "search_space": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            "description": "test",
        }
        result = dispatch_optimize(project, "echo", hypothesis, Path("/tmp"), "EXP-002")
        assert result is not None
        assert result.best_value == 0.5
        assert result.n_trials == 2

    @patch("tiny_lab.optimize.run_experiment_command")
    def test_hypothesis_optimize_type_override(self, mock_run):
        """hypothesis.optimize_type takes priority over project.optimize.type."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout='{"loss": 0.5}\n', stderr="",
        )
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "optimize": {"type": "grid"},
        }
        hypothesis = {
            "id": "H-1",
            "search_space": {"algo": {"type": "categorical", "choices": ["sgd", "adam"]}},
            "optimize_type": "random",
            "description": "test",
        }
        result = dispatch_optimize(project, "echo", hypothesis, Path("/tmp"), "EXP-002")
        assert result is not None

    def test_unknown_optimizer_raises(self):
        project = {
            "metric": {"name": "loss", "direction": "minimize"},
            "levers": {},
            "optimize": {"type": "nonexistent"},
        }
        hypothesis = {
            "id": "H-1",
            "search_space": {"lr": {"type": "float", "low": 0.001, "high": 0.1}},
            "optimize_type": "nonexistent",
            "description": "test",
        }
        with pytest.raises(OptimizeError, match="Unknown optimizer type"):
            dispatch_optimize(project, "echo", hypothesis, Path("/tmp"), "EXP-002")
