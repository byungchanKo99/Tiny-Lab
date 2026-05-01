You are closing the cycle between the phase that just ran and the next
one. The point is to make the hypothesis update _visible_ — to record
not only what happened but how it changes the outgoing hypothesis.

Without this step, results pile up but the hypothesis trail goes
silent — exactly the failure mode the DBI LAB analysis surfaced
("결과만 기록되고 해석이 누락되는 패턴").

Current iteration: {iter}
Project directory: {project_dir}
Phase that just ran: {current_phase_id}

## Inputs to read

- `research/{iter}/research_plan.json` — find the entry whose `id` matches
  `{current_phase_id}` to recover the _incoming hypothesis_ the phase was
  supposed to test.
- `research/{iter}/results/{current_phase_id}*.json` — what the phase
  actually produced. Read every result file for this phase, not just one.
- `research/{iter}/phases/.hypothesis_log.json` — earlier entries from
  this iteration's preceding phases (if any). Treat as append-only.
- `research/constraints.json` — invariants the outgoing hypothesis must
  still respect.

## What to write

Append (do not overwrite) one entry to
`research/{iter}/phases/.hypothesis_log.json`. Schema for the file:

```json
{
  "iteration": {iteration},
  "entries": [
    {
      "phase_id": "phase_3_baseline",
      "ran_at": "<ISO timestamp>",
      "incoming_hypothesis": "1 sentence — the claim the phase was set up to test",
      "result_interpretation": "1-2 sentences — what the result *means*, not just the metric value",
      "outgoing_hypothesis": "1 sentence — the updated claim that next phases should test",
      "drift_axis": "mechanism | metric | scope | tool | none"
    }
  ]
}
```

If the file does not exist yet, create it with `iteration` set and
`entries` containing only the new entry. If it exists, parse, append the
new entry to `entries`, and write back.

## Field-by-field rules

- **incoming_hypothesis** must be the hypothesis the phase was _designed
  for_ — pull from research_plan.json's phase description, not from your
  imagination after the fact.
- **result_interpretation** must reference at least one concrete result
  (e.g., "MAE 3.4 confirms the model captures short-horizon trends but
  fails on extreme events — see results/phase_3_baseline.json"). Vague
  interpretations like "the model improved" are not allowed.
- **outgoing_hypothesis** can be one of:
  - confirmed (same hypothesis, more confident → state it again with
    sharper conditions)
  - refined (same direction, narrower or wider scope)
  - replaced (the result killed the incoming hypothesis → outgoing is
    a new claim that explains the result)
  - opened (result revealed a sub-question → outgoing is the sub-question)
- **drift_axis** captures _what_ moved between incoming and outgoing:
  - mechanism — the proposed cause of the effect changed
  - metric — the success criterion changed
  - scope — the population / dataset / setting changed
  - tool — the implementation approach changed
  - none — outgoing equals incoming

## Hard rules

- Append-only. Never delete or rewrite previous entries — they are the
  iteration's hypothesis trail.
- If the result file is missing or unreadable, write the entry anyway
  with `result_interpretation: "phase output unavailable — see error log"`
  and `drift_axis: "none"`. The trail must not have gaps.
- Do not change `research_plan.json` from this step. Plan changes are
  the next CHECKPOINT's job.
