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

## Step 5.5: Classify the delta from the previous iteration

Read `research/.iterations.json` and the previous iter's
`research/iter_<N-1>/reflect.json` (skip if this is iter 1). Look at the
_concrete artifacts_ that changed (which result files appeared, which
research_plan.json phases changed, what new mentions appeared in the
paper draft) and classify the delta into ONE of:

- **continued** — same direction, same phase set, results similar in
  kind to last iter
- **deepened** — same direction, but added new analyses, sub-experiments,
  or refined the methodology in the same frame
- **pivoted** — same problem but different methodology family or framing
  (e.g., "metaphor → control-theoretic formulation")
- **new_track** — added a parallel research thread (new phase set
  unrelated to the previous one)
- **paused** — no real progress on the main thread; if 1-line status is
  identical to last iter, this is the honest label
- **completed** — the original goal was reached this iter

You must produce ONE concrete piece of evidence (file path or specific
phase id) that justifies the label — vague claims like "we made progress"
are not allowed. Also identify WHAT triggered this delta:

- **internal** — your own analysis of last iter's results
- **external** — a paper, dataset, reviewer note, or other outside input
- **timeline_pressure** — a deadline or external schedule
- **random** — exploration not tied to a specific signal

Carry these into Step 8's `delta_from_previous_iter`, `delta_evidence`,
and `delta_trigger` fields.

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

## Step 6.4: Generate, score, and select follow-up directions

If your decision may be `add_phases`, `idea_mutation`, or `domain_pivot`,
create an explicit `idea_portfolio` before deciding. Generate at least 3
candidate directions:

1. a conservative deepening direction grounded in the strongest artifact,
2. a diagnostic/error-analysis or ablation direction that could explain a
   surprising result or failure mode,
3. a more creative pivot, cross-dataset, cross-domain, or reframing
   direction that could change the research trajectory.

For each candidate, write:

- `direction`: one concrete next research direction
- `rationale`: why this follows from the evidence
- `evidence`: concrete artifact path or phase id
- `scores`: numeric 1-5 values for `novelty`, `feasibility`,
  `expected_information_gain`, `risk`, and `artifact_cost`
- `score`: your overall selection score
- `status`: `promote_next`, `defer`, or `discard`

Then choose exactly one `selected_direction`. Selection must not be random:
explain why the selected candidate has the best balance of information gain,
feasibility, novelty, risk, and artifact cost. The selected direction must
match one `idea_portfolio` candidate and one `promote_next`
`future_iteration_seeds` entry.

## Step 6.5: External trigger for any direction change

If your tentative decision is `idea_mutation` or `domain_pivot` (or the
delta classification was `pivoted` / `new_track`), identify the trigger
explicitly:

- **trigger_source**: paper | reviewer_feedback | external_event |
  pure_internal_analysis | timeline_pressure
- **trigger_artifact**: file path, URL, or 1-line external event
  description
- **trigger_date**: ISO date when the trigger arrived (use today if it's
  a fresh internal analysis)

Why this matters: pivots that look like "internal analysis" often were
actually triggered by an outside paper or a deadline a few days earlier.
Forcing this attribution helps EXPLORE later understand what kind of
external stimulus tends to unlock progress in this project.

Carry into Step 8's `pivot_trigger` field.

## Step 6.6: Framing change (optional)

A _framing change_ is when the **justification frame** for the same
problem shifts — e.g., "metaphor → control-theoretic formulation",
"empirical patch → principled mechanism", "single-task → multi-task
view". This is different from `pivoted` (which is a change in
methodology); framing is the change in _how you justify what you're
doing_.

If a framing change happened this iter, fill `framing_change` with:

- `from_frame` — 1 sentence describing the old justification
- `to_frame` — 1 sentence describing the new justification
- `axis` — justification | mechanism | scope | metric
- `evidence_artifact` — file path that documents the new frame

Otherwise omit the field.

## Step 6.7: Static drift check (drift_warning)

Read the previous 3 iterations' `reflect.json` (skip if fewer exist).
Compare their `delta_evidence` strings to the one you just wrote in
Step 5.5. If your new evidence is essentially the same as all 3 prior
ones (paraphrase aside) — i.e., you have been writing the same "what
changed" line for 4 iterations in a row — then set `drift_warning: true`.

When `drift_warning` is true, your decision in Step 7 MUST be one of
`idea_mutation` or `domain_pivot` — `add_phases` (continued/deepened
work) is blocked. The intuition: 4 iterations of the same delta is the
most reliable signal of hidden stagnation, even when individual results
look fine.

## Step 7: Decide

Choose ONE of these decisions:

- **done**: ONLY use this if ALL of the following are true:

  1. The original goal is fully achieved (metric target met)
  2. There are NO promising follow-up directions remaining
  3. You cannot think of a single experiment that would yield new insight
     If you have future_iteration_seeds or any "Future Work" ideas, you are NOT done — use idea_mutation instead.

