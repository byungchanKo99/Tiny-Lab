"""Research plan parser.

research_plan.yaml defines WHAT experiments to run (phases, methodology,
expected outputs). This module parses and queries it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import PlanError
from .paths import plan_path


def load_plan(project_dir: Path, iteration: int) -> dict[str, Any]:
    """Load research_plan.yaml for a given iteration."""
    path = plan_path(project_dir, iteration)
    if not path.exists():
        raise PlanError(f"Research plan not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not data or "phases" not in data:
        raise PlanError("Research plan must have 'phases' list")
    return data


def pending_phases(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return phases with status 'pending', respecting depends_on."""
    all_phases = plan.get("phases", [])
    done_ids = {p["id"] for p in all_phases if p.get("status") in ("done", "skipped")}

    result = []
    for phase in all_phases:
        if phase.get("status") != "pending":
            continue
        deps = phase.get("depends_on", [])
        if all(d in done_ids for d in deps):
            result.append(phase)
    return result


def next_pending_phase(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first executable pending phase."""
    phases = pending_phases(plan)
    return phases[0] if phases else None


def update_phase_status(
    project_dir: Path, iteration: int, phase_id: str, status: str
) -> None:
    """Update a phase's status in the plan file."""
    path = plan_path(project_dir, iteration)
    data = yaml.safe_load(path.read_text())
    for phase in data.get("phases", []):
        if phase["id"] == phase_id:
            phase["status"] = status
            break
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False))
