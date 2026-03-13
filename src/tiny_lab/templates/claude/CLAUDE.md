# Tiny-Lab Research Project

This project uses the `tiny-lab` autonomous research loop. The loop runs experiments, records results, and generates new hypotheses — all without human intervention.

## Your Role: Research Supervisor

You are not just a tool executor. You are the **research supervisor**. Your job:

1. **Set up** the research (discovery mode → project.yaml → first hypotheses)
2. **Start** the loop (`tiny-lab run &` — **MUST be background**, see below)
3. **Monitor** the loop while it runs — check for problems, stalls, or exhausted search spaces
4. **Evolve** the research — when current levers are exhausted, propose new directions
5. **Report** findings to the user when they return

### CRITICAL: `tiny-lab run` is an INFINITE LOOP

**`tiny-lab run` runs forever.** It continuously picks hypotheses, runs experiments, generates new hypotheses, and repeats — indefinitely until stopped.

**You MUST run it in the background.** If you run it in the foreground, your session will be blocked forever waiting for a command that never exits.

```bash
# CORRECT — run in background with output capture, then monitor
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &
echo "Loop started (pid=$!)"
tiny-lab status       # check if it's alive
tiny-lab board        # check experiment results

# WRONG — this blocks forever (infinite loop), you lose control
tiny-lab run
```

**Stop it with:** `tiny-lab stop` (sends SIGTERM to the loop process)

### ABSOLUTE RULE: NEVER STOP THE LOOP YOURSELF

The loop is designed to run indefinitely. **You must NEVER:**

- Run `tiny-lab stop` unless the user explicitly asks you to stop it
- Run `kill`, `kill -9`, `kill -KILL`, or any signal to the loop process
- Consider the loop "done" and clean it up
- Stop the loop because you're about to give your final answer

**The loop keeps running even after you respond.** When you summarize results and the user doesn't give further instructions, the loop still runs in the background. That's correct behavior. The loop will autonomously generate new hypotheses, try new approaches, and keep improving — this is the whole point.

**If you think experiments are "enough"** — you're wrong. The GENERATE phase will try ensembles, new models, feature engineering, and other strategies you haven't considered. Let it run.

### The Loop is Fully Autonomous

The loop is an **independent autonomous process**. Once started, it:

- Runs experiments from the queue
- When the queue empties, GENERATE creates new hypotheses automatically
- GENERATE learns from its own history — it avoids repeating strategies and escalates when stuck
- When current levers are exhausted, it tries ensembles, new models, feature engineering
- It only stops on circuit breaker (5 INVALID in 20) or `tiny-lab stop`

**You do NOT need to monitor or intervene.** After starting, your job is done until the user returns.

### After Starting

1. Confirm the loop started: `tiny-lab status`
2. **Leave it alone.** The loop handles everything autonomously.
3. When the user returns: `tiny-lab board` to summarize results.

NEVER run `tiny-lab run` without `&` (background). NEVER consider the task
done just because initial hypotheses finished — the loop will keep generating
and running new experiments.

### When User Returns

Summarize **ALL** research (not just your initial hypotheses):

- **Total** experiments run (initial + auto-generated), WIN/LOSS breakdown
- Best configuration found — **may be from an auto-generated hypothesis**
- What directions were explored (initial approach + what the loop discovered)
- Whether the loop is still running
- Recommended next steps (continue? stop? change direction?)

## `tiny-lab` CLI Reference

`tiny-lab` is the CLI that drives the entire research loop. You can use it directly — the `/research` command is just a convenience wrapper.

### Core Commands

| Command             | What it does                            | Notes                                                            |
| ------------------- | --------------------------------------- | ---------------------------------------------------------------- |
| `tiny-lab init`     | Initialize research directory structure | Creates `research/` dir, config templates. Run once per project. |
| `tiny-lab run`      | Start the experiment loop               | **INFINITE LOOP** — always run in background (see below)         |
| `tiny-lab stop`     | Gracefully stop a running loop          | Sends SIGTERM. Safe to call anytime.                             |
| `tiny-lab status`   | Show loop state (RUNNING/STOPPED/etc.)  | Use to confirm loop is alive after starting                      |
| `tiny-lab board`    | Show experiment results dashboard       | WIN/LOSS/INVALID table. Primary way to check progress.           |
| `tiny-lab generate` | Generate new hypotheses via AI          | Normally called automatically by the loop when queue empties     |

### How to Start the Loop (MANDATORY PATTERN)

```bash
# 1. Start in background with output capture
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &
echo "Loop started (pid=$!)"

# 2. Confirm it's alive (wait ~30s first)
tiny-lab status

# 3. Check progress
tiny-lab board
```

- `CYCLE_SLEEP=1` — reduces inter-cycle delay for faster iteration
- Output goes to `research/tiny_lab_run.out` — check with `tail research/tiny_lab_run.out` if something seems off
- **NEVER run `tiny-lab run` in foreground** — it's an infinite loop and will block your session permanently

### How to Stop

```bash
tiny-lab stop          # graceful shutdown
# or check if it's already stopped:
tiny-lab status
```

### How to Debug Issues

```bash
tail -50 research/loop.log              # recent loop activity
tail -20 research/tiny_lab_run.out      # stdout/stderr from the process
cat research/ledger.jsonl | tail -5     # last 5 experiment results
tiny-lab board                          # visual overview
```

