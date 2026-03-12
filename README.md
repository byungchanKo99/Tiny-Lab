# tiny-lab

Deterministic AI-driven research loop. Define levers, set a metric, and let the loop run experiments automatically.

## Install

```bash
pip install git+https://github.com/byungchanko/Tiny-Lab.git
```

## 30-Second Setup

```bash
cd your-project
tiny-lab init            # Scaffold project (auto-detects Claude Code or Codex CLI)
tiny-lab init --global   # Also install /research command globally (~/.claude/)
```

Then start research:

```bash
# With Claude Code:
/research 호텔 가격 최적화하고 싶어

# With any provider:
tiny-lab discover "optimize hotel pricing"
```

The AI will analyze your data, ask what metric to optimize, what variables to experiment with — then set up everything and start running.

## Manual Setup

```bash
mkdir my-experiment && cd my-experiment
tiny-lab init              # Scaffold project files
vim research/project.yaml  # Configure your experiment
tiny-lab run               # Start the loop (Ctrl+C to stop)
```

## How It Works

```
┌─ CHECK_QUEUE ──→ SELECT ──→ BUILD_COMMAND ──→ RUN ──→ EVALUATE ──→ RECORD ─┐
│                                                                              │
│  (queue empty)                                                               │
└──→ GENERATE (AI creates new hypotheses) ──→ back to CHECK_QUEUE ────────────┘
```

1. **Pick** a hypothesis from the queue
2. **Build** the experiment command (replace CLI flags, modify code, or run a script)
3. **Run** the experiment
4. **Evaluate** the result (parse stdout JSON, run eval script, or AI scoring)
5. **Record** WIN/LOSS/INVALID to the ledger
6. **Repeat** until stopped

## CLI Commands

| Command             | Description                                               |
| ------------------- | --------------------------------------------------------- |
| `tiny-lab init`     | Scaffold a new experiment project (auto-detects provider) |
| `tiny-lab discover` | Interactive research setup (works with any provider)      |
| `tiny-lab run`      | Start the research loop                                   |
| `tiny-lab status`   | Show current loop state                                   |
| `tiny-lab stop`     | Stop a running loop                                       |
| `tiny-lab board`    | Show experiment results dashboard                         |
| `tiny-lab generate` | Generate new hypotheses via AI                            |

## Project Structure (after `tiny-lab init`)

```
your-project/
  AGENTS.md                              # Agent instructions (provider-agnostic)
  CLAUDE.md                              # Agent guide (auto-generated)
  research/
    project.yaml                         # Experiment config
    hypothesis_queue.yaml                # What to try next
    questions.yaml                       # Research questions
    ledger.jsonl                         # Results log
  .claude/
    commands/research.md                 # /research command
    agents/
      hypothesis-generator.md            # Generates hypotheses
      code-modifier.md                   # Modifies code (build.type: code)
      ux-evaluator.md                    # Scores artifacts (evaluate.type: llm)
```

## project.yaml Example

```yaml
name: hotel-pricing
description: "Optimize hotel RevPAR by adjusting pricing parameters"

agent:
  provider: claude # claude | codex

build:
  type: flag # flag | script | code

run:
  type: command # surface | command | pipeline

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
  season_weight:
    flag: "--season-weight"
    baseline: 0.5
    space: [0.3, 0.5, 0.7, 1.0]

rules:
  - "Change command-line flags only"
  - "Do not install packages"
```

Your experiment script must print the metric as JSON to stdout:

```json
{ "revpar": 142.5 }
```

## Plugin Types

| Phase    | Type          | Description                             | Needs AI? |
| -------- | ------------- | --------------------------------------- | --------- |
| BUILD    | `flag`        | Replace CLI flags in baseline command   | No        |
| BUILD    | `script`      | Use predefined script per lever:value   | No        |
| BUILD    | `code`        | AI modifies source code                 | Yes       |
| RUN      | `command`     | Direct shell execution                  | No        |
| RUN      | `surface`     | Via surface control plane               | No        |
| RUN      | `pipeline`    | Multi-step with background processes    | No        |
| EVALUATE | `stdout_json` | Parse metric from stdout                | No        |
| EVALUATE | `script`      | Run separate eval script                | No        |
| EVALUATE | `llm`         | AI scores artifacts (screenshots, HTML) | Yes       |

## Requirements

- Python 3.10+
- One of:
  - [Claude Code](https://claude.ai/claude-code) — full experience (`/research` command, hooks, agents)
  - [Codex CLI](https://github.com/openai/codex) — set `agent.provider: codex` in project.yaml

## Legacy

This repo also contains the original `bin/surface` control plane and `examples/mlx/` trainer from the 1.0 release. See `bin/surface --help` for the original experiment tooling. The `tiny-lab` CLI is the v2 interface built on top.

## Credits

- Trevin Peterson — original tiny-lab system design
- Andrej Karpathy — `autoresearch` and the research-loop framing
- Full attribution in `CREDITS.md`
