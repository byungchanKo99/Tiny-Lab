"""Hypothesis queue read/write utilities."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from .paths import queue_path


def load_queue(project_dir: Path) -> list[dict[str, Any]]:
    """Load hypothesis queue from YAML.

    If the YAML is corrupt (e.g. AI wrote unquoted colons), attempts to
    restore from the .bak backup created by save_queue.
    """
    path = queue_path(project_dir)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        from .logging import log
        log(f"QUEUE: YAML parse error in {path.name}, attempting recovery from backup")
        backup = path.with_suffix(path.suffix + ".bak")
        if backup.exists():
            try:
                data = yaml.safe_load(backup.read_text())
                # Restore from backup
                shutil.copy2(backup, path)
                log(f"QUEUE: restored from {backup.name}")
            except yaml.YAMLError:
                log(f"QUEUE: backup also corrupt, returning empty queue")
                return []
        else:
            log(f"QUEUE: no backup found, returning empty queue")
            return []
    if not data or "hypotheses" not in data:
        return []
    return data["hypotheses"]


def save_queue(project_dir: Path, hypotheses: list[dict[str, Any]]) -> None:
    """Save hypothesis queue to YAML.

    Creates a .bak backup before writing so load_queue can recover from
    corrupt files written by AI agents.
    """
    path = queue_path(project_dir)
    # Backup current file before overwriting
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    path.write_text(yaml.dump({"hypotheses": hypotheses}, default_flow_style=False, allow_unicode=True))


def pending_hypotheses(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter for pending hypotheses."""
    return [h for h in queue if h.get("status") == "pending"]
