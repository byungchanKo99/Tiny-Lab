"""Event system for the research loop."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .logging import log


class EventType(str, Enum):
    LOOP_STARTED = "loop_started"
    LOOP_STOPPED = "loop_stopped"
    EXPERIMENT_DONE = "experiment_done"
    NEW_BEST = "new_best"
    GENERATE_ENTER = "generate_enter"
    CIRCUIT_BREAKER_WARNING = "circuit_breaker_warning"


def emit_event(
    project_dir: Path,
    event: EventType,
    data: dict[str, Any] | None = None,
    on_event_cmd: str | None = None,
) -> None:
    """Write event to .events.jsonl and optionally fire a callback command."""
    try:
        record = {
            "event": event.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        events_path = project_dir / "research" / ".events.jsonl"
        with events_path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if on_event_cmd:
            env = {**os.environ, "TINYLAB_EVENT": event.value, "TINYLAB_EVENT_DATA": json.dumps(data or {})}
            subprocess.Popen(on_event_cmd, shell=True, env=env,  # noqa: S602
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        # Event failure must never kill the loop
        pass


def load_events(project_dir: Path, last_n: int = 50) -> list[dict[str, Any]]:
    """Load the most recent N events."""
    path = project_dir / "research" / ".events.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-last_n:]


def compute_action_needed(
    loop_alive: bool,
    events: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    queue_counts: dict[str, int],
    lock_exists: bool = False,
) -> tuple[bool, list[str]]:
    """Determine whether the agent should intervene. Returns (needed, reasons)."""
    reasons: list[str] = []

    # Check recent events for NEW_BEST
    recent_types = {e.get("event") for e in events[-10:]}
    if EventType.NEW_BEST.value in recent_types:
        for e in reversed(events[-10:]):
            if e.get("event") == EventType.NEW_BEST.value:
                d = e.get("data", {})
                reasons.append(f"New best result: {d.get('exp_id', '?')} ({d.get('metric_value', '?')})")
                break

    # CIRCUIT_BREAKER_WARNING
    if EventType.CIRCUIT_BREAKER_WARNING.value in recent_types:
        for e in reversed(events[-10:]):
            if e.get("event") == EventType.CIRCUIT_BREAKER_WARNING.value:
                d = e.get("data", {})
                reasons.append(f"Circuit breaker approaching ({d.get('invalid_count', '?')}/{d.get('threshold', '?')} INVALID)")
                break

    # Consecutive failures: last 3+ ledger entries are LOSS or INVALID
    if len(ledger) >= 3:
        recent_classes = [r.get("class", "") for r in ledger[-3:]]
        if all(c in ("LOSS", "INVALID") for c in recent_classes):
            reasons.append("Consecutive failures detected")

    # Loop stopped unexpectedly: lock exists but process is dead
    if lock_exists and not loop_alive:
        reasons.append("Loop stopped unexpectedly")

    # Queue empty while loop is running
    if loop_alive and queue_counts.get("pending", 0) == 0:
        reasons.append("Queue empty, entering GENERATE")

    return (len(reasons) > 0, reasons)
