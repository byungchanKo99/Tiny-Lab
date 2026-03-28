"""Tests for filesystem lock."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tiny_lab.lock import Lock, LockError


class TestLock:
    def test_acquires_and_releases(self, tmp_path):
        (tmp_path / "research").mkdir()
        with Lock(tmp_path) as lock:
            assert lock.path.exists()
            assert lock.path.read_text().strip() == str(os.getpid())
        assert not lock.path.exists()

    def test_stale_lock_is_overridden(self, tmp_path):
        (tmp_path / "research").mkdir()
        lock_file = tmp_path / "research" / ".loop-lock"
        lock_file.write_text("99999999")  # non-existent PID
        with Lock(tmp_path):
            pass  # should not raise

    def test_active_lock_raises(self, tmp_path):
        (tmp_path / "research").mkdir()
        lock_file = tmp_path / "research" / ".loop-lock"
        lock_file.write_text(str(os.getpid()))  # current process = "active"
        with pytest.raises(LockError, match="Another"):
            with Lock(tmp_path):
                pass
