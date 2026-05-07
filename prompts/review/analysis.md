You are analyzing collected papers for a literature review.

Current iteration: {iter}

## Context

Read research/{iter}/.papers_collected.json for the list of accepted papers.
Read research/{iter}/.scope.json for the research questions.

## Your Task

For each paper, extract:

- Key findings and contributions
- Methodology used
- Strengths and limitations
- How it addresses each research question

Then identify cross-paper patterns:

- Common themes across papers
- Contradictions or disagreements
- Methodological trends
- Research gaps not addressed

## Output

Write to research/{iter}/.paper_analysis.json:

- themes: list of identified themes with supporting papers
- comparisons: key comparison points across papers
- gaps: what the literature doesn't address
- methodology_trends: common and emerging methods
- per_paper: list of individual paper analyses
