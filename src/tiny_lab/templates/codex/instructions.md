# Tiny-Lab Research Project (Codex)

This project uses the `tiny-lab` autonomous research loop. The loop runs experiments, records results, and generates new hypotheses — all without human intervention.

## Your Role

1. **Set up** the research (`tiny-lab discover` → project.yaml → first hypotheses)
2. **Start** the loop (`tiny-lab run &` — **MUST be background**, it runs forever)
3. **Report** findings to the user when they return

### CRITICAL: `tiny-lab run` is an INFINITE LOOP

**`tiny-lab run` runs forever.** It continuously picks hypotheses, runs experiments, generates new hypotheses, and repeats indefinitely.

```bash
tiny-lab run &
tiny-lab status       # confirm it started
```

### The Loop is Fully Autonomous

Once started, the loop handles everything:

- Runs experiments, records results
- Generates new hypotheses when the queue empties (GENERATE phase)
- GENERATE learns from its own history — avoids repeating strategies, escalates when stuck
- Tries ensembles, new models, feature engineering when current levers are exhausted

**You do NOT need to monitor or intervene.** After starting, leave it alone until the user returns.

### DO NOT STOP AFTER INITIAL HYPOTHESES

Your initial hypotheses are just the seed. The loop generates NEW hypotheses after the queue empties. These auto-generated experiments often find better results.

### When User Returns

Report **ALL** experiments (initial + auto-generated):

- Total experiments, WIN/LOSS breakdown
- Best configuration found (may be from auto-generated hypothesis)
- What directions were explored
- Whether loop is still running
- Recommended next steps

## Dependencies

Before starting the loop, install all required packages:

- **Experiment script** — whatever your script needs (sklearn, xgboost, etc.)
- **Optimizer** — if using `custom` optimizer, install whatever the optimizer script needs.
- **Evaluation tools** — custom eval tools (UI testing, browser automation, etc.)

The loop fails at runtime if dependencies are missing. **Install before `tiny-lab run`.**

## CLI Commands

```bash
tiny-lab init            # Scaffold project
tiny-lab discover "..."  # Interactive research setup
tiny-lab run &           # Start loop (background!)
tiny-lab status          # Check loop state
tiny-lab stop            # Stop loop
tiny-lab board           # Results dashboard
tiny-lab generate        # Generate new hypotheses
```

## Key Files

| File                             | Purpose            | Editable            |
| -------------------------------- | ------------------ | ------------------- |
| `research/project.yaml`          | Experiment config  | Yes                 |
| `research/hypothesis_queue.yaml` | Hypothesis queue   | Yes (follow format) |
| `research/questions.yaml`        | Research questions | Yes                 |
| `research/ledger.jsonl`          | Experiment results | No (append-only)    |
| `research/loop.log`              | Loop execution log | No                  |

## ABSOLUTE RULE: NEVER STOP THE LOOP YOURSELF

The loop is designed to run indefinitely. **You must NEVER:**

- Run `tiny-lab stop` unless the user explicitly asks you to stop it
- Run `kill`, `kill -9`, `kill -KILL`, or any signal to the loop process
- Consider the loop "done" and clean it up
- Stop the loop because you're about to give your final answer or summary

**The loop keeps running even after you respond.** When you summarize results, the loop still runs in the background. That's correct behavior. The GENERATE phase will autonomously try ensembles, new models, feature engineering, and other strategies. Let it run.

**If you think experiments are "enough"** — you're wrong. Let the loop continue.

## Hypothesis Format

Each hypothesis picks an **approach** (strategy). The optimizer handles parameter tuning using `search_space` from `project.yaml`.

```yaml
- id: H-001
  status: pending
  approach: xgboost_stacking
  description: "XGBoost + LightGBM stacking ensemble"
  reasoning: "Combine gradient boosting variants for better generalization"
```

Required: `id`, `status`, `approach`, `description`.
Optional: `search_space` (approach-specific params not in project.yaml), `reasoning`, `code_changes`, `references`.

**Key principle:** YOU decide the **strategy** (approach). The **optimizer** decides the **parameters**.

- DO: Pick a new model family, ensemble method, or feature engineering approach
- DON'T: Specify exact parameter values — the optimizer handles this
- NEVER: Same approach + different ranges = NOT a new hypothesis

## GENERATE Phase: Output Schema

When the loop triggers you to generate hypotheses, write `research/.generate_summary.json` with these fields:

| Field                  | Required    | Type     | Notes                                                                   |
| ---------------------- | ----------- | -------- | ----------------------------------------------------------------------- |
| `state`                | ✅          | string   | `EXPLORING` / `REFINING` / `SATURATED` / `STUCK`                        |
| `reasoning`            | ✅          | string   | 2–3 sentences on diagnosis and choices                                  |
| `best_so_far`          | ✅          | object   | `{experiment_id, metric_value, config}`                                 |
| `hypotheses_added`     | ✅          | string[] | IDs added (e.g. `["H-006", "H-007"]`)                                   |
| `changes_made`         | ✅          | string[] | Changes to project.yaml or code                                         |
| `experiments_analyzed` | ✅          | integer  | Number of past experiments reviewed                                     |
| `references`           | ⬜ optional | string[] | Techniques, papers, or prior experiments that inspired these hypotheses |

`references` is optional — include it only when a hypothesis is directly inspired by a known technique or prior experiment.

## Important

- **Do not modify `research/ledger.jsonl`** — append-only source of truth
- **Do not kill the loop process** — use `tiny-lab stop` only when user asks
- The circuit breaker stops after 5 INVALID in last 20 experiments
