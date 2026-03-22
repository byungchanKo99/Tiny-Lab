# Agent Instructions: Tiny-Lab

You have access to `tiny-lab`, an autonomous experiment loop. Use it.

## When to use tiny-lab

When the user wants to optimize, experiment, or find the best configuration for anything:

- "이 모델 성능 올려줘" → tiny-lab
- "최적의 파라미터 찾아줘" → tiny-lab
- "A/B 테스트 해봐" → tiny-lab
- "어떤 설정이 best인지 알고 싶어" → tiny-lab

## How to use it

### 1. Initialize

```bash
tiny-lab init
```

This scaffolds `research/project.yaml`, hypothesis queue, and supporting files.

### 2. Configure (or let discovery do it)

Either manually edit `research/project.yaml` or run:

```bash
tiny-lab discover "what you want to optimize"
```

Discovery will scan data/scripts, analyze them, and set up everything.

**MANDATORY in project.yaml:**

- `approaches` — maps approach names to execution config (`model`, `description`). Use when approach names differ from actual model names (e.g., `lgbm_tuned → model: lgbm`).
- `search_space` — per-approach parameter definitions (e.g., `lgbm_tuned: {n_estimators: ...}`)
- `optimize` — optimizer config (`type: random`, `time_budget: 300`, `n_trials: 20`)
- `levers` — CLI flag mappings including a `model` lever if approaches use different models

### 3. Run the loop

**Choose the right mode based on the user's intent:**

```bash
# Infinite mode (default) — open-ended optimization, never exits on its own
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &

# Finite mode (--until-idle) — stops when queue is empty, no GENERATE phase
CYCLE_SLEEP=1 tiny-lab run --until-idle > research/tiny_lab_run.out 2>&1 &
```

You MUST run it as a **background process**. Do NOT run it in the foreground.

The loop will:

- Pick a hypothesis (approach) from the queue
- Build the experiment command (inject model + parameters via levers)
- Optimize — run inner loop (grid/random/custom) to find best params for this approach
- Evaluate the result (WIN/LOSS/MARGINAL/INVALID)
- Record to `research/ledger.jsonl`
- **Infinite mode:** When the queue is empty, generate new hypotheses autonomously and repeat
- **Until-idle mode:** When the queue is empty, stop automatically

### 4. Monitor — YOUR PRIMARY JOB AFTER STARTING THE LOOP

**The loop never stops on its own. Your initial hypotheses are just the STARTING POINT.**

After the initial queue is exhausted, the loop enters GENERATE and creates NEW approach-based hypotheses autonomously. This means better results may appear AFTER your initial hypotheses are done.

**DO NOT stop monitoring when your initial hypotheses finish.**
**DO NOT report final results based only on your initial hypotheses.**

```bash
tiny-lab status   # Is it alive? What phase?
tiny-lab board    # Results dashboard — check this REPEATEDLY
```

**Intervene when:**

- Stagnation warning — many experiments without best improvement, try different approaches
- Many INVALID — experiment command is broken, diagnose and fix
- Many LOSS/MARGINAL — current approaches aren't working, try fundamentally different direction

### 5. Report

**Report must include ALL experiments, not just your initial hypotheses.**

When reporting (user asks, or loop stops):

- **Total** experiments run (including auto-generated), WIN/LOSS ratio
- **Best configuration** — approach + best hyperparameters found by optimizer
- What was explored — initial approaches AND what the loop discovered
- Whether the loop is still running or stopped
- Recommended next steps (continue? change direction? stop?)

## Key files

| File                             | What it is         | Can you edit it?    |
| -------------------------------- | ------------------ | ------------------- |
| `research/project.yaml`          | Experiment config  | Yes                 |
| `research/hypothesis_queue.yaml` | What to try next   | Yes (follow format) |
| `research/questions.yaml`        | Research questions | Yes                 |
| `research/ledger.jsonl`          | Results log        | No (append-only)    |

## Important

- **`tiny-lab run` is an INFINITE LOOP** — always run in background, stop with `tiny-lab stop`
- Each hypothesis = an approach (strategy name), NOT parameter values
- The optimizer handles parameter tuning, you handle strategy selection
- Don't modify `ledger.jsonl` — it's the source of truth
- The circuit breaker stops after 5 INVALID in last 20 experiments
- Install all required dependencies before starting the loop
