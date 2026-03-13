"""Pluggable inner-loop optimizers for hypothesis search spaces.

Dispatches to optuna (TPE), grid, random, or custom optimizers based on
hypothesis or project configuration. Each optimizer runs N trials of the
base experiment command with varied parameters and returns the best result.
"""
from __future__ import annotations

import itertools
import json
import random as _random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import OptimizeError
from .evaluate import extract_metric_from_stdout
from .logging import log
from .run import run_experiment_command


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class OptimizeResult:
    """Result from an inner-loop optimization run."""

    best_value: float | None
    best_params: dict[str, Any]
    n_trials: int
    total_seconds: float
    all_trials: list[dict[str, Any]] = field(default_factory=list)
    best_stdout: str = ""
    best_stderr: str = ""


# ---------------------------------------------------------------------------
# Search space helpers
# ---------------------------------------------------------------------------

_VALID_PARAM_TYPES = {"int", "float", "categorical"}


def parse_search_space(space_dict: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate and normalize a search space definition.

    Each parameter must have a 'type' and type-specific bounds:
    - int/float: low, high, optional log (bool), optional step
    - categorical: choices (list)
    """
    parsed: dict[str, dict[str, Any]] = {}
    for name, spec in space_dict.items():
        if not isinstance(spec, dict):
            raise OptimizeError(f"search_space.{name}: expected dict, got {type(spec).__name__}")
        ptype = spec.get("type")
        if ptype not in _VALID_PARAM_TYPES:
            raise OptimizeError(
                f"search_space.{name}: type must be one of {sorted(_VALID_PARAM_TYPES)}, got '{ptype}'"
            )
        if ptype in ("int", "float"):
            if "low" not in spec or "high" not in spec:
                raise OptimizeError(f"search_space.{name}: int/float params require 'low' and 'high'")
            if spec["low"] >= spec["high"]:
                raise OptimizeError(f"search_space.{name}: low ({spec['low']}) must be < high ({spec['high']})")
        elif ptype == "categorical":
            if "choices" not in spec or not isinstance(spec["choices"], list) or not spec["choices"]:
                raise OptimizeError(f"search_space.{name}: categorical params require non-empty 'choices' list")
        parsed[name] = spec
    return parsed


def _sample_param(spec: dict[str, Any]) -> Any:
    """Sample a single parameter from its spec (for random/grid)."""
    ptype = spec["type"]
    if ptype == "categorical":
        return _random.choice(spec["choices"])
    elif ptype == "int":
        return _random.randint(int(spec["low"]), int(spec["high"]))
    elif ptype == "float":
        if spec.get("log"):
            import math
            log_low = math.log(spec["low"])
            log_high = math.log(spec["high"])
            return math.exp(_random.uniform(log_low, log_high))
        return _random.uniform(spec["low"], spec["high"])
    return None  # unreachable after parse_search_space validation


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def build_trial_command(
    base_command: str,
    params: dict[str, Any],
    project: dict[str, Any],
) -> str:
    """Convert trial parameters into CLI flags appended to the base command.

    1. If the param name matches a lever with a 'flag' mapping, substitute the flag.
    2. Otherwise, append --param_name value.
    """
    import re
    cmd = base_command
    levers = project.get("levers", {})

    for param_name, value in params.items():
        lever = levers.get(param_name)
        if lever and "flag" in lever:
            flag = lever["flag"]
            baseline_value = str(lever.get("baseline", ""))
            pattern = re.compile(re.escape(flag) + r"\s+" + re.escape(baseline_value))
            replacement = f"{flag} {value}"
            if pattern.search(cmd):
                cmd = pattern.sub(replacement, cmd)
            else:
                cmd = f"{cmd} {flag} {value}"
        else:
            cmd = f"{cmd} --{param_name} {value}"

    return cmd


# ---------------------------------------------------------------------------
# Trial runner
# ---------------------------------------------------------------------------

def _run_single_trial(
    project: dict[str, Any],
    command: str,
    exp_id: str,
    trial_idx: int,
    project_dir: Path,
) -> subprocess.CompletedProcess[str] | None:
    """Execute a single trial, returning CompletedProcess or None on failure."""
    trial_exp_id = f"{exp_id}_t{trial_idx}"
    try:
        return run_experiment_command(project, command, trial_exp_id, project_dir)
    except Exception as e:
        log(f"OPTIMIZE: trial {trial_idx} failed — {e}")
        return None


def _extract_trial_metric(
    result: subprocess.CompletedProcess[str] | None,
    metric_name: str,
) -> float | None:
    """Extract metric value from a trial's stdout."""
    if result is None or result.returncode != 0:
        return None
    return extract_metric_from_stdout(result.stdout, metric_name)


def _is_better(new: float, old: float | None, direction: str) -> bool:
    """Check if new metric is better than old given direction."""
    if old is None:
        return True
    if direction == "minimize":
        return new < old
    return new > old


# ---------------------------------------------------------------------------
# Pluggable optimizers
# ---------------------------------------------------------------------------

def _run_random(
    project: dict[str, Any],
    base_command: str,
    search_space: dict[str, dict[str, Any]],
    project_dir: Path,
    exp_id: str,
    *,
    n_trials: int | None = None,
    time_budget: int | None = None,
) -> OptimizeResult:
    """Random sampling optimizer — no external dependencies."""
    metric_name = project["metric"]["name"]
    direction = project["metric"].get("direction", "minimize")
    max_trials = n_trials or 20

    best_value: float | None = None
    best_params: dict[str, Any] = {}
    best_stdout = ""
    best_stderr = ""
    all_trials: list[dict[str, Any]] = []
    start = time.monotonic()

    for i in range(max_trials):
        if time_budget and (time.monotonic() - start) >= time_budget:
            log(f"OPTIMIZE[random]: time budget ({time_budget}s) reached after {i} trials")
            break

        params = {name: _sample_param(spec) for name, spec in search_space.items()}
        cmd = build_trial_command(base_command, params, project)
        result = _run_single_trial(project, cmd, exp_id, i, project_dir)
        value = _extract_trial_metric(result, metric_name)

        trial_record = {"params": params, "value": value, "state": "complete" if value is not None else "fail"}
        all_trials.append(trial_record)

        if value is not None and _is_better(value, best_value, direction):
            best_value = value
            best_params = params
            best_stdout = result.stdout if result else ""
            best_stderr = result.stderr if result else ""

    total_seconds = time.monotonic() - start
    log(f"OPTIMIZE[random]: {len(all_trials)} trials in {total_seconds:.1f}s, best={best_value}")

    return OptimizeResult(
        best_value=best_value,
        best_params=best_params,
        n_trials=len(all_trials),
        total_seconds=total_seconds,
        all_trials=all_trials,
        best_stdout=best_stdout,
        best_stderr=best_stderr,
    )


def _run_grid(
    project: dict[str, Any],
    base_command: str,
    search_space: dict[str, dict[str, Any]],
    project_dir: Path,
    exp_id: str,
    *,
    time_budget: int | None = None,
    **_kwargs: Any,
) -> OptimizeResult:
    """Grid search — enumerate all combinations of categorical/discrete params."""
    metric_name = project["metric"]["name"]
    direction = project["metric"].get("direction", "minimize")

    # Build discrete grid
    axes: dict[str, list[Any]] = {}
    for name, spec in search_space.items():
        if spec["type"] == "categorical":
            axes[name] = spec["choices"]
        elif spec["type"] == "int":
            step = spec.get("step", 1)
            axes[name] = list(range(int(spec["low"]), int(spec["high"]) + 1, step))
        elif spec["type"] == "float":
            # For float grid, require explicit choices or step
            step = spec.get("step")
            if step:
                vals = []
                v = spec["low"]
                while v <= spec["high"]:
                    vals.append(round(v, 10))
                    v += step
                axes[name] = vals
            else:
                # Fall back to 5 evenly spaced values
                n = 5
                lo, hi = spec["low"], spec["high"]
                axes[name] = [round(lo + (hi - lo) * i / (n - 1), 10) for i in range(n)]

    param_names = list(axes.keys())
    combinations = list(itertools.product(*(axes[n] for n in param_names)))

    best_value: float | None = None
    best_params: dict[str, Any] = {}
    best_stdout = ""
    best_stderr = ""
    all_trials: list[dict[str, Any]] = []
    start = time.monotonic()

    for i, combo in enumerate(combinations):
        if time_budget and (time.monotonic() - start) >= time_budget:
            log(f"OPTIMIZE[grid]: time budget ({time_budget}s) reached after {i} trials")
            break

        params = dict(zip(param_names, combo))
        cmd = build_trial_command(base_command, params, project)
        result = _run_single_trial(project, cmd, exp_id, i, project_dir)
        value = _extract_trial_metric(result, metric_name)

        trial_record = {"params": params, "value": value, "state": "complete" if value is not None else "fail"}
        all_trials.append(trial_record)

        if value is not None and _is_better(value, best_value, direction):
            best_value = value
            best_params = params
            best_stdout = result.stdout if result else ""
            best_stderr = result.stderr if result else ""

    total_seconds = time.monotonic() - start
    log(f"OPTIMIZE[grid]: {len(all_trials)}/{len(combinations)} trials in {total_seconds:.1f}s, best={best_value}")

    return OptimizeResult(
        best_value=best_value,
        best_params=best_params,
        n_trials=len(all_trials),
        total_seconds=total_seconds,
        all_trials=all_trials,
        best_stdout=best_stdout,
        best_stderr=best_stderr,
    )


def _run_optuna(
    project: dict[str, Any],
    base_command: str,
    search_space: dict[str, dict[str, Any]],
    project_dir: Path,
    exp_id: str,
    *,
    n_trials: int | None = None,
    time_budget: int | None = None,
) -> OptimizeResult:
    """Optuna TPE optimizer — requires optuna (lazy import)."""
    try:
        import optuna
    except ImportError:
        raise OptimizeError("optuna is not installed. Install with: pip install tiny-lab[optimize]")

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    metric_name = project["metric"]["name"]
    direction = project["metric"].get("direction", "minimize")
    optuna_direction = "minimize" if direction == "minimize" else "maximize"

    best_stdout = ""
    best_stderr = ""
    all_trials: list[dict[str, Any]] = []
    start = time.monotonic()

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_stdout, best_stderr
        params: dict[str, Any] = {}
        for name, spec in search_space.items():
            if spec["type"] == "categorical":
                params[name] = trial.suggest_categorical(name, spec["choices"])
            elif spec["type"] == "int":
                params[name] = trial.suggest_int(name, int(spec["low"]), int(spec["high"]),
                                                  step=spec.get("step", 1),
                                                  log=spec.get("log", False))
            elif spec["type"] == "float":
                params[name] = trial.suggest_float(name, spec["low"], spec["high"],
                                                    step=spec.get("step"),
                                                    log=spec.get("log", False))

        cmd = build_trial_command(base_command, params, project)
        result = _run_single_trial(project, cmd, exp_id, trial.number, project_dir)
        value = _extract_trial_metric(result, metric_name)

        trial_record = {"params": params, "value": value, "state": "complete" if value is not None else "fail"}
        all_trials.append(trial_record)

        if value is None:
            raise optuna.TrialPruned("No metric extracted")

        return value

    study = optuna.create_study(direction=optuna_direction)
    study.optimize(
        objective,
        n_trials=n_trials or 20,
        timeout=time_budget,
        show_progress_bar=False,
    )

    total_seconds = time.monotonic() - start

    if study.best_trial:
        best_value = study.best_value
        best_params = study.best_params
        # Re-run best to capture stdout (or find from trials)
        best_idx = study.best_trial.number
        if best_idx < len(all_trials) and all_trials[best_idx]["value"] is not None:
            # Reconstruct command for best stdout
            cmd = build_trial_command(base_command, best_params, project)
            re_result = _run_single_trial(project, cmd, exp_id, len(all_trials), project_dir)
            if re_result:
                best_stdout = re_result.stdout
                best_stderr = re_result.stderr
    else:
        best_value = None
        best_params = {}

    log(f"OPTIMIZE[optuna]: {len(all_trials)} trials in {total_seconds:.1f}s, best={best_value}")

    return OptimizeResult(
        best_value=best_value,
        best_params=best_params,
        n_trials=len(all_trials),
        total_seconds=total_seconds,
        all_trials=all_trials,
        best_stdout=best_stdout,
        best_stderr=best_stderr,
    )


def _run_custom(
    project: dict[str, Any],
    base_command: str,
    search_space: dict[str, dict[str, Any]],
    project_dir: Path,
    exp_id: str,
    hypothesis: dict[str, Any],
    *,
    time_budget: int | None = None,
    **_kwargs: Any,
) -> OptimizeResult:
    """Custom optimizer — runs user-provided script."""
    script = hypothesis.get("optimize_script")
    if not script:
        raise OptimizeError("optimize_type='custom' requires 'optimize_script' in hypothesis")

    metric_name = project["metric"]["name"]
    workdir = project.get("workdir", ".")
    workdir_path = project_dir / workdir

    start = time.monotonic()

    env_extra = {
        "TINYLAB_BASE_COMMAND": base_command,
        "TINYLAB_SEARCH_SPACE": json.dumps(search_space),
        "TINYLAB_METRIC_NAME": metric_name,
        "TINYLAB_DIRECTION": project["metric"].get("direction", "minimize"),
        "TINYLAB_EXP_ID": exp_id,
    }
    import os
    env = {**os.environ, **env_extra}

    try:
        result = subprocess.run(
            script, shell=True, text=True, capture_output=True,
            cwd=str(workdir_path), env=env,
            timeout=time_budget + 60 if time_budget else None,
        )
    except subprocess.TimeoutExpired:
        raise OptimizeError(f"Custom optimizer timed out after {time_budget}s")

    total_seconds = time.monotonic() - start

    # Parse result — expect JSON on last line of stdout
    best_value: float | None = None
    best_params: dict[str, Any] = {}
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            best_value = data.get(metric_name) or data.get("best_value")
            best_params = data.get("best_params", data.get("params", {}))
            break
        except json.JSONDecodeError:
            continue

    log(f"OPTIMIZE[custom]: finished in {total_seconds:.1f}s, best={best_value}")

    return OptimizeResult(
        best_value=best_value,
        best_params=best_params,
        n_trials=1,  # custom manages its own trials
        total_seconds=total_seconds,
        all_trials=[{"params": best_params, "value": best_value, "state": "complete"}],
        best_stdout=result.stdout,
        best_stderr=result.stderr,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _get_optimizer(opt_type: str) -> Any:
    """Look up optimizer function by name (allows patching in tests)."""
    optimizers = {
        "optuna": _run_optuna,
        "grid": _run_grid,
        "random": _run_random,
    }
    return optimizers.get(opt_type)


def dispatch_optimize(
    project: dict[str, Any],
    base_command: str,
    hypothesis: dict[str, Any],
    project_dir: Path,
    exp_id: str,
) -> OptimizeResult | None:
    """Route to the appropriate optimizer.

    Priority:
    1. hypothesis.optimize_type (per-hypothesis override)
    2. project.optimize.type (project default)
    3. 'optuna' fallback (falls back to 'random' if optuna not installed)

    Returns None if no search_space is defined.
    """
    # Hypothesis-level search_space overrides/extends project-level
    project_space = project.get("search_space", {})
    hypothesis_space = hypothesis.get("search_space", {})
    search_space_raw = {**project_space, **hypothesis_space}
    if not search_space_raw:
        return None

    search_space = parse_search_space(search_space_raw)
    optimize_config = project.get("optimize", {})

    # Determine optimizer type
    opt_type = (
        hypothesis.get("optimize_type")
        or optimize_config.get("type")
        or "optuna"
    )

    # Time budget and trial count
    time_budget = optimize_config.get("time_budget")
    n_trials = optimize_config.get("n_trials")

    log(f"OPTIMIZE: dispatching {opt_type} for {hypothesis.get('id', '?')} "
        f"({len(search_space)} params, time_budget={time_budget}, n_trials={n_trials})")

    if opt_type == "custom":
        return _run_custom(
            project, base_command, search_space, project_dir, exp_id, hypothesis,
            time_budget=time_budget,
        )

    if opt_type == "optuna":
        try:
            return _run_optuna(
                project, base_command, search_space, project_dir, exp_id,
                n_trials=n_trials, time_budget=time_budget,
            )
        except OptimizeError:
            log("OPTIMIZE: optuna not available, falling back to random")
            opt_type = "random"

    optimizer = _get_optimizer(opt_type)
    if optimizer is None:
        raise OptimizeError(f"Unknown optimizer type: {opt_type}")

    return optimizer(
        project, base_command, search_space, project_dir, exp_id,
        n_trials=n_trials, time_budget=time_budget,
    )
