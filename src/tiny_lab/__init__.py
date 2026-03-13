"""Tiny Lab — Deterministic AI-driven research loop for experiments."""

try:
    from importlib.metadata import version
    __version__ = version("tiny-lab")
except Exception:
    __version__ = "0.0.0-dev"
