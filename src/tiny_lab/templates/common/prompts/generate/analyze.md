You are analyzing experiment results for a research loop.

PROJECT: {project_name}
METRIC: {metric_name} (direction: {metric_direction})

DOMAIN: {research_domain_type}
DATA: {research_data_characteristics}
CONSTRAINTS: {research_constraints}

RESEARCH FINDINGS:
{research_reasoning}

UNEXPLORED DIRECTIONS (from literature):
{research_unexplored_directions}

{failure_history}

Read these files and analyze:

- research/ledger.jsonl — all past experiments. Count WIN/LOSS/MARGINAL/INVALID. Find the best result.
- research/hypothesis_queue.yaml — what's pending, what's done.
- research/project.yaml — current configuration, search_space.

Also read the experiment script/code if it exists — understanding the actual implementation helps identify gaps.

Pay special attention to:

- LOSS and INVALID experiments — what patterns caused failures?
- Which approaches have been tried and which haven't?
- optimize_result in ledger entries — what parameters were optimal?
- Are the tried approaches appropriate for this domain type? (e.g., using tabular models for time series data is suboptimal)
- Which literature-suggested techniques from UNEXPLORED DIRECTIONS haven't been tried yet?

Write your analysis as JSON to research/.step_analyze.json with:

- total_experiments: total count
- wins, losses, marginals, invalids: counts by class
- best_experiment: {id, metric_value, approach}
- patterns: observed patterns from results
- failure_patterns: common failure patterns to avoid
- domain_mismatch: approaches that don't fit the domain (e.g., "random_forest used for time series without windowing")
- gap_analysis: techniques from literature not yet tried
