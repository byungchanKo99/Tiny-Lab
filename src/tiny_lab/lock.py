"""Filesystem-based lock for single-instance enforcement."""
from __future__ import annotations

import os
from pathlib import Path

from .errors import TinyLabError
from .paths import lock_path


class LockError(TinyLabError):
    """Another tiny-lab instance is running."""


class Lock:
    """Context manager for exclusive lock."""

    def __init__(self, project_dir: Path) -> None:
        self.path = lock_path(project_dir)

    def __enter__(self) -> Lock:
        if self.path.exists():
            try:
                pid = int(self.path.read_text().strip())
                os.kill(pid, 0)
                raise LockError(f"Another tiny-lab is running (pid={pid})")
            except (ValueError, OSError):
                pass  # stale lock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *args: object) -> None:
        self.path.unlink(missing_ok=True)
