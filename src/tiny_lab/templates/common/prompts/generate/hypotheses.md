You are generating hypotheses for a research loop.

PROJECT: {project_name}
METRIC: {metric_name} (direction: {metric_direction})
OPTIMIZER: {optimize_type} (time_budget: {time_budget}s, n_trials: {n_trials})

DIAGNOSIS: {diagnose_state}
{diagnose_reasoning}

ANALYSIS PATTERNS: {analyze_patterns}
FAILURE PATTERNS: {analyze_failure_patterns}

RESEARCH TECHNIQUES: {research_techniques}

LEVERS (for parameter flag mapping):
{levers_text}

RULES:
{rules_text}

Based on the diagnosis, generate 3-5 hypotheses.

YOU decide the STRATEGY (approach). The optimizer decides the PARAMETERS.

- DO: "Try stacking ensemble", "Try feature engineering with PCA"
- DON'T: "Try lr=0.05" (this is the optimizer's job)

**If EXPLORING:** Try fundamentally different approaches (algorithms, architectures).
**If REFINING:** Suggest narrowing search_space or increasing n_trials for best approach.
**If SATURATED:** Ensemble top approaches, novel architectures, feature engineering. At least 2 bold moves.
**If STUCK:** Diagnose pipeline issues, try minimal experiment to verify baseline.

Each hypothesis MUST have:

- id: H-{{next number}} (check existing IDs in research/hypothesis_queue.yaml)
- status: pending
- approach: "algorithm/method name"
- description: "what and why"
- reasoning: "cite technique, paper, prior experiment"

Append to research/hypothesis_queue.yaml under the hypotheses key. Do NOT remove existing entries.

Write step output as JSON to research/.step_hypotheses.json with:

- hypotheses_added: list of IDs added
- changes_made: any changes to project.yaml or code
