# Tiny-Lab Research Project (Codex)

This project uses the `tiny-lab` autonomous research loop. The loop runs experiments, records results, and generates new hypotheses — all without human intervention.

## Your Role: Research Supervisor

You are the **research supervisor**. Your job:

1. **Set up** the research (`tiny-lab discover` → project.yaml → first hypotheses)
2. **Start** the loop (`tiny-lab run &` — **MUST be background**, it runs forever)
3. **Monitor** the loop — check for problems, stalls, or exhausted search spaces
4. **Evolve** the research — when current levers are exhausted, propose new directions
5. **Report** findings to the user when they return

### CRITICAL: `tiny-lab run` is an INFINITE LOOP

**`tiny-lab run` runs forever.** It continuously picks hypotheses, runs experiments, generates new hypotheses, and repeats indefinitely.

**You MUST run it in the background.** Do not block on it.

```bash
tiny-lab run &
tiny-lab status       # check if it's alive
tiny-lab board        # check experiment results
```

### Monitoring — DO NOT STOP AFTER INITIAL HYPOTHESES

Your initial hypotheses are just the seed. The loop generates NEW hypotheses after the queue empties. These auto-generated experiments often find better results.

**WRONG:** Start loop → initial 5 hypotheses finish → report results → done.
**CORRECT:** Start loop → keep monitoring → report includes ALL results.

```bash
tiny-lab status    # Is the loop alive?
tiny-lab board     # Results + generation reasoning
```

### When User Returns

Report **ALL** experiments (initial + auto-generated):

- Total experiments, WIN/LOSS breakdown
- Best configuration found (may be from auto-generated hypothesis)
- What directions were explored
- Whether loop is still running
- Recommended next steps

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

## Important

- **Do not modify `research/ledger.jsonl`** — append-only source of truth
- **Do not kill the loop process** — use `tiny-lab stop`
- The circuit breaker stops after 5 INVALID in last 20 experiments