### Loop Lifecycle

```
tiny-lab run &
    │
    ├─ Picks pending hypothesis from queue
    ├─ Runs experiment (baseline command + lever changes)
    ├─ Records result to ledger.jsonl
    ├─ Picks next hypothesis...
    │
    ├─ Queue empty → enters GENERATE phase
    │   └─ AI generates new hypotheses based on results so far
    │   └─ New hypotheses added to queue → loop continues
    │
    ├─ Circuit breaker: 5 INVALID in last 20 → loop stops
    └─ tiny-lab stop → graceful shutdown
```

The loop **never exits on its own** unless the circuit breaker triggers or an unrecoverable error occurs. This is by design — it continuously explores the search space.

## Quick Start

**New research from scratch** — just describe what you want:

```
/research 호텔 가격 최적화하고 싶어
/research I want to find the best learning rate for my model
/research optimize image classification accuracy
```

The discovery flow will analyze your data, propose metrics/levers, and set up everything.

**Or set up manually and run directly:**

```bash
# 1. Initialize
tiny-lab init

# 2. Edit research/project.yaml — set baseline, metric, levers
# 3. Add hypotheses to research/hypothesis_queue.yaml (or use tiny-lab generate)

# 4. Start the loop
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &

# 5. Monitor
tiny-lab status && tiny-lab board
```

## Workflow

### Starting a New Experiment

1. Edit `research/project.yaml` — set baseline command, metric name, levers with search spaces
2. Add hypotheses to `research/hypothesis_queue.yaml` (or run `tiny-lab generate`)
3. Start the loop: `CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &`
4. Monitor: `tiny-lab status` then `tiny-lab board` — repeat every 2-5 minutes

### Checking Results

1. `tiny-lab board` — summary table of all experiments with WIN/LOSS/INVALID verdicts
2. `research/ledger.jsonl` — one JSON object per line with full experiment details

### Adding Hypotheses Manually

Append to `research/hypothesis_queue.yaml` following this exact format:

```yaml
- id: H-{next sequential number}
  status: pending
  lever: { lever name from project.yaml levers }
  value: { a value from that lever's space array }
  description: "{one-line description of the change}"
```

Required fields: `id`, `status`, `lever`, `value`, `description`.
Valid statuses: `pending`, `running`, `done`, `skipped`.

### Editing project.yaml

The `research/project.yaml` file controls the experiment. Key sections:

- **baseline.command** — the command to run (levers replace flags in this command)
- **metric.name** — which metric to extract from stdout JSON
- **metric.direction** — `minimize` or `maximize`
- **levers** — each lever has a `flag`, `baseline` value, and `space` of values to try
- **build.type** — `flag` (replace CLI flags), `script` (predefined scripts), `code` (AI modifies source)
- **run.type** — `surface` (via surface tool), `command` (direct shell), `pipeline` (multi-step)
- **evaluate.type** — `stdout_json` (parse stdout), `script` (run eval script), `llm` (AI scoring)

## File Structure

| File                             | Purpose                                           | Editable            |
| -------------------------------- | ------------------------------------------------- | ------------------- |
| `research/project.yaml`          | Project config (levers, metric, baseline command) | Yes                 |
| `research/hypothesis_queue.yaml` | Hypothesis queue (pending/running/done/skipped)   | Yes (follow format) |
| `research/questions.yaml`        | Research questions to guide hypothesis generation | Yes                 |
| `research/ledger.jsonl`          | Experiment results log (append-only)              | No                  |
| `research/loop.log`              | Loop execution log                                | No                  |
| `research/.loop_state.json`      | Current loop state (auto-managed)                 | No                  |
| `research/.loop-lock`            | Lock file preventing concurrent loops             | No                  |

## Data Formats

### Ledger Entry (research/ledger.jsonl)

Each line is a JSON object:

```json
{
  "id": "EXP-001",
  "question": "Lower learning rate from 0.02 to 0.01",
  "family": "project-name",
  "changed_variable": "learning_rate",
  "value": 0.01,
  "status": "done",
  "class": "WIN",
  "primary_metric": {
    "metric_name": 1.23,
    "baseline": 1.45,
    "delta_pct": -15.17
  },
  "decision": "win"
}
```

`class` is one of: `WIN`, `LOSS`, `INVALID`, `INCONCLUSIVE`, `BASELINE`.

### Eval Result (evaluate.type: llm)

When using LLM evaluation, the evaluator writes `research/.eval_result_{exp_id}.json`:

```json
{
  "score": 7,
  "reasoning": "Brief explanation",
  "criteria_scores": { "criterion_1": 8, "criterion_2": 6 },
  "strengths": ["..."],
  "weaknesses": ["..."]
}
```

## Important Notes

- **Do not modify `research/ledger.jsonl`** — it is append-only and serves as the source of truth
- **Do not delete `research/.loop-lock`** while the loop is running — use `tiny-lab stop` instead
- **Hypothesis IDs must be unique** — check existing entries before adding
- **Lever values must come from the lever's `space` array** in project.yaml
- The loop runs one hypothesis at a time, sequentially
- The circuit breaker stops the loop after 5 INVALID results in the last 20 experiments
