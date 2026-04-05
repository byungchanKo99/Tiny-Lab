"""State persistence — .state.json read/write.

Tracks current iteration, state, and resume context.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .paths import state_path


@dataclass
class LoopState:
    """Persistent loop state."""

    current_iteration: int = 1
    state: str = "INIT"
    current_phase_id: str | None = None  # which research_plan phase is active
    resumable: bool = True
    consecutive_failures: int = 0
    phase_retries: int = 0  # retries for current phase (resets on phase change)
    session_id: str | None = None  # Claude session ID — persists across states within iteration


def load_state(project_dir: Path) -> LoopState:
    """Load state from .state.json, or return default."""
    path = state_path(project_dir)
    if not path.exists():
        return LoopState()
    try:
        data = json.loads(path.read_text())
        return LoopState(
            current_iteration=data.get("current_iteration", 1),
            state=data.get("state", "INIT"),
            current_phase_id=data.get("current_phase_id"),
            resumable=data.get("resumable", True),
            consecutive_failures=data.get("consecutive_failures", 0),
            phase_retries=data.get("phase_retries", 0),
            session_id=data.get("session_id"),
        )
    except (json.JSONDecodeError, KeyError):
        return LoopState()


def save_state(project_dir: Path, loop_state: LoopState) -> None:
    """Write state to .state.json."""
    path = state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(loop_state), indent=2) + "\n")


def set_state(project_dir: Path, new_state: str, **overrides: Any) -> LoopState:
    """Update the current state and optionally other fields."""
    ls = load_state(project_dir)
    ls.state = new_state
    for k, v in overrides.items():
        if hasattr(ls, k):
            setattr(ls, k, v)
    save_state(project_dir, ls)
    return ls
