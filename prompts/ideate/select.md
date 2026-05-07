You are finalizing the hypothesis selection.

This is the **SELECT** step — the user picks one candidate (or asks to
re-diverge / re-shape). Output is the canonical hypothesis.json that will
seed the downstream research preset.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read these files:

- research/{iter}/.diverge.json — original candidates
- research/{iter}/.evaluation_matrix.json — scored ranking
- research/.shaped_input.json — user's original framing

## Step 1: Present the recommendation to the user

Show the user:

1. The recommended top-1 candidate (id, hypothesis, weighted_total, key
   tradeoff)
2. The runner-up
3. The Pareto-optimal set as a brief table

Format compactly. The user is expected to read this in 30 seconds and
decide:

- **Accept top-1** → proceed with the recommendation
- **Pick a different candidate** → user names which (e.g., "C3")
- **Redo divergence** → "redo" — the candidates aren't satisfying; DIVERGE
  will run again
- **Reshape input** → "reshape" — the topic itself was off; SHAPE_LITE will
  re-run

## Step 2: Wait for user decision

Ask: "Which to select? (default: top-1, or 'C2' / 'C3' / 'redo' / 'reshape')"

If the session is non-interactive (autonomous fallback), select the top-1
recommendation and note the assumption.

## Step 3: Write hypothesis

Once a candidate is chosen, write the final hypothesis.

Write research/{iter}/hypothesis.json:

```json
{
  "verdict": "selected | redo | reshape",
  "selected_id": "C1",
  "hypothesis": "the chosen H1, declarative and falsifiable",
  "null_hypothesis": "H0",
  "operational_metric": "how to measure",
  "minimum_evidence": "what result counts as supporting H1",
  "rationale": "why the user (or top-1 default) picked this one",
  "rejected_with_reason": [
    { "id": "C2", "reason": "why it didn't win" }
  ],
  "next_preset": "ml-experiment | novel-method | data-analysis | review-paper",
  "handoff_constraints": {
    "objective": "rephrased for the next preset's SHAPE_FULL",
    "metric": { "name": "...", "direction": "minimize | maximize", "target": null, "unit": "..." },
    "invariants": [ ... carry over from constraints.json ... ],
    "exploration_bounds": {
      "allowed": [ ... narrowed from candidate ... ],
      "forbidden": [ ... carry over ... ]
    }
  },
  "decision_mode": "user | autonomous_default"
}
```

Also write a top-level **research/hypothesis.json** (mirror of the iteration
file, without the `{iter}/` prefix) so downstream presets can find it
without knowing the iteration number.

If `verdict` is `redo` or `reshape`, write minimal fields (verdict + reason
only) — the workflow will route accordingly and the full hypothesis will
be written after the re-run.

## Important

- **Do not invent a hypothesis** that wasn't in the candidate set. SELECT
  is for choosing, not inventing. If the user wants something not on the
  list, that's a `redo`.
- **Preserve the candidate's hypothesis verbatim** in the `hypothesis`
  field. Refine it only if the user explicitly asks.
- The `handoff_constraints` block is the bridge to the next preset — make
  it complete enough that running `tiny-lab init --preset <next> &&
tiny-lab shape research/.handoff_constraints.json` would work directly.
