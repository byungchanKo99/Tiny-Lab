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

    prompt = f"""You are the autonomous research strategist for an experiment loop.
You don't just generate hypotheses — you drive the entire research forward.
Think like a senior researcher who comes in, reviews all results so far, and decides what to try next.

PROJECT: {project['name']}
DESCRIPTION: {project['description']}
METRIC: {project['metric']['name']} (direction: {project['metric'].get('direction', 'minimize')})

CURRENT LEVERS:
{chr(10).join(levers_desc)}

RULES:
{chr(10).join('- ' + r for r in project.get('rules', []))}

STEP 1: READ AND ANALYZE (do this first, do not skip)

Read these files and build a mental model of the research so far:
- research/ledger.jsonl — all past experiments. Analyze: which worked, which didn't, what patterns emerge.
- research/questions.yaml — research questions. Which are answered? Which remain open?
- research/hypothesis_queue.yaml — what's pending, what's done. Are we stuck in a rut?
- research/project.yaml — current configuration, levers, baseline command.

Also read the actual experiment script/code if it exists. Understanding what the code does
helps you propose smarter experiments.

STEP 2: DIAGNOSE THE RESEARCH STATE

Based on your analysis, classify the current state:

A. **EXPLORING** — untried values remain in current levers → generate hypotheses from untried values.
B. **REFINING** — best region found, need finer granularity → add intermediate values around the best result.
C. **SATURATED** — current levers fully explored, diminishing returns → time to evolve.
D. **STUCK** — many INVALID/LOSS, something is fundamentally wrong → diagnose and fix.

STEP 3: ACT BASED ON STATE

**If EXPLORING:**
- Pick untried values, prioritize based on trends in existing results.
- If a lever trends upward, try higher values. If noisy, fill gaps.

**If REFINING:**
- The best experiment so far used specific lever values. Add finer-grained values around those.
- Edit research/project.yaml to extend the lever's space with interpolated values.
- Example: best was rate=1.1, space was [0.8, 0.9, 1.0, 1.1, 1.2] → add [1.05, 1.15, 1.25]

**If SATURATED — this is where you earn your keep:**
You have FULL AUTHORITY to evolve the research. Do any of the following:

1. **Add new levers** — read the experiment script, find parameters not yet experimented with.
   Add them to research/project.yaml with a reasonable search space.

2. **Change the approach** — if flag-based experiments plateau, consider:
   - Feature engineering: create new input features from existing data
   - Algorithm change: try a different model/method entirely
   - Ensemble: combine the best configurations
   - Preprocessing: normalize, scale, handle outliers differently

3. **Modify the experiment code** — if build.type allows it, or if you can propose a code change:
   - Write a new script variant
   - Add a preprocessing step
   - Implement an ensemble of the top-performing configurations

4. **Update research questions** — add new questions to research/questions.yaml
   that reflect what you've learned and what's worth exploring next.

5. **Change the baseline** — if experiments consistently beat the original baseline,
   update baseline.command in project.yaml to the best-known configuration.
   Future experiments will be measured against this new bar.

**If STUCK:**
- Read research/loop.log for error details
- Check if the experiment command is working
- Verify data files exist and are valid
- Simplify: try a minimal experiment to confirm the pipeline works

STEP 4: GENERATE HYPOTHESES

After any modifications to project.yaml, generate 3-5 hypotheses.

Each hypothesis MUST have:
- id: H-{{next number}} (check existing IDs in the queue)
- status: pending
- lever: {{lever name, "multi" for combinations, or new lever name if you added one}}
- value: {{value to try}}
- description: "{{one line — include your REASONING, not just what you're changing}}"

Append to research/hypothesis_queue.yaml under the hypotheses key.
Do NOT remove existing entries.

IMPORTANT: Every hypothesis description should explain WHY, not just WHAT.
Bad:  "Try learning_rate 0.05"
Good: "Learning rate 0.01 won by 15% over 0.02 — try 0.05 to see if the trend continues or if we've overshot"

Log what you did and why to research/loop.log (append a summary line)."""

    before = load_queue(project_dir)

    try:
        result = run_claude_fn(prompt, allowed_tools="Read,Write,Edit,Bash", cwd=str(project_dir))
        if result.returncode != 0:
            log(f"GENERATE: AI subprocess exited with code {result.returncode}")
    except RuntimeError as e:
        log(f"GENERATE: {e}")
        return False

    # Validate new entries
    after = load_queue(project_dir)
    valid_count = _validate_new_entries(before, after, project_dir)

    return valid_count > 0
