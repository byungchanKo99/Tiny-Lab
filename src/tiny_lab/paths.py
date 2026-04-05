"""Centralized path definitions for tiny-lab."""
from __future__ import annotations

from pathlib import Path


def research_dir(project_dir: Path) -> Path:
    return project_dir / "research"


def shared_dir(project_dir: Path) -> Path:
    return project_dir / "shared"


def knowledge_dir(project_dir: Path) -> Path:
    return shared_dir(project_dir) / "knowledge"


def constraints_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "constraints.json"


def convergence_log_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "convergence_log.json"


def workflow_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".workflow.json"


def state_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".state.json"


def intervention_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".intervention.json"


def iterations_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".iterations.json"


def lock_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".loop-lock"


def iter_dir(project_dir: Path, iteration: int) -> Path:
    return research_dir(project_dir) / f"iter_{iteration}"


def phases_dir(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "phases"


def results_dir(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "results"


def plan_path(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "research_plan.json"


def reflect_path(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "reflect.json"
