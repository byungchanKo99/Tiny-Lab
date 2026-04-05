You are forcing exploration in a new direction. The system has detected convergence —
recent iterations have been too similar in approach.

Current iteration: {iter}
Project directory: {project_dir}

## Your Task

Read these files:

- research/convergence_log.json — what has been tried so far
- research/constraints.json — boundaries that must be respected
- shared/knowledge/ — accumulated knowledge from prior research
- research/{iter}/reflect.json — the latest reflection

## Step 1: Map the explored space

List ALL approach_categories from convergence_log.json entries.
For each, note:

- What was the core idea?
- What was the outcome? (best metric, key insight)
- Why might it have plateaued?

## Step 2: Root cause analysis of the plateau

Before exploring new directions, understand WHY the current approach plateaued.
This is critical — without understanding the wall, you'll just hit it again from a different angle.

Ask yourself:

- What is the **bottleneck**? Is it data, model capacity, problem formulation, or feature quality?
- Which features/inputs contribute most to the current best result? Why?
- Are there **implicit dependencies** in the current approach? (e.g., relying on a signal that won't be available at inference time)
- Is the model learning what we WANT it to learn, or a shortcut?
- What would a **domain expert** say is the fundamental limitation?

Write a brief diagnosis (2-3 sentences) before proceeding.

## Step 3: Identify unexplored directions

Based on the explored space, the plateau diagnosis, and shared/knowledge/, identify directions NOT yet tried.

**Think at multiple abstraction levels:**

### Level 1 — Problem decomposition

Can the problem be broken into sub-problems that are each easier to solve?

- What intermediate results could be produced first, then used as input to the next stage?
- Can a sub-task teach the system useful representations that the main task alone can't?
- Is there a natural pipeline in this domain where output of step A feeds into step B?

### Level 2 — Problem reframing

- Different formulation of the same goal (e.g., predict relative instead of absolute, classify instead of regress)
- Different input/output relationship (end-to-end → multi-stage, direct → residual)
- Different paradigm (single-pass → iterative refinement, bottom-up → top-down)

### Level 3 — Methodology change

- Different family of methods entirely (e.g., analytical → empirical, generative → discriminative)
- Different representation of the same data (e.g., raw → transformed, flat → hierarchical)
- Different optimization target (primary metric → proxy metric, single → multi-objective)

### Level 4 — Input/data perspective

- What if a key input is a CLUE, not just a feature? ("X is important" → "learn to produce X first")
- What if removing an input reveals a more robust signal?
- What if the available data contains information that could serve as a better training signal?

### Level 5 — Domain knowledge exploitation

- What domain-specific rules, constraints, or structure could be directly encoded into the approach?
- What would a domain expert do manually that the current system doesn't do?
- What approaches from the domain literature (in shared/knowledge/) have NOT been tried?

Filter out anything in constraints.exploration_bounds.forbidden.

## Step 4: Select the most promising divergent direction

Pick ONE direction that is:

1. **Fundamentally different** from the last 3 iterations — not a variation, a genuine alternative
2. **Within constraints** — respects all invariants and exploration_bounds
3. **Grounded** — has some basis in domain knowledge or literature, not random

## Step 5: Generate concrete seed

Turn the direction into a concrete, actionable seed:

- Specific enough to plan experiments (specificity 4-6)
- Clear about what changes vs. previous iterations
- Explains WHY this direction might work where others didn't

## Step 6: Write output

Write research/{iter}/.explore_seed.json:

```json
{
  "plateau_diagnosis": "2-3 sentence root cause analysis of WHY the current approach hit a wall",
  "explored_space": [
    {
      "category": "...",
      "iterations": [1, 2],
      "outcome": "...",
      "plateau_reason": "..."
    }
  ],
  "unexplored_directions": [
    {
      "direction": "...",
      "basis": "why this might work",
      "novelty": "how it differs"
    }
  ],
  "selected_direction": "the chosen direction",
  "new_seed": "concrete description of the new research direction",
  "rationale": "why this direction is worth trying now",
  "difference_from_recent": "explicit comparison with last 3 iterations",
  "approach_category": "new category label for convergence tracking"
}
```

## Important

- The goal is DIVERSITY, not optimization. Don't pick "the most likely to improve metrics."
  Pick "the most different approach that still has a chance."
- If all obvious directions have been tried, think harder. Combine ideas from different
  iterations. Look at the problem from a completely different angle.
- The new seed will be passed to IDEA_REFINE, so it doesn't need to be a complete plan —
  just a clear direction with enough substance to refine.
