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


_GENERATE_PROMPT_TEMPLATE = """\
You are the autonomous research strategist for an experiment loop.
You don't just generate hypotheses — you drive the entire research forward.
Think like a senior researcher who comes in, reviews all results so far, and decides what to try next.

PROJECT: {project_name}
DESCRIPTION: {project_description}
METRIC: {metric_name} (direction: {metric_direction})

CURRENT LEVERS:
{levers_text}

RULES:
{rules_text}

STEP 1: READ AND ANALYZE (do this first, do not skip)

Read these files and build a mental model of the research so far:
- research/ledger.jsonl — all past experiments. Analyze: which worked, which didn't, what patterns emerge.
- research/questions.yaml — research questions. Which are answered? Which remain open?
- research/hypothesis_queue.yaml — what's pending, what's done. Are we stuck in a rut?
- research/project.yaml — current configuration, levers, baseline command.

Also read the actual experiment script/code if it exists. Understanding what the code does
helps you propose smarter experiments.

- Pay special attention to LOSS and INVALID experiments. What patterns caused failures? Do NOT repeat them.

STEP 2: DIAGNOSE THE RESEARCH STATE

Based on your analysis, classify the current state:

A. **EXPLORING** — untried values remain in current levers → generate hypotheses from untried values.
B. **REFINING** — best region found, need finer granularity → add intermediate values around the best result. Keep this phase SHORT (1-2 cycles max). If refinement yields <1% improvement, escalate to SATURATED.
C. **SATURATED** — current levers explored OR refinement stalled → time for a MAJOR strategic shift. This is the most important state — see below.
D. **STUCK** — many INVALID/LOSS, something is fundamentally wrong → diagnose and fix.

IMPORTANT: Do NOT stay in EXPLORING/REFINING forever. If the last 2+ generation cycles have been EXPLORING or REFINING within the same lever set, you MUST escalate to SATURATED and try something fundamentally different.

STEP 3: ACT BASED ON STATE

**If EXPLORING:**
- Pick untried values, prioritize based on trends in existing results.
- If a lever trends upward, try higher values. If noisy, fill gaps.

**If REFINING:**
- The best experiment so far used specific lever values. Add finer-grained values around those.
- Edit research/project.yaml to extend the lever's space with interpolated values.
- Example: best was rate=1.1, space was [0.8, 0.9, 1.0, 1.1, 1.2] → add [1.05, 1.15, 1.25]

**If SATURATED — this is where you earn your keep:**
You have FULL AUTHORITY to evolve the research. You MUST make bold, structural changes — not just tweak hyperparameters. Do at least 2 of the following per SATURATED cycle:

1. **Try fundamentally different models/algorithms** — don't just tune within one model family.
   If you've been tuning CatBoost, try neural nets, SVMs, or a completely different paradigm.
   If you've been doing gradient boosting, try stacking/blending the top performers.

2. **Ensemble the best configurations** — take the top 3-5 performing configs and combine them.
   Implement voting, stacking, or weighted averaging. This often beats any single model.
   Modify the experiment script to support ensemble mode if needed.

3. **Feature engineering** — create interaction features, polynomial features, target encoding,
   time-based features, or domain-specific transformations. Modify the experiment script.

4. **Change the approach entirely** — if flag-based experiments plateau:
   - Switch build.type to "code" and let experiments modify the script directly
   - Add preprocessing steps (scaling, outlier removal, feature selection)
   - Try dimensionality reduction before modeling
   - Implement cross-validation strategy changes

5. **Add new levers** — read the experiment script, find parameters not yet experimented with.
   Add them to research/project.yaml with an ambitious search space.

6. **Update research questions** — add new questions to research/questions.yaml
   that reflect what you've learned and what's worth exploring next.

7. **Raise the bar** — if experiments consistently beat the original baseline,
   update baseline.command in project.yaml to the best-known configuration.
   Future experiments will be measured against this new, higher bar.

ANTI-PATTERN: Generating 5 hypotheses that all tweak the same hyperparameter by small amounts.
GOOD PATTERN: 1 ensemble hypothesis + 1 new model family + 1 feature engineering + 2 novel ideas.

**If STUCK — systematic diagnosis protocol:**
1. Read research/loop.log for the last 5 error details
2. Identify the failure pattern:
   - Commands failing to execute? → check exit codes, paths, dependencies
   - Metric extraction failing? → check stdout format matches expected JSON
   - All experiments losing? → the baseline may have shifted, or lever space is exhausted
3. Based on diagnosis:
   - Pipeline broken → try a minimal experiment (simplest lever value) to verify baseline
   - Metric format changed → update the experiment script's output format
   - Losing pattern → escalate to SATURATED and try a fundamentally different approach
4. If 3+ experiments fail the same way, do NOT generate similar hypotheses

STEP 4: GENERATE HYPOTHESES

After any modifications to project.yaml, generate 3-5 hypotheses.

Each hypothesis MUST have:
- id: H-{{next number}} (check existing IDs in the queue)
- status: pending
- lever: {{lever name, or "multi" for combinations}}
- value: {{single string/number for one lever, OR a dict like {{"lr": "0.05", "batch_size": "32"}} for multi-lever}}
- description: "{{one line — include your REASONING, not just what you're changing}}"

MULTI-LEVER COMBINATIONS:
When you want to test multiple levers simultaneously, use lever: "multi" and value as a dict.
Example: {{id: H-10, status: pending, lever: "lr+batch_size", value: {{"lr": "0.05", "batch_size": "32"}}, description: "..."}}

Append to research/hypothesis_queue.yaml under the hypotheses key.
Do NOT remove existing entries.

IMPORTANT: Every hypothesis description should explain WHY, not just WHAT.
Bad:  "Try learning_rate 0.05"
Good: "Learning rate 0.01 won by 15% over 0.02 — try 0.05 to see if the trend continues or if we've overshot"

STEP 5: WRITE GENERATION SUMMARY

After generating hypotheses, write a JSON summary file to research/.generate_summary.json:

```json
{{
  "state": "EXPLORING|REFINING|SATURATED|STUCK",
  "reasoning": "2-3 sentence explanation of your diagnosis and why you chose these hypotheses",
  "best_so_far": {{"experiment_id": "EXP-XXX", "metric_value": 123.4, "config": "brief description"}},
  "hypotheses_added": ["H-XX", "H-YY", ...],
  "changes_made": ["extended lever X space", "added new lever Y", ...],
  "references": ["(optional) technique or paper that inspired these", "based on EXP-003 trend"],
  "experiments_analyzed": 10
}}
```

The 'references' field is optional — cite when a hypothesis is inspired by a technique, paper, or prior experiment.

This file will be overwritten each generation cycle. The loop will archive it.
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

    prompt = _GENERATE_PROMPT_TEMPLATE.format(
        project_name=project["name"],
        project_description=project["description"],
        metric_name=project["metric"]["name"],
        metric_direction=project["metric"].get("direction", "minimize"),
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
            tools=["Read", "Write", "Edit", "Bash"],
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
