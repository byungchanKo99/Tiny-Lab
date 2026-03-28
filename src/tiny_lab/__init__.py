"""tiny-lab v5 — plan-driven AI research loop."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tiny-lab")
except PackageNotFoundError:
    __version__ = "unknown"
