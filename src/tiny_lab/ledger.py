"""Ledger read/write utilities for experiment results."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .logging import log
from .schemas import validate, ValidationError


def load_ledger(project_dir: Path) -> list[dict[str, Any]]:
    """Load all ledger entries from ledger.jsonl."""
    path = project_dir / "research" / "ledger.jsonl"
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
    path = project_dir / "research" / "ledger.jsonl"
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


def next_experiment_id(ledger: list[dict[str, Any]]) -> str:
    """Generate the next sequential experiment ID."""
    max_num = 1
    for row in ledger:
        exp_id = row.get("id", "")
        m = re.match(r"EXP-(\d+)", exp_id)
        if m:
            max_num = max(max_num, int(m.group(1)) + 1)
    return f"EXP-{max_num:03d}"
