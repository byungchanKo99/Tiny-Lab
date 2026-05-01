You are generating diverse research candidates, grounded in a literature
scan and gap analysis.

This is the **DIVERGE** step of `ideate-deep`. Same goal as the lite
version (3-5 distinct candidate hypotheses), but you have richer inputs:
the field map and the ranked opportunities. Use them.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read these files (in this order):

- research/{iter}/.lit_scan.json — sub-problems, methods, key papers
- research/{iter}/.gap_analysis.json — ranked opportunities
- research/.shaped_input.json, research/constraints.json — user framing
- shared/knowledge/ — accumulated notes
- research/{iter}/.lit_scan.ref_verification.json (if exists) — which
  citations were verified

## Step 1: Map opportunities to candidates

Each candidate must address at least one entry from
gap_analysis.ranked_opportunities. Use the `gap_id` for traceability.

Spread candidates across opportunities — do not clump multiple candidates
on the highest-scoring gap if that means losing diversity.

## Step 2: Generate 3-5 candidates with diversity axes

Same diversity requirements as the lite version:

1. **Sub-problem axis**: don't bunch on one sub-problem
2. **Methodology axis**: different families
3. **Risk/payoff axis**: at least one safe + one ambitious

Plus, in deep mode:

4. **Gap-type axis**: include candidates that target different gap types
   (explicit vs implicit). Implicit-gap candidates tend to be higher
   novelty, lower confidence.

## Step 3: For each candidate, write a hypothesis with explicit grounding

Each candidate needs:

- **Hypothesis (H1)**: declarative, falsifiable
- **Null hypothesis (H0)**
- **Operational metric**: measurement protocol
- **Minimum viable evidence**: result threshold for supporting H1
- **Targeted gap_id**: which opportunity this addresses
- **Methodological precedent**: which key paper from .lit_scan.json
  inspires the method (cite by title; the verifier already confirmed
  these in the lit_scan step)
- **Distinguishing claim**: how does this candidate's H1 differ from the
  precedent paper's claim? (One sentence — this is the novelty argument.)

## Step 4: Map to next-preset

Same as lite: pick `ml-experiment | novel-method | data-analysis | review-paper`
per candidate.

## Step 5: Write output

Write research/{iter}/.diverge.json:

```json
{
  "diverge_strategy": "1-2 sentences on how you spread the candidates",
  "gap_coverage": {
    "addressed_gap_ids": ["implicit_0", "explicit_2"],
    "uncovered_gap_ids": ["implicit_1"],
    "uncovered_reason": "why these top-ranked gaps did not yield candidates"
  },
  "candidates": [
    {
      "id": "C1",
      "label": "short slug",
      "topic": "sub-problem this targets",
      "hypothesis": "H1 — single declarative sentence",
      "null_hypothesis": "H0",
      "operational_metric": "how to measure",
      "minimum_evidence": "what result counts as supporting H1",
      "methodology_family": "training-free | fine-tuned | retrieval | ...",
      "risk_payoff": "safe | balanced | ambitious",
      "sub_problem_axis": "label",
      "next_preset": "ml-experiment | novel-method | data-analysis | review-paper",
      "targeted_gap_id": "implicit_0",
      "methodological_precedent": {
        "title": "verbatim title of source paper",
        "url": "https://arxiv.org/..."
      },
      "distinguishing_claim": "how H1 differs from the precedent's claim",
      "grounded_in": ["url-1", "url-2"]
    }
  ]
}
```

## Important

- **Gap coverage matters**. Reviewers will check that high-ranked gaps
  from gap_analysis are addressed (or that you explained why not).
- **Distinguishing claim is the novelty argument** for EVALUATE_MATRIX.
  Make it sharp — vague claims get scored down.
- **Cite real sources only.** ref_verify will check `grounded_in` and
  `methodological_precedent.url` after this step writes.
- Aim for `len(candidates) ∈ [3, 5]`.
