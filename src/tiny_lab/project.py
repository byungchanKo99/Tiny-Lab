"""Load and validate project.yaml configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .paths import project_yaml_path
from .schemas import validate_project_deep


def load_project(project_dir: Path) -> dict[str, Any]:
    """Load project.yaml from the research/ subdirectory."""
    path = project_yaml_path(project_dir)
    if not path.exists():
        raise FileNotFoundError(f"project.yaml not found at {path}")
    data = yaml.safe_load(path.read_text())
    # Auto-migrate old schema versions
    from .migrate import needs_migration, migrate_and_save
    if needs_migration(data):
        data = migrate_and_save(data, path)
    validate_project_deep(data)
    return data
