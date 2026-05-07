You are analyzing related work for a novel method paper.

Current iteration: {iter}

## Context

Read research/{iter}/.domain_research.json for domain SOTA and references.

## Your Task

Go deeper than domain research — focus on:

1. What are the specific limitations of existing methods?
2. Where is the research gap that our method will fill?
3. What prior attempts have been made to address this gap?
4. What makes existing approaches insufficient?

Use WebSearch for additional targeted searches:

- "{limitation} {domain} improvement"
- "beyond {existing_method} {domain}"

## Output

Write to research/{iter}/.related_work.json:

- papers: detailed list of related papers
- limitations_of_existing: specific limitations grouped by method
- research_gap: clear statement of what's missing
- our_position: how our work relates to and extends prior work
