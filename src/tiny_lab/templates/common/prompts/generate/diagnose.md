You are diagnosing the state of a research loop.

DOMAIN: {research_domain_type}
CONSTRAINTS: {research_constraints}

ANALYSIS:

- Total experiments: {analyze_total_experiments}
- Wins: {analyze_wins}, Losses: {analyze_losses}, Marginals: {analyze_marginals}, Invalids: {analyze_invalids}
- Best: {analyze_best_experiment}
- Patterns: {analyze_patterns}
- Domain mismatches: {analyze_domain_mismatch}
- Gap (untried from literature): {analyze_gap_analysis}
- Optimizer efficiency: {analyze_optimizer_efficiency}

{generation_history}

{escalation}

{stagnation}

Classify the current research state:

- **EXPLORING** — fundamentally different approaches remain untried (check gap_analysis)
- **REFINING** — best approach found, can deepen search or re-explore with more trials
- **SATURATED** — current approaches exhausted, need major strategic shift (ensemble, feature engineering, new paradigm)
- **STUCK** — many failures, something is fundamentally wrong

Decision guide:

- If gap_analysis has untried techniques → EXPLORING (try them first)
- If domain_mismatch is non-empty → STUCK (wrong approach types being used)
- If many MARGINAL and no WIN → SATURATED (marginal improvements, need paradigm shift)
- If last 2+ cycles were EXPLORING/REFINING → escalate to SATURATED
- If optimizer_efficiency shows underexplored approaches → REFINING with meta_actions to increase time_budget
- If best approach had few trials (underexplored) while other approaches had more → REFINING to re-run best with more trials
- If many experiments since best AND all recent variants are of the SAME model family → SATURATED (stuck in local optimum, need fundamentally different direction — not more variants of the same model)

IMPORTANT: Focus on APPROACHES, not parameter values. The optimizer handles parameters.

## Meta-actions

If the analysis shows optimizer configuration issues (underexplored approaches, insufficient time_budget), you can recommend meta-actions. These are changes to `project.yaml`'s `optimize` section, NOT new hypotheses.

Examples:

- `time_budget` too low for slow models → recommend increasing (guard rail: max 1800s, max 3x per cycle)
- `n_trials` too low → recommend increasing (guard rail: max 200, max 3x per cycle)

Write your diagnosis as JSON to research/.step_diagnose.json with:

- state: one of EXPLORING, REFINING, SATURATED, STUCK
- reasoning: 2-3 sentence explanation referencing domain context, gap analysis, and optimizer efficiency
- best_so_far: {experiment_id, metric_value, config}
- meta_actions: list of recommended optimize config changes (e.g., ["increase time_budget from 300 to 600"]). Empty list if no changes needed.
