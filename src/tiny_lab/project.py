"""Load and validate project.yaml configuration.

All project dict key access should go through the accessor functions
below so that key paths are defined in one place (SSOT).
"""
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


# ---------------------------------------------------------------------------
# Accessor functions — SSOT for project dict key paths
# ---------------------------------------------------------------------------

def project_name(p: dict[str, Any]) -> str:
    return p["name"]


def project_description(p: dict[str, Any]) -> str:
    return p.get("description", "")


def metric_name(p: dict[str, Any]) -> str:
    return p["metric"]["name"]


def metric_direction(p: dict[str, Any]) -> str:
    return p["metric"].get("direction", "minimize")


def baseline_command(p: dict[str, Any]) -> str:
    return p["baseline"]["command"].strip()


def baseline_eval_command(p: dict[str, Any]) -> str | None:
    return p["baseline"].get("eval_command")


def build_type(p: dict[str, Any]) -> str:
    return p.get("build", {}).get("type", "flag")


def build_config(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("build", {})


def run_type(p: dict[str, Any]) -> str:
    return p.get("run", {}).get("type", "command")


def evaluate_type(p: dict[str, Any]) -> str:
    return p.get("evaluate", {}).get("type", "stdout_json")


def evaluate_config(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("evaluate", {})


def optimize_config(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("optimize", {})


def levers(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("levers", {})


def approaches(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("approaches", {})


def approach_config(p: dict[str, Any], approach: str) -> dict[str, Any]:
    return p.get("approaches", {}).get(approach, {})


def model_for_approach(p: dict[str, Any], approach: str) -> str:
    """Return the actual model value for an approach. Falls back to approach name."""
    cfg = approach_config(p, approach)
    return cfg.get("model", approach)


def search_space(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("search_space", {})


def search_space_for_approach(p: dict[str, Any], approach: str) -> dict[str, Any]:
    """Get search_space for a specific approach.

    project.yaml format:
      search_space:
        lightgbm:
          num_leaves: {type: int, low: 20, high: 127}
        xgboost:
          max_depth: {type: int, low: 3, high: 15}
    """
    ss = p.get("search_space", {})
    return ss.get(approach, {})


def workdir(p: dict[str, Any]) -> str:
    return p.get("workdir", ".")


def rules(p: dict[str, Any]) -> list[str]:
    return p.get("rules", [])


def immutable_files(p: dict[str, Any]) -> list[str]:
    return p.get("immutable_files", [])
