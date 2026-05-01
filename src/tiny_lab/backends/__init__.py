"""AI backend abstraction.

Two backends ship in v7.7: claude (default), codex (opt-in).
The active backend can be set globally via `--engine` or per-state via
`spec.engine` in workflow JSON.
"""
from __future__ import annotations

from .base import AiBackend, BackendResult, get_backend

__all__ = ["AiBackend", "BackendResult", "get_backend"]
