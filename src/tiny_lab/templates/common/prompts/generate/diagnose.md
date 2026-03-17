You are diagnosing the state of a research loop.

ANALYSIS:

- Total experiments: {analyze_total_experiments}
- Wins: {analyze_wins}, Losses: {analyze_losses}, Invalids: {analyze_invalids}
- Best: {analyze_best_experiment}
- Patterns: {analyze_patterns}

{generation_history}

{escalation}

Classify the current research state:

- **EXPLORING** — fundamentally different approaches remain untried
- **REFINING** — best approach found, optimizer can narrow search space
- **SATURATED** — current approaches exhausted, need major strategic shift
- **STUCK** — many failures, something is fundamentally wrong

IMPORTANT: Focus on APPROACHES, not parameter values. The optimizer handles parameters.
If last 2+ cycles were EXPLORING/REFINING, you MUST escalate to SATURATED.

Write your diagnosis as JSON to research/.step_diagnose.json with:

- state: one of EXPLORING, REFINING, SATURATED, STUCK
- reasoning: 2-3 sentence explanation
- best_so_far: {{experiment_id, metric_value, config}}
