You are refining a research idea using the Socratic method.

Current iteration: {iter}
Project directory: {project_dir}

## Context

You have domain knowledge and data understanding from previous steps:

- Read research/{iter}/.domain_research.json — domain SOTA, required preprocessing, pitfalls
- Read research/{iter}/.data_analysis.json — actual data characteristics, quality issues
- Read research/{iter}/.data_viz_manifest.json and inspect generated
  research/{iter}/data_viz/*.png when present — use the visual evidence and
  `researcher_readout` to decide preprocessing, target framing, leakage checks,
  baselines, and the first modeling move.
- Read research/{iter}/.iteration_seed.json if it exists. When present,
  this is the active seed for the current iteration; refine that new
  direction instead of falling back to the original user idea. If it contains
  `idea_portfolio`, `selected_direction`, or `selection_rationale`, preserve
  the selected direction's tradeoff logic and do not revive deferred or
  discarded candidates unless new evidence makes them relevant.
- Read research/.user_idea.txt — the user's original idea (if exists)
- If this is a REVISE loop, read the prior professor review and treat its required actions as the corrective brief:

{review_feedback_summary}

## Your Task

Concretize the research idea until every aspect is decidable.
If prior review feedback is present, the refined idea must explicitly address every required action or explain why it is no longer applicable.

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
- What did the data visualizations reveal that should change the framing,
  preprocessing, split protocol, baseline, or metric?

## Step 5: Write refined idea

Write to research/{iter}/.idea_refined.json with required fields:

- goal: one sentence, specific and measurable
- inputs: exact list of features/data
- outputs: exact target variables
- metric: name, direction (minimize/maximize), target value
- constraints: list of constraints
- preprocessing_required: from domain research + data analysis
- data_visualization_evidence:
  generated_figures: list of figure filenames from .data_viz_manifest.json that shaped the idea
  key_visual_patterns: concrete patterns observed in the figures
  implications_for_plan: how the visual evidence changes preprocessing, split, baselines, or phases
- gap_analysis:
  covered: what the user's idea already included
  added_from_domain: what domain research added
  user_decisions: decisions made (by user or by assumption in autonomous mode)
- review_response:
  required when prior REVISE feedback is present. Copy every prior required action exactly and state how the refined idea addresses it:
  addressed_required_actions: list of {action, how_addressed, planned_change}
  intentionally_deferred: list of {action, reason}; use only if a prior action is no longer applicable. The reason must explain what changed and name the replacement validation or framing.
- idea_provenance:
  inspirations: list of {paper_id_or_url, key_idea_borrowed, how_adapted}
  — every external source whose method/insight you are reusing,
  with one phrase on what you borrowed and one on how it was adapted
  here. Pulled from .domain_research.json references; any new source
  must be a real paper (the ref-verify hook will check).
  differentiation: one sentence — how this is NOT just `<closest prior
  work>`. Without this, EVALUATE/STORY_TELL has nothing to anchor
  novelty claims against.
