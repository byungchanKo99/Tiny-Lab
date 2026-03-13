"""Hypothesis queue read/write utilities."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .paths import queue_path


def load_queue(project_dir: Path) -> list[dict[str, Any]]:
    """Load hypothesis queue from YAML."""
    path = queue_path(project_dir)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    if not data or "hypotheses" not in data:
        return []
    return data["hypotheses"]


def save_queue(project_dir: Path, hypotheses: list[dict[str, Any]]) -> None:
    """Save hypothesis queue to YAML."""
    path = queue_path(project_dir)
    path.write_text(yaml.dump({"hypotheses": hypotheses}, default_flow_style=False, allow_unicode=True))


def pending_hypotheses(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter for pending hypotheses."""
    return [h for h in queue if h.get("status") == "pending"]
