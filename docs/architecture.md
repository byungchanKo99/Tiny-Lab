# Tiny-Lab Architecture

## System Overview

```
                              tiny-lab CLI
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                 │
              cmd_init        cmd_run           cmd_board
              cmd_discover    cmd_stop           cmd_status
              cmd_generate
                                │
                                ▼
                    ┌───────────────────────┐
                    │    ResearchLoop       │
                    │    (State Machine)    │
                    └───────────┬───────────┘
                                │
          ┌─────────┬───────────┼───────────┬──────────┐
          ▼         ▼           ▼           ▼          ▼
       generate   build       run       evaluate    record
          │         │           │           │          │
          ▼         ▼           ▼           ▼          ▼
      ┌──────┐ ┌────────┐ ┌────────┐ ┌─────────┐ ┌────────┐
      │ AI   │ │ flag   │ │command │ │stdout   │ │ledger  │
      │ gen  │ │ script │ │command │ │ _json   │ │.jsonl  │
      │      │ │ code   │ │pipeline│ │script   │ │        │
      └──┬───┘ └───┬────┘ └────────┘ │llm     │ └────────┘
         │         │                  └─────────┘
         ▼         ▼
    ┌─────────────────┐
    │  AIProvider      │
    │  (abstract)      │
    ├─────────────────┤
    │ ClaudeProvider  │
    │ CodexProvider   │
    └─────────────────┘
```

## Loop State Machine

```
                         ┌─────────────┐
                         │ CHECK_QUEUE │◄─────────────────────────┐
                         └──────┬──────┘                          │
                   queue empty? │ has pending?               sleep │
                    ┌───────────┴──────────┐                      │
                    ▼                      ▼                      │
             ┌──────────┐          ┌──────────┐                   │
             │ GENERATE │          │  SELECT  │                   │
             └────┬─────┘          └────┬─────┘                   │
                  │                     │                         │
                  │                     ▼                         │
                  │              ┌─────────────┐   fail           │
                  │              │BUILD_COMMAND ├──────┐          │
                  │              └──────┬───────┘      │          │
                  │                     │ ok           skip       │
                  │                     ▼              │          │
                  │              ┌─────────────┐       │          │
                  │              │     RUN     │       │          │
                  │              └──────┬──────┘       │          │
                  │                     │              │          │
                  │                     ▼              │          │
                  │              ┌─────────────┐       │          │
                  │              │  EVALUATE   │       │          │
                  │              └──────┬──────┘       │          │
                  │                     │              │          │
                  │                     ▼              │          │
                  │              ┌─────────────┐       │          │
                  └──────────────┤   RECORD    ├───────┘──────────┘
                                 └─────────────┘

  Circuit Breaker: 5+ INVALID in last 20 → HALT at CHECK_QUEUE
```

## Module Dependency Graph

```
                            ┌─────────┐
                            │ cli.py  │ (entry point)
                            └────┬────┘
                   ┌─────────────┼─────────────────┐
                   ▼             ▼                  ▼
             ┌──────────┐ ┌───────────┐      ┌───────────┐
             │ loop.py  │ │dashboard  │      │ report.py │
             └────┬─────┘ └─────┬─────┘      └───────────┘
                  │             │
    ┌─────┬───┬──┴──┬───┬──────┤
    ▼     ▼   ▼     ▼   ▼      ▼
generate build run evaluate baseline
    │     │         │
    │     └────┬────┘
    │          ▼
    │    ┌───────────┐
    └───►│ providers │
         ├───────────┤
         │  claude   │
         │  codex    │
         └───────────┘

  Shared by all:
  ┌─────────┬──────────┬─────────┬──────────┬─────────┐
  │ schemas │ paths.py │ errors  │ logging  │ migrate │
  │  .py    │          │  .py    │   .py    │   .py   │
  ├─────────┼──────────┼─────────┼──────────┼─────────┤
  │ queue   │ ledger   │ lock.py │ events   │ envutil │
  │  .py    │   .py    │         │   .py    │   .py   │
  └─────────┴──────────┴─────────┴──────────┴─────────┘
```

## Data Flow

```
  project.yaml ──load──► migrate ──► validate ──► project dict
                                                       │
  hypothesis_queue.yaml ◄──save──┐                     │
       │                         │                     ▼
       └──load──► pending list ──┼──► SELECT ──► BUILD ──► RUN ──► EVALUATE
                                 │                                     │
                                 │       ┌──── judge_verdict() ◄──────┘
                                 │       ▼
  ledger.jsonl ◄─── append ◄── RECORD ──► events.jsonl
       │                                      │
       └──► dashboard / board / report        └──► --on-event callback
       └──► GENERATE (AI reads history)
```

