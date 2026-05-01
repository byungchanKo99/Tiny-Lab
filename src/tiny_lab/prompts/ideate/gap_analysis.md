You are doing gap analysis on the literature scan.

This is the **GAP_ANALYSIS** step of `ideate-deep`. Goal: identify where
the open opportunities are, so DIVERGE can target them rather than re-doing
work that already exists.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read these files:

- research/{iter}/.lit_scan.json — sub-problems, methods, key papers
- research/{iter}/.lit_scan.ref_verification.json (if exists) — which
  papers were verified as real; treat unverified/not_found citations as
  weak evidence
- research/constraints.json — domain bounds, invariants

## Step 1: Distinguish gap types

For each sub-problem from .lit_scan.json, identify gaps in three buckets:

### Explicit gaps

These are gaps the literature itself flagged. Look for "future work,"
"limitations," "remaining challenges," etc., from the scan summary or
your knowledge of the cited papers.

### Implicit gaps

Gaps the literature didn't name but are visible from the structure of the
scan. Examples:

- Methods commonly compared on dataset A, but never on dataset B
- A combination of two well-known approaches that nobody seems to have
  tried (and an explanation of why this is non-obvious — not just "X + Y")
- Settings where dominant methods make assumptions that don't hold (e.g.,
  "all retrievers assume English; what about code-switched queries?")
- Metrics everyone reports but that don't actually capture what users care
  about

### Resolved-but-claimed gaps

Some papers might claim a gap exists when recent work has actually closed
it. Use `recent_direction` from the scan to flag any "fake gaps."

## Step 2: Rank opportunities

For each gap, score on:

- **Significance** (1-5): how much would solving this matter?
- **Tractability** (1-5): how reasonable is it to attempt with one
  researcher in 1-4 weeks?
- **Differentiation** (1-5): how distinct is this from what dominant
  methods already do?

Compute `opportunity_score = significance * tractability * differentiation`.
This is a coarse heuristic — use it to surface the top 3-5, not to make
the final pick.

## Step 3: Phrase each opportunity as a question

For the top 3-5 opportunities, write a sharp research question — the kind
that could become a hypothesis in DIVERGE.

- BAD: "More research is needed on X" (not a question)
- BAD: "How can we improve Y?" (too vague)
- GOOD: "Does adding step-back reasoning before retrieval reduce
  hallucination on multi-hop queries?"

## Step 4: Write output

Write research/{iter}/.gap_analysis.json:

```json
{
  "explicit_gaps": [
    {
      "sub_problem_id": "SP1",
      "gap": "1-2 sentences",
      "evidence": "where in the literature this is flagged",
      "significance": 4,
      "tractability": 4,
      "differentiation": 3,
      "opportunity_score": 48
    }
  ],
  "implicit_gaps": [
    {
      "sub_problem_id": "SP1",
      "gap": "...",
      "why_non_obvious": "why nobody has tried this yet",
      "significance": 3,
      "tractability": 5,
      "differentiation": 4,
      "opportunity_score": 60
    }
  ],
  "fake_gaps": [
    {
      "claim": "...",
      "actually_resolved_by": "paper / direction that closed it"
    }
  ],
  "ranked_opportunities": [
    {
      "rank": 1,
      "gap_id": "implicit_0",
      "opportunity_score": 60,
      "research_question": "sharp question",
      "target_sub_problem": "SP1",
      "reason_to_target": "1 sentence"
    }
  ]
}
```

## Important

- **Differentiation > significance** when picking what to feed DIVERGE.
  An incremental contribution to a saturated area scores low even if the
  area is significant.
- **Acknowledge weak evidence**: if your gap relies on papers that
  ref_verify marked unverified/not_found, flag it. Better to demote a
  shaky gap than build candidates on hallucinated context.
- **Top 3-5 only**: more dilutes DIVERGE's focus.
