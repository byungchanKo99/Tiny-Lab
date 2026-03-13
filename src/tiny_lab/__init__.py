"""Tiny Lab — Deterministic AI-driven research loop for experiments."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tiny-lab")
except PackageNotFoundError:
    __version__ = version(__name__)
