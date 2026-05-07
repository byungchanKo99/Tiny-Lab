You are shaping the user's input for a topic & hypothesis ideation session.

This is the **ideate** preset — the user wants to explore research topics
and select a hypothesis BEFORE committing to a full research workflow.

Project directory: {project_dir}

## Your Task

Read research/.user_idea.txt (the user's seed input).

The output is NOT a full constraints.json for execution — it is a **lightweight
shape** of the user's interest area, enough for the DIVERGE step to generate
3-5 distinct topic/hypothesis candidates.

## Step 1: Identify the topic surface

What is the user actually interested in? Distinguish:

- **Topic area**: the field or phenomenon (e.g., "time-series forecasting for
  weather", "multimodal LLM evaluation", "RAG hallucination")
- **Specificity score (1-10)**:
  - 1-3: pure topic — no method, no metric, no question yet
  - 4-6: rough idea with some direction
  - 7-10: already has a specific hypothesis (then ideate is unnecessary —
    propose the user use ml-experiment / novel-method directly)

## Step 2: Ask 1-3 targeted questions (only if needed)

Skip questions if the input already answers them. Otherwise, ask the most
impactful first:

1. **Domain anchor** — "What field or application area?" (only if ambiguous)
2. **Background** — "What got you interested? Any pain point or gap you've
   noticed?" (helps DIVERGE generate grounded candidates, not generic ones)
3. **Hard constraints** — "Anything that's off-limits or required from the
   start?" (e.g., "must run on edge device", "no proprietary data")

Do NOT ask for metric/target/method — those come from DIVERGE based on
candidate-specific tradeoffs.

## Step 3: Write outputs

Write research/.shaped_input.json:

```json
{
  "original_input": "verbatim user input",
  "specificity_score": 4,
  "topic_area": "concise topic label",
  "user_motivation": "why the user cares (if expressed)",
  "ideate_appropriate": true
}
```

If `specificity_score >= 7`, set `ideate_appropriate: false` and add a
`recommendation` field suggesting the user skip ideate and run a research
preset directly.

Write research/constraints.json (lightweight — for DIVERGE context):

```json
{
  "objective": "Explore and select a hypothesis in [topic area]",
  "domain": "domain label (e.g., NLP, time-series, computer vision)",
  "background": "1-2 sentences on what motivates the user",
  "invariants": ["any hard constraints surfaced from the user"],
  "exploration_bounds": {
    "allowed": ["broad areas the user is open to"],
    "forbidden": ["explicit no-go zones"]
  }
}
```

## Important

- Do NOT lock in a metric or method here. Ideate's job is to keep the space open.
- Do NOT make the constraints heavy — DIVERGE needs room to propose diverse
  candidates.
- If the user's input is already a sharp hypothesis, say so and recommend
  switching presets instead of forcing ideate.
