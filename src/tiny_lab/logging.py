"""Shared logging utility for the research loop."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

_log_path: Path | None = None


def configure_log(project_dir: Path) -> None:
    """Set the log file path based on project directory."""
    global _log_path
    _log_path = project_dir / "research" / "loop.log"


def log(message: str) -> None:
    """Print and optionally write to log file."""
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    if _log_path:
        try:
            with _log_path.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass
