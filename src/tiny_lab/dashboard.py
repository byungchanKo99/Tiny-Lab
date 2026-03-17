"""Domain query functions for status and board dashboards."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .events import load_events
from .generate import load_generate_history
from .ledger import load_ledger, get_baseline_metric, find_best_result
from .paths import state_path, lock_path, queue_path
from .project import load_project
from .queue import load_queue


def build_status_data(project_dir: Path) -> dict[str, Any]:
    """Build structured status data."""
    _state_path = state_path(project_dir)
    _lock_path = lock_path(project_dir)
    _queue_path = queue_path(project_dir)

    # Loop alive?
    alive = False
    pid = None
    if _lock_path.exists():
        try:
            pid = int(_lock_path.read_text().strip())
            os.kill(pid, 0)
            alive = True
        except (ValueError, OSError):
            pass

    data: dict[str, Any] = {
        "loop": "RUNNING" if alive else "STOPPED",
        "pid": pid,
    }

    # State
    if _state_path.exists():
        try:
            state = json.loads(_state_path.read_text())
            data["state"] = state.get("state")
            data["updated_at"] = state.get("updated_at")
            ctx = state.get("context", {})
            data["current_hypothesis"] = ctx.get("hypothesis_id")
        except json.JSONDecodeError:
            pass

    # Queue stats
    queue_counts: dict[str, int] = {}
    if _queue_path.exists():
        try:
            qdata = yaml.safe_load(_queue_path.read_text()) or {}
            for h in qdata.get("hypotheses", []):
                s = h.get("status", "unknown")
                queue_counts[s] = queue_counts.get(s, 0) + 1
        except yaml.YAMLError:
            queue_counts["error"] = -1  # signal corrupt queue
    data["queue"] = queue_counts

    # Recent ledger entries
    ledger = load_ledger(project_dir)
    recent = ledger[-5:]
    data["recent_experiments"] = [
        {
            "id": r.get("id"),
            "class": r.get("class"),
            "metric": {k: v for k, v in r.get("primary_metric", {}).items() if k not in ("baseline", "delta_pct")},
            "description": r.get("question", "")[:60],
        }
        for r in recent
    ]

    data["recent_events"] = load_events(project_dir, last_n=5)

    return data


def build_board_data(project_dir: Path) -> dict[str, Any] | None:
    """Load and compute all data needed for the experiment dashboard."""
    try:
        project = load_project(project_dir)
    except FileNotFoundError:
        return None

    metric_name = project["metric"]["name"]
    direction = project["metric"].get("direction", "minimize")
    ledger = load_ledger(project_dir)
    baseline = get_baseline_metric(project_dir, metric_name)
    queue = load_queue(project_dir)

    # Best result
    best_row = find_best_result(ledger, metric_name, direction)

    # Class counts
    counts: dict[str, int] = {}
    for row in ledger:
        c = row.get("class", "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1

    # Queue counts
    queue_counts: dict[str, int] = {}
    for h in queue:
        s = h.get("status", "unknown")
        queue_counts[s] = queue_counts.get(s, 0) + 1

    # Extract baseline command from ledger or project config
    baseline_command = project.get("baseline", {}).get("command", "")
    baseline_entry = next((r for r in ledger if r.get("class") == "BASELINE"), None)
    if baseline_entry and baseline_entry.get("config", {}).get("baseline_command"):
        baseline_command = baseline_entry["config"]["baseline_command"]

    return {
        "project": project,
        "metric_name": metric_name,
        "direction": direction,
        "ledger": ledger,
        "baseline": baseline,
        "baseline_command": baseline_command,
        "best_row": best_row,
        "counts": counts,
        "queue_counts": queue_counts,
        "gen_history": load_generate_history(project_dir),
        "recent_events": load_events(project_dir, last_n=10),
    }
