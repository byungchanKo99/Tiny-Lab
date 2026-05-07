"""Claude Code backend — wraps the `claude -p` CLI."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from .base import BackendResult
from ..processes import clear_active_backend, write_active_backend


class ClaudeBackend:
    """Calls `claude -p` and parses its --output-format json envelope."""

    name = "claude"
    supports_resume = True

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
        # Send the prompt on stdin rather than as an argv element. This keeps
        # full research prompts out of `ps`/`pgrep` output.
        cmd: list[str] = ["claude", "-p", "--input-format", "text", "--output-format", "json"]
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

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(cwd),
            )
            write_active_backend(cwd, backend=self.name, pid=proc.pid, command=cmd)
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
            returncode = proc.returncode
        except FileNotFoundError:
            return BackendResult(
                exit_code=127,
                stdout="",
                stderr="Backend command not found: claude",
                session_id=None,
            )
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                stdout, stderr = "", ""
            return BackendResult(
                exit_code=124,
                stdout=stdout or "",
                stderr=((stderr + "\n") if stderr else "") + f"Backend command timed out after {timeout:g}s: claude",
                session_id=None,
            )
        finally:
            if "proc" in locals():
                clear_active_backend(cwd, pid=proc.pid)

        # Claude may include a session_id in JSON error envelopes (for example
        # auth failures). Only expose a session id that came from a successful
        # invocation; otherwise the engine will retry a session Claude never
        # actually created.
        out_session = None
        if returncode == 0 and not _is_error_envelope(stdout):
            # Claude's JSON envelope may carry a different session_id (esp. on resume).
            out_session = _extract_session_id(stdout) or resolved_session

        return BackendResult(
            exit_code=returncode,
            stdout=stdout,
            stderr=stderr,
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


def _is_error_envelope(stdout: str) -> bool:
    if not stdout:
        return False
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return bool(data.get("is_error"))
