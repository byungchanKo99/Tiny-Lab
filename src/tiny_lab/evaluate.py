"""EVALUATE plugins — score experiment results."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .envutil import make_env
from .errors import EvaluateError
from .logging import log
from .providers.base import AIProvider
from .schemas import validate_eval_result, ValidationError


def extract_metric_from_stdout(stdout: str, metric_name: str) -> float | None:
    """Extract metric from the last JSON object in stdout."""
    for raw in reversed(stdout.splitlines()):
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if metric_name in data:
            return data[metric_name]
        if "metric" in data and metric_name in data["metric"]:
            return data["metric"][metric_name]
        for val in data.values():
            if isinstance(val, dict) and metric_name in val:
                return val[metric_name]
    return None


def evaluate_stdout_json(
    project: dict[str, Any],
    run_result: subprocess.CompletedProcess[str] | None,
) -> float | None:
    """Extract numeric metric from stdout JSON."""
    metric_name = project["metric"]["name"]
    if run_result and run_result.returncode == 0:
        return extract_metric_from_stdout(run_result.stdout, metric_name)
    return None


EVAL_MAX_RETRIES = 2
EVAL_RETRY_DELAYS = [5, 15]


def evaluate_with_script(
    project: dict[str, Any],
    run_result: subprocess.CompletedProcess[str] | None,
    exp_id: str,
    project_dir: Path,
) -> float | None:
    """Run a separate evaluation script that outputs JSON with the metric."""
    import time

    eval_config = project.get("evaluate", {})
    eval_command = eval_config.get("command") or project["baseline"].get("eval_command")
    if not eval_command:
        log("EVALUATE[script]: no eval command configured")
        return None

    workdir = project.get("workdir", ".")
    workdir_path = project_dir / workdir
    env = make_env(project_dir, exp_id)
    max_retries = eval_config.get("max_retries", EVAL_MAX_RETRIES)

    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                eval_command, shell=True, text=True, capture_output=True,
                cwd=str(workdir_path), env=env, timeout=300,
            )
        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                delay = EVAL_RETRY_DELAYS[min(attempt, len(EVAL_RETRY_DELAYS) - 1)]
                log(f"EVALUATE[script]: timed out (attempt {attempt + 1}), retrying in {delay}s")
                time.sleep(delay)
                continue
            log("EVALUATE[script]: eval script timed out after all retries")
            return None

        if result.returncode != 0:
            if attempt < max_retries:
                delay = EVAL_RETRY_DELAYS[min(attempt, len(EVAL_RETRY_DELAYS) - 1)]
                log(f"EVALUATE[script]: failed (exit={result.returncode}, attempt {attempt + 1}), retrying in {delay}s")
                time.sleep(delay)
                continue
            log(f"EVALUATE[script]: eval script failed (exit={result.returncode}) after all retries")
            return None

        metric_name = project["metric"]["name"]
        return extract_metric_from_stdout(result.stdout, metric_name)

    return None


def evaluate_with_llm(
    project: dict[str, Any],
    run_result: subprocess.CompletedProcess[str] | None,
    hypothesis: dict[str, Any],
    exp_id: str,
    project_dir: Path,
    provider: AIProvider | None = None,
) -> float | None:
    """AI provider evaluates artifacts. Non-deterministic."""
    if provider is None:
        raise EvaluateError("evaluate.type=llm requires an AI provider")

    eval_config = project.get("evaluate", {})
    artifacts = eval_config.get("artifacts", [])
    criteria = eval_config.get("criteria", [])
    score_range = eval_config.get("score_range", [1, 10])

    artifacts_desc = "\n".join(f"- {a}" for a in artifacts) if artifacts else "- (check project workdir for outputs)"
    criteria_desc = "\n".join(f"- {c}" for c in criteria) if criteria else "- General quality assessment"

    prompt = f"""You are the evaluator for the research loop.

PROJECT: {project['name']}
EXPERIMENT: {exp_id}
HYPOTHESIS: {hypothesis['description']}
METRIC: {project['metric']['name']} (score range: {score_range[0]}-{score_range[1]})

ARTIFACTS TO EVALUATE:
{artifacts_desc}

EVALUATION CRITERIA:
{criteria_desc}

TASK:
1. Read/view each artifact listed above.
2. Evaluate against each criterion.
3. Assign a single numeric score from {score_range[0]} to {score_range[1]}.
4. Output your result as a single JSON line to stdout:
   {{"score": <number>, "reasoning": "<brief explanation>"}}

Write the JSON result to research/.eval_result_{exp_id}.json

Be objective. Score based on the criteria, not on effort."""

    max_attempts = 2
    last_errors = ""
    for attempt in range(1, max_attempts + 1):
        current_prompt = prompt
        if attempt > 1:
            current_prompt += f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION: {last_errors}\nPlease fix the output format and try again."

        log(f"EVALUATE[llm]: calling {provider.name} for {exp_id} (attempt {attempt}/{max_attempts})")
        try:
            provider.run(current_prompt, tools=["Read", "Bash"], max_turns=10, cwd=str(project_dir))
        except RuntimeError:
            log(f"EVALUATE[llm]: subagent call failed for {exp_id}")
            return None

        eval_result_path = project_dir / "research" / f".eval_result_{exp_id}.json"
        if not eval_result_path.exists():
            last_errors = "Result file not created"
            log(f"EVALUATE[llm]: {exp_id} — result file not found")
            continue

        try:
            data = json.loads(eval_result_path.read_text())
        except json.JSONDecodeError as e:
            last_errors = f"Invalid JSON: {e}"
            log(f"EVALUATE[llm]: {exp_id} — invalid JSON in result file")
            continue

        # Validate against schema
        range_tuple = (score_range[0], score_range[1])
        errors = validate_eval_result(data, score_range=range_tuple, strict=False)
        if errors:
            last_errors = "; ".join(errors)
            log(f"EVALUATE[llm]: {exp_id} — validation failed: {errors}")
            continue

        score = data["score"]
        log(f"EVALUATE[llm]: {exp_id} scored {score} -- {data.get('reasoning', '')[:80]}")
        return float(score)

    log(f"EVALUATE[llm]: could not extract valid score for {exp_id} after {max_attempts} attempts")
    return None


def judge_verdict(project: dict[str, Any], new_metric: float | None, baseline_metric: float | None) -> str:
    """Compare experiment metric against baseline."""
    if new_metric is None:
        return "INVALID"
    if baseline_metric is None:
        return "INCONCLUSIVE"
    direction = project["metric"].get("direction", "minimize")
    if direction == "minimize":
        return "WIN" if new_metric < baseline_metric else "LOSS"
    else:
        return "WIN" if new_metric > baseline_metric else "LOSS"


def dispatch_evaluate(
    project: dict[str, Any],
    run_result: subprocess.CompletedProcess[str] | None,
    hypothesis: dict[str, Any],
    exp_id: str,
    project_dir: Path,
    provider: AIProvider | None = None,
) -> float | None:
    """Route to the correct EVALUATE plugin based on project.yaml evaluate.type."""
    eval_type = project.get("evaluate", {}).get("type", "stdout_json")

    if eval_type == "stdout_json":
        return evaluate_stdout_json(project, run_result)
    elif eval_type == "script":
        return evaluate_with_script(project, run_result, exp_id, project_dir)
    elif eval_type == "llm":
        return evaluate_with_llm(project, run_result, hypothesis, exp_id, project_dir, provider)
    else:
        raise ValueError(f"Unknown evaluate type: {eval_type}")
