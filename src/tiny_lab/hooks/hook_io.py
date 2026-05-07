"""Dual-mode hook I/O — works for both Claude Code and Codex CLI.

Claude Code passes hook context via environment variables and uses exit
codes (1 = block, 0 = allow). Codex passes context via stdin JSON and
expects a JSON response on stdout (exit 0 + permissionDecision = "deny"
to block).

This module abstracts both forms so the actual hook scripts stay agnostic.

Usage:
    from _io import read_hook_input, deny, allow

    payload = read_hook_input()
    if some_violation(payload):
        deny(payload, reason="state X does not allow Write to Y")
    else:
        allow()  # or just `return 0`
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

try:  # Package import path
    from .tool_names import WRITE_TOOL_NAMES
except ImportError:  # Script-copied hook path
    from tool_names import WRITE_TOOL_NAMES  # type: ignore


CLAUDE = "claude"
CODEX = "codex"


@dataclass
class HookInput:
    """Normalized hook input. Same shape no matter which harness called us."""

    runtime: str  # "claude" | "codex"
    event: str  # PreToolUse | PostToolUse | etc.
    tool_name: str
    file_path: str
    file_paths: tuple[str, ...]
    command: str
    raw: dict[str, Any]  # full payload for advanced use


def read_hook_input(event_name: str | None = None) -> HookInput:
    """Detect the runtime and parse the input.

    Detection order:
    1. If a `CLAUDE_TOOL_*` env var is set → Claude Code mode.
    2. Else try to read stdin as JSON → Codex mode.
    3. If neither yields anything → empty Claude payload (no-op).

    Why env-first: select() with a 0s timeout is unreliable on pipes —
    it can return "no data ready" even when data is present — so stdin
    presence cannot be used as a robust runtime signal. Claude Code's
    env-var contract IS reliable, so use it as the primary discriminator.
    """
    if any(k.startswith("CLAUDE_TOOL_") for k in os.environ):
        return _from_claude_env(event_name)
    payload = _try_read_stdin_json()
    if payload is not None:
        return _from_codex(payload, event_name)
    return _from_claude_env(event_name)


def deny(hook: HookInput, reason: str) -> None:
    """Block the tool call. Picks the right exit semantics for the runtime."""
    if hook.runtime == CODEX:
        out = {
            "hookSpecificOutput": {
                "hookEventName": hook.event,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        # Codex: exit 0 + JSON on stdout means "structured response."
        sys.stdout.write(json.dumps(out))
        sys.stdout.flush()
        sys.exit(0)
    # Claude: nonzero exit + human message on stderr/stdout.
    sys.stderr.write(reason + "\n")
    sys.exit(1)


def allow() -> None:
    """Pass through. Both runtimes treat empty exit-0 as allow."""
    sys.exit(0)


def info(hook: HookInput, message: str) -> None:
    """Emit an informational note (no decision change)."""
    if hook.runtime == CODEX:
        out = {"systemMessage": message}
        sys.stdout.write(json.dumps(out))
        sys.stdout.flush()
    else:
        sys.stdout.write(message + "\n")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _try_read_stdin_json() -> dict[str, Any] | None:
    """Return parsed JSON from stdin if any was piped in; else None.

    Only invoked when no Claude env vars are present (env-first detection
    in `read_hook_input`). Safe to do a blocking read here because:
    - If stdin is a TTY → bail (no machine input expected).
    - If stdin is /dev/null → read() returns "" instantly.
    - If stdin is a closed pipe → read() returns "" instantly.
    - If stdin is a pipe with data (Codex case) → read() returns it.
    """
    if sys.stdin is None or not hasattr(sys.stdin, "fileno"):
        return None
    try:
        if sys.stdin.isatty():
            return None
    except (OSError, ValueError):
        return None
    try:
        text = sys.stdin.read()
    except OSError:
        return None
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _from_codex(payload: dict[str, Any], event_name: str | None) -> HookInput:
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    # Codex's apply_patch corresponds to Claude's Write/Edit. Normalize so
    # downstream code that checks `tool_name in WRITE_TOOL_NAMES` keeps
    # working without per-runtime branching.
    normalized_tool = tool_name
    file_path = ""
    file_paths: tuple[str, ...] = ()
    command = ""

    if tool_name == "apply_patch":
        # apply_patch input shape: {"input": "*** Begin Patch\n*** Add File: path\n..."}
        # We extract every touched file path from the patch text.
        file_paths = _extract_paths_from_patch(tool_input)
        file_path = file_paths[0] if file_paths else ""
        normalized_tool = "Write" if _patch_has_add_file(tool_input) else "Edit"
    elif tool_name == "Bash":
        command = str(tool_input.get("command", ""))
    elif tool_name in WRITE_TOOL_NAMES:
        # Some MCP variants expose Write/Edit directly. Use the documented field.
        file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        file_paths = (file_path,) if file_path else ()
    elif tool_name.startswith("mcp__"):
        # MCP tools — best-effort path extraction
        for key in ("file_path", "path", "filename"):
            if key in tool_input:
                file_path = str(tool_input[key])
                file_paths = (file_path,) if file_path else ()
                break

    return HookInput(
        runtime=CODEX,
        event=str(payload.get("hook_event_name") or event_name or ""),
        tool_name=normalized_tool,
        file_path=file_path,
        file_paths=file_paths,
        command=command,
        raw=payload,
    )


def _from_claude_env(event_name: str | None) -> HookInput:
    file_path = os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", "")
    return HookInput(
        runtime=CLAUDE,
        event=event_name or os.environ.get("CLAUDE_HOOK_EVENT", ""),
        tool_name=os.environ.get("CLAUDE_TOOL_NAME", ""),
        file_path=file_path,
        file_paths=(file_path,) if file_path else (),
        command=os.environ.get("CLAUDE_TOOL_INPUT_COMMAND", ""),
        raw=dict(os.environ),
    )


def _extract_paths_from_patch(tool_input: dict[str, Any]) -> tuple[str, ...]:
    """Pull all target paths from a codex apply_patch payload.

    Patch format excerpt:
      *** Begin Patch
      *** Add File: research/iter_1/.foo.json
      ...
      *** Update File: research/iter_1/.bar.json
      *** End Patch
    """
    patch_text = str(tool_input.get("input") or tool_input.get("patch") or "")
    if not patch_text:
        return ()
    paths: list[str] = []
    for line in patch_text.splitlines():
        line = line.strip()
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: "):
            if line.startswith(prefix):
                paths.append(line[len(prefix):].strip())
                break
    return tuple(paths)


def _patch_has_add_file(tool_input: dict[str, Any]) -> bool:
    patch_text = str(tool_input.get("input") or tool_input.get("patch") or "")
    return any(line.strip().startswith("*** Add File: ") for line in patch_text.splitlines())