- **add_phases**: Current direction is right, but we need more phases. Specify exactly what phases to add (e.g., "add ensemble phase", "add error analysis phase", "add missing baseline").

- **idea_mutation**: Results suggest a new research direction. This starts a new iteration. Use this when:

  - You have promising follow-up ideas (future_iteration_seeds)
  - The paper's Future Work section has actionable items
  - A different approach could yield better results
  - Cross-domain evaluation or new data could add value
    **Prefer this over done.** Research is iterative — if there's a next question worth asking, ask it.

- **domain_pivot**: Our domain understanding was wrong or incomplete. Need to research again from scratch.

## Step 8: Write reflection

Write to research/{iter}/reflect.json with required fields:

- **decision**: one of done, add_phases, idea_mutation, domain_pivot
- **reason**: 2-3 sentences explaining why, citing specific experiment results
- **best_result**: best experiment details (phase_id, metric_value, config)
- **diagnosis**: root cause analysis for gaps (from Step 2)
- **missing_experiments**: list of experiments that should be added (from Step 3)
- **contributions**: draft contribution bullets (from Step 4)
- **delta_from_previous_iter** (from Step 5.5): one of [continued, deepened, pivoted, new_track, paused, completed]. For iter 1, use "new_track".
- **delta_evidence** (from Step 5.5): one sentence — what concretely changed since the previous iter, citing a file path or phase id
- **delta_trigger** (from Step 5.5): one of [internal, external, timeline_pressure, random]
- **drift_warning** (from Step 6.7): true | false. If true, decision MUST be idea_mutation or domain_pivot
- **pivot_trigger** (from Step 6.5, only if decision is idea_mutation/domain_pivot OR delta is pivoted/new_track):
  - `trigger_source`: paper | reviewer_feedback | external_event | pure_internal_analysis | timeline_pressure
  - `trigger_artifact`: file path / URL / event description
  - `trigger_date`: ISO date
- **framing_change** (from Step 6.6, only if a framing change happened):
  - `from_frame`, `to_frame`, `axis`, `evidence_artifact`
- **idea_portfolio** (required unless decision is `done`): at least 3 candidate
  direction objects from Step 6.4, each with `direction`, `rationale`,
  `evidence`, `scores`, `score`, and `status`
- **selected_direction** (required unless decision is `done`):
  - `direction`: exactly one candidate direction from `idea_portfolio`
  - `reason`: why this was selected over the other candidates
  - `evidence`: concrete artifact path or phase id
  - `selection_rule`: the decision rule used
  - `score`: selected candidate score
- **selection_rationale** (required unless decision is `done`): one sentence
  explaining the tradeoff behind the selected direction
- **future_iteration_seeds**: list of `{direction, status, reason}` where status is one of:
  - `promote_next` — strong enough to drive the next iteration
  - `defer` — interesting but not now; revisit after current direction matures
  - `discard` — explored mentally and rejected; record why so it does not come back
    ALWAYS include this list, even if decision is "done".
- **abandoned_hypotheses** (optional but encouraged): list of `{hypothesis, reason}` for ideas
  killed in this iter — they will be appended to `shared/knowledge/abandoned.json` and
  consulted by EXPLORE to prevent revisiting the same dead ends.
- **new_idea**: (required if decision is idea_mutation) pick the most promising
  `promote_next` seed and expand it into a concrete research idea
- **carry_over**: (only if new iteration) which artifacts to keep

**Critical**: If any future_iteration_seed has status `promote_next`, your decision
should almost certainly be idea_mutation, not done. "I have a promotable idea but I'm
stopping" is a contradiction.

## Step 8.5: Append to abandoned set (if any)

If you wrote `abandoned_hypotheses`, also append each entry to
`shared/knowledge/abandoned.json` (create the file if missing). Schema:

```json
{
  "entries": [
    {"iteration": N, "hypothesis": "...", "reason": "...", "killed_at": "<ISO date>"}
  ]
}
```

EXPLORE will read this file and avoid generating seeds that match
abandoned hypotheses by keyword overlap.

## Step 9: Update convergence log

Read research/convergence_log.json (create if it doesn't exist).
Append an entry for this iteration:

```json
{
  "iteration": {iteration},
  "seed_summary": "one-line summary of this iteration's core approach",
  "seed_keywords": ["3-5 keywords describing the method/approach"],
  "outcome_summary": "one-line summary of the key result",
  "approach_category": "broad category label (e.g., 'rnn_sequence_model', 'tree_ensemble', 'statistical_baseline')"
}
```

Write the updated convergence_log.json to research/convergence_log.json.
This log is used by the engine to detect convergence and trigger exploration of new directions.

Be honest. If the results are mediocre, say so. If the idea needs to change, change it.
