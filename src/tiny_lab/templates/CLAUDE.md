# tiny-lab Research Project

This project uses **tiny-lab v6** -- a plan-driven AI research loop that automates the full cycle: understand, plan, execute, reflect.

## Quick Start

```bash
# 1. Write your research idea
echo "Your research idea here" > research/.user_idea.txt

# 2. Run the loop
tiny-lab run

# 3. The engine will:
#    - Research the domain (web search, literature)
#    - Analyze your data
#    - Refine the idea
#    - Create a research plan
#    - STOP at PLAN_REVIEW for your approval
#    - Execute phases (code, run, evaluate)
#    - Write a paper draft
#    - Reflect and iterate
```

## Workflow

```
DOMAIN_RESEARCH --> DATA_DEEP_DIVE --> IDEA_REFINE --> PLAN
    --> PLAN_REVIEW (mandatory stop -- you review here)
        approve    --> start execution
        modify     --> back to PLAN with feedback
        stop       --> end
    --> PHASE_CODE --> PHASE_RUN --> PHASE_EVALUATE --> PHASE_RECORD
    --> (repeat for each phase)
    --> PAPER_DRAFT --> REFLECT
        done       --> finish
        add_phases --> back to PLAN
        idea_mutation --> new iteration
```

## Commands

| Command                      | Description                                        |
| ---------------------------- | -------------------------------------------------- |
| `tiny-lab init`              | Initialize project (default: ml-experiment preset) |
| `tiny-lab run`               | Start or resume the research loop                  |
| `tiny-lab run "your idea"`   | Start with a research idea                         |
| `tiny-lab status`            | Show current state, iteration, phase               |
| `tiny-lab board`             | Results dashboard with metrics                     |
| `tiny-lab intervene approve` | Approve plan and continue                          |
| `tiny-lab intervene modify`  | Send plan back for revision                        |
| `tiny-lab intervene skip`    | Skip current phase                                 |
| `tiny-lab intervene stop`    | Stop the loop                                      |
| `tiny-lab resume`            | Resume from last state                             |
| `tiny-lab fork`              | Fork to new iteration                              |
| `tiny-lab stop`              | Send stop signal                                   |

## Reviewing the Plan

When the loop reaches **PLAN_REVIEW**, it stops and waits. To review:

```bash
# Check the plan
cat research/iter_1/research_plan.json | python -m json.tool

# Or use the dashboard
tiny-lab board

# Approve to start execution
tiny-lab intervene approve

# Or send back for changes
tiny-lab intervene modify
```

## Key Files

| File                                 | Purpose                           |
| ------------------------------------ | --------------------------------- |
| `research/.user_idea.txt`            | Your research idea (input)        |
| `research/.workflow.json`            | State machine definition          |
| `research/.state.json`               | Current loop state                |
| `research/iter_N/research_plan.json` | Experiment plan with phases       |
| `research/iter_N/phases/*.py`        | AI-generated experiment scripts   |
| `research/iter_N/results/*.json`     | Phase outputs and metrics         |
| `research/iter_N/paper_draft.md`     | Generated paper draft             |
| `research/iter_N/reflect.json`       | Iteration reflection and decision |
| `research/loop.log`                  | Engine log                        |

## How Phase Execution Works

For each phase in the plan:

1. **PHASE_CODE** -- AI writes a Python script based on the plan methodology
2. **PHASE_RUN** -- Engine executes the script
3. If it fails, AI sees the error and rewrites the script (up to 10 retries)
4. **PHASE_EVALUATE** -- Validates output against expected schema
5. **PHASE_RECORD** -- Marks phase as done

The AI maintains session context across retries, so it remembers what it tried before.

## Presets

| Preset          | Use Case                                          |
| --------------- | ------------------------------------------------- |
| `ml-experiment` | ML model development with data analysis (default) |
| `review-paper`  | Literature review and synthesis                   |
| `novel-method`  | Novel method design and validation                |
| `data-analysis` | Data exploration and analysis                     |
| `custom`        | Minimal template for custom workflows             |

```bash
tiny-lab init --preset review-paper
```
