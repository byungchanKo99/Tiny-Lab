You are generating diverse research topic & hypothesis candidates.

This is the **DIVERGE** step of the ideate preset. Goal: produce 3-5
fundamentally different candidate hypotheses within the user's topic area,
so the next step can evaluate them on novelty/feasibility/falsifiability.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read these files first:

- research/.shaped_input.json — topic area, user motivation
- research/constraints.json — domain, invariants, exploration bounds
- shared/knowledge/ — any prior research notes (if iterating)

## Step 1: Survey the topic area (lightly)

Use WebSearch to ground yourself in the topic. You are NOT doing a full
literature review — just enough to know:

- What sub-problems exist in this area?
- What are 2-3 dominant approaches/methods?
- Where are the recently-noted gaps or open problems?

Save any useful sources to shared/knowledge/ as `<keyword>.md` notes (1-2
paragraphs each, with URLs).

**Do not invent papers.** Only cite sources you actually fetched.

## Step 2: Generate candidates with deliberate diversity

Produce **3-5 candidates** that differ across at least these axes:

1. **Sub-problem axis** — different facets of the topic (e.g., for
   "RAG hallucination": detection vs. mitigation vs. evaluation benchmark)
2. **Methodology axis** — different family of methods (e.g., training-free
   vs. fine-tuned vs. retrieval-augmented)
3. **Risk/payoff axis** — at least one "safe" candidate (low risk, smaller
   contribution) AND one "ambitious" candidate (higher risk, larger
   contribution if it works)

Anti-patterns to avoid:

- All candidates being slight variations of the same idea
- All candidates using the same methodology with different hyperparameters
- Candidates that violate constraints.invariants

## Step 3: For each candidate, draft a falsifiable hypothesis

Each candidate must include:

- **Hypothesis** (H1): a single declarative sentence that could be FALSE
  - GOOD: "Adding step-back reasoning before retrieval reduces RAG
    hallucination rate by ≥15% on TruthfulQA"
  - BAD: "Step-back reasoning helps RAG" (not measurable)
- **Null hypothesis** (H0): the contrary that the experiment must rule out
- **Operational metric**: how the hypothesis would be tested
- **Minimum viable evidence**: what result would count as supporting H1

## Step 4: Map to next-preset

For each candidate, suggest which downstream preset fits best:

- `ml-experiment` — model training/comparison
- `novel-method` — proposing a new architecture/algorithm
- `data-analysis` — pattern discovery in data
- `review-paper` — meta-analysis / survey

## Step 5: Write output

Write research/{iter}/.diverge.json:

```json
{
  "diverge_strategy": "1-2 sentences on how you spread the candidates",
  "literature_notes": [
    {
      "title": "Title of paper",
      "url": "https://...",
      "relevance": "why this informs candidates"
    }
  ],
  "candidates": [
    {
      "id": "C1",
      "label": "short slug (3-5 words)",
      "topic": "the specific sub-problem this targets",
      "hypothesis": "single declarative sentence (H1)",
      "null_hypothesis": "H0",
      "operational_metric": "how to measure",
      "minimum_evidence": "what result counts as supporting H1",
      "methodology_family": "training-free | fine-tuned | retrieval | ...",
      "risk_payoff": "safe | balanced | ambitious",
      "sub_problem_axis": "label for what facet this covers",
      "next_preset": "ml-experiment | novel-method | data-analysis | review-paper",
      "grounded_in": ["url-1", "url-2"]
    }
  ]
}
```

## Important

- **Diversity over polish.** Better to have 4 sharply different candidates
  than 5 polished-but-similar ones.
- **Falsifiability is non-negotiable.** If you cannot write a clear H0,
  rewrite the hypothesis until you can.
- **Cite real sources only.** A reference verification hook will check URLs
  after this step. Hallucinated citations will be removed and counted
  against the candidate.
- Aim for `len(candidates) ∈ [3, 5]`. Fewer than 3 means you didn't diverge
  enough; more than 5 dilutes the evaluation.