## Plugin Architecture

```
  ┌──────────────────────────────────────────────────────┐
  │                  dispatch_build()                     │
  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
  │  │   flag   │  │  script  │  │  code (AI agent) │   │
  │  │ replace  │  │ lookup   │  │  modify source   │   │
  │  │ CLI args │  │ mapping  │  │  via provider    │   │
  │  └──────────┘  └──────────┘  └──────────────────┘   │
  └──────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────┐
  │                   dispatch_run()                      │
  │  ┌──────────┐  ┌──────────────────┐                   │
  │  │ command  │  │    pipeline      │                   │
  │  │ direct   │  │ multi-step +     │                   │
  │  │ shell    │  │ background tasks │                   │
  │  └──────────┘  └──────────────────┘                   │
  └──────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────┐
  │                dispatch_evaluate()                    │
  │  ┌────────────┐  ┌──────────┐  ┌────────────────┐   │
  │  │stdout_json │  │  script  │  │  llm (AI eval) │   │
  │  │ parse last │  │ run eval │  │  score via     │   │
  │  │ JSON line  │  │ command  │  │  provider      │   │
  │  └────────────┘  └──────────┘  └────────────────┘   │
  └──────────────────────────────────────────────────────┘
```

## Schema & Migration

```
  Old project.yaml          load_project()         Validated dict
  (no schema_version)  ──►  needs_migration? ──►  schema_version: 2
                                │ yes
                                ▼
                         migrate_and_save()
                         (write-back to disk)

  Migration Chain:
  v1 ──(_migrate_v1_to_v2)──► v2 ──(future)──► v3 ...
```

## File Layout (research/)

```
  research/
  ├── project.yaml              # Config (name, metric, levers, build/run/eval)
  ├── hypothesis_queue.yaml     # Hypothesis states (pending/running/done/skipped)
  ├── ledger.jsonl              # Append-only experiment results
  ├── questions.yaml            # Research questions
  ├── loop.log                  # Human-readable loop log
  ├── reports/                  # Per-experiment markdown reports
  │   └── EXP-001.md
  ├── .loop-lock                # PID lock (loop running)
  ├── .loop_state.json          # State snapshot (crash recovery)
  ├── .events.jsonl             # Event log
  ├── .generate_summary.json    # Current generation cycle (transient)
  └── .generate_history.jsonl   # Archive of all generation cycles
```

## Module Summary (25 modules)

| Module                  | Layer    | Purpose                                       |
| ----------------------- | -------- | --------------------------------------------- |
| `__init__.py`           | Meta     | Package version (importlib.metadata)          |
| `cli.py`                | Entry    | CLI commands & argument parsing               |
| `loop.py`               | Core     | State machine (7 states, CycleContext)        |
| `generate.py`           | Logic    | AI hypothesis generation + history            |
| `build.py`              | Plugin   | Build dispatching (flag/script/code)          |
| `run.py`                | Plugin   | Run dispatching (command/pipeline)            |
| `evaluate.py`           | Plugin   | Evaluate dispatching (stdout_json/script/llm) |
| `baseline.py`           | Logic    | Baseline measurement & recording              |
| `project.py`            | Data     | Load & validate project.yaml                  |
| `migrate.py`            | Data     | Schema versioning & migration chain           |
| `schemas.py`            | Data     | Lightweight validation engine                 |
| `queue.py`              | Data     | Hypothesis queue I/O                          |
| `ledger.py`             | Data     | Experiment ledger I/O                         |
| `dashboard.py`          | Query    | Status & board data aggregation               |
| `report.py`             | Query    | HTML report generation (Chart.js)             |
| `events.py`             | Infra    | Event emission & loading                      |
| `paths.py`              | Infra    | File path definitions                         |
| `errors.py`             | Infra    | Exception hierarchy                           |
| `logging.py`            | Infra    | Loop log management                           |
| `lock.py`               | Infra    | PID lock management                           |
| `envutil.py`            | Infra    | Subprocess env setup                          |
| `providers/__init__.py` | Factory  | Provider factory & detection                  |
| `providers/base.py`     | Abstract | AIProvider interface                          |
| `providers/claude.py`   | Impl     | Claude Code provider                          |
| `providers/codex.py`    | Impl     | Codex CLI provider                            |
