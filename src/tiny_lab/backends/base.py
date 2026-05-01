"""AI backend protocol and registry.

Each backend wraps one CLI tool (claude, codex, …) and exposes the same
small surface: invoke a one-shot prompt with allowed tools and return the
result. Session continuity is optional — if the backend supports it, it
returns a session_id; otherwise sessions are stateless and the engine
will pass full context each call.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class BackendResult:
    """One backend invocation's outcome."""

    exit_code: int
    stdout: str
    stderr: str
    session_id: str | None = None  # if backend supports session resume


class AiBackend(Protocol):
    """Backend protocol — every AI client implementation satisfies this."""

    name: str  # short id used in --engine and spec.engine

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
        """Run the backend with a single prompt.

        Args:
            prompt: complete prompt text to send.
            cwd: working directory the backend runs in.
            model: model id (backend-specific; ignored if backend has no choice).
            allowed_tools: list of tool names to permit; None = backend default.
            session_id: prior session to resume; None = fresh session.
            timeout: hard subprocess timeout in seconds.

        Returns:
            BackendResult with exit code, stdout, stderr, and (optionally)
            the resolved session_id for resume on next call.
        """
        ...


# Lazy registry — populated on first get_backend() call to avoid importing
# every backend module at startup.
_REGISTRY: dict[str, AiBackend] = {}


def get_backend(name: str) -> AiBackend:
    """Look up a backend by name. Loads the module on first request."""
    if name in _REGISTRY:
        return _REGISTRY[name]

    if name == "claude":
        from .claude import ClaudeBackend
        _REGISTRY[name] = ClaudeBackend()
    elif name == "codex":
        from .codex import CodexBackend
        _REGISTRY[name] = CodexBackend()
    else:
        from ..errors import TinyLabError
        raise TinyLabError(
            f"Unknown backend: '{name}'. Known: claude, codex. "
            f"Set the right name in --engine or workflow state.engine."
        )

    return _REGISTRY[name]
