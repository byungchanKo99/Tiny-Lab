"""Conditional process handler — resolve condition and transition."""
from __future__ import annotations

from ..conditions import resolve_condition
from ..logging import log
from ..state import LoopState
from ..workflow import StateSpec
from . import EngineContext, StateResult


class ConditionalProcessHandler:
    """Generic handler for process states that just resolve a condition and transition."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        if isinstance(spec.next, dict) and spec.condition:
            next_state = resolve_condition(
                spec.condition, spec.next,
                ctx.project_dir, ls.current_iteration,
            )
            return StateResult(transition=next_state)
        elif isinstance(spec.next, str):
            return StateResult(transition=spec.next)
        return StateResult()
