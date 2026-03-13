"""Centralized file path definitions for the research directory."""
from __future__ import annotations

from pathlib import Path


def research_dir(project_dir: Path) -> Path:
    return project_dir / "research"


def ledger_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "ledger.jsonl"


def queue_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "hypothesis_queue.yaml"


def project_yaml_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "project.yaml"


def lock_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".loop-lock"


def state_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".loop_state.json"


def events_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".events.jsonl"


def log_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "loop.log"


def generate_summary_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".generate_summary.json"


def generate_history_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".generate_history.jsonl"


def eval_result_path(project_dir: Path, exp_id: str) -> Path:
    return research_dir(project_dir) / f".eval_result_{exp_id}.json"
