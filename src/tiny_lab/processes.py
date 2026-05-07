"""Runtime process bookkeeping for Tiny-Lab backend children."""
from __future__ import annotations

import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import active_backend_path


def write_active_backend(
    project_dir: Path,
    *,
    backend: str,
    pid: int,
    command: list[str],
    state: str | None = None,
    iteration: int | None = None,
    phase_id: str | None = None,
) -> None:
    """Record the active backend subprocess for status/stop commands."""
    path = active_backend_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "backend": backend,
        "pid": pid,
        "command": _redacted_command(command),
        "state": state,
        "iteration": iteration,
        "phase_id": phase_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")


def clear_active_backend(project_dir: Path, *, pid: int | None = None) -> None:
    """Clear the active backend record if it matches the completed process."""
    path = active_backend_path(project_dir)
    if not path.exists():
        return
    if pid is not None:
        current = read_active_backend(project_dir)
        if current and current.get("pid") != pid:
            return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def read_active_backend(project_dir: Path) -> dict[str, Any] | None:
    path = active_backend_path(project_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_pid(pid: int, sig: signal.Signals = signal.SIGINT) -> bool:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return False
    return True


def _redacted_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            redacted.append("<value>")
            skip_next = False
            continue
        redacted.append(part)
        if part in {"--model", "--allowedTools", "--allowed-tools", "--session-id", "--resume", "--cd", "-C", "--sandbox"}:
            skip_next = True
    return redacted
