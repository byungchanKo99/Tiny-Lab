You are writing a research paper draft.

Current iteration: {iter}

## Context

Read all artifacts from this iteration:

- research/{iter}/.domain_research.yaml
- research/{iter}/.related_work.yaml
- research/{iter}/.method_design.yaml
- research/{iter}/research_plan.yaml
- research/{iter}/results/ — all experiment results
- research/{iter}/reflect.yaml

## Your Task

Write a complete paper draft following standard structure:

1. **Abstract** — problem, method, key result, conclusion (150-250 words)
2. **Introduction** — motivation, gap, contribution, paper structure
3. **Related Work** — from .related_work.yaml, position our work
4. **Method** — from .method_design.yaml, detailed description
5. **Experiments** — from results/, setup, baselines, results tables
6. **Discussion** — from reflect.yaml, analysis, limitations
7. **Conclusion** — summary, future work

Include placeholders for figures: [Figure 1: ...]

## Output

Write to research/{iter}/paper_draft.md as a complete markdown document.
