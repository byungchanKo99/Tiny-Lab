"""Load and validate project.yaml configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schemas import validate_project_deep


def load_project(project_dir: Path) -> dict[str, Any]:
    """Load project.yaml from the research/ subdirectory."""
    path = project_dir / "research" / "project.yaml"
    if not path.exists():
        raise FileNotFoundError(f"project.yaml not found at {path}")
    data = yaml.safe_load(path.read_text())
    validate_project_deep(data)
    return data
