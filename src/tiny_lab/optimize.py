"""Optimizer inner loop for phase type=optimize.

Runs N trials of a command with varied parameters,
tracks the best result. Reused from v4 core logic.
"""
from __future__ import annotations

import random
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging import log


@dataclass
class OptimizeResult:
    best_value: float | None
    best_params: dict[str, Any]
    n_trials: int
    total_seconds: float
    all_trials: list[dict[str, Any]] = field(default_factory=list)


def inject_flag(cmd: str, flag: str, old_value: str, new_value: Any) -> str:
    """Replace a CLI flag's value in a command string, or append if not present."""
    pattern = re.compile(re.escape(flag) + r"\s+" + re.escape(str(old_value)))
    replacement = f"{flag} {new_value}"
    if pattern.search(cmd):
        return pattern.sub(replacement, cmd)
    return f"{cmd} {flag} {new_value}"


def _sample_param(spec: dict[str, Any]) -> Any:
    ptype = spec["type"]
    if ptype == "categorical":
        return random.choice(spec["choices"])
    elif ptype == "int":
        return random.randint(int(spec["low"]), int(spec["high"]))
    elif ptype == "float":
        if spec.get("log"):
            import math
            return math.exp(random.uniform(math.log(spec["low"]), math.log(spec["high"])))
        return random.uniform(spec["low"], spec["high"])
    return None


def _extract_metric(stdout: str, metric_name: str) -> float | None:
    """Extract metric from last JSON object in stdout."""
    import json
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if metric_name in data:
                return float(data[metric_name])
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return None


def _is_better(new: float, old: float | None, direction: str) -> bool:
    if old is None:
        return True
    return new < old if direction == "minimize" else new > old


def run_optimize(
    base_command: str,
    phase_config: dict[str, Any],
    metric_name: str,
    direction: str,
    project_dir: Path,
    levers: dict[str, Any] | None = None,
) -> OptimizeResult:
    """Run the optimizer inner loop for a phase.

    Args:
        base_command: The baseline command to modify
        phase_config: The phase's optimize section from research_plan.yaml
        metric_name: Metric to extract from stdout
        direction: "minimize" or "maximize"
        project_dir: Project root
        levers: CLI flag mappings (lever_name → {flag, baseline})
    """
    opt_type = phase_config.get("type", "random")
    time_budget = phase_config.get("time_budget", 300)
    max_trials = phase_config.get("n_trials", 20)
    search_space = phase_config.get("search_space", {})
    approaches = phase_config.get("approaches", {})
    levers = levers or {}

    best_value: float | None = None
    best_params: dict[str, Any] = {}
    all_trials: list[dict[str, Any]] = []
    start = time.monotonic()

    # For each approach
    for approach_name, approach_cfg in (approaches.items() if approaches else {"default": {}}.items()):
        model = approach_cfg.get("model", approach_name) if isinstance(approach_cfg, dict) else approach_name
        approach_space = search_space.get(approach_name, {})

        if not approach_space:
            # No search space — single run with this approach
            cmd = base_command
            if "model" in levers:
                ml = levers["model"]
                cmd = inject_flag(cmd, ml["flag"], ml.get("baseline", ""), model)

            log(f"OPTIMIZE: running {approach_name} (no search_space, single run)")
            result = subprocess.run(
                cmd, shell=True, text=True, capture_output=True,
                cwd=str(project_dir), timeout=time_budget + 60,
            )
            value = _extract_metric(result.stdout, metric_name) if result.returncode == 0 else None
            trial = {"approach": approach_name, "params": {}, "value": value, "state": "complete" if value else "fail"}
            all_trials.append(trial)
            if value is not None and _is_better(value, best_value, direction):
                best_value = value
                best_params = {"model": model}
            continue

        # With search space — run N trials
        for i in range(max_trials):
            if time.monotonic() - start >= time_budget:
                log(f"OPTIMIZE: time budget reached after {i} trials for {approach_name}")
                break

            params = {name: _sample_param(spec) for name, spec in approach_space.items()}
            cmd = base_command

            # Inject model
            if "model" in levers:
                ml = levers["model"]
                cmd = inject_flag(cmd, ml["flag"], ml.get("baseline", ""), model)

            # Inject params
            for param_name, value in params.items():
                lever = levers.get(param_name)
                if lever and "flag" in lever:
                    cmd = inject_flag(cmd, lever["flag"], lever.get("baseline", ""), value)
                else:
                    cmd = f"{cmd} --{param_name} {value}"

            try:
                result = subprocess.run(
                    cmd, shell=True, text=True, capture_output=True,
                    cwd=str(project_dir), timeout=time_budget,
                )
                value = _extract_metric(result.stdout, metric_name) if result.returncode == 0 else None
            except subprocess.TimeoutExpired:
                value = None

            trial = {
                "approach": approach_name, "params": params,
                "value": value, "state": "complete" if value is not None else "fail",
            }
            all_trials.append(trial)

            if value is not None and _is_better(value, best_value, direction):
                best_value = value
                best_params = {"model": model, **params}

    total_seconds = time.monotonic() - start
    n = len(all_trials)
    log(f"OPTIMIZE: {n} trials in {total_seconds:.1f}s, best={best_value}")

    return OptimizeResult(
        best_value=best_value,
        best_params=best_params,
        n_trials=n,
        total_seconds=total_seconds,
        all_trials=all_trials,
    )
