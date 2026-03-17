"""Hypothesis generation via AI provider subagent."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging import log
from .paths import generate_summary_path, generate_history_path
from .queue import load_queue, save_queue, pending_hypotheses
from .schemas import validate_hypothesis_entry, ValidationError


def _sanitize_queue_yaml(project_dir: Path) -> None:
    """Re-save queue through yaml.dump to fix YAML-unsafe text from AI.

    AI agents often write reasoning fields with unquoted colons, which
    breaks YAML parsing. Loading and re-saving through yaml.dump quotes
    all strings properly.
    """
    from .paths import queue_path
    path = queue_path(project_dir)
    if not path.exists():
        return
    try:
        import yaml
        data = yaml.safe_load(path.read_text())
        if data and "hypotheses" in data:
            # Re-save through yaml.dump — this quotes all unsafe strings
            path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
    except yaml.YAMLError:
        log("GENERATE: queue YAML is corrupt after AI write, restoring from backup")
        backup = path.with_suffix(path.suffix + ".bak")
        if backup.exists():
            import shutil
            shutil.copy2(backup, path)
            log("GENERATE: restored queue from backup")


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
        entry.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        errors = validate_hypothesis_entry(entry, strict=False)
        if errors:
            log(f"GENERATE: invalid hypothesis {entry.get('id', '?')}: {errors}")
            invalid_ids.append(entry.get("id"))
        else:
            valid_count += 1

    # Remove invalid entries or save updated entries (with generated_at)
    if invalid_ids:
        cleaned = [h for h in after if h.get("id") not in invalid_ids]
        save_queue(project_dir, cleaned)
        log(f"GENERATE: removed {len(invalid_ids)} invalid entries")
    elif new_entries:
        # Save back to persist generated_at timestamps
        save_queue(project_dir, after)

    return valid_count


def _build_pipeline_context(project: dict[str, Any], project_dir: Path) -> dict[str, Any]:
    """Build the initial context dict for the generate pipeline."""
    from .project import (
        project_name, project_description, metric_name, metric_direction,
        levers, optimize_config, rules,
    )

    levers_desc = []
    for name, lever in levers(project).items():
        if "flag" in lever:
            levers_desc.append(f"  {name}: flag={lever['flag']}, baseline={lever['baseline']}, space={lever['space']}")
        else:
            levers_desc.append(f"  {name}: type={lever.get('type', 'choice')}, space={lever['space']}")

    opt_cfg = optimize_config(project)
    history = load_generate_history(project_dir)
    forced = _check_escalation(history)
    escalation_msg = ""
    if forced:
        escalation_msg = (
            f"MANDATORY ESCALATION: Last cycles were {[h.get('state') for h in history[-3:]]}.\n"
            f"You MUST classify as {forced} and take bold action:\n"
            f"1. Choose a fundamentally different approach\n"
            f"2. Do NOT tweak the same levers as recent failures"
        )

    return {
        "project_name": project_name(project),
        "project_description": project_description(project),
        "metric_name": metric_name(project),
        "metric_direction": metric_direction(project),
        "optimize_type": opt_cfg.get("type", "random"),
        "time_budget": opt_cfg.get("time_budget", "unlimited"),
        "n_trials": opt_cfg.get("n_trials", "auto"),
        "levers_text": "\n".join(levers_desc),
        "rules_text": "\n".join("- " + r for r in rules(project)),
        "failure_history": _format_failure_history(project_dir, metric_name(project)),
        "generation_history": _format_history(history[-5:]),
        "escalation": escalation_msg,
    }


def _format_failure_history(project_dir: Path, metric_name: str) -> str:
    """Summarize LOSS/INVALID experiments for GENERATE prompt injection."""
    from .ledger import load_ledger
    ledger = load_ledger(project_dir)
    failures = [r for r in ledger if r.get("class") in ("LOSS", "INVALID")]
    if not failures:
        return ""
    recent = failures[-15:]
    lines = ["FAILED APPROACHES (avoid repeating these):\n"]
    for r in recent:
        pm = r.get("primary_metric", {})
        delta = pm.get("delta_pct", "?")
        desc = r.get("question", "")[:80]
        lines.append(f"  - {r['id']} [{r.get('class')}]: {r.get('changed_variable')}={r.get('value')} "
                     f"(delta={delta}%) — {desc}")
    return "\n".join(lines)


def _format_history(entries: list[dict[str, Any]]) -> str:
    """Format recent generation history for prompt injection."""
    if not entries:
        return ""
    lines = ["YOUR PREVIOUS GENERATION CYCLES (most recent last):",
             "Review these to avoid repeating strategies. If you see a pattern, escalate.\n"]
    for i, e in enumerate(entries, 1):
        state = e.get("state", "?")
        reasoning = e.get("reasoning", "")[:120]
        added = e.get("hypotheses_added_count", 0)
        changes = ", ".join(e.get("changes_made", []))
        lines.append(f"  Cycle {i}: state={state}, +{added} hypotheses")
        if reasoning:
            lines.append(f"    Reasoning: {reasoning}")
        if changes:
            lines.append(f"    Changes: {changes}")
        refs = e.get("references", [])
        if refs:
            lines.append(f"    References: {', '.join(refs[:3])}")
    return "\n".join(lines)


def _check_escalation(history: list[dict[str, Any]]) -> str | None:
    """Force SATURATED if recent 2+ cycles are EXPLORING/REFINING."""
    if len(history) < 2:
        return None
    recent = [h.get("state", "").upper() for h in history[-3:]]
    non_saturated = sum(1 for s in recent if s in ("EXPLORING", "REFINING"))
    if non_saturated >= 2:
        return "SATURATED"
    return None


def generate_hypotheses(project: dict[str, Any], project_dir: Path, provider: Any) -> bool:
    """Generate new hypotheses using metadata-driven pipeline.

    Each step runs as a separate LLM call with schema-validated output.
    Step order is enforced by the pipeline engine, not by prompt instructions.
    """
    from .pipeline import run_pipeline

    pipeline_path = Path(__file__).parent / "templates" / "common" / "generate_pipeline.yaml"
    context = _build_pipeline_context(project, project_dir)

    before = load_queue(project_dir)

    result = run_pipeline(pipeline_path, context, provider, project_dir)

    if not result.success:
        log(f"GENERATE: pipeline failed at step '{list(result.steps.keys())[-1] if result.steps else '?'}'")
        # Still try to salvage any hypotheses that were added before failure
        _sanitize_queue_yaml(project_dir)
        after = load_queue(project_dir)
        valid_count = _validate_new_entries(before, after, project_dir)
        if valid_count > 0:
            log(f"GENERATE: salvaged {valid_count} hypotheses from partial pipeline run")
        _archive_generate_summary(project_dir, valid_count)
        return valid_count > 0

    # Post-processing (same as before)
    _sanitize_queue_yaml(project_dir)
    after = load_queue(project_dir)
    valid_count = _validate_new_entries(before, after, project_dir)
    _archive_generate_summary(project_dir, valid_count)

    return valid_count > 0


def _archive_generate_summary(project_dir: Path, valid_count: int) -> None:
    """Read .generate_summary.json (written by AI), archive to .generate_history.jsonl."""
    summary_path = generate_summary_path(project_dir)
    history_path = generate_history_path(project_dir)

    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypotheses_added_count": valid_count,
    }

    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
            entry.update(summary)
        except json.JSONDecodeError:
            log("GENERATE: could not parse .generate_summary.json")
    else:
        entry["state"] = "UNKNOWN"
        entry["reasoning"] = "(AI did not write summary)"

    with history_path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Clean up the per-cycle file
    summary_path.unlink(missing_ok=True)
    log(f"GENERATE: archived summary (state={entry.get('state', '?')}, added={valid_count})")


def load_generate_history(project_dir: Path) -> list[dict[str, Any]]:
    """Load generation history for dashboard display."""
    path = generate_history_path(project_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
