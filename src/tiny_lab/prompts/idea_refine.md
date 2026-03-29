You are refining a research idea using the Socratic method.

Current iteration: {iter}
Project directory: {project_dir}

## Context

You have domain knowledge and data understanding from previous steps:

- Read research/{iter}/.domain_research.json — domain SOTA, required preprocessing, pitfalls
- Read research/{iter}/.data_analysis.json — actual data characteristics, quality issues
- Read research/.user_idea.txt — the user's original idea (if exists)

## Your Task

Concretize the research idea until every aspect is decidable.

## Step 1: Decompose the idea into testable propositions

Break down into:

- Goal: what exactly are we trying to achieve?
- Inputs: what data goes in?
- Outputs: what comes out?
- Metric: how do we measure success? What's the target value?
- Baseline: what's the simplest approach to compare against?
- Constraints: real-time? offline? hardware limits?

## Step 2: Check decidability

For each proposition, verify:

- Is it precisely defined? (not "good performance" but "ATE < 50m")
- Can we observe it? (do we have the data to test this?)
- Can we evaluate it? (is the metric measurable?)

## Step 3: Ask about undecidable points

For anything that can't be decided from domain research + data analysis alone:

- Ask 1-3 targeted questions, most impactful first
- Vague preference words ("good", "fast", "accurate") MUST be converted to numbers
- If domain research provides a standard, propose it: "Domain standard is ATE@30s. Use this?"
- If the user is unavailable (autonomous mode), decide based on domain research and note the assumption

## Step 4: Gap analysis

Compare the user's idea against domain knowledge:

- What did the user mention that's covered?
- What essential steps from domain research are missing from the idea?
- What did domain research add that the user didn't think of?

## Step 5: Write refined idea

Write to research/{iter}/.idea_refined.json with required fields:

- goal: one sentence, specific and measurable
- inputs: exact list of features/data
- outputs: exact target variables
- metric: name, direction (minimize/maximize), target value
- constraints: list of constraints
- preprocessing_required: from domain research + data analysis
- gap_analysis:
  covered: what the user's idea already included
  added_from_domain: what domain research added
  user_decisions: decisions made (by user or by assumption in autonomous mode)
