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
from .paths import events_path as _events_path


class EventType(str, Enum):
    LOOP_STARTED = "loop_started"
    LOOP_STOPPED = "loop_stopped"
    EXPERIMENT_DONE = "experiment_done"
    NEW_BEST = "new_best"
    GENERATE_ENTER = "generate_enter"
    CIRCUIT_BREAKER_WARNING = "circuit_breaker_warning"
    IDLE_STOP = "idle_stop"


_event_seq = 0


def _next_seq() -> int:
    global _event_seq
    _event_seq += 1
    return _event_seq


def reset_event_seq() -> None:
    """Reset sequence counter (for testing only)."""
    global _event_seq
    _event_seq = 0


def emit_event(
    project_dir: Path,
    event: EventType,
    data: dict[str, Any] | None = None,
    on_event_cmd: str | None = None,
    *,
    source: str = "tiny-lab",
    loop_state: str | None = None,
) -> None:
    """Write event to .events.jsonl and optionally fire a callback command."""
    try:
        record = {
            "event": event.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "loop_state": loop_state,
            "sequence": _next_seq(),
            "data": data or {},
        }
        events_path = _events_path(project_dir)
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
    path = _events_path(project_dir)
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


