You are validating a seed idea before the next iteration begins.

Current iteration: {iter}
Project directory: {project_dir}

## Your Task

Read these files:

- research/{iter}/reflect.json — the reflection with future_iteration_seeds and new_idea
- research/constraints.json — invariants that must hold
- research/convergence_log.json — history of past approaches (if exists)

## Step 1: Extract the seed

From reflect.json, get the `new_idea` field (or the top `future_iteration_seeds` entry).
This is the proposed direction for the next iteration.

## Step 2: Constraint check

For each invariant in constraints.json:

- Does the seed violate it? Even implicitly?
- Does the seed's approach fall within exploration_bounds?

If ANY constraint is violated:

- Set status to "alert"
- Explain which constraint is violated and why

## Step 3: Specificity check

Score the seed on a 1-10 specificity scale (same as shape_full):

- > 7: Too specific — the reflection over-prescribed the next step
- <3: Too vague — the reflection didn't concretize enough
- 3-7: Good range

If outside 3-7, adjust the seed to bring it into range.

## Step 4: Write output

Write research/{iter}/.seed_validation.json:

```json
{
  "original_seed": "the seed as stated in reflect.json",
  "status": "pass | alert",
  "specificity_score": 5,
  "constraint_violations": [],
  "adjustments": ["any modifications made to bring seed into range"],
  "validated_seed": "the final seed (possibly adjusted)",
  "alert_reason": "only if status is alert"
}
```

## Important

- If status is "pass", the engine will proceed automatically.
- If status is "alert", the engine will notify the user.
- Do NOT block good seeds — only alert on genuine constraint violations.
- Minor adjustments to specificity are fine and should be done silently.
