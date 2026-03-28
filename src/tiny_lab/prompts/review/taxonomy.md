You are creating a taxonomy for a literature review.

Current iteration: {iter}

## Context

Read research/{iter}/.paper_analysis.yaml for themes, comparisons, and gaps.

## Your Task

Organize the analyzed papers into a structured taxonomy:

1. Define classification dimensions (e.g., by method, by application, by data type)
2. Place each paper into categories
3. Identify which categories are well-covered and which are sparse

## Output

Write to research/{iter}/.taxonomy.yaml:

- categories: hierarchical category structure
- classification_criteria: what dimensions are used
- paper_mapping: which papers belong to which categories
- coverage_analysis: well-covered vs sparse categories
