You are writing a generation summary for a research loop.

DIAGNOSIS: {diagnose_state} — {diagnose_reasoning}
BEST SO FAR: {diagnose_best_so_far}
HYPOTHESES ADDED: {hypotheses_hypotheses_added}
CHANGES MADE: {hypotheses_changes_made}

PREPARATION RESULTS:

- Verified approaches: {prepare_verified}
- Packages installed: {prepare_installed_packages}
- Code changes: {prepare_code_changes}
- Lever changes: {prepare_lever_changes}
- Failed approaches: {prepare_failed}

Write a JSON summary to research/.step_summary.json with:

- state: "{diagnose_state}"
- reasoning: 2-3 sentence explanation of your diagnosis and choices
- best_so_far: {diagnose_best_so_far}
- hypotheses_added: {hypotheses_hypotheses_added}
- changes_made: combined list of hypothesis changes + preparation changes
- experiments_analyzed: number of experiments you reviewed
- references: techniques or papers that inspired these hypotheses (optional)

Also append a one-line summary to research/loop.log.
