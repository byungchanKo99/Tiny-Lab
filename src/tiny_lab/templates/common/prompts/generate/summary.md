You are writing a generation summary for a research loop.

DIAGNOSIS: {diagnose_state} — {diagnose_reasoning}
BEST SO FAR: {diagnose_best_so_far}
HYPOTHESES ADDED: {hypotheses_hypotheses_added}
CHANGES MADE: {hypotheses_changes_made}

Write a JSON summary to research/.step_summary.json with:

- state: "{diagnose_state}"
- reasoning: 2-3 sentence explanation of your diagnosis and choices
- best_so_far: {diagnose_best_so_far}
- hypotheses_added: {hypotheses_hypotheses_added}
- changes_made: {hypotheses_changes_made}
- experiments_analyzed: number of experiments you reviewed
- references: techniques or papers that inspired these hypotheses (optional)

Also append a one-line summary to research/loop.log.
