"""Event system for tiny-lab v5.

Emits structured events to .events.jsonl for external consumers
(nanoclaw, dashboard, monitoring).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _events_path(project_dir: Path) -> Path:
    return project_dir / "research" / ".events.jsonl"


def emit(project_dir: Path, event: str, data: dict[str, Any] | None = None, **extra: Any) -> None:
    """Append a structured event to .events.jsonl."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "data": data or {},
        **extra,
    }
    path = _events_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_events(project_dir: Path, last_n: int = 50) -> list[dict[str, Any]]:
    """Load recent events."""
    path = _events_path(project_dir)
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    events = []
    for line in lines[-last_n:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


# Convenience emitters

def state_entered(project_dir: Path, state: str, iteration: int, **extra: Any) -> None:
    emit(project_dir, "state_entered", {"state": state, "iteration": iteration, **extra})


def phase_started(project_dir: Path, phase_id: str, iteration: int) -> None:
    emit(project_dir, "phase_started", {"phase_id": phase_id, "iteration": iteration})


def phase_completed(project_dir: Path, phase_id: str, iteration: int, status: str) -> None:
    emit(project_dir, "phase_completed", {"phase_id": phase_id, "iteration": iteration, "status": status})


def iteration_started(project_dir: Path, iteration: int, idea: str = "") -> None:
    emit(project_dir, "iteration_started", {"iteration": iteration, "idea": idea})


def iteration_completed(project_dir: Path, iteration: int, decision: str, reason: str = "") -> None:
    emit(project_dir, "iteration_completed", {"iteration": iteration, "decision": decision, "reason": reason})


def error_occurred(project_dir: Path, state: str, error: str) -> None:
    emit(project_dir, "error", {"state": state, "error": error})


def loop_done(project_dir: Path, reason: str = "") -> None:
    emit(project_dir, "loop_done", {"reason": reason})
