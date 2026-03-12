"""Hypothesis generation via Claude CLI subagent."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .logging import log
from .schemas import validate_hypothesis_entry, ValidationError


def load_queue(project_dir: Path) -> list[dict[str, Any]]:
    """Load hypothesis queue from YAML."""
    path = project_dir / "research" / "hypothesis_queue.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    if not data or "hypotheses" not in data:
        return []
    return data["hypotheses"]


def save_queue(project_dir: Path, hypotheses: list[dict[str, Any]]) -> None:
    """Save hypothesis queue to YAML."""
    path = project_dir / "research" / "hypothesis_queue.yaml"
    path.write_text(yaml.dump({"hypotheses": hypotheses}, default_flow_style=False, allow_unicode=True))


def pending_hypotheses(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter for pending hypotheses."""
    return [h for h in queue if h.get("status") == "pending"]


def _validate_new_entries(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    project_dir: Path,
) -> int:
    """Validate newly added hypothesis entries. Remove invalid ones. Return count of valid new entries."""
    before_ids = {h.get("id") for h in before}
    new_entries = [h for h in after if h.get("id") not in before_ids]

    if not new_entries:
        return 0

    valid_count = 0
    invalid_ids = []

    for entry in new_entries:
        errors = validate_hypothesis_entry(entry, strict=False)
        if errors:
            log(f"GENERATE: invalid hypothesis {entry.get('id', '?')}: {errors}")
            invalid_ids.append(entry.get("id"))
        else:
            valid_count += 1

    # Remove invalid entries
    if invalid_ids:
        cleaned = [h for h in after if h.get("id") not in invalid_ids]
        save_queue(project_dir, cleaned)
        log(f"GENERATE: removed {len(invalid_ids)} invalid entries")

    return valid_count


def generate_hypotheses(project: dict[str, Any], project_dir: Path, run_claude_fn: Any) -> bool:
    """Generate new hypotheses using Claude CLI subagent."""
    levers_desc = []
    for name, lever in project["levers"].items():
        if "flag" in lever:
            levers_desc.append(f"  {name}: flag={lever['flag']}, baseline={lever['baseline']}, space={lever['space']}")
        else:
            levers_desc.append(f"  {name}: type={lever.get('type', 'choice')}, space={lever['space']}")

    prompt = f"""You are the hypothesis generator for the research loop.

PROJECT: {project['name']}
DESCRIPTION: {project['description']}
METRIC: {project['metric']['name']} (direction: {project['metric'].get('direction', 'minimize')})

LEVERS:
{chr(10).join(levers_desc)}

RULES:
{chr(10).join('- ' + r for r in project.get('rules', []))}

Read these files:
- research/ledger.jsonl (past experiment results)
- research/questions.yaml (research questions)
- research/hypothesis_queue.yaml (existing queue -- check for duplicates)

Generate 3-5 new hypotheses. Each MUST have these exact fields:
- id: H-{{next number}} (string, required)
- status: pending (string, required — must be "pending")
- lever: {{lever name}} (string, required — must match a key in project.yaml levers)
- value: {{value from space}} (number or string, required — must be from the lever's space)
- description: "{{one line}}" (string, required)

Append them to research/hypothesis_queue.yaml under the hypotheses key.
Do NOT remove existing entries. Only append new ones."""

    before = load_queue(project_dir)

    try:
        result = run_claude_fn(prompt, cwd=str(project_dir))
        if result.returncode != 0:
            log(f"GENERATE: claude exited with code {result.returncode}")
    except RuntimeError as e:
        log(f"GENERATE: {e}")
        return False

    # Validate new entries
    after = load_queue(project_dir)
    valid_count = _validate_new_entries(before, after, project_dir)

    return valid_count > 0
