You are writing the final review paper that synthesizes all iterations of literature analysis.

Project directory: {project_dir}

## Your Task

Read ALL of these:

- research/constraints.json — original objective and scope
- research/.iterations.json — iteration history
- research/iter\_\*/.scope.json — scope definitions
- research/iter\_\*/.papers_collected.json — all collected papers
- research/iter\_\*/.paper_analysis.json — analysis results
- research/iter\_\*/.taxonomy.json — classification systems
- research/iter\_\*/review_draft.md — iteration-level drafts
- research/iter\_\*/reflect.json — reflections
- shared/knowledge/ — accumulated knowledge
- research/convergence_log.json — exploration trajectory (if exists)

## Paper Structure

Write research/final_paper.md:

```markdown
# [Title]: A Systematic Review of [Topic]

## Abstract

[Problem space, scope, method, key findings, number of papers reviewed, main contributions]

## 1. Introduction

[From constraints.json: why this review matters, research questions, scope boundaries]

## 2. Methodology

[Search strategy, inclusion/exclusion criteria, screening process, analysis method.
If multiple iterations: "Initial search yielded N papers; after expanding scope in iter_2, M additional papers were included."]

## 3. Taxonomy / Classification Framework

[The final classification system from the last taxonomy iteration.
Explain how categories were derived. Visual: table or tree diagram.]

## 4. Analysis by Category

[For each taxonomy category:

- What papers fall here?
- What are the common approaches?
- What are the results/findings?
- What are the limitations?
  Use comparison tables where possible.]

## 5. Cross-Cutting Themes

[Patterns that span multiple categories:

- Trends over time
- Methodological convergence/divergence
- Contradictions between studies
- Emerging directions]

## 6. Research Gaps

[Grounded in the taxonomy — which intersections are empty?
Prioritize by potential impact.]

## 7. Discussion

[What does this body of work tell us?
What are the limitations of THIS review?
What would change the conclusions?]

## 8. Conclusion

[Key takeaways, top 3 gaps, recommendation for future work.
Did we achieve constraints.goal.success_criteria?]

## References

[All papers from all iterations, properly formatted]
```

## Writing Principles

1. A review paper's value is in SYNTHESIS, not listing. Don't just describe papers — compare, contrast, and connect them.
2. The taxonomy should help readers navigate the field, not just organize your notes.
3. Gaps should be specific enough that a reader knows what paper to write next.
4. If iterations explored different angles (via EXPLORE), explain why and what each added.
