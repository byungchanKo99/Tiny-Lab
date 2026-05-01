You are evaluating candidate hypotheses on a scoring matrix.

This is the **EVALUATE_MATRIX** step. Score each candidate from DIVERGE on
three independent axes, then rank.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read research/{iter}/.diverge.json — the candidates to score.

Read research/{iter}/.ref_verification.json IF IT EXISTS — output of the
reference-verification hook. Penalize candidates whose `grounded_in` URLs
were marked `not_found`.

## Scoring rubric

Score each candidate on three axes, **0-10**, with explicit rationale.
**Do not average all three into a single number** until the final ranking
step — keep them separate so the user can see tradeoffs.

### Axis 1: Novelty (0-10)

How much does this candidate differ from existing published work?

- 0-3: this is exactly what existing papers already do
- 4-6: incremental — adapts an existing method to a new setting
- 7-9: novel combination or genuinely new angle
- 10: nobody has tried this (verify with WebSearch — claim with caution)

Required: cite at least one source you searched to support the score.
Honest "score 4 because [paper X] already does this" beats inflated 8s.

### Axis 2: Feasibility (0-10)

Can this be executed within reasonable resources (assume one
researcher, 1-4 weeks, standard compute)?

- 0-3: requires resources unavailable to most researchers
- 4-6: doable but with significant engineering or data collection
- 7-9: clear path with available tools/datasets
- 10: trivially executable

Consider:

- Data availability (public benchmark? proprietary?)
- Compute requirements (single GPU? multi-node?)
- Engineering complexity (custom training loop? off-the-shelf?)
- Evaluation difficulty (automated metric? human eval?)

### Axis 3: Falsifiability (0-10)

How crisply can H1 be tested against H0?

- 0-3: no clear way to operationalize, or H0 cannot be rejected with any
  reasonable experiment
- 4-6: testable but with subjective metric or unclear thresholds
- 7-9: clear quantitative test with established protocol
- 10: pre-registrable; the experiment design writes itself

## Step 1: Score each candidate

For every candidate from .diverge.json, produce:

```json
{
  "id": "C1",
  "novelty": { "score": 6, "rationale": "...", "evidence": ["url-1"] },
  "feasibility": { "score": 8, "rationale": "..." },
  "falsifiability": { "score": 7, "rationale": "..." },
  "ref_verification_penalty": 0,
  "weighted_total": 7.0,
  "key_risks": ["specific risk 1", "specific risk 2"],
  "killer_objection": "the single strongest reason this might fail"
}
```

`weighted_total` = `0.4 * novelty + 0.3 * feasibility + 0.3 * falsifiability`,
minus `ref_verification_penalty` (subtract 1.0 for each not_found URL in
the candidate's `grounded_in`).

## Step 2: Identify Pareto-optimal set

Some candidates dominate others (higher on every axis). The non-dominated
set is the "Pareto front" — these are the meaningful choices. Highlight it.

## Step 3: Rank with tradeoff commentary

Final ranking is NOT just by `weighted_total`. Include:

- The Pareto-optimal set (these are the only candidates worth selecting)
- For each Pareto-optimal candidate, one sentence on its distinctive
  tradeoff (e.g., "C2: highest novelty but lowest feasibility — high-risk
  bet")
- A recommended top-1 with reasoning, but acknowledge alternatives

## Step 4: Write output

Write research/{iter}/.evaluation_matrix.json:

```json
{
  "scored_candidates": [ ... per-candidate scoring objects ... ],
  "pareto_optimal_ids": ["C1", "C3"],
  "ranking": [
    {
      "rank": 1,
      "id": "C1",
      "weighted_total": 7.4,
      "tradeoff_note": "...",
      "is_pareto_optimal": true
    }
  ],
  "recommendation": {
    "top_id": "C1",
    "reasoning": "why this candidate over the others",
    "runner_up_id": "C3",
    "runner_up_reasoning": "..."
  }
}
```

## Important

- **Be honest with novelty scores.** Inflated novelty leads to wasted
  research effort. If you can find a paper that did 80% of this, score it 4.
- **Penalize hallucinated references.** A candidate built on fake citations
  has unverified novelty claims — apply the penalty rigorously.
- **Pareto > weighted total.** A candidate that wins one axis decisively
  may be the right pick even if its weighted_total is lower.
