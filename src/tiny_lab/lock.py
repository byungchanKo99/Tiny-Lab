"""Process lock management for the research loop."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .logging import log


class LockManager:
    """File-based PID lock with stale-process cleanup."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._acquired = False

    def acquire(self) -> bool:
        """Acquire the lock. Returns False if another live process holds it."""
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text().strip())
                os.kill(pid, 0)
                return False
            except (ValueError, OSError):
                log(f"LOCK: removing orphan lock (pid={self.lock_path.read_text().strip()})")
                self.lock_path.unlink(missing_ok=True)
        self.lock_path.write_text(str(os.getpid()))
        self._acquired = True
        return True

    def release(self) -> None:
        """Release the lock if held."""
        if self._acquired:
            self.lock_path.unlink(missing_ok=True)
            self._acquired = False

    def __enter__(self) -> LockManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
