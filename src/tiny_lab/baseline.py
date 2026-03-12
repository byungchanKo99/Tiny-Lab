"""Baseline measurement for the research loop."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .evaluate import evaluate_stdout_json, evaluate_with_script
from .ledger import append_ledger, get_baseline_metric
from .logging import log
from .run import dispatch_run


def ensure_baseline(project: dict[str, Any], project_dir: Path) -> bool:
    """Run baseline command and record to ledger if no BASELINE entry exists."""
    metric_name = project["metric"]["name"]
    if get_baseline_metric(project_dir, metric_name) is not None:
        log("BASELINE: already recorded in ledger")
        return True

    baseline_cmd = project.get("baseline", {}).get("command")
    if not baseline_cmd:
        log("BASELINE: no baseline.command in project.yaml — cannot establish baseline")
        return False

    log(f"BASELINE: running baseline command: {baseline_cmd[:120]}")
    try:
        run_result = dispatch_run(project, baseline_cmd, "BASELINE", project_dir)
    except (subprocess.TimeoutExpired, ValueError) as e:
        log(f"BASELINE: failed to run — {e}")
        return False

    if run_result.returncode != 0:
        log(f"BASELINE: command failed (exit={run_result.returncode})")
        log(f"BASELINE: stderr={run_result.stderr[:500]}")
        return False

    eval_type = project.get("evaluate", {}).get("type", "stdout_json")
    if eval_type == "stdout_json":
        metric_val = evaluate_stdout_json(project, run_result)
    elif eval_type == "script":
        metric_val = evaluate_with_script(project, run_result, "BASELINE", project_dir)
    else:
        log("BASELINE: evaluate.type=llm — baseline metric must be set manually")
        return False

    if metric_val is None:
        log(f"BASELINE: could not extract {metric_name} from baseline output")
        log(f"BASELINE: stdout={run_result.stdout[:500]}")
        return False

    entry = {
        "id": "EXP-001",
        "question": "Baseline measurement",
        "family": project["name"],
        "changed_variable": "baseline",
        "value": "baseline",
        "control": "EXP-001",
        "status": "done",
        "class": "BASELINE",
        "primary_metric": {
            metric_name: metric_val,
            "baseline": metric_val,
            "delta_pct": 0.0,
        },
        "decision": "baseline",
        "notes": f"Command: {baseline_cmd}",
    }
    append_ledger(project_dir, entry)
    log(f"BASELINE: recorded {metric_name}={metric_val}")
    return True
