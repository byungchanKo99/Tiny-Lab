"""Codex (OpenAI codex CLI) backend.

Default invocation:

    codex exec --json --skip-git-repo-check --cd <cwd> [--model <model>] [--sandbox <sb>]

The prompt is sent on stdin so local process listings do not expose the
rendered research prompt.

The exact codex CLI surface evolves; if your installed `codex` uses a
different command shape, override the entire base command via the
TINYLAB_CODEX_CMD environment variable. It accepts a shell-quoted string
for the base command; Tiny-Lab still sends the prompt on stdin.

Example:
    export TINYLAB_CODEX_CMD="codex exec --json --skip-git-repo-check"
"""
from __future__ import annotations

import json
import os
import signal
import shlex
import subprocess
from pathlib import Path

from .base import BackendResult
from ..processes import clear_active_backend, write_active_backend


# Sandbox mapping: tiny-lab states declare allowed_write_globs which
# implies workspace-write; if no writes are allowed we use read-only.
_DEFAULT_SANDBOX_WITH_WRITES = "workspace-write"
_DEFAULT_SANDBOX_READONLY = "read-only"


def _base_cmd() -> list[str]:
    override = os.environ.get("TINYLAB_CODEX_CMD")
    if override:
        return shlex.split(override)
    return ["codex", "exec", "--json", "--skip-git-repo-check"]


class CodexBackend:
    """Calls the `codex` CLI. Stateless (no session resume)."""

    name = "codex"
    supports_resume = False

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

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(cwd),
                start_new_session=(os.name != "nt"),
            )
            write_active_backend(cwd, backend=self.name, pid=proc.pid, command=cmd)
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
            returncode = proc.returncode
        except FileNotFoundError:
            return BackendResult(
                exit_code=127,
                stdout="",
                stderr=f"Backend command not found: {cmd[0]}",
                session_id=None,
            )
        except subprocess.TimeoutExpired:
            stdout, stderr = _collect_after_timeout(proc)
            return BackendResult(
                exit_code=124,
                stdout=stdout or "",
                stderr=((stderr + "\n") if stderr else "") + f"Backend command timed out after {timeout:g}s: {cmd[0]}",
                session_id=None,
            )
        finally:
            if "proc" in locals():
                clear_active_backend(cwd, pid=proc.pid)

        # Codex --json writes streaming events; the last event typically
        # carries the final response. We surface stdout as-is for the engine
        # to parse if it needs to. Session id (if any) lives in event metadata.
        out_session = _extract_session_id(stdout)

        return BackendResult(
            exit_code=returncode,
            stdout=stdout,
            stderr=stderr,
            session_id=out_session,
        )


def _collect_after_timeout(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """Terminate Codex and its child vendor process group after hard timeout."""
    _signal_backend_process_group(proc, signal.SIGTERM)
    try:
        return proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        _signal_backend_process_group(proc, signal.SIGKILL)
        try:
            return proc.communicate(timeout=5)
        except Exception:
            return "", ""
    except Exception:
        return "", ""


def _signal_backend_process_group(proc: subprocess.Popen[str], sig: signal.Signals) -> None:
    if os.name != "nt":
        try:
            os.killpg(proc.pid, sig)
            return
        except ProcessLookupError:
            return
        except PermissionError:
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    except Exception:
        pass


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
