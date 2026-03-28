# tiny-lab

Plan-driven AI research loop. Understand the domain, create a research plan, execute phases, reflect and iterate.

```
┌─ UNDERSTANDING ──────────────────────────────────────────────────────┐
│  DOMAIN_RESEARCH → DATA_DEEP_DIVE → IDEA_REFINE → PLAN             │
└──────────────────────────────────────────────────────────────────────┘
                         ↓
┌─ EXECUTION ──────────────────────────────────────────────────────────┐
│  PHASE_SELECT → PHASE_CODE → PHASE_RUN → EVALUATE → RECORD         │
│       ↑                                                    │        │
│       └──────────────── CHECKPOINT ────────────────────────┘        │
└──────────────────────────────────────────────────────────────────────┘
                         ↓
┌─ REFLECTION ─────────────────────────────────────────────────────────┐
│  REFLECT → DONE | add phases | idea mutation | domain pivot         │
└──────────────────────────────────────────────────────────────────────┘
```

## Install

```bash
pip install git+https://github.com/byungchanko/Tiny-Lab.git
```

Requires **Python 3.10+** and [Claude Code](https://claude.ai/claude-code).

## Quick Start

```bash
# Initialize with a preset
tiny-lab init --preset ml-experiment

# Start the research loop
tiny-lab run "호텔 취소 예측 최적화"

# Monitor
tiny-lab status
tiny-lab board
```

## Presets

| Preset          | Description                      | Phases                                                  |
| --------------- | -------------------------------- | ------------------------------------------------------- |
| `ml-experiment` | ML model training + optimization | Understanding → Plan → Code → Optimize → Reflect        |
| `review-paper`  | Literature review                | Scope → Search → Analysis → Taxonomy → Synthesis        |
| `novel-method`  | New method paper                 | Related Work → Method Design → Experiment → Paper Draft |
| `data-analysis` | EDA + insights                   | Understanding → Plan → Analysis → Visualization         |
| `custom`        | Empty template                   | Define your own workflow                                |

```bash
tiny-lab init --preset review-paper
```

## How It Works

1. **Understand** — domain research, data analysis, Socratic idea refinement
2. **Plan** — generate research_plan.yaml with phases, methodology, output schemas
3. **Execute** — AI generates code for each phase, runs it, validates output
4. **Reflect** — analyze results, decide: done / add phases / change idea / pivot domain

The loop can iterate autonomously: reflect → modify idea → re-plan → re-execute.

## Two YAMLs

| File                                 | Role                                                  |
| ------------------------------------ | ----------------------------------------------------- |
| `research/.workflow.yaml`            | **System**: how the state machine works (from preset) |
| `research/iter_N/research_plan.yaml` | **Content**: what experiments to run (AI-generated)   |

## Key Design

- **Hook-enforced state machine**: Claude Code hooks block actions not allowed in current state. AI can't skip phases.
- **Artifact-driven transitions**: writing `.domain_research.yaml` auto-advances to DATA_DEEP_DIVE. No "I'm done" declarations.
- **Iteration management**: each Understanding→Plan→Execute→Reflect cycle gets its own `iter_N/` directory.
- **Meta workflow**: states defined in YAML, not code. Add/remove/reorder phases by editing `.workflow.yaml`.
- **Intervention protocol**: lab manager writes `.intervention.yaml` to approve, skip, modify, or stop.

## CLI

| Command              | Description            |
| -------------------- | ---------------------- |
| `tiny-lab init`      | Initialize with preset |
| `tiny-lab run`       | Start the loop         |
| `tiny-lab status`    | Show current state     |
| `tiny-lab board`     | Results dashboard      |
| `tiny-lab stop`      | Stop the loop          |
| `tiny-lab resume`    | Resume from last state |
| `tiny-lab fork`      | Fork to new iteration  |
| `tiny-lab intervene` | Send intervention      |

## File Structure

```
project/
  research/
    .workflow.yaml           # State machine definition
    .state.json              # Current state
    .iterations.yaml         # Iteration history
    iter_1/
      research_plan.yaml     # What to do
      .domain_research.yaml  # Domain knowledge
      .data_analysis.yaml    # Data understanding
      .idea_refined.yaml     # Concrete idea
      reflect.yaml           # Reflection + decision
      phases/                # AI-generated scripts
      results/               # Phase outputs (JSON)
  shared/
    data/raw/                # Original data
    data/preprocessed/       # Processed data
    models/                  # Checkpoints
    lib/                     # Reusable code
```

## Architecture

See [docs/v5-architecture.md](docs/v5-architecture.md) for the full design.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT
