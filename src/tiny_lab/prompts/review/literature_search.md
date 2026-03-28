You are searching for papers for a systematic literature review.

Current iteration: {iter}

## Context

Read research/{iter}/.scope.yaml for research questions, inclusion/exclusion criteria, and search terms.

## Your Task

Use WebSearch to find relevant papers. Search multiple sources:

1. Google Scholar: "site:scholar.google.com {search_terms}"
2. arXiv: "site:arxiv.org {search_terms}"
3. Semantic Scholar: "site:semanticscholar.org {search_terms}"
4. Domain-specific venues mentioned in scope

For each paper found:

- Title, authors, year, venue
- Abstract summary (1-2 sentences)
- Relevance to each research question (high/medium/low)
- Passes inclusion criteria? (yes/no with reason)

## Screening

Apply inclusion/exclusion criteria from scope.yaml to filter papers.

## Output

Write to research/{iter}/.papers_collected.yaml:

- papers: list of accepted papers (title, authors, year, venue, url, relevance_summary)
- total_found: total papers discovered
- after_screening: papers that passed screening
- search_queries_used: list of queries executed
- gaps: topics with few/no results (may need additional searches)
