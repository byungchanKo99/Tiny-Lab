#!/usr/bin/env python3
"""Backward-compatible wrapper. Use `tiny-lab run` instead."""
import sys
from pathlib import Path

# Add src/ to path so tiny_lab can be imported without pip install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tiny_lab.loop import ResearchLoop

if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parents[1]
    loop = ResearchLoop(project_dir)
    raise SystemExit(loop.run())
