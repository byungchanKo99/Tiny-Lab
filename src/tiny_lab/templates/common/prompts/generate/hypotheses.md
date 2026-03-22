You are generating hypotheses for a research loop.

PROJECT: {project_name}
METRIC: {metric_name} (direction: {metric_direction})
OPTIMIZER: {optimize_type} (time_budget: {time_budget}s, n_trials: {n_trials})

DOMAIN: {research_domain_type}
CONSTRAINTS: {research_constraints}

DIAGNOSIS: {diagnose_state}
{diagnose_reasoning}

ANALYSIS PATTERNS: {analyze_patterns}
FAILURE PATTERNS: {analyze_failure_patterns}
DOMAIN MISMATCH: {analyze_domain_mismatch}
GAP ANALYSIS (literature techniques not yet tried): {analyze_gap_analysis}

UNEXPLORED DIRECTIONS (from research step): {research_unexplored_directions}

OPTIMIZER EFFICIENCY: {analyze_optimizer_efficiency}
META-ACTIONS RECOMMENDED: {diagnose_meta_actions}

{tried_families}

LEVERS (for parameter flag mapping):
{levers_text}

RULES:
{rules_text}

Based on the diagnosis and gap analysis, generate 3-5 hypotheses.

## Priority order for hypothesis generation:

1. **Gap analysis first** — if literature suggests techniques not yet tried, prioritize those
2. **Domain-appropriate** — approaches must fit the domain type (e.g., sequence models for time series, not random forest)
3. **Fundamentally different** — each hypothesis should be a genuinely different strategy, not a parameter variant

## Rules:

YOU decide the STRATEGY (approach). The optimizer decides the PARAMETERS.

- DO: "Try stacking ensemble", "Try Transformer encoder for sequence data"
- DON'T: "Try lr=0.05" (this is the optimizer's job)
- DON'T: Use approaches flagged as domain mismatches

**If EXPLORING:** Try approaches from gap_analysis and unexplored_directions.
**If REFINING:** Suggest narrowing search_space or increasing n_trials for best approach.
**If SATURATED:** Ensemble top approaches, novel architectures, feature engineering. At least 2 bold moves from literature.
**If STUCK:** Diagnose pipeline issues, try minimal experiment to verify baseline.

## Approach naming:

The approach name must match a key in `project.yaml` `approaches:` (if defined) or `search_space:`.

- If `approaches:` exists, the approach name maps to a `model` value via `approaches.{name}.model`
- If `approaches:` does not exist, the approach name is used directly as the `--model` value
- CORRECT: `approach: lgbm_tuned` (maps to `model: lgbm` via approaches), `approach: stacking_ensemble`
- WRONG: `approach: "python train.py --model lstm"` (command, not name)
- WRONG: `approach: "lstm_high_hidden_size"` (parameter description)

Each hypothesis MUST have:

- id: H-{next number} (check existing IDs in research/hypothesis_queue.yaml)
- status: pending
- approach: "algorithm/method name"
- description: "what and why — cite the gap analysis or literature finding"
- reasoning: "cite paper, benchmark, or prior experiment"

Append to research/hypothesis_queue.yaml under the hypotheses key. Do NOT remove existing entries.

Write step output as JSON to research/.step_hypotheses.json with:

- hypotheses_added: list of IDs added
- changes_made: any changes to project.yaml or code
