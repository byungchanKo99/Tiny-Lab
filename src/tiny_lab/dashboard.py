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
from .project import load_project, levers as get_levers, baseline_command as get_baseline_cmd
from .queue import load_queue


def _build_experiment_diff(row: dict[str, Any], lever_baselines: dict[str, Any]) -> str:
    """Build a human-readable diff string showing what changed from baseline.

    Examples:
      "model: lgbm → xgboost"
      "lr: 0.01 → 0.05, depth: 6 → 4"
      "approach: stacking_ensemble (new)"
    """
    if row.get("class") == "BASELINE":
        return "(baseline)"

    parts = []

    # Approach-based
    if row.get("approach"):
        parts.append(f"approach: {row['approach']}")
        opt = row.get("optimize_result", {})
        bp = opt.get("best_params", {})
        if bp:
            for k, v in bp.items():
                bl = lever_baselines.get(k, {}).get("baseline")
                if bl is not None:
                    parts.append(f"{k}: {bl} → {v}")
                else:
                    parts.append(f"{k}: {v}")
        return ", ".join(parts)

    # Legacy lever-based
    changed = row.get("changed_variable", "")
    value = row.get("value")
    config = row.get("config", {})

    if isinstance(value, dict):
        # multi-lever
        for k, v in value.items():
            bl = lever_baselines.get(k, {}).get("baseline")
            if bl is not None:
                parts.append(f"{k}: {bl} → {v}")
            else:
                parts.append(f"{k}: {v}")
    elif changed and value is not None:
        bl = lever_baselines.get(changed, {}).get("baseline")
        if bl is not None:
            parts.append(f"{changed}: {bl} → {value}")
        else:
            parts.append(f"{changed}: {value}")
    elif config:
        for k, v in config.items():
            if k == "baseline_command":
                continue
            bl = lever_baselines.get(k, {}).get("baseline")
            if bl is not None:
                parts.append(f"{k}: {bl} → {v}")
            else:
                parts.append(f"{k}: {v}")

    return ", ".join(parts) if parts else ""


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

    # Approach-level aggregation for charts
    approach_summary: dict[str, dict[str, Any]] = {}
    for row in ledger:
        if row.get("class") == "BASELINE":
            continue
        key = row.get("approach") or row.get("changed_variable", "unknown")
        if key not in approach_summary:
            approach_summary[key] = {"wins": 0, "losses": 0, "best_value": None, "best_params": {}}
        cls = row.get("class", "")
        if cls == "WIN":
            approach_summary[key]["wins"] += 1
        elif cls == "LOSS":
            approach_summary[key]["losses"] += 1
        val = row.get("primary_metric", {}).get(metric_name)
        if val is not None:
            cur_best = approach_summary[key]["best_value"]
            if cur_best is None or (direction == "maximize" and val > cur_best) or (direction == "minimize" and val < cur_best):
                approach_summary[key]["best_value"] = val
                opt = row.get("optimize_result", {})
                approach_summary[key]["best_params"] = opt.get("best_params", {})

    # Build diff for each experiment
    lever_baselines = get_levers(project)
    for row in ledger:
        row["_diff"] = _build_experiment_diff(row, lever_baselines)
        # Flatten optimizer best_params for easy display
        opt = row.get("optimize_result", {})
        if opt.get("best_params"):
            row["_best_params_str"] = ", ".join(f"{k}={v}" for k, v in opt["best_params"].items())
        else:
            row["_best_params_str"] = ""

    # --- Insights ---
    insights: dict[str, Any] = {}
    non_baseline = [r for r in ledger if r.get("class") != "BASELINE"]

    # Experiment rate & timing
    if len(non_baseline) >= 2:
        from .events import load_events as _load_events
        events = _load_events(project_dir, last_n=999)
        done_events = [e for e in events if e.get("event") == "experiment_done"]
        if len(done_events) >= 2:
            from datetime import datetime
            try:
                first_ts = datetime.fromisoformat(done_events[0]["timestamp"])
                last_ts = datetime.fromisoformat(done_events[-1]["timestamp"])
                elapsed = (last_ts - first_ts).total_seconds()
                if elapsed > 0:
                    rate = len(done_events) / (elapsed / 3600)
                    insights["experiments_per_hour"] = round(rate, 1)
                    insights["total_elapsed_minutes"] = round(elapsed / 60, 1)
            except (KeyError, ValueError):
                pass

    # Total optimizer trials
    total_trials = sum(r.get("optimize_result", {}).get("n_trials", 0) for r in ledger)
    total_opt_seconds = sum(r.get("optimize_result", {}).get("total_seconds", 0) for r in ledger)
    insights["total_optimizer_trials"] = total_trials
    insights["total_optimizer_seconds"] = round(total_opt_seconds, 1)

    # Pending queue + ETA
    pending_count = queue_counts.get("pending", 0)
    insights["pending_count"] = pending_count
    if pending_count > 0 and insights.get("experiments_per_hour"):
        eta_hours = pending_count / insights["experiments_per_hour"]
        insights["eta_minutes"] = round(eta_hours * 60, 1)

    # Convergence: experiments since last best
    if best_row and non_baseline:
        best_idx = next((i for i, r in enumerate(non_baseline) if r.get("id") == best_row.get("id")), None)
        if best_idx is not None:
            insights["experiments_since_best"] = len(non_baseline) - 1 - best_idx

    # Recent trend (last 5 metric values)
    recent_vals = []
    for r in non_baseline[-5:]:
        v = r.get("primary_metric", {}).get(metric_name)
        if v is not None:
            recent_vals.append(v)
    if len(recent_vals) >= 2:
        if direction == "maximize":
            improving = recent_vals[-1] > recent_vals[0]
        else:
            improving = recent_vals[-1] < recent_vals[0]
        insights["recent_trend"] = "improving" if improving else "plateaued"
        insights["recent_values"] = recent_vals

    # Next pending hypothesis
    pending = [h for h in queue if h.get("status") == "pending"]
    if pending:
        nxt = pending[0]
        insights["next_hypothesis"] = {
            "id": nxt.get("id"),
            "approach": nxt.get("approach", nxt.get("lever", "")),
            "description": nxt.get("description", "")[:80],
        }

    # Approaches not yet tried
    tried_approaches = set()
    for r in non_baseline:
        a = r.get("approach") or r.get("changed_variable")
        if a:
            tried_approaches.add(a)
    search_sp = project.get("search_space", {})
    if search_sp:
        # If there are categorical params with model choices
        for param, spec in search_sp.items():
            if isinstance(spec, dict) and spec.get("type") == "categorical":
                untried = [c for c in spec.get("choices", []) if c not in tried_approaches]
                if untried:
                    insights.setdefault("untried_approaches", []).extend(untried)

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
        "approach_summary": approach_summary,
        "insights": insights,
        "gen_history": load_generate_history(project_dir),
        "recent_events": load_events(project_dir, last_n=10),
    }
