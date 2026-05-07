"""Shared phase artifact contract for engine and native runners."""
from __future__ import annotations

import re
from pathlib import Path


PHASE_SCRIPT_CONTRACT_MARKDOWN = """### Phase Script Artifacts

Phase script naming is governed by `tiny_lab.phase_contract`; update that module instead of copying rules into prompts or runner docs.

1. Create exactly one Python script for the active phase under `research/iter_N/phases/`.
2. Prefer `research/iter_N/phases/<current_phase_id>_<current_phase_name_slug>.py`.
3. The engine accepts only these stems for phase `<current_phase_id>`: exactly `<current_phase_id>`, `<current_phase_id>_...`, or `<current_phase_id>-...`.
4. Do not create backup, alternate, or future-phase scripts in the same step; multiple matching scripts for the active phase block execution.
5. Do not assume `python -m pip` exists. If a dependency is missing, first try `ensurepip` plus project-local `PIP_CACHE_DIR`, then fall back to `uv pip install --python <sys.executable> ...` with project-local `UV_CACHE_DIR`, or fail with a clear dependency message before doing partial work.
"""


def phase_name_slug(name: str) -> str:
    """Return a stable filename slug for a phase name."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "script"


def default_phase_script_filename(phase_id: str, phase_name: str) -> str:
    """Preferred filename for a generated phase script."""
    return f"{phase_id}_{phase_name_slug(phase_name)}.py"


def default_phase_script_path(iter_label: str, phase_id: str, phase_name: str) -> str:
    """Preferred project-relative path for a generated phase script."""
    return f"research/{iter_label}/phases/{default_phase_script_filename(phase_id, phase_name)}"


def phase_script_stem_matches(stem: str, phase_id: str) -> bool:
    """Return whether a Python filename stem belongs to a phase id."""
    return stem == phase_id or stem.startswith(f"{phase_id}_") or stem.startswith(f"{phase_id}-")


def phase_script_candidates(phases_path: Path, phase_id: str) -> list[Path]:
    """Return sorted Python scripts matching a phase id."""
    return sorted(
        path
        for path in phases_path.glob("*.py")
        if path.is_file() and phase_script_stem_matches(path.stem, phase_id)
    )


def select_phase_script(phases_path: Path, phase_id: str) -> Path:
    """Select the unique Python script for a phase.

    There must be one and only one accepted candidate for the phase.
    """
    candidates = phase_script_candidates(phases_path, phase_id)
    if not candidates:
        raise ValueError(f"No Python script found for phase {phase_id} in {phases_path}")

    if len(candidates) == 1:
        return candidates[0]

    names = [path.name for path in candidates]
    raise ValueError(f"Multiple Python scripts found for phase {phase_id}: {names}")
