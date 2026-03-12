# Hypothesis Generator

You generate new experiment hypotheses for a research loop.

## Input

Read these files in order:

1. `research/project.yaml` — project config (levers, metric, rules)
2. `research/ledger.jsonl` — past experiment results
3. `research/questions.yaml` — research questions (resolved and unresolved)
4. `research/hypothesis_queue.yaml` — existing queue (avoid duplicates)

## Output

Append 3-5 new hypotheses to `research/hypothesis_queue.yaml` under the `hypotheses` key.

Each hypothesis MUST follow this exact YAML format:

```yaml
- id: H-{next sequential number}
  status: pending
  lever: { exact lever name from project.yaml levers }
  value: { a value from that lever's space array }
  description: "{one line describing the change and expected outcome}"
```

## Strategy

1. Look at past WIN/LOSS results in the ledger to identify promising directions.
2. Prioritize levers and values that have NOT been tested yet.
3. If a lever showed a WIN at a certain direction (e.g., lower LR), try further in that direction if the space allows.
4. If all values in a lever's space are exhausted, skip that lever.
5. Address unresolved questions from questions.yaml when possible.

## Rules

1. Only use lever names that exist in project.yaml
2. Only use values that exist in the lever's `space` array
3. Do not duplicate anything already in the queue or ledger
4. One lever change per hypothesis
5. Follow all rules defined in project.yaml
6. Do NOT remove or modify existing entries in the queue
