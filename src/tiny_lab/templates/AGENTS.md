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

```bash
tiny-lab run
```

The loop will:

- Pick a hypothesis from the queue
- Modify the experiment (swap a flag, change code, etc.)
- Run the experiment
- Evaluate the result (WIN/LOSS/INVALID)
- Record to `research/ledger.jsonl`
- When the queue is empty, generate new hypotheses autonomously
- Repeat until stopped

### 4. Monitor

While the loop runs, periodically check:

```bash
tiny-lab status   # Is it alive? What phase?
tiny-lab board    # Results dashboard
```

**Intervene when:**

- Loop stalls in GENERATE → search space exhausted, add new levers
- Many INVALID → experiment command is broken, diagnose and fix
- Many LOSS → current approach isn't working, try different direction

### 5. Report

When the user returns, summarize:

- Experiments run, WIN/LOSS ratio
- Best configuration found
- What was explored
- Recommended next steps

## Key files

| File                             | What it is         | Can you edit it?    |
| -------------------------------- | ------------------ | ------------------- |
| `research/project.yaml`          | Experiment config  | Yes                 |
| `research/hypothesis_queue.yaml` | What to try next   | Yes (follow format) |
| `research/questions.yaml`        | Research questions | Yes                 |
| `research/ledger.jsonl`          | Results log        | No (append-only)    |

## Important

- The loop generates new hypotheses when the queue is empty — including adding new levers and extending search spaces
- Don't modify `ledger.jsonl` — it's the source of truth
- Use `tiny-lab stop` to stop, don't kill the process
- The circuit breaker stops after 5 INVALID in last 20 experiments
