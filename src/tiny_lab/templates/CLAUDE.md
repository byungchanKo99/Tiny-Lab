# tiny-lab Research Project

This project uses tiny-lab v5 — a plan-driven AI research loop.

## How it works

1. **Understand** — domain research, data analysis, idea refinement
2. **Plan** — generate research_plan.json with phases and output schemas
3. **Execute** — AI generates code per phase, runs it, validates output
4. **Reflect** — analyze results, iterate or complete

## State enforcement

Hooks enforce the current state. You can only write files allowed by the current workflow state. If a Write is blocked, check `research/.state.json` for the current state and `research/.workflow.json` for what's allowed.

## Key files

| File                                 | Purpose                  |
| ------------------------------------ | ------------------------ |
| `research/.workflow.json`            | State machine definition |
| `research/.state.json`               | Current state            |
| `research/iter_N/research_plan.json` | Experiment plan          |
| `research/iter_N/phases/`            | AI-generated scripts     |
| `research/iter_N/results/`           | Phase outputs            |

## Commands

```bash
tiny-lab status    # Current state
tiny-lab board     # Results
tiny-lab stop      # Stop loop
```
