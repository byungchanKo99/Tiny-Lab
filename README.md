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

# AI-guided setup — analyzes your data, proposes config:
tiny-lab discover "optimize hotel cancellation prediction"
# Or with Claude Code:
/research 호텔 취소 예측 최적화하고 싶어

# Start the loop (always in background)
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &

# Monitor
tiny-lab status            # RUNNING / STOPPED
tiny-lab board             # Results dashboard + pending queue
tiny-lab board --plot      # With ASCII sparklines
tiny-lab board --html      # Chart.js HTML report
tiny-lab board --live      # Real-time dashboard on localhost
```

## Two Research Modes

| User Intent                              | Mode                                            | Command                     |
| ---------------------------------------- | ----------------------------------------------- | --------------------------- |
| "Compare 5 models", "test these configs" | **Finite** — stops when queue is exhausted      | `tiny-lab run --until-idle` |
| "Optimize accuracy", "find best params"  | **Infinite** — generates new hypotheses forever | `tiny-lab run`              |

Both modes **must** run in background (`&`). Infinite mode never exits on its own — stop it with `tiny-lab stop`.

## How It Works

1. **Pick** a hypothesis (approach) from the queue
2. **Build** the experiment command — inject model via `model` lever + optimizer params via `search_space`
3. **Optimize** — run inner loop (grid/random/custom) to find best hyperparameters for this approach
4. **Evaluate** the result — WIN (>1% improvement), MARGINAL (<1%), LOSS, or INVALID
5. **Record** to the append-only ledger with full diff and best_params
6. **Repeat** — in infinite mode, GENERATE pipeline creates new approach hypotheses when the queue empties

The loop halts on **circuit breaker** (5 INVALID in last 20) or **stagnation** (warns every 20 experiments without new best) or `tiny-lab stop`.

## CLI

| Command             | Description                            | Key Flags                                                                      |
| ------------------- | -------------------------------------- | ------------------------------------------------------------------------------ |
| `tiny-lab init`     | Scaffold experiment project            | `--global` (install /research to ~/.claude/), `--update` (overwrite templates) |
| `tiny-lab discover` | AI-guided interactive setup            | Natural language intent argument                                               |
| `tiny-lab run`      | Start the research loop                | `--until-idle` (finite mode), `--on-event CMD` (webhook)                       |
| `tiny-lab status`   | Show loop state & queue counts         | `--json` (structured output)                                                   |
| `tiny-lab stop`     | Graceful shutdown (SIGTERM)            |                                                                                |
| `tiny-lab board`    | Experiment dashboard + insights        | `--export csv/json`, `--plot`, `--html [FILE]`, `--live`                       |
| `tiny-lab generate` | Manually trigger hypothesis generation |                                                                                |

### Dashboard Features

- **Best result** with full hyperparameter diff (baseline → best)
- **Approach comparison** chart (best metric per approach)
- **Pending queue** — what's coming next
- **Insights** — experiments/hour, convergence status, stagnation warnings, ETA
- **Live mode** (`--live`) — real-time updates via JS polling, no page reload

### Environment Variables

| Variable           | Default     | Description                                       |
| ------------------ | ----------- | ------------------------------------------------- |
| `CYCLE_SLEEP`      | `30`        | Seconds between experiment cycles (recommend `1`) |
| `TINYLAB_PROVIDER` | auto-detect | Force `claude` or `codex`                         |
| `CLAUDE_MAX_TURNS` | `20`        | Max turns for Claude provider                     |

## project.yaml

```yaml
name: hotel-cancellation
description: "Hotel cancellation prediction with rolling window CV"

build:
  type: flag

run:
  type: command

evaluate:
  type: stdout_json

baseline:
  command: "python train.py --model logistic"

metric:
  name: roc_auc
  direction: maximize

# CLI flag mappings — needed for optimizer to inject params
levers:
  model:
    flag: "--model"
    baseline: "logistic"
  learning_rate:
    flag: "--lr"
    baseline: 0.1
  max_depth:
    flag: "--max-depth"
    baseline: 6

