You are validating a literature review before synthesis begins.

Current iteration: {iter}
Project directory: {project_dir}

## Your Task

Read these files:

- research/{iter}/.scope.json — review scope (research questions, inclusion/exclusion criteria)
- research/{iter}/.papers_collected.json — collected papers
- research/{iter}/.paper_analysis.json — analysis results (themes, comparisons, gaps)
- research/{iter}/.taxonomy.json — classification system
- research/constraints.json — invariants and goal

## Validation Criteria

### A. Constraint alignment (MUST pass)

- Does the scope respect constraints.invariants?
- Are all papers within exploration_bounds?

### B. Coverage sufficiency

- Are enough papers collected to answer the research questions?
- Are key venues/authors in the field represented?
- Is there temporal coverage (not just one year)?

### C. Taxonomy quality

- Are classification categories mutually exclusive and collectively exhaustive?
- Is each paper classifiable under the taxonomy?
- Are categories justified by the data, not imposed top-down?

### D. Gap identification

- Are research gaps grounded in evidence (missing intersections in taxonomy)?
- Are gaps actionable (someone could write a paper to fill them)?

### E. Analysis depth

- Are comparisons across papers meaningful (not just listing)?
- Are contradictions between papers identified?
- Are methodological strengths/weaknesses noted?

## Output

Write research/{iter}/.plan_validation.json:

```json
{
  "verdict": "APPROVE or REJECT",
  "checks": {
    "constraint_alignment": "pass or fail",
    "coverage_sufficiency": "sufficient or insufficient",
    "taxonomy_quality": "clear or weak",
    "gap_identification": "grounded or superficial",
    "analysis_depth": "deep or shallow"
  },
  "issues": [
    {
      "criterion": "...",
      "severity": "blocker or warning",
      "description": "...",
      "suggestion": "..."
    }
  ],
  "required_fixes": []
}
```
