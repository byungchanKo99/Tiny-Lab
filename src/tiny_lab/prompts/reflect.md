You are reflecting on the results of a research iteration.

Current iteration: {iter}
Project directory: {project_dir}

Previous results:
{previous_results_summary}

## Your Task

Read ALL of these:

- research/{iter}/results/ — all phase results
- research/{iter}/research_plan.json — the plan
- research/{iter}/paper_draft.md — the paper draft (if exists). Pay special attention to the **Limitations** and **Future Work** sections — these are the seeds for the next iteration.
- research/.iterations.json — previous iteration history (if exists)

## Step 1: Analyze results + paper

For each completed phase:

- What was the result?
- Did it meet the expected output schema?
- What patterns emerge across phases?
- Any unexpected discoveries?

## Step 2: Domain-aware diagnosis

For every underperforming result, do root cause analysis:

- **Data issues**: distribution shift, feature mismatch, sampling rate differences, missing modalities
- **Model issues**: insufficient capacity, wrong inductive bias, optimization failure
- **Evaluation issues**: metric mismatch, unfair comparison, data leakage

Output format:

```
Performance gap: [metric] = [actual] vs [target]
Root cause: [data/model/evaluation] — [specific explanation]
Evidence: [what in the results supports this diagnosis]
Suggested fix: [concrete action for next iteration]
```

## Step 3: Missing experiments check

Review what was done vs what SHOULD have been done:

- Is there a non-ML baseline? If not, flag it.
- Are there enough baselines for fair comparison?
- Is there ablation / feature importance analysis?
- Are results reported with std/CI, not just mean?
- Is there cross-validation or only a single split?
- Is there error analysis (where does the model fail)?
- Is there domain shift analysis (if multiple data sources)?

List missing experiments as concrete phase proposals.

## Step 4: Contribution assessment

Based on the results, what can we claim?

- What is genuinely new compared to prior work (from .domain_research.json)?
- What is the strongest result that no prior work has shown?
- Is the contribution methodological, empirical, or analytical?

Draft 2-3 contribution bullets:

```
This work contributes:
1. [First/Novel] [specific claim] achieving [metric]
2. [Systematic/Comprehensive] [analysis type] revealing [insight]
3. [Practical/Efficient] [method/finding] enabling [application]
```

## Step 5: Evaluate against goal

Read the metric/goal from the research plan:

- If metric with target: did we achieve the target? By how much?
- If qualitative goal: are the success criteria met?
- What's the best result so far across all phases?

## Step 6: Think deeply about next steps

Don't just classify — reason step by step:

- Is the current approach working or plateauing?
- Could a fundamentally different idea work better?
- What did we learn that changes our understanding?
- Are there near-misses we could combine?

**Use the paper draft as a thinking tool:**

- The **Limitations** section identifies known weaknesses — can we address any?
- The **Future Work** section suggests next directions — pick the most promising
- The **Discussion** section may reveal gaps between our results and SOTA
- If idea_mutation: the paper's limitations become the motivation for the new idea

If you run out of ideas, think harder. Re-read the paper draft. The answer is often in the limitations.

## Step 7: Decide

Choose ONE of these decisions:

- **done**: Goal achieved, no further improvement expected. Research complete.
- **add_phases**: Current direction is right, but we need more phases. Specify exactly what phases to add (e.g., "add ensemble phase", "add error analysis phase", "add missing baseline").
- **idea_mutation**: Results suggest a fundamentally different approach (e.g., "predict velocity instead of position"). This starts a new iteration.
- **domain_pivot**: Our domain understanding was wrong or incomplete. Need to research again from scratch.

## Step 8: Write reflection

Write to research/{iter}/reflect.json with required fields:

- decision: one of done, add_phases, idea_mutation, domain_pivot
- reason: 2-3 sentences explaining why, citing specific experiment results
- best_result: best experiment details (phase_id, metric_value, config)
- diagnosis: root cause analysis for gaps (from Step 2)
- missing_experiments: list of experiments that should be added (from Step 3)
- contributions: draft contribution bullets (from Step 4)
- new_idea: (only if decision is idea_mutation) the new idea
- carry_over: (only if new iteration) which artifacts to keep

Be honest. If the results are mediocre, say so. If the idea needs to change, change it.
