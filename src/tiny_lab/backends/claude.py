"""Claude Code backend — wraps the `claude -p` CLI."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from .base import BackendResult


class ClaudeBackend:
    """Calls `claude -p` and parses its --output-format json envelope."""

    name = "claude"

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
        cmd: list[str] = ["claude", "-p", prompt, "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        if session_id:
            cmd.extend(["--resume", session_id])
            resolved_session = session_id
        else:
            resolved_session = str(uuid.uuid4())
            cmd.extend(["--session-id", resolved_session])

        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )

        # Claude's JSON envelope may carry a different session_id (esp. on resume).
        out_session = _extract_session_id(proc.stdout) or resolved_session

        return BackendResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            session_id=out_session,
        )


def _extract_session_id(stdout: str) -> str | None:
    if not stdout:
        return None
    try:
        data = json.loads(stdout)
        return data.get("session_id")
    except (json.JSONDecodeError, AttributeError):
        return None
