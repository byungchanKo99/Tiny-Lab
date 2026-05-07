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
  similar → run `tiny-lab brief` and follow its current-state contract.

If no workflow exists yet, tell the user to run `tiny-lab init --preset
<name>` first.

{{TINY_LAB_RUNNER_CONTRACT}}

## Tool naming differences (Codex ↔ Claude)

The hooks normalize tool names so the workflow JSON can stay
runtime-agnostic:

| Workflow JSON name | Codex tool    | Claude tool    |
| ------------------ | ------------- | -------------- |
| `Write` / `Edit`   | `apply_patch` | `Write`/`Edit`/`MultiEdit` |
| `Bash`             | `Bash`        | `Bash`         |
| `Read`             | (built-in)    | `Read`         |

When `allowed_tools` lists `Write`, you may use `apply_patch` for new
files. When it lists `Edit`, you may use `apply_patch` for updates; the
gate checks every file touched by the patch.

{{TINY_LAB_NATIVE_ENGINE_SELECTION}}
