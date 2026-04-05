"""Handler protocol, registry, and result types.

Handlers are the units of work in the engine. Each state in the workflow
is dispatched to a handler that executes its logic and returns a StateResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..errors import WorkflowError
from ..state import LoopState
from ..workflow import StateSpec


@dataclass
class StateResult:
    """Outcome of a handler execution.

    transition: explicit next state, or None to use spec.next
    state_overrides: kwargs passed to set_state (e.g. current_phase_id)
    """

    transition: str | None = None
    state_overrides: dict[str, Any] = field(default_factory=dict)


class StateHandler(Protocol):
    """Protocol that all handlers must satisfy."""

    def execute(
        self,
        spec: StateSpec,
        ls: LoopState,
        ctx: EngineContext,
    ) -> StateResult: ...


@dataclass
class EngineContext:
    """Shared context passed to every handler. Thin — just project references."""

    project_dir: "Path"  # type: ignore[name-defined]  # noqa: F821
    workflow: "Workflow"  # type: ignore[name-defined]  # noqa: F821
    model: str = "sonnet"  # claude model: sonnet | haiku | opus

    @property
    def autonomy(self) -> Any:
        return self.workflow.autonomy

    @property
    def intervention(self) -> Any:
        return self.workflow.intervention


class HandlerRegistry:
    """Maps (state_type, state_id) → handler. ID match takes priority."""

    def __init__(self) -> None:
        self._by_id: dict[str, StateHandler] = {}
        self._by_type: dict[str, StateHandler] = {}

    def on_type(self, state_type: str, handler: StateHandler) -> None:
        self._by_type[state_type] = handler

    def on_id(self, state_id: str, handler: StateHandler) -> None:
        self._by_id[state_id] = handler

    def get(self, spec: StateSpec) -> StateHandler:
        if spec.id in self._by_id:
            return self._by_id[spec.id]
        if spec.type in self._by_type:
            return self._by_type[spec.type]
        raise WorkflowError(f"No handler for state {spec.id} (type={spec.type})")
