# tiny-lab native runner (Codex agent)

This file is the Codex CLI counterpart to the Claude Code skill at
`.claude/skills/tiny-lab/SKILL.md`. Codex auto-loads `AGENTS.md` from
the project root, so the same orchestration logic is available without a
manual trigger.

You are operating inside a tiny-lab research project. Drive the workflow
from this Codex session — do **not** spawn the engine subprocess via
`tiny-lab run` unless the user asks for autonomous mode.

## When to engage

- A `research/.workflow.json` exists in the cwd → there is an active
  tiny-lab workflow you can advance.
- The user asks to "continue", "next step", "tiny-lab으로 진행", or
  similar → resume from `research/.state.json`.

If no workflow exists yet, tell the user to run `tiny-lab init --preset
<name>` first.

## Hard rules — DO NOT VIOLATE

1. **The state machine is authoritative.** Read `research/.state.json`
   at the start of every turn. The `state` field tells you which
   workflow step you are on. Do NOT skip ahead, do NOT collapse multiple
   steps into one turn.
2. **Read the workflow JSON, not your memory.** Open
   `research/.workflow.json`, find the entry whose `id` matches the
   current state, and follow ITS `prompt`, `allowed_tools`,
   `allowed_write_globs`, and `completion`. Different presets reorder
   states differently — never assume.
3. **Hooks will enforce you.** `state_gate.py` (PreToolUse) blocks
   tools/paths the current state does not permit; `state_advance.py`
   (PostToolUse) advances `.state.json` when a valid completion artifact
   is written. They run dual-mode (Codex stdin JSON + Claude env vars).
   Trust them — do not try to update `.state.json` yourself.
4. **One state per turn (default).** Complete the current state's
   artifact, let the hook advance the state, then surface to the user
   what just happened and propose the next step. Only chain states in
   one turn if the user explicitly asks for "auto" mode.
5. **Constraints are non-negotiable.** Always honor
   `research/constraints.json` — it carries the user's invariants and
   forbidden zones. The engine path injects this into every prompt
   automatically; here you must read it yourself before acting.

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
          - Read research/constraints.json and use it as a preamble
          - Execute the prompt's instructions using only allowed_tools
          - Write the artifact path declared in completion.artifact
          - PostToolUse hook advances .state.json automatically
     c. If type == "process":
          - Resolve the condition (built-in check OR file field) and
            advance .state.json yourself only if no hook handles process
            states. The safest action is to call `tiny-lab status` to
            let the engine logic surface the next state.
     d. If type == "checkpoint":
          - Wait for user input. Show the dashboard
            (`tiny-lab board`) and ask what to do next
            (approve / modify_plan / skip_phase / stop).
  5. Report what happened in 1-2 sentences. Stop unless user said "auto".
```

## Tool naming differences (Codex ↔ Claude)

The hooks normalize tool names so the workflow JSON can stay
runtime-agnostic:

| Workflow JSON name | Codex tool    | Claude tool    |
| ------------------ | ------------- | -------------- |
| `Write` / `Edit`   | `apply_patch` | `Write`/`Edit` |
| `Bash`             | `Bash`        | `Bash`         |
| `Read`             | (built-in)    | `Read`         |

When `allowed_tools` lists `Write`, you may use `apply_patch` — the gate
hook treats them as equivalent.

## Engine selection (multi-backend)

The state spec may include `"engine": "claude"` to force a specific
state to run on Claude instead of Codex (or vice versa). In native
agent mode you ARE the engine — you cannot literally hand off to the
other vendor mid-session. So:

- If the current state has `"engine": "claude"` and you are Codex →
  suggest dropping back to CLI mode (`tiny-lab run --engine claude`)
  for that state, then resuming
- Otherwise execute it yourself and warn the user once that the
  "intended engine was claude but native mode is using codex"

## Failure modes — when to bail

- Same artifact rewritten 3+ times and `state_advance` still hasn't
  advanced → there's a `required_fields` mismatch. Read the manifest /
  artifact and tell the user what's missing.
- `state_gate` blocks an `apply_patch` to a path you believe is correct
  → the preset's `allowed_write_globs` may be too narrow; surface to
  user rather than working around the hook.
- `.state.json` shows `consecutive_failures >=
circuit_breaker.max_consecutive_failures` → the engine would stop
  here; you should too. Tell the user and propose `tiny-lab resume` or
  a manual fix.

## Compatibility with the CLI engine path

This native runner and `tiny-lab run` are **mutually compatible**:

- They both read/write the same `.state.json`, `.workflow.json`, and
  artifacts.
- You can interrupt CLI runs and continue here, or vice versa.
- Hooks fire in both modes — enforcement is identical.
- Codex sessions are stateless across turns, so no session_id is
  threaded by tiny-lab; that field in `.state.json` is informational
  only when the engine ran on Codex.

If the user says "run autonomously" or "go full auto", suggest dropping
to CLI mode (`tiny-lab run --engine codex`) — it's purpose-built for
that. This native mode is best for interactive, step-by-step progression.

## Quick commands the agent orchestrates

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
remind them they can leave the chat and run `tiny-lab run --engine codex`
to let the engine drive the rest — `.state.json` carries the position
over.
