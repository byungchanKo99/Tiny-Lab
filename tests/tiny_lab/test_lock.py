"""Tests for LockManager."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tiny_lab.lock import LockManager


@pytest.fixture()
def lock_path(tmp_path: Path) -> Path:
    return tmp_path / "test.lock"


class TestLockManager:
    def test_acquire_and_release(self, lock_path: Path):
        lock = LockManager(lock_path)
        assert lock.acquire() is True
        assert lock_path.exists()
        lock.release()
        assert not lock_path.exists()

    def test_double_acquire_same_process_fails(self, lock_path: Path):
        lock1 = LockManager(lock_path)
        assert lock1.acquire() is True
        lock2 = LockManager(lock_path)
        # Same PID holds the lock, os.kill(pid, 0) succeeds
        assert lock2.acquire() is False
        lock1.release()

    def test_stale_lock_cleaned(self, lock_path: Path):
        # Write a PID that doesn't exist
        lock_path.write_text("999999999")
        lock = LockManager(lock_path)
        assert lock.acquire() is True
        lock.release()

    def test_invalid_pid_in_lock_file(self, lock_path: Path):
        lock_path.write_text("not_a_number")
        lock = LockManager(lock_path)
        assert lock.acquire() is True
        lock.release()

    def test_context_manager(self, lock_path: Path):
        lock = LockManager(lock_path)
        lock.acquire()
        with lock:
            assert lock_path.exists()
        assert not lock_path.exists()

    def test_release_without_acquire_is_noop(self, lock_path: Path):
        lock = LockManager(lock_path)
        lock.release()  # should not raise

    def test_writes_current_pid(self, lock_path: Path):
        lock = LockManager(lock_path)
        lock.acquire()
        assert int(lock_path.read_text().strip()) == os.getpid()
        lock.release()
