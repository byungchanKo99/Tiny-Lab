---
name: tiny-lab
description: Drive a tiny-lab research workflow natively from the chat session. Use when the user wants to run, resume, or progress a tiny-lab project (look for `research/.workflow.json` in the cwd) without spawning a separate `tiny-lab run` subprocess. Honors the project's state machine — each step is enforced by `state_gate` / `state_advance` hooks. Keeps the CLI engine path available; this skill is the interactive alternative.
---

# tiny-lab native runner

This skill lets you drive the tiny-lab state machine **inside the current
Claude Code chat** instead of spawning the engine via `tiny-lab run`.
The state machine is the same; the executor is you (this session) instead
of a `claude -p` subprocess.

## When to use this skill

Trigger on:

- "tiny-lab으로 진행", "tiny-lab 다음 단계", "tiny-lab native"
- User asks to advance / continue a tiny-lab workflow without leaving the chat
- A tiny-lab project exists (`research/.workflow.json` is present) and the
  user wants to step through it interactively

Do NOT use when:

- The user explicitly invokes `tiny-lab run` (let the CLI engine handle it)
- No `research/.workflow.json` in the cwd — tell the user to `tiny-lab init`
  first

## Hard rules — DO NOT VIOLATE

1. **The state machine is authoritative.** Read `research/.state.json` at
   the start of every turn. The `state` field tells you which workflow
   step you are on. Do NOT skip ahead, do NOT collapse multiple steps
   into one turn.
2. **Read the workflow JSON, not your memory.** Open
   `research/.workflow.json`, find the entry whose `id` matches the
   current state, and follow ITS `prompt`, `allowed_tools`,
   `allowed_write_globs`, and `completion`. Different presets reorder
   states differently — never assume.
3. **Hooks will enforce you.** `state_gate.py` (PreToolUse) blocks
   tools/paths the current state does not permit; `state_advance.py`
   (PostToolUse) advances `.state.json` when a valid completion artifact
   is written. Trust them — do not try to update `.state.json` yourself.
4. **One state per turn (default).** Complete the current state's
   artifact, let the hook advance the state, then surface to the user
   what just happened and propose the next step. Only chain states in
   one turn if the user explicitly asks for "auto" mode.
5. **Constraints are non-negotiable.** Always honor `research/constraints.json`
   (it's auto-injected into every prompt by the engine path; here you
   must read it yourself before acting).

## Loop you run

```
While not DONE:
  1. Read research/.state.json
  2. If state is INIT → tell user to set constraints (or run tiny-lab shape)
  3. If state is DONE → summarize and exit
  4. Otherwise:
     a. Read research/.workflow.json → find the current state's spec
     b. If type == "ai_session":
          - Load the prompt file (relative to project root)
          - Inject context placeholders ({iter}, {project_dir}, etc.)
          - Inject the constraints preamble from constraints.json
          - Execute the prompt's instructions using only allowed_tools
          - Write the artifact path declared in completion.artifact
          - Hook advances .state.json automatically
     c. If type == "process":
          - These resolve conditions and transition. Inspect the condition
            (built-in check OR file field) and update .state.json yourself
            ONLY if no hook handles process states (read engine.py for
            the precise rules). Usually: invoke the CLI helper —
            `tiny-lab status` — to let the engine resolve and surface.
     d. If type == "checkpoint":
          - Wait for user input. Show the dashboard
            (`tiny-lab board`) and ask what to do next
            (approve / modify_plan / skip_phase / stop).
  5. Report what happened in 1-2 sentences. Stop unless user said "auto".
```

## Context placeholders to substitute

Prompts use `{iter}`, `{project_dir}`, `{current_phase_id}`, etc.
Build the substitution dict from `.state.json`:

| Placeholder                  | Source                                     |
| ---------------------------- | ------------------------------------------ |
| `{iter}`                     | `iter_<current_iteration>`                 |
| `{iteration}`                | `current_iteration` (number)               |
| `{project_dir}`              | `pwd`                                      |
| `{current_phase_id}`         | `current_phase_id` from .state.json        |
| `{current_phase}`            | the phase dict from research_plan.json     |
| `{previous_results_summary}` | concat of `research/iter_N/results/*.json` |

If a placeholder is irrelevant for the current state, leave it blank.

## Engine selection (multi-backend)

The state spec may include `"engine": "codex"` to run that specific state
on Codex instead of Claude. In native skill mode you ARE Claude — you
cannot literally hand off to Codex from inside the chat. So:

- If the current state has `"engine": "codex"` and the user wants the
  intended backend → suggest dropping back to CLI mode
  (`tiny-lab run --engine codex`) for that state, then resuming the skill
- Otherwise execute it yourself and warn the user once that the
  "intended engine was codex but native mode is using claude"

## Allowed-tools enforcement reminder

Each state has `allowed_tools`. Before doing tool calls that turn,
double-check you are only using tools in that list. The hook will block
violations, but checking yourself avoids wasted attempts and confusing
errors. If a state needs a tool not on the list, that's a bug in the
preset — surface it instead of silently switching.

## Failure modes — when to bail

- Same artifact rewritten 3+ times and `state_advance` still hasn't
  advanced → there's a `required_fields` mismatch. Read the manifest /
  artifact and tell the user what's missing.
- `state_gate` blocks a Write to a path you believe is correct → the
  preset's `allowed_write_globs` may be too narrow; surface to user
  rather than working around the hook.
- `.state.json` shows `consecutive_failures >= circuit_breaker.max_consecutive_failures`
  → the engine would stop here; you should too. Tell the user and propose
  `tiny-lab resume` or a manual fix.

## Compatibility with the CLI engine path

This skill and `tiny-lab run` are **mutually compatible**:

- They both read/write the same `.state.json`, `.workflow.json`, and
  artifacts.
- You can interrupt CLI runs and continue in skill mode, or vice versa.
- Hooks fire in both modes — enforcement is identical.
- Session ids differ: the engine resumes Claude sessions across states;
  the skill is one continuous chat (no session_id manipulation needed).

If the user says "run autonomously" or "go full auto", suggest dropping
to CLI mode (`tiny-lab run`) — it's purpose-built for that. The skill is
best for interactive, step-by-step progression.

## Quick commands the skill orchestrates

```bash
# Inspect (always safe)
tiny-lab status              # one-line summary
tiny-lab board               # full dashboard with viz manifests
cat research/.state.json     # raw current state

# State surgery (use sparingly)
tiny-lab intervene approve   # pass a checkpoint
tiny-lab intervene stop      # halt the loop
tiny-lab fork --enter PLAN   # branch a new iteration
```

When the user wants to switch back to autonomous mode mid-workflow,
remind them they can leave the chat and run `tiny-lab run` to let the
engine drive the rest — `.state.json` carries the position over.