# Approach name → execution config (model, description)
# Separates approach identity from actual --model value
approaches:
  lgbm_tuned:
    model: lgbm # --model lgbm (not lgbm_tuned)
    description: "LightGBM hyperparameter tuning"
  lgbm_regularized:
    model: lgbm # same model, different search_space
    description: "LightGBM with strong regularization"
  xgboost:
    model: xgb
    description: "XGBoost gradient boosting"

# Per-approach parameter definitions — pure optimizer config
search_space:
  lgbm_tuned:
    num_leaves: { type: int, low: 20, high: 127 }
    learning_rate: { type: float, low: 0.01, high: 0.3, log: true }
    n_estimators: { type: int, low: 50, high: 500 }
  lgbm_regularized:
    reg_alpha: { type: float, low: 0.0, high: 10.0 }
    reg_lambda: { type: float, low: 0.0, high: 10.0 }
  xgboost:
    max_depth: { type: int, low: 3, high: 15 }
    learning_rate: { type: float, low: 0.01, high: 0.3, log: true }

# Built-in: grid, random. External tools: custom + optimize_script
optimize:
  type: random
  time_budget: 300
  n_trials: 20

rules:
  - "Install required dependencies before starting the loop"
```

Your experiment script must print the metric as JSON to stdout:

```json
{ "roc_auc": 0.862 }
```

## Hypothesis Format

Each hypothesis picks an **approach** — a strategy name matching a key in `approaches:` (or `search_space:`):

```yaml
hypotheses:
  - id: H-001
    status: pending
    approach: lgbm_tuned
    description: "LightGBM hyperparameter tuning"
    reasoning: "Leaf-wise growth often outperforms on tabular data"
  - id: H-002
    status: pending
    approach: xgboost
    description: "XGBoost with regularization"
    reasoning: "L1/L2 regularization for robust generalization"
```

The `model` lever auto-injects the **model** value (from `approaches:`) into the baseline command. For example, `approach: lgbm_tuned` → `approaches.lgbm_tuned.model: lgbm` → `--model lgbm`. The optimizer then tunes only the parameters defined for that approach in `search_space`.

## Plugin Types

| Phase    | Type          | Description                                                   | Needs AI? |
| -------- | ------------- | ------------------------------------------------------------- | --------- |
| BUILD    | `flag`        | Replace CLI flags in baseline command + inject model approach | No        |
| BUILD    | `script`      | Use predefined script per lever:value                         | No        |
| BUILD    | `code`        | AI modifies source code via sub-agent                         | Yes       |
| RUN      | `command`     | Direct shell execution                                        | No        |
| RUN      | `pipeline`    | Multi-step workflow with background processes                 | No        |
| OPTIMIZE | `grid`        | Exhaustive parameter grid search (built-in)                   | No        |
| OPTIMIZE | `random`      | Random sampling (built-in, default)                           | No        |
| OPTIMIZE | `custom`      | External optimizer script (optuna, NAS, etc.)                 | No        |
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

```
Entry       cli
Core        loop (state machine)
Logic       generate, pipeline, build, run, optimize, evaluate, baseline
Data        project (accessors), queue, ledger, schemas, migrate
Query       dashboard, report, server
Infra       paths, errors, logging, lock, events, envutil
Providers   claude, codex (via abstract AIProvider)
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/tiny_lab/
```

253 tests covering state machine, optimizer inner loop, pipeline engine, approach dedup, stagnation detection, MARGINAL verdict, YAML recovery, and more.

## Credits

Forked from [trevin-creator/Tiny-Lab](https://github.com/trevin-creator/Tiny-Lab).

- Trevin Peterson — original tiny-lab system design
- Andrej Karpathy — `autoresearch` and the research-loop framing
- Full attribution in `CREDITS.md`

## License

MIT
