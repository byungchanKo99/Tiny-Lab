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
# CORRECT — run in background, then monitor
tiny-lab run &
tiny-lab status       # check if it's alive
tiny-lab board        # check experiment results

# WRONG — this blocks forever, you lose control
tiny-lab run
```

**Stop it with:** `tiny-lab stop` (sends SIGTERM to the loop process)

### Monitoring Checklist — DO NOT STOP AFTER INITIAL HYPOTHESES

**Your initial hypotheses are just the seed.** The loop autonomously generates NEW hypotheses after the queue empties (GENERATE phase). These auto-generated experiments often find better results than your initial ones.

**WRONG behavior:** Start loop → initial 5 hypotheses finish → report results → done.
**CORRECT behavior:** Start loop → initial hypotheses finish → loop generates more → keep monitoring → report includes ALL results.

After starting the loop, **continuously** check:

```bash
tiny-lab status    # Is the loop alive? What state is it in?
tiny-lab board     # How are experiments going? WIN/LOSS ratio?
```

**Watch for these situations:**

| Signal                              | What it means                            | What to do                                                                |
| ----------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------- |
| Loop is in GENERATE for a long time | Search space may be exhausted            | Check ledger — if all lever values tried, add new levers or extend spaces |
| Many consecutive INVALID results    | Baseline or experiment command is broken | Read loop.log, diagnose the error, fix the command                        |
| Many consecutive LOSS results       | Current direction isn't working          | Analyze patterns in ledger, propose a different approach                  |
| Loop stopped unexpectedly           | Crash or circuit breaker triggered       | Check loop.log, restart if safe                                           |
| All experiments are WIN             | Search space is too conservative         | Extend the space with more aggressive values                              |
| Initial queue exhausted             | Loop enters GENERATE phase               | **Keep monitoring** — new experiments are being created automatically     |

### When User Returns

Summarize **ALL** research (not just your initial hypotheses):

- **Total** experiments run (initial + auto-generated), WIN/LOSS breakdown
- Best configuration found — **may be from an auto-generated hypothesis**
- What directions were explored (initial approach + what the loop discovered)
- Whether the loop is still running
- Recommended next steps (continue? stop? change direction?)

## Quick Start

**New research from scratch** — just describe what you want:

```
/research 호텔 가격 최적화하고 싶어
/research I want to find the best learning rate for my model
/research optimize image classification accuracy
```

The discovery flow will analyze your data, propose metrics/levers, and set up everything.

**Manage existing research:**

```bash
tiny-lab status          # Check current loop state
tiny-lab run &           # Start the research loop IN BACKGROUND (runs forever!)
tiny-lab stop            # Stop a running loop
tiny-lab board           # Show experiment results dashboard
tiny-lab generate        # Generate new hypotheses via AI
```

Or use `/research start|status|stop|generate|board` inside Claude Code.

## Workflow

### Starting a New Experiment

1. Edit `research/project.yaml` — set baseline command, metric name, levers with search spaces
2. Add hypotheses to `research/hypothesis_queue.yaml` (or run `tiny-lab generate`)
3. Run `tiny-lab run &` in the background — the loop picks hypotheses, runs experiments, and records results **indefinitely**

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
