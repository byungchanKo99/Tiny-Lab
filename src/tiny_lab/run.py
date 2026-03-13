"""RUN plugins — execute experiments."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .envutil import make_env
from .errors import RunError
from .logging import log


def run_experiment_command(
    project: dict[str, Any],
    command: str,
    exp_id: str,
    project_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Direct subprocess execution."""
    workdir = project.get("workdir", ".")
    workdir_path = project_dir / workdir
    max_seconds = (project.get("calibration", {}).get("max_total_seconds")
                   or project.get("run", {}).get("timeout"))
    env = make_env(project_dir, exp_id)
    return subprocess.run(
        command, shell=True, text=True, capture_output=True,
        cwd=str(workdir_path), env=env,
        timeout=max_seconds + 60 if max_seconds else None,
    )


def run_experiment_pipeline(
    project: dict[str, Any],
    command: str,
    exp_id: str,
    project_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute a multi-step pipeline defined in project.yaml run.steps."""
    steps = project.get("run", {}).get("steps", [])
    if not steps:
        raise ValueError("Pipeline run type requires run.steps in project.yaml")

    workdir = project.get("workdir", ".")
    workdir_path = project_dir / workdir
    env = make_env(project_dir, exp_id)

    combined_stdout = ""
    combined_stderr = ""
    background_procs: list[subprocess.Popen[str]] = []

    try:
        for step in steps:
            step_name = step.get("name", "unnamed")
            step_cmd = step.get("command", "")
            wait_seconds = step.get("wait", 0)
            background = step.get("background", False) or step_cmd.rstrip().endswith("&")

            if background:
                clean_cmd = step_cmd.rstrip().rstrip("&").strip()
                log(f"RUN[pipeline]: {step_name} (background) -> {clean_cmd}")
                proc = subprocess.Popen(
                    clean_cmd, shell=True, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=str(workdir_path), env=env,
                )
                background_procs.append(proc)
                if wait_seconds:
                    time.sleep(wait_seconds)
            else:
                log(f"RUN[pipeline]: {step_name} -> {step_cmd}")
                result = subprocess.run(
                    step_cmd, shell=True, text=True, capture_output=True,
                    cwd=str(workdir_path), env=env, timeout=300,
                )
                combined_stdout += result.stdout
                combined_stderr += result.stderr
                if result.returncode != 0:
                    log(f"RUN[pipeline]: {step_name} failed (exit={result.returncode})")
                    return subprocess.CompletedProcess(
                        args=step_cmd, returncode=result.returncode,
                        stdout=combined_stdout, stderr=combined_stderr,
                    )
    finally:
        for proc in background_procs:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    return subprocess.CompletedProcess(
        args="pipeline", returncode=0,
        stdout=combined_stdout, stderr=combined_stderr,
    )


RUN_MAX_RETRIES = 2
RUN_RETRY_DELAYS = [5, 15]


def dispatch_run(
    project: dict[str, Any],
    command: str,
    exp_id: str,
    project_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Route to the correct RUN plugin based on project.yaml run.type."""
    run_type = project.get("run", {}).get("type", "command")
    max_retries = project.get("run", {}).get("max_retries", RUN_MAX_RETRIES)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            if run_type == "command":
                return run_experiment_command(project, command, exp_id, project_dir)
            elif run_type == "pipeline":
                return run_experiment_pipeline(project, command, exp_id, project_dir)
            else:
                raise RunError(f"Unknown run type: {run_type}")
        except subprocess.TimeoutExpired as e:
            last_error = RunError(f"Experiment {exp_id} timed out: {e}")
            if attempt < max_retries:
                delay = RUN_RETRY_DELAYS[min(attempt, len(RUN_RETRY_DELAYS) - 1)]
                log(f"RUN: {exp_id} failed (attempt {attempt + 1}), retrying in {delay}s")
                time.sleep(delay)
            else:
                raise last_error from e
        except RunError as e:
            last_error = e
            if attempt < max_retries:
                delay = RUN_RETRY_DELAYS[min(attempt, len(RUN_RETRY_DELAYS) - 1)]
                log(f"RUN: {exp_id} failed (attempt {attempt + 1}), retrying in {delay}s")
                time.sleep(delay)
            else:
                raise
    raise last_error  # unreachable, but satisfies type checker
