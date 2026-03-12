# Research Agent

You are the research agent for this project. Configuration is in `research/project.yaml`.

## Scope

- Work only within the project defined in `research/project.yaml`.
- Change command-line flags only unless a human explicitly asks for code edits.
- Launch through `bin/surface` on the configured lane.

## Architecture

This research loop is managed by a **deterministic Python state machine** (`bin/research_loop.py`).
The agent is only called for **hypothesis generation** — everything else (queue management,
command building, experiment execution, evaluation, recording) is handled by code.

## Hypothesis Generation

When invoked, read these files:

1. `research/project.yaml` — levers, metric, rules
2. `research/ledger.jsonl` — past results
3. `research/questions.yaml` — research questions
4. `research/hypothesis_queue.yaml` — existing queue

Generate new hypotheses using only levers and values defined in `project.yaml`.
Append them to `research/hypothesis_queue.yaml` in the structured YAML format.

## Hard Rules

1. One changed variable per run.
2. Follow all rules defined in `research/project.yaml`.
3. Do not edit the eval bundle.
4. Do not install packages from a hypothesis.
5. `INVALID` is not `LOSS`.

## Running the Loop

```bash
# Start the deterministic loop
python3 bin/research_loop.py

# Or from Claude Code
/research start
```
