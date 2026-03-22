"""Hypothesis generation via AI provider subagent."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .logging import log
from .paths import generate_summary_path, generate_history_path, project_yaml_path
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


def _extract_model_family(approach: str) -> str | None:
    """Extract the base model family from an approach name.

    'lgbm_high_capacity' → 'lgbm'
    'xgboost_deep_tuned' → 'xgboost'
    'stacking_ensemble' → None (genuinely new)
    """
    known_families = [
        "lgbm", "lightgbm", "xgboost", "xgb", "rf", "random_forest",
        "gbm", "gradient_boosting", "catboost", "logistic", "lr",
        "svm", "knn", "neural", "mlp", "ada", "adaboost",
    ]
    approach_lower = approach.lower()
    for family in known_families:
        if approach_lower.startswith(family) or f"_{family}" in approach_lower:
            return family
    return None


def _check_approach_duplicates(
    new_entries: list[dict[str, Any]],
    project_dir: Path,
) -> list[str]:
    """Detect hypotheses that are just parameter variants of already-tried approaches.

    Returns list of IDs to reject with reasons logged.
    """
    from .ledger import load_ledger
    ledger = load_ledger(project_dir)

    # Collect model families already tried
    tried_families: dict[str, int] = {}  # family → count
    for row in ledger:
        if row.get("class") == "BASELINE":
            continue
        approach = row.get("approach") or row.get("changed_variable", "")
        family = _extract_model_family(approach)
        if family:
            tried_families[family] = tried_families.get(family, 0) + 1

    reject_ids = []
    for entry in new_entries:
        approach = entry.get("approach", "")
        family = _extract_model_family(approach)
        if family and tried_families.get(family, 0) >= 3:
            log(f"GENERATE: rejecting {entry.get('id', '?')} — "
                f"'{approach}' is a variant of '{family}' "
                f"(already {tried_families[family]} experiments). "
                f"Try a fundamentally different approach.")
            reject_ids.append(entry.get("id"))

    return reject_ids


def _validate_new_entries(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    project_dir: Path,
) -> int:
    """Validate newly added hypothesis entries. Remove invalid and duplicate ones."""
    before_ids = {h.get("id") for h in before}
    new_entries = [h for h in after if h.get("id") not in before_ids]

    if not new_entries:
        return 0

    valid_count = 0
    invalid_ids = []

    # Schema validation
    for entry in new_entries:
        entry.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        errors = validate_hypothesis_entry(entry, strict=False)
        if errors:
            log(f"GENERATE: invalid hypothesis {entry.get('id', '?')}: {errors}")
            invalid_ids.append(entry.get("id"))

    # Duplicate approach detection — reject parameter variants of overtried families
    duplicate_ids = _check_approach_duplicates(
        [e for e in new_entries if e.get("id") not in invalid_ids],
        project_dir,
    )
    invalid_ids.extend(duplicate_ids)

    valid_count = len(new_entries) - len(invalid_ids)

    # Remove invalid/duplicate entries or save updated entries
    if invalid_ids:
        cleaned = [h for h in after if h.get("id") not in invalid_ids]
        save_queue(project_dir, cleaned)
        log(f"GENERATE: removed {len(invalid_ids)} entries ({len(duplicate_ids)} duplicate approach variants)")
    elif new_entries:
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
        space = lever.get("space", [])
        if "flag" in lever:
            levers_desc.append(f"  {name}: flag={lever['flag']}, baseline={lever.get('baseline', '?')}, space={space}")
        else:
            levers_desc.append(f"  {name}: type={lever.get('type', 'choice')}, space={space}")

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

    # Single pass over ledger: tried families + non-baseline collection
    from .ledger import load_ledger, find_best_result
    ledger = load_ledger(project_dir)
    tried_families: dict[str, int] = {}
    non_baseline: list[dict[str, Any]] = []
    for row in ledger:
        if row.get("class") == "BASELINE":
            continue
        non_baseline.append(row)
        approach = row.get("approach") or row.get("changed_variable", "")
        family = _extract_model_family(approach)
        if family:
            tried_families[family] = tried_families.get(family, 0) + 1
    saturated_families = [f"{f} ({c} experiments)" for f, c in tried_families.items() if c >= 3]
    tried_msg = ""
    if saturated_families:
        tried_msg = (
            f"SATURATED MODEL FAMILIES (do NOT generate more variants of these):\n"
            f"  {', '.join(saturated_families)}\n"
            f"Hypotheses using these families will be REJECTED. Try something fundamentally different."
        )

    # Stagnation detection
    best_row = None
    if non_baseline:
        mname = metric_name(project)
        mdir = metric_direction(project)
        best_row = find_best_result(ledger, mname, mdir)
    stagnation_msg = ""
    if best_row and non_baseline:
        best_idx = next((i for i, r in enumerate(non_baseline) if r.get("id") == best_row.get("id")), None)
        if best_idx is not None:
            since_best = len(non_baseline) - 1 - best_idx
            if since_best >= 20:
                stagnation_msg = (
                    f"STAGNATION WARNING: {since_best} experiments since last best result ({best_row.get('id')}).\n"
                    f"Current approaches are NOT improving. You MUST try something radically different:\n"
                    f"- Ensemble/stacking of existing models\n"
                    f"- Feature engineering (interactions, PCA, encoding)\n"
                    f"- Completely different paradigm (neural net, SVM, etc.)\n"
                    f"- Preprocessing changes (scaling, outlier removal)"
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
        "tried_families": tried_msg,
        "stagnation": stagnation_msg,
        "trial_summary": _build_trial_summary(ledger, opt_cfg),
    }


def _build_trial_summary(ledger: list[dict[str, Any]], opt_cfg: dict[str, Any]) -> str:
    """Build per-approach trial count summary for optimizer efficiency analysis."""
    time_budget = opt_cfg.get("time_budget", 300)
    max_trials = opt_cfg.get("n_trials", 20)
    entries: list[str] = []

    for row in ledger:
        if row.get("class") == "BASELINE":
            continue
        approach = row.get("approach") or row.get("changed_variable", "")
        opt = row.get("optimize_result", {})
        n_trials = opt.get("n_trials", 0)
        total_secs = opt.get("total_seconds", 0)
        best_val = opt.get("best_value")
        if n_trials == 0:
            continue

        time_per_trial = total_secs / n_trials if n_trials > 0 else 0
        # Flag as underexplored if used less than half the max_trials
        sufficient = n_trials >= max(max_trials * 0.5, 10)
        flag = "" if sufficient else " ⚠ UNDEREXPLORED"
        entries.append(
            f"  {row.get('id', '?')} ({approach}): "
            f"{n_trials}/{max_trials} trials, "
            f"{time_per_trial:.1f}s/trial, "
            f"total={total_secs:.0f}s/{time_budget}s budget, "
            f"best={best_val}{flag}"
        )

    if not entries:
        return ""

    header = (
        f"OPTIMIZER TRIAL SUMMARY (time_budget={time_budget}s, max_trials={max_trials}):\n"
        f"Approaches marked ⚠ UNDEREXPLORED may rank lower due to insufficient trials, not model quality.\n"
    )
    return header + "\n".join(entries)


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
        changes = ", ".join(str(c) for c in e.get("changes_made", []))
        lines.append(f"  Cycle {i}: state={state}, +{added} hypotheses")
        if reasoning:
            lines.append(f"    Reasoning: {reasoning}")
        if changes:
            lines.append(f"    Changes: {changes}")
        refs = e.get("references", [])
        if refs:
            lines.append(f"    References: {', '.join(str(r) for r in refs[:3])}")
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


# ---------------------------------------------------------------------------
# Guard rails for meta-actions (optimize config changes)
# ---------------------------------------------------------------------------

_OPTIMIZE_LIMITS = {
    "time_budget": (60, 1800),     # 1 min to 30 min
    "n_trials": (5, 200),          # 5 to 200
}
_MAX_CHANGE_RATIO = 3.0  # max 3x change per cycle


def _validate_optimize_changes(project_dir: Path, original_cfg: dict[str, Any]) -> list[str]:
    """Validate and clamp any optimize config changes made by the pipeline.

    Returns list of changes applied (for logging/summary).
    """
    path = project_yaml_path(project_dir)
    if not path.exists():
        return []

    data = yaml.safe_load(path.read_text())
    if not data or "optimize" not in data:
        return []

    current = data["optimize"]
    changes: list[str] = []
    clamped = False

    for key, (lo, hi) in _OPTIMIZE_LIMITS.items():
        if key not in current:
            continue
        new_val = current[key]
        old_val = original_cfg.get(key)

        if not isinstance(new_val, (int, float)):
            continue

        # Check if changed
        if old_val is not None and new_val == old_val:
            continue

        # Apply ratio limit first (against original value, before absolute clamp)
        if old_val and old_val > 0:
            ratio = new_val / old_val
            if ratio > _MAX_CHANGE_RATIO:
                capped = int(old_val * _MAX_CHANGE_RATIO)
                log(f"GENERATE: clamping optimize.{key} from {new_val} to {capped} "
                    f"(max {_MAX_CHANGE_RATIO}x increase per cycle)")
                new_val = capped
                clamped = True
            elif ratio < 1.0 / _MAX_CHANGE_RATIO:
                floored = max(int(old_val / _MAX_CHANGE_RATIO), lo)
                log(f"GENERATE: clamping optimize.{key} from {new_val} to {floored} "
                    f"(max {_MAX_CHANGE_RATIO}x decrease per cycle)")
                new_val = floored
                clamped = True

        # Then clamp to absolute limits
        if new_val < lo:
            log(f"GENERATE: clamping optimize.{key} from {new_val} to {lo} (minimum)")
            new_val = lo
            clamped = True
        elif new_val > hi:
            log(f"GENERATE: clamping optimize.{key} from {new_val} to {hi} (maximum)")
            new_val = hi
            clamped = True

        current[key] = new_val
        if old_val != new_val:
            changes.append(f"optimize.{key}: {old_val} → {new_val}")

    if clamped:
        data["optimize"] = current
        path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False))

    if changes:
        log(f"GENERATE: optimize config changed: {', '.join(changes)}")

    return changes


def generate_hypotheses(project: dict[str, Any], project_dir: Path, provider: Any) -> bool:
    """Generate new hypotheses using metadata-driven pipeline.

    Each step runs as a separate LLM call with schema-validated output.
    Step order is enforced by the pipeline engine, not by prompt instructions.
    """
    from .pipeline import run_pipeline
    from .project import optimize_config

    pipeline_path = Path(__file__).parent / "templates" / "common" / "generate_pipeline.yaml"
    context = _build_pipeline_context(project, project_dir)

    # Snapshot optimize config before pipeline (for guard rail comparison)
    original_opt_cfg = dict(optimize_config(project))

    before = load_queue(project_dir)

    result = run_pipeline(pipeline_path, context, provider, project_dir)

    # Guard rail: validate any optimize config changes made by the pipeline
    opt_changes = _validate_optimize_changes(project_dir, original_opt_cfg)

    if not result.success:
        log(f"GENERATE: pipeline failed at step '{list(result.steps.keys())[-1] if result.steps else '?'}'")
        # Still try to salvage any hypotheses that were added before failure
        _sanitize_queue_yaml(project_dir)
        after = load_queue(project_dir)
        valid_count = _validate_new_entries(before, after, project_dir)
        if valid_count > 0:
            log(f"GENERATE: salvaged {valid_count} hypotheses from partial pipeline run")
        _archive_generate_summary(project_dir, valid_count, opt_changes)
        return valid_count > 0

    # Post-processing (same as before)
    _sanitize_queue_yaml(project_dir)
    after = load_queue(project_dir)
    valid_count = _validate_new_entries(before, after, project_dir)
    _archive_generate_summary(project_dir, valid_count, opt_changes)

    return valid_count > 0


def _archive_generate_summary(project_dir: Path, valid_count: int, opt_changes: list[str] | None = None) -> None:
    """Read summary from AI output or pipeline step files, archive to history."""
    summary_path = generate_summary_path(project_dir)
    history_path = generate_history_path(project_dir)

    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypotheses_added_count": valid_count,
    }
    if opt_changes:
        entry["optimize_changes"] = opt_changes

    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
            entry.update(summary)
        except json.JSONDecodeError:
            log("GENERATE: could not parse .generate_summary.json")
    else:
        # Fallback: read pipeline step outputs for partial summary
        research_dir = project_dir / "research"
        diagnose_path = research_dir / ".step_diagnose.json"
        hypotheses_path = research_dir / ".step_hypotheses.json"

        if diagnose_path.exists():
            try:
                diagnose = json.loads(diagnose_path.read_text())
                entry["state"] = diagnose.get("state", "UNKNOWN")
                entry["reasoning"] = diagnose.get("reasoning", "(from diagnose step)")
                entry["best_so_far"] = diagnose.get("best_so_far", {})
            except json.JSONDecodeError:
                pass

        if hypotheses_path.exists():
            try:
                hyp = json.loads(hypotheses_path.read_text())
                entry.setdefault("hypotheses_added", hyp.get("hypotheses_added", []))
                entry.setdefault("changes_made", hyp.get("changes_made", []))
            except json.JSONDecodeError:
                pass

        if "state" not in entry:
            entry["state"] = "UNKNOWN"
            entry["reasoning"] = "(pipeline did not produce summary or diagnose output)"

    with history_path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Clean up per-cycle files
    summary_path.unlink(missing_ok=True)
    for step_file in (project_dir / "research").glob(".step_*.json"):
        step_file.unlink(missing_ok=True)
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
