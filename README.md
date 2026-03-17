# tiny-lab

Deterministic AI-driven research loop. Define approaches, set a metric, and let the loop run experiments automatically.

```
┌─ OUTER LOOP (LLM picks strategy) ─────────────────────────────────────────┐
│                                                                            │
│  CHECK_QUEUE → SELECT → BUILD                                              │
│                           ↓                                                │
│              ┌─ INNER LOOP (optimizer tunes params) ──┐                    │
│              │  search_space defined?                  │                    │
│              │  YES → grid | random | custom optimizer │                    │
│              │  NO  → single run (no tuning needed)   │                    │
│              └────────────────────────────────────────┘                    │
│                           ↓                                                │
│                     EVALUATE → RECORD → back to CHECK_QUEUE                │
│                                                                            │
│  Queue empty? → GENERATE pipeline                                          │
│    research → analyze → diagnose → hypotheses → summary                    │
└────────────────────────────────────────────────────────────────────────────┘
```

## Install

```bash
pip install git+https://github.com/byungchanko/Tiny-Lab.git
```

Requires **Python 3.10+** and one of:

- [Claude Code](https://claude.ai/claude-code) — full experience (`/research` command, hooks, sub-agents)
- [Codex CLI](https://github.com/openai/codex) — set `agent.provider: codex` in project.yaml

## Quick Start

```bash
cd your-project
tiny-lab init              # Scaffold project (auto-detects Claude Code or Codex CLI)

# AI-guided setup — analyzes your data, proposes metrics & levers:
tiny-lab discover "optimize hotel pricing"
# Or with Claude Code:
/research 호텔 가격 최적화하고 싶어

# Start the loop (always in background)
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &

# Monitor
tiny-lab status            # RUNNING / STOPPED
tiny-lab board             # Results dashboard
tiny-lab board --plot      # With ASCII sparklines
tiny-lab board --html      # Chart.js HTML report
```

## Two Research Modes

| User Intent                              | Mode                                            | Command                     |
| ---------------------------------------- | ----------------------------------------------- | --------------------------- |
| "Compare 5 models", "test these configs" | **Finite** — stops when queue is exhausted      | `tiny-lab run --until-idle` |
| "Optimize accuracy", "find best params"  | **Infinite** — generates new hypotheses forever | `tiny-lab run`              |

Both modes **must** run in background (`&`). Infinite mode never exits on its own — stop it with `tiny-lab stop`.

## How It Works

1. **Pick** a hypothesis (approach) from the queue
2. **Build** the experiment command (flag substitution, code modification, or script)
3. **Optimize** — if `search_space` is defined, run inner loop (grid/random/custom) to find best params; otherwise single run
4. **Evaluate** the result (parse stdout JSON, run eval script, or AI scoring)
5. **Record** WIN / LOSS / INVALID to the append-only ledger
6. **Repeat** — in infinite mode, GENERATE pipeline creates new hypotheses when the queue empties

The loop halts on **circuit breaker** (5 INVALID in last 20 experiments) or `tiny-lab stop`.

## CLI

| Command             | Description                               | Key Flags                                                                      |
| ------------------- | ----------------------------------------- | ------------------------------------------------------------------------------ |
| `tiny-lab init`     | Scaffold experiment project               | `--global` (install /research to ~/.claude/), `--update` (overwrite templates) |
| `tiny-lab discover` | AI-guided interactive setup               | Natural language intent argument                                               |
| `tiny-lab run`      | Start the research loop                   | `--until-idle` (finite mode), `--on-event CMD` (webhook)                       |
| `tiny-lab status`   | Show loop state & queue counts            | `--json` (structured output)                                                   |
| `tiny-lab stop`     | Graceful shutdown (SIGTERM)               |                                                                                |
| `tiny-lab board`    | Experiment results dashboard              | `--export csv/json`, `--plot`, `--html [FILE]`                                 |
| `tiny-lab generate` | Manually trigger AI hypothesis generation |                                                                                |

### Environment Variables

| Variable           | Default     | Description                                       |
| ------------------ | ----------- | ------------------------------------------------- |
| `CYCLE_SLEEP`      | `30`        | Seconds between experiment cycles (recommend `1`) |
| `TINYLAB_PROVIDER` | auto-detect | Force `claude` or `codex`                         |
| `CLAUDE_MAX_TURNS` | `20`        | Max turns for Claude provider                     |

## project.yaml

```yaml
name: hotel-pricing
description: "Optimize hotel RevPAR by adjusting pricing parameters"

build:
  type: flag # flag | script | code

run:
  type: command # command | pipeline

evaluate:
  type: stdout_json # stdout_json | script | llm

baseline:
  command: "python3 pricing_model.py --rate-adj 1.0 --season-weight 0.5"

metric:
  name: revpar
  direction: maximize # minimize | maximize

levers:
  rate_adjustment:
    flag: "--rate-adj"
    baseline: 1.0
    space: [0.8, 0.9, 1.0, 1.1, 1.2]

# Parameter type definitions — optimizer searches within these
search_space:
  rate_adj: { type: float, low: 0.5, high: 2.0 }
  season_weight: { type: float, low: 0.1, high: 1.0 }

# Optimizer config (built-in: grid, random; external: custom)
optimize:
  type: random
  n_trials: 20

rules:
  - "Change command-line flags only"
  - "Do not install packages"
```

Your experiment script must print the metric as JSON to stdout:

```json
{ "revpar": 142.5 }
```

## What You Write

| What                                     | Who writes it                         | Notes                                                          |
| ---------------------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| **Experiment script** (e.g., `train.py`) | You                                   | The actual model training / evaluation code                    |
| `research/project.yaml`                  | AI proposes, you confirm              | `tiny-lab discover` or `/research` generates it interactively  |
| `research/hypothesis_queue.yaml`         | AI proposes, you confirm              | Initial hypotheses; also auto-generated by `tiny-lab generate` |
| Custom optimizer script                  | You (only if `optimize.type: custom`) | Optional — built-in `grid` / `random` cover most cases         |

In practice, **you only need to write the experiment script**. Everything else is generated through conversation:

```bash
tiny-lab discover "optimize hotel pricing"   # AI analyzes your code, proposes project.yaml + hypotheses
tiny-lab run                                  # Loop runs autonomously
```

When an **AI agent** (Claude Code, Codex CLI) drives the full workflow, the user writes nothing — the agent discovers the project, configures the YAML, generates hypotheses, and runs the loop end-to-end.

## Plugin Types

| Phase    | Type          | Description                                                   | Needs AI? |
| -------- | ------------- | ------------------------------------------------------------- | --------- |
| BUILD    | `flag`        | Replace CLI flags in baseline command (single or multi-lever) | No        |
| BUILD    | `script`      | Use predefined script per lever:value                         | No        |
| BUILD    | `code`        | AI modifies source code via sub-agent                         | Yes       |
| RUN      | `command`     | Direct shell execution                                        | No        |
| RUN      | `pipeline`    | Multi-step workflow with background processes                 | No        |
| EVALUATE | `stdout_json` | Parse metric from last JSON object in stdout                  | No        |
| EVALUATE | `script`      | Run separate eval script (supports retries)                   | No        |
| EVALUATE | `llm`         | AI scores artifacts (screenshots, HTML, etc.)                 | Yes       |

## Project Structure

After `tiny-lab init`:

```
your-project/
  AGENTS.md                          # Agent instructions (provider-agnostic)
  CLAUDE.md                          # Claude Code guide (auto-generated)
  research/
    project.yaml                     # Experiment config
    hypothesis_queue.yaml            # Hypothesis queue (pending/running/done/skipped)
    questions.yaml                   # Research questions
    ledger.jsonl                     # Append-only results log
    loop.log                         # Loop execution log
    reports/                         # Per-experiment markdown reports
    .loop-lock                       # PID lock file
    .loop_state.json                 # Crash recovery state
    .events.jsonl                    # Event log
    .generate_history.jsonl          # AI generation reasoning history
  .claude/
    commands/research.md             # /research slash command
    agents/
      hypothesis-generator.md        # Generates hypotheses
      code-modifier.md               # Modifies code (build.type: code)
      ux-evaluator.md                # Scores artifacts (evaluate.type: llm)
```

## Architecture

25 modules organized in layers:

| Layer         | Modules                                                                    |
| ------------- | -------------------------------------------------------------------------- |
| **Entry**     | `cli`                                                                      |
| **Core**      | `loop` (state machine)                                                     |
| **Logic**     | `generate`, `pipeline`, `build`, `run`, `optimize`, `evaluate`, `baseline` |
| **Data**      | `project`, `queue`, `ledger`, `schemas`, `migrate`                         |
| **Query**     | `dashboard`, `report`                                                      |
| **Infra**     | `paths`, `errors`, `logging`, `lock`, `events`, `envutil`                  |
| **Providers** | `claude`, `codex` (via abstract `AIProvider`)                              |

Schema versioning with auto-migration (v1 → v2). See `docs/architecture.md` for detailed diagrams.

## Development

```bash
pip install -e ".[dev]"
pytest tests/tiny_lab/
```

246 tests covering state machine transitions, plugin dispatch, optimizer inner loop, pipeline engine, schema migration, event system, error recovery, and circuit breaker.

## Credits

Forked from [trevin-creator/Tiny-Lab](https://github.com/trevin-creator/Tiny-Lab).

- Trevin Peterson — original tiny-lab system design
- Andrej Karpathy — `autoresearch` and the research-loop framing
- Full attribution in `CREDITS.md`

## License

MIT
