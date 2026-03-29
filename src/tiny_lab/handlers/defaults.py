"""Default handler registries for presets."""
from __future__ import annotations

from . import HandlerRegistry
from .ai_session import AiSessionHandler
from .checkpoint import CheckpointHandler
from .conditional import ConditionalProcessHandler
from .phase import (
    PhaseSelectHandler,
    PhaseRunHandler,
    PhaseEvaluateHandler,
    PhaseRecordHandler,
)
from .reflect import ReflectDoneHandler


def base_registry() -> HandlerRegistry:
    """Registry with just the three type-level handlers.

    Suitable for simple presets (review-paper, custom) that have
    no phase execution states.
    """
    reg = HandlerRegistry()
    reg.on_type("ai_session", AiSessionHandler())
    reg.on_type("checkpoint", CheckpointHandler())
    reg.on_type("process", ConditionalProcessHandler())
    return reg


def research_registry() -> HandlerRegistry:
    """Registry for research presets with phase execution.

    Used by ml-experiment, novel-method, data-analysis.
    """
    reg = base_registry()
    reg.on_id("PHASE_SELECT", PhaseSelectHandler())
    reg.on_id("PHASE_RUN", PhaseRunHandler())
    reg.on_id("PHASE_EVALUATE", PhaseEvaluateHandler())
    reg.on_id("PHASE_RECORD", PhaseRecordHandler())
    reg.on_id("REFLECT_DONE", ReflectDoneHandler())
    return reg
