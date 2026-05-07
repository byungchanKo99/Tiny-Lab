"""Conditional process handler — resolve condition and transition."""
from __future__ import annotations

from ..advancement import resolve_next_state
from ..errors import StateError
from ..state import LoopState
from ..workflow import StateSpec
from . import EngineContext, StateResult


class ConditionalProcessHandler:
    """Generic handler for process states that just resolve a condition and transition."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        next_state, problem = resolve_next_state(
            spec,
            ctx.project_dir,
            ls.current_iteration,
            current_phase_id=ls.current_phase_id,
        )
        if problem:
            raise StateError(problem)
        if next_state:
            return StateResult(transition=next_state)
        return StateResult()
