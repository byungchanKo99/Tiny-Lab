"""Ledger read/write utilities for experiment results."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .logging import log
from .paths import ledger_path
from .schemas import validate, ValidationError


def load_ledger(project_dir: Path) -> list[dict[str, Any]]:
    """Load all ledger entries from ledger.jsonl."""
    path = ledger_path(project_dir)
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # Warn on invalid entries but still include them
        errors = validate(entry, "ledger_entry", strict=False)
        if errors:
            log(f"LEDGER: warning — entry {entry.get('id', '?')} has issues: {errors}")
        rows.append(entry)
    return rows


def append_ledger(project_dir: Path, entry: dict[str, Any]) -> None:
    """Append a single entry to ledger.jsonl. Validates before writing."""
    validate(entry, "ledger_entry")
    path = ledger_path(project_dir)
    with path.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def get_baseline_metric(project_dir: Path, metric_name: str) -> float | None:
    """Get the baseline metric value from the ledger."""
    for row in reversed(load_ledger(project_dir)):
        if row.get("class") == "BASELINE":
            pm = row.get("primary_metric", {})
            if metric_name in pm:
                return pm[metric_name]
    return None


def find_best_result(
    ledger: list[dict[str, Any]],
    metric_name: str,
    direction: str = "minimize",
) -> dict[str, Any] | None:
    """Find the best experiment result by metric value."""
    best = None
    for row in ledger:
        if row.get("class") in ("BASELINE", "INVALID"):
            continue
        val = row.get("primary_metric", {}).get(metric_name)
        if val is None:
            continue
        if best is None:
            best = row
        else:
            best_val = best["primary_metric"][metric_name]
            if direction == "maximize" and val > best_val:
                best = row
            elif direction == "minimize" and val < best_val:
                best = row
    return best


def next_experiment_id(ledger: list[dict[str, Any]]) -> str:
    """Generate the next sequential experiment ID."""
    max_num = 1
    for row in ledger:
        exp_id = row.get("id", "")
        m = re.match(r"EXP-(\d+)", exp_id)
        if m:
            max_num = max(max_num, int(m.group(1)) + 1)
    return f"EXP-{max_num:03d}"
