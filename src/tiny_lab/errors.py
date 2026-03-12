"""Domain-specific error hierarchy for Tiny-Lab."""
from __future__ import annotations


class TinyLabError(Exception):
    """Base error for all Tiny-Lab operations."""


class BuildError(TinyLabError):
    """Raised when BUILD phase fails."""


class RunError(TinyLabError):
    """Raised when RUN phase fails."""


class EvaluateError(TinyLabError):
    """Raised when EVALUATE phase fails."""
