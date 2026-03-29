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

## Step 2: Evaluate against goal

Read the metric/goal from the research plan:

- If metric with target: did we achieve the target? By how much?
- If qualitative goal: are the success criteria met?
- What's the best result so far across all phases?

## Step 3: Think deeply about next steps

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

## Step 4: Decide

Choose ONE of these decisions:

- **done**: Goal achieved, no further improvement expected. Research complete.
- **add_phases**: Current direction is right, but we need more phases (e.g., "add ensemble phase").
- **idea_mutation**: Results suggest a fundamentally different approach (e.g., "predict velocity instead of position"). This starts a new iteration.
- **domain_pivot**: Our domain understanding was wrong or incomplete. Need to research again from scratch.

## Step 5: Write reflection

Write to research/{iter}/reflect.json with required fields:

- decision: one of done, add_phases, idea_mutation, domain_pivot
- reason: 2-3 sentences explaining why, citing specific experiment results
- best_result: best experiment details (phase_id, metric_value, config)
- new_idea: (only if decision is idea_mutation) the new idea
- carry_over: (only if new iteration) which artifacts to keep

Be honest. If the results are mediocre, say so. If the idea needs to change, change it.
