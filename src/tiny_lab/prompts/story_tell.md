You are writing the final research paper that tells the story of this entire research journey.

Project directory: {project_dir}

## Your Task

Read ALL of these:

- research/constraints.json — the original objective and goal
- research/.iterations.json — iteration history (decisions, reasons)
- research/iter\_\*/reflect.json — each iteration's reflection
- research/iter\_\*/results/ — all experiment results (JSON + visualizations)
- research/iter\_\*/research_plan.json — each iteration's plan
- research/iter\_\*/paper_draft.md — iteration-level drafts (if they exist)
- shared/knowledge/ — accumulated prior research
- research/convergence_log.json — exploration trajectory (if exists)

## Paper structure

Write research/final_paper.md with the following structure:

```markdown
# [Title]

[Choose a title that captures the research contribution, not just the topic]

## Abstract

[3-5 sentences: problem, approach, key findings, significance.
This should stand alone — a reader should understand the contribution without reading further.]

## 1. Introduction

[Derive from constraints.json:

- What problem are we solving? (objective)
- Why does it matter?
- What constraints make it challenging? (invariants)
- What is our specific goal? (success_criteria)
- Brief overview of approach and findings]

## 2. Related Work

[Synthesize from shared/knowledge/:

- What methods exist for this problem?
- What are their strengths and limitations?
- How does our work differ?
  Do NOT just list papers — organize by theme and explain relationships]

## 3. Method

[Tell the STORY of discovery across iterations:

- "We first explored [iter_1 approach], which [result/insight]."
- "This led us to [iter_2 approach], motivated by [what we learned]."
- "After detecting convergence, we pivoted to [explorer seed], which [outcome]."
  The reader should understand WHY each decision was made, not just WHAT was done.
  Include key equations/algorithms for the winning approach.]

## 4. Experiments & Results

[Present results across ALL iterations:

- Comparison table: approach | metric | key parameters for each iteration's best result
- Highlight the progression: how did performance evolve?
- Include the most important visualizations (reference PNGs in results/)
- Report statistics: mean +/- std, confidence intervals where available]

## 5. Analysis

[Go deeper than results:

- Why did the winning approach work?
- Why did failed approaches fail? (root cause, not just "it didn't work")
- What patterns emerged across iterations?
- Where does the model still struggle? (error analysis)]

## 6. Discussion

[Broader implications:

- What is the contribution? (methodological? empirical? analytical?)
- What are the limitations? Be honest.
- What would a practitioner need to know to apply this?
- How does this relate to the broader field?]

## 7. Conclusion

[3-5 sentences:

- Did we achieve constraints.goal.success_criteria? By how much?
- What is the key takeaway?
- What is the most promising future direction?]

## References

[Compile from shared/knowledge/ and iteration-level domain research]
```

## Writing principles

1. **Narrative over enumeration** — Don't list results. Tell the story of how understanding evolved.
2. **Honesty over spin** — If results are mediocre, say so. If an approach failed, explain why.
3. **Specificity over vagueness** — Use exact numbers, not "significant improvement." Use exact method names, not "advanced techniques."
4. **Iteration as strength** — The fact that multiple approaches were tried is a feature, not a bug. It shows thorough exploration.
5. **Constraints as framing** — Use the invariants from constraints.json to explain why certain approaches were/weren't viable.

## Important

- This is NOT another iteration-level paper_draft. It covers the ENTIRE research journey.
- Reference specific files (results/phase_X.json, iter_N/paper_draft.md) for the reader's reference.
- If the research involved an Explorer (BFS) pivot, highlight it — that's a key part of the story.
- The paper should be self-contained: a reader who hasn't seen the raw data should understand the full arc.
