You are doing a focused literature scan to ground topic exploration.

This is the **LITERATURE_SCAN** step of `ideate-deep`. Goal: produce a
compact map of the topic area — sub-problems, dominant methods, and the
key papers — that DIVERGE and GAP_ANALYSIS will build on.

You are NOT doing a systematic review. You ARE doing 30-60 minutes of
informed scanning that a senior researcher would do before brainstorming.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read research/.shaped_input.json and research/constraints.json — the
topic area and any user-supplied background.

Check shared/knowledge/ — if prior runs left notes here, build on them
instead of re-scanning.

## Step 1: Decompose the topic into sub-problems

What are the 3-6 distinct sub-problems within this topic? Examples:

- Topic "RAG hallucination" → detection, mitigation, evaluation, attribution,
  retrieval-quality, prompt-format
- Topic "time-series weather forecasting" → short-horizon, long-horizon,
  uncertainty quantification, multi-variable, extreme events

For each sub-problem, write one sentence on what makes it distinct.

## Step 2: Identify dominant methods per sub-problem

For each sub-problem, list 1-3 dominant approach families with a 1-line
characterization. Be concrete (paper-level when possible), not generic.

- BAD: "use neural networks"
- GOOD: "encoder-only retrievers fine-tuned with contrastive loss (DPR,
  Contriever)"

## Step 3: Pull key papers (cite real ones only)

Use WebSearch to find 5-12 representative papers across the sub-problems.

For each paper:

- Title (verbatim)
- arXiv ID or DOI (preferred over bare URL)
- Year
- Sub-problem(s) it addresses
- Why it's representative (1 sentence)

**Hallucination guardrail**: Do not list a paper unless WebSearch returned
it. The PostToolUse `ref_verify` hook will check every URL/arXiv ID after
this step writes — `not_found` references are visible to downstream steps
and will lower confidence in your output.

Save the most useful 2-4 papers to `shared/knowledge/<slug>.md` as 1-2
paragraph notes (verbatim title, URL, what claim/finding to remember).

## Step 4: Recent direction (last 12-18 months)

What direction has the field moved in recently? One paragraph max. This
helps GAP_ANALYSIS distinguish "old gap that's been filled" from "still
open."

## Step 5: Write output

Write research/{iter}/.lit_scan.json:

```json
{
  "scan_summary": "2-3 sentence overview of what the topic looks like",
  "sub_problems": [
    {
      "id": "SP1",
      "label": "short slug",
      "description": "what makes this sub-problem distinct",
      "open_questions": ["specific question 1", "specific question 2"]
    }
  ],
  "dominant_methods": [
    {
      "sub_problem_id": "SP1",
      "method_family": "label",
      "characterization": "1-line description",
      "representative_papers": ["title 1", "title 2"]
    }
  ],
  "key_papers": [
    {
      "title": "verbatim title",
      "url": "https://arxiv.org/abs/...",
      "arxiv_id": "1234.56789",
      "doi": null,
      "year": 2024,
      "sub_problems": ["SP1"],
      "why_representative": "1 sentence"
    }
  ],
  "recent_direction": "1-paragraph trend summary",
  "search_queries_used": ["query 1", "query 2"]
}
```

## Important

- **Compact, not comprehensive.** Aim for 5-12 papers, not 50. Quality of
  selection matters more than coverage.
- **Honest gaps**: if you can't find good papers for a sub-problem, say so.
  An empty `representative_papers` list is better than a hallucinated one.
- **Cite real sources only.** Verification runs automatically.
