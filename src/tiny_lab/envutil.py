"""Subprocess environment setup utilities."""
from __future__ import annotations

import os
from pathlib import Path


def make_env(project_dir: Path, exp_id: str | None = None) -> dict[str, str]:
    """Build environment dict for subprocess execution.

    Centralizes the TINY_LAB_ROOT / EXPERIMENT_ID pattern used across
    run.py, evaluate.py, and baseline.py.
    """
    env = os.environ.copy()
    env["TINY_LAB_ROOT"] = str(project_dir)
    if exp_id:
        env["EXPERIMENT_ID"] = exp_id
    return env
