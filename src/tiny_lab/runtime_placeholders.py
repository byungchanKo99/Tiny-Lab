"""Runtime placeholder resolution shared by engine and native runner paths."""
from __future__ import annotations

from typing import Any


def resolve_runtime_placeholders(
    value: Any,
    *,
    iteration: int,
    current_phase_id: str | None = None,
) -> str:
    """Resolve workflow placeholders that are known from runtime state."""
    text = str(value)
    replacements = {
        "{iter}": f"iter_{iteration}",
        "{iteration}": str(iteration),
    }
    if current_phase_id is not None:
        replacements["{current_phase_id}"] = str(current_phase_id)
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    return text
