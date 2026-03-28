"""Unified logging for tiny-lab v5."""
from __future__ import annotations

from datetime import datetime


def log(msg: str, *, file: str = "research/loop.log") -> None:
    """Append a timestamped message to the log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line)
    try:
        with open(file, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass
