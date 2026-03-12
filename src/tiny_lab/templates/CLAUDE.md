# Tiny-Lab Research Project

This project uses the `tiny-lab` autonomous research loop. The loop runs experiments, records results, and generates new hypotheses — all without human intervention.

## Your Role: Research Supervisor

You are not just a tool executor. You are the **research supervisor**. Your job:

1. **Set up** the research (discovery mode → project.yaml → first hypotheses)
2. **Start** the loop (`tiny-lab run`)
3. **Monitor** the loop while it runs — check for problems, stalls, or exhausted search spaces
4. **Evolve** the research — when current levers are exhausted, propose new directions
5. **Report** findings to the user when they return

### Monitoring Checklist

After starting the loop, periodically check:

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

### When User Returns

Summarize the research:

- How many experiments ran, WIN/LOSS breakdown
- Best configuration found (which lever values produced the best metric)
- What directions were explored
- Recommended next steps

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
tiny-lab run             # Start the research loop (Ctrl+C to stop)
tiny-lab stop            # Stop a running loop
tiny-lab board           # Show experiment results dashboard
tiny-lab generate        # Generate new hypotheses via AI
```

Or use `/research start|status|stop|generate|board` inside Claude Code.

## Workflow

### Starting a New Experiment

1. Edit `research/project.yaml` — set baseline command, metric name, levers with search spaces
2. Add hypotheses to `research/hypothesis_queue.yaml` (or run `tiny-lab generate`)
3. Run `tiny-lab run` — the loop picks hypotheses from the queue, runs them, and records results

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
