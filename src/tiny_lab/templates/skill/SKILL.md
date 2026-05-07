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

{{TINY_LAB_RUNNER_CONTRACT}}

{{TINY_LAB_NATIVE_ENGINE_SELECTION}}
