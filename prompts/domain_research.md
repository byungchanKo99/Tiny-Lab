You are conducting domain research for a new AI research project.

Current iteration: {iter}
Project directory: {project_dir}

## Your Task

The user has an idea for a research project. Before planning anything, you must deeply understand the domain.

## Step 1: Read the user's idea

Read research/{iter}/.iteration_seed.json if it exists. When present, this
is the active research direction for the current iteration; use `new_idea`,
`future_iteration_seed`, `selected_direction`, `selection_rationale`,
`idea_portfolio`, and `rationale` as the research intent. Treat
`selected_direction` as the chosen direction and use `idea_portfolio` only as
context for why alternatives were deferred or discarded. If that file does not exist, read
research/{iter}/.explore_seed.json if it exists and use `new_seed`,
`selected_direction`, and `rationale`. Otherwise, read research/.user_idea.txt
if it exists. This is the user's raw research intent.

## Step 2: Search academic literature, bounded

Use WebSearch when it is available, but keep this state bounded enough for full-auto execution. Run at most two high-value searches before writing the artifact:

1. Domain-specific state of the art:

   - "{idea keywords} state of the art 2025"
   - "{idea keywords} benchmark models"

2. Academic papers:

   - "site:scholar.google.com {key terms}"
   - "site:arxiv.org {key terms} 2024 2025"

3. Practical benchmarks:

   - "kaggle {domain} winning solution"
   - "{domain} machine learning best practices"

4. Known pitfalls:
   - "common mistakes {domain} machine learning"
   - "{domain} data leakage preprocessing"

If WebSearch/WebFetch is unavailable, slow, or unnecessary for a synthetic/local task, do not stall. Write a conservative offline artifact with `references: []`, clearly mark `literature_search_status` as "offline_or_unavailable", and base `sota_models`, metrics, preprocessing, and pitfalls on stable general ML knowledge. Do not claim novelty, SOTA, or prior-work superiority from an offline artifact.

## Step 3: Synthesize findings

Write your findings to research/{iter}/.domain_research.json with these required fields:

- domain_type: detected problem type (e.g., "time_series_regression", "tabular_classification")
- sota_models: list of state-of-the-art models for this domain
- required_preprocessing: domain-specific preprocessing steps that are ESSENTIAL
- standard_metrics: what metrics are standard in this domain
- known_pitfalls: things that commonly go wrong
- references: list of papers/URLs with author, year, key findings
- literature_search_status: "searched" or "offline_or_unavailable"

## Step 4: Save to shared knowledge

Also save a copy of your findings to shared/knowledge/ so it persists across iterations:

- Write shared/knowledge/domain\_{domain_type}.json with the same content as the domain research
- If shared/knowledge/ already has domain research from a previous iteration, READ it first and MERGE new findings (don't overwrite — accumulate)

This prevents repeating the same literature search in future iterations.

Be thorough. The quality of the entire research depends on this step.
