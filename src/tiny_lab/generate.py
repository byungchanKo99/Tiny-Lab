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


_GENERATE_PROMPT_TEMPLATE = """\
You are the autonomous research strategist for an experiment loop with a built-in optimizer.

YOU decide the STRATEGY. The optimizer decides the PARAMETERS.
- DO: "Try ViT with augmentation" + search_space for lr, epochs, patch_size
- DON'T: "Try lr=0.05" (this is the optimizer's job)

PROJECT: {project_name}
DESCRIPTION: {project_description}
METRIC: {metric_name} (direction: {metric_direction})
OPTIMIZER: {optimize_type} (time_budget: {time_budget}s, n_trials: {n_trials})

CURRENT LEVERS (for parameter flag mapping):
{levers_text}

RULES:
{rules_text}

STEP 0: RESEARCH EXISTING APPROACHES

Before analyzing results, search the web for relevant techniques:
- Search for papers, blog posts, or known best practices for this type of problem
- Look for benchmark results on similar datasets or tasks
- Find techniques that top practitioners use

Use WebSearch to find relevant information.
Cite what you find in your hypothesis reasoning fields.

STEP 1: READ AND ANALYZE (do this first, do not skip)

Read these files and build a mental model of the research so far:
- research/ledger.jsonl — all past experiments with optimize_result details
- research/questions.yaml — research questions
- research/hypothesis_queue.yaml — pending/done hypotheses
- research/project.yaml — current configuration

Pay special attention to optimize_result in ledger entries — these show how many trials
the optimizer ran and what parameters it found optimal for each approach.

STEP 2: DIAGNOSE THE RESEARCH STATE

Same as before: EXPLORING, REFINING, SATURATED, or STUCK.
But now focus on APPROACHES rather than individual parameter values.

STEP 3: ACT BASED ON STATE

**If EXPLORING:** Try fundamentally different approaches (algorithms, architectures).
**If REFINING:** Narrow the search space or increase n_trials for the best approach.
**If SATURATED:** Ensemble top approaches, try novel architectures, or feature engineering.
**If STUCK:** Check if search spaces are mis-specified or if the approach itself is flawed.

STEP 4: GENERATE HYPOTHESES

Parameter types (search_space) are defined in project.yaml — the optimizer uses them automatically.
You focus on WHICH APPROACH to try, not which parameters to tune.

Each hypothesis MUST have:
- id: H-{{next number}}
- status: pending
- approach: "{{algorithm/method name}}"
- description: "{{what you're trying and why}}"
- reasoning: "{{cite technique, paper, prior experiment}}"

Optional:
- search_space: {{extra params specific to this approach, not already in project.yaml}}
- code_changes: "description of script changes needed" (triggers BUILD[code])
- optimize_type: "grid|random|custom" (override project default)
- references: ["papers", "URLs"]

Example:
- id: H-10
  status: pending
  approach: "xgboost_stacking"
  description: "XGBoost+LightGBM stacking ensemble"
  reasoning: "Stacking often outperforms individual models (Wolpert, 1992). Top 3 approaches were XGB, LGB, RF."

CRITICAL RULES:
- Do NOT define search_space per hypothesis unless the approach needs params NOT in project.yaml
- Same approach + different parameter ranges = NOT a new hypothesis (optimizer handles ranges)
- Each hypothesis = a fundamentally different strategy/algorithm

ANTI-PATTERN: Multiple hypotheses for the same approach with different search_space ranges.
GOOD PATTERN: Each hypothesis tries a fundamentally different approach.

STEP 5: WRITE GENERATION SUMMARY

Write to research/.generate_summary.json:

```json
{{
  "state": "EXPLORING|REFINING|SATURATED|STUCK",
  "reasoning": "2-3 sentence explanation",
  "best_so_far": {{"experiment_id": "EXP-XXX", "metric_value": 123.4, "config": "brief description"}},
  "hypotheses_added": ["H-XX", "H-YY"],
  "changes_made": ["added approach X", "narrowed search space for Y"],
  "references": ["technique or paper"],
  "experiments_analyzed": 10
}}
```

Also log what you did and why to research/loop.log (append a summary line)."""


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
    """Generate new hypotheses using AI provider."""
    levers_desc = []
    for name, lever in project["levers"].items():
        if "flag" in lever:
            levers_desc.append(f"  {name}: flag={lever['flag']}, baseline={lever['baseline']}, space={lever['space']}")
        else:
            levers_desc.append(f"  {name}: type={lever.get('type', 'choice')}, space={lever['space']}")

    opt_cfg = project.get("optimize", {})
    prompt = _GENERATE_PROMPT_TEMPLATE.format(
        project_name=project["name"],
        project_description=project.get("description", ""),
        metric_name=project["metric"]["name"],
        metric_direction=project["metric"].get("direction", "minimize"),
        optimize_type=opt_cfg.get("type", "random"),
        time_budget=opt_cfg.get("time_budget", "unlimited"),
        n_trials=opt_cfg.get("n_trials", "auto"),
        levers_text="\n".join(levers_desc),
        rules_text="\n".join("- " + r for r in project.get("rules", [])),
    )

    # Inject generation history context
    history = load_generate_history(project_dir)
    history_text = _format_history(history[-5:])
    if history_text:
        prompt = history_text + "\n\n" + prompt

    # Inject failure history so AI avoids repeating failed approaches
    failure_text = _format_failure_history(project_dir, project["metric"]["name"])
    if failure_text:
        prompt = failure_text + "\n\n" + prompt

    # Code-level escalation: force SATURATED if stuck in EXPLORING/REFINING
    forced = _check_escalation(history)
    if forced:
        escalation_msg = (
            f"MANDATORY ESCALATION: Last cycles were {[h.get('state') for h in history[-3:]]}.\n"
            f"You MUST classify as {forced} and take bold action:\n"
            f"1. Review ALL failed experiments — what patterns caused LOSS/INVALID?\n"
            f"2. Choose a fundamentally different approach (new algorithm, ensemble, feature engineering)\n"
            f"3. Do NOT tweak the same levers as recent failures\n"
            f"4. If levers are exhausted, ADD new levers to project.yaml"
        )
        prompt = escalation_msg + "\n\n" + prompt

    summary_path = generate_summary_path(project_dir)
    schema_path = Path(__file__).parent / "templates" / "codex" / "schemas" / "generate_summary.json"

    before = load_queue(project_dir)

    try:
        result = provider.run_structured(
            prompt,
            output_path=summary_path,
            schema_path=schema_path,
            tools=["Read", "Write", "Edit", "Bash", "WebSearch", "WebFetch"],
            cwd=str(project_dir),
        )
        if result.returncode != 0:
            log(f"GENERATE: {provider.name} exited with code {result.returncode}")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-10:]:
                    log(f"GENERATE: stderr: {line}")
    except RuntimeError as e:
        log(f"GENERATE: {e}")
        return False

    # Sanitize YAML: AI may have written unquoted colons or other YAML-unsafe text.
    # Re-save through yaml.dump to ensure valid YAML.
    _sanitize_queue_yaml(project_dir)

    # Validate new entries
    after = load_queue(project_dir)
    valid_count = _validate_new_entries(before, after, project_dir)

    # Archive generation summary to history
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
