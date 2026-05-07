You are doing the inline handoff inside a single workflow run.

This is the **IDEATE_INLINE_HANDOFF** step — used only when the user
opted into `--ideate-first` to run ideate followed immediately by a
research preset in one continuous loop.

Project directory: {project_dir}

## Context

Read research/hypothesis.json — the selected hypothesis with
`handoff_constraints`.

## Your Task

Replace research/constraints.json with the `handoff_constraints` block
from hypothesis.json, so downstream research-preset states (DOMAIN_RESEARCH,
PLAN, etc.) see the correct objective/metric/invariants — not the
lightweight shape from SHAPE_LITE.

## Steps

1. Load hypothesis.json
2. Extract the `handoff_constraints` object
3. Write it to research/constraints.json (overwrite — the lite shape is
   intentionally replaced by the post-ideation, sharper version)
4. Append to research/.handoff_log.md a one-line note recording the
   transition (timestamp + selected_id + next_preset)

## Output schema (research/constraints.json)

```json
{
  "objective": "from handoff_constraints.objective",
  "goal": {
    "metric": "...",
    "direction": "minimize | maximize | null",
    "target": null,
    "unit": "...",
    "success_criteria": "from minimum_evidence in hypothesis"
  },
  "invariants": ["..."],
  "exploration_bounds": {
    "allowed": ["..."],
    "forbidden": ["..."]
  },
  "ideated_from": {
    "selected_id": "C1",
    "hypothesis": "H1",
    "null_hypothesis": "H0",
    "iteration": "iter_N"
  }
}
```

The `ideated_from` field is required — it preserves the chain of reasoning
so downstream prompts (especially PLAN and STORY_TELL) can reference the
hypothesis explicitly.

## Important

- This is a deterministic file-rewrite step; do NOT change the
  hypothesis content. Just transform schema + add provenance.
- After this writes, the engine will route to the research preset's
  first post-shape state (e.g., DOMAIN_RESEARCH) — no further action
  needed from you.
