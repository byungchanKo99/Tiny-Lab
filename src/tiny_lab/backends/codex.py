"""Codex (OpenAI codex CLI) backend.

Default invocation:

    codex exec "<prompt>" --json --cd <cwd> [--model <model>] [--sandbox <sb>]

The exact codex CLI surface evolves; if your installed `codex` uses a
different command shape, override the entire base command via the
TINYLAB_CODEX_CMD environment variable. It accepts a shell-quoted string
and the prompt is appended as the last argument.

Example:
    export TINYLAB_CODEX_CMD="codex exec --json --skip-git-repo-check"
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from .base import BackendResult


# Sandbox mapping: tiny-lab states declare allowed_write_globs which
# implies workspace-write; if no writes are allowed we use read-only.
_DEFAULT_SANDBOX_WITH_WRITES = "workspace-write"
_DEFAULT_SANDBOX_READONLY = "read-only"


def _base_cmd() -> list[str]:
    override = os.environ.get("TINYLAB_CODEX_CMD")
    if override:
        return shlex.split(override)
    return ["codex", "exec", "--json"]


class CodexBackend:
    """Calls the `codex` CLI. Stateless (no session resume)."""

    name = "codex"

    def invoke(
        self,
        prompt: str,
        cwd: Path,
        *,
        model: str | None = None,
        allowed_tools: list[str] | None = None,
        session_id: str | None = None,
        timeout: float = 1800.0,
    ) -> BackendResult:
        cmd = list(_base_cmd())

        if model:
            cmd.extend(["--model", model])

        # If the state declares writable globs, give codex workspace-write;
        # otherwise hold it to read-only. allowed_tools is a Claude concept
        # that codex doesn't have a direct equivalent for — codex grants
        # tools based on sandbox + harness defaults.
        sandbox = (
            _DEFAULT_SANDBOX_WITH_WRITES if allowed_tools and any(
                t in {"Write", "Edit", "Bash"} for t in allowed_tools
            )
            else _DEFAULT_SANDBOX_READONLY
        )
        cmd.extend(["--sandbox", sandbox])

        # Working directory
        cmd.extend(["--cd", str(cwd)])

        # Prompt is the trailing positional
        cmd.append(prompt)

        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )

        # Codex --json writes streaming events; the last event typically
        # carries the final response. We surface stdout as-is for the engine
        # to parse if it needs to. Session id (if any) lives in event metadata.
        out_session = _extract_session_id(proc.stdout)

        return BackendResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            session_id=out_session,
        )


def _extract_session_id(stdout: str) -> str | None:
    """Walk codex's JSON event stream and return any session id encountered."""
    if not stdout:
        return None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Different codex versions name this differently; check common keys.
        for key in ("session_id", "sessionId", "thread_id", "threadId"):
            sid = event.get(key) if isinstance(event, dict) else None
            if sid:
                return str(sid)
    return None
