You are analyzing experiment results for a research loop.

PROJECT: {project_name}
METRIC: {metric_name} (direction: {metric_direction})

RESEARCH FINDINGS:
{research_reasoning}

{failure_history}

Read these files and analyze:

- research/ledger.jsonl — all past experiments. Count WIN/LOSS/INVALID. Find the best result.
- research/hypothesis_queue.yaml — what's pending, what's done.
- research/project.yaml — current configuration, search_space.

Also read the experiment script/code if it exists.

Pay special attention to:

- LOSS and INVALID experiments — what patterns caused failures?
- Which approaches have been tried and which haven't?
- optimize_result in ledger entries — what parameters were optimal?

Write your analysis as JSON to research/.step_analyze.json with:

- total_experiments: total count
- wins, losses, invalids: counts by class
- best_experiment: {{id, metric_value, approach}}
- patterns: observed patterns from results
- failure_patterns: common failure patterns to avoid
