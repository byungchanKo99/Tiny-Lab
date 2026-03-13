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

### 3. Run the loop

**Choose the right mode based on the user's intent:**

```bash
# Infinite mode (default) — open-ended optimization, never exits on its own
# Use for: "optimize accuracy", "find best params", "improve performance"
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &

# Finite mode (--until-idle) — stops when queue is empty, no GENERATE phase
# Use for: "compare these 5 models", "test these configs", bounded comparisons
CYCLE_SLEEP=1 tiny-lab run --until-idle > research/tiny_lab_run.out 2>&1 &
```

You MUST run it as a **background process**. Do NOT run it in the foreground.

The loop will:

- Pick a hypothesis from the queue
- Modify the experiment (swap a flag, change code, etc.)
- Run the experiment
- Evaluate the result (WIN/LOSS/INVALID)
- Record to `research/ledger.jsonl`
- **Infinite mode:** When the queue is empty, generate new hypotheses autonomously and repeat indefinitely
- **Until-idle mode:** When the queue is empty, stop automatically

### 4. Monitor — YOUR PRIMARY JOB AFTER STARTING THE LOOP

**The loop never stops on its own. Your initial hypotheses are just the STARTING POINT.**

After the initial queue is exhausted, the loop enters GENERATE and creates NEW hypotheses autonomously — trying new lever values, adding new levers, extending search spaces. This means better results may appear AFTER your initial hypotheses are done.

**DO NOT stop monitoring when your initial hypotheses finish.**
**DO NOT report final results based only on your initial hypotheses.**

```bash
tiny-lab status   # Is it alive? What phase?
tiny-lab board    # Results dashboard — check this REPEATEDLY
```

**Monitoring loop (keep doing this while the loop runs):**

1. Check `tiny-lab board` periodically
2. If the loop generated new hypotheses and ran them → new results exist → update your understanding
3. If the best result changed → note it
4. Only report to the user when:
   - The user asks for status
   - The loop stops (circuit breaker, crash, or `tiny-lab stop`)
   - You have enough data to make a meaningful recommendation

**Intervene when:**

- Loop stalls in GENERATE → search space exhausted, add new levers
- Many INVALID → experiment command is broken, diagnose and fix
- Many LOSS → current approach isn't working, try different direction

### 5. Report

**Report must include ALL experiments, not just your initial hypotheses.**

When reporting (user asks, or loop stops):

- **Total** experiments run (including auto-generated ones), WIN/LOSS ratio
- **Best configuration found** — this may be from an auto-generated hypothesis, not your initial ones
- What was explored — initial hypotheses AND what the loop discovered on its own
- Whether the loop is still running or stopped
- Recommended next steps (continue loop? change direction? stop?)

## Key files

| File                             | What it is         | Can you edit it?    |
| -------------------------------- | ------------------ | ------------------- |
| `research/project.yaml`          | Experiment config  | Yes                 |
| `research/hypothesis_queue.yaml` | What to try next   | Yes (follow format) |
| `research/questions.yaml`        | Research questions | Yes                 |
| `research/ledger.jsonl`          | Results log        | No (append-only)    |

## Important

- **`tiny-lab run` is an INFINITE LOOP** — it never exits on its own. Always run it in the background and monitor with `tiny-lab status` / `tiny-lab board`. Stop it with `tiny-lab stop`.
- The loop generates new hypotheses when the queue is empty — including adding new levers and extending search spaces
- Don't modify `ledger.jsonl` — it's the source of truth
- Use `tiny-lab stop` to stop, don't kill the process
- The circuit breaker stops after 5 INVALID in last 20 experiments
