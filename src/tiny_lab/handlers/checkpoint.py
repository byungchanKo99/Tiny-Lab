"""Checkpoint handler — wait for intervention or auto-approve."""
from __future__ import annotations

import json
import time

from ..errors import StateError
from ..logging import log
from ..paths import intervention_path
from ..plan import update_phase_status
from ..state import LoopState, set_state
from ..workflow import StateSpec
from . import EngineContext, StateResult


class CheckpointHandler:
    """Wait for intervention or auto-approve based on autonomy mode."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        ipath = intervention_path(ctx.project_dir)

        # Existing intervention
        if ipath.exists():
            return _process_intervention(spec, ls, ctx, ipath)

        # Autonomous → auto-approve
        if ctx.autonomy.mode == "autonomous":
            log(f"ENGINE: checkpoint {spec.id} — autonomous mode, auto-approving")
            return _advance(spec, "approve", ls, ctx)

        # Supervised → poll for intervention
        timeout = ctx.intervention.timeout_seconds
        start = time.monotonic()
        log(f"ENGINE: checkpoint {spec.id}, waiting for intervention (timeout={timeout}s)")

        while time.monotonic() - start < timeout:
            if ipath.exists():
                return _process_intervention(spec, ls, ctx, ipath)
            time.sleep(5)

        log("ENGINE: checkpoint timeout, auto-advancing")
        return _advance(spec, "approve", ls, ctx)


def _process_intervention(
    spec: StateSpec, ls: LoopState, ctx: EngineContext, ipath: "Path",  # type: ignore[name-defined] # noqa: F821
) -> StateResult:
    intervention = json.loads(ipath.read_text())
    ipath.unlink()
    action = intervention.get("action", "approve")
    log(f"ENGINE: intervention received: {action}")

    if action == "skip_phase" and ls.current_phase_id:
        update_phase_status(ctx.project_dir, ls.current_iteration, ls.current_phase_id, "skipped")

    return _advance(spec, action, ls, ctx)


def _advance(spec: StateSpec, action: str, ls: LoopState, ctx: EngineContext) -> StateResult:
    if isinstance(spec.next, dict):
        target = spec.next.get(action, spec.next.get("approve", "DONE"))
        return StateResult(transition=target)
    elif isinstance(spec.next, str):
        return StateResult(transition=spec.next)
    return StateResult(transition="DONE")
