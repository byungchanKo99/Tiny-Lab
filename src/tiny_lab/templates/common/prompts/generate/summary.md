You are writing a generation summary for a research loop.

DIAGNOSIS: {think_state} — {think_reasoning}
BEST SO FAR: {think_best_so_far}
HYPOTHESES ADDED: {think_hypotheses_added}
CHANGES MADE: {think_changes_made}

PREPARATION RESULTS:

- Verified approaches: {prepare_verified}
- Packages installed: {prepare_installed_packages}
- Code changes: {prepare_code_changes}
- Lever changes: {prepare_lever_changes}
- Failed approaches: {prepare_failed}

Write a JSON summary to research/.step_summary.json with:

- state: "{think_state}"
- reasoning: 2-3 sentence explanation of your diagnosis and choices
- best_so_far: {think_best_so_far}
- hypotheses_added: {think_hypotheses_added}
- changes_made: combined list of hypothesis changes + preparation changes
- experiments_analyzed: number of experiments you reviewed
- references: techniques or papers that inspired these hypotheses (optional)

Also append a one-line summary to research/loop.log.
