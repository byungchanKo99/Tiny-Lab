"""Workflow definition parser and validator.

workflow.json defines the state machine: states, transitions, allowed
tools, completion conditions, and error handling. This module parses
it into typed dataclasses and validates the graph.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import WorkflowError


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CompletionSpec:
    """What artifact must be produced to complete a state."""

    artifact: str  # glob pattern, e.g. "research/{iter}/.domain_research.json"
    required_fields: list[str] = field(default_factory=list)


@dataclass
class ErrorSpec:
    """Error handling for a state."""

    max_retries: int = 0
    retry_to: str | None = None  # state to go back to on retry
    on_exhaust: str = "skip_phase"  # skip_phase | stop | ask


@dataclass
class ConditionSpec:
    """Condition for process/checkpoint state transitions."""

    source: str | None = None  # YAML file to read
    field: str | None = None  # field to extract
    check: str | None = None  # built-in check name


@dataclass
class StateSpec:
    """A single state in the workflow."""

    id: str
    type: str  # ai_session | process | checkpoint
    prompt: str | None = None  # prompt template path
    allowed_tools: list[str] = field(default_factory=list)
    allowed_write_globs: list[str] = field(default_factory=list)
    blocked_bash_patterns: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)
    interactive: bool = False
    interactive_fallback: str = "self_answer"  # self_answer | wait | skip
    mandatory: bool = False  # checkpoint always waits, even in autonomous mode
    completion: CompletionSpec | None = None
    error: ErrorSpec | None = None
    condition: ConditionSpec | None = None
    next: str | dict[str, str] | None = None  # str for single, dict for conditional


@dataclass
class AutonomySpec:
    """Autonomy settings."""

    mode: str = "autonomous"  # autonomous | supervised
    max_iterations: int = 5
    allow_idea_mutation: bool = True
    stop_on_target: bool = True
    max_consecutive_failures: int = 3


@dataclass
class InterventionSpec:
    """Intervention settings."""

    checkpoint: str = "between_phases"  # between_phases | on_failure | never
    timeout_seconds: int = 3600


@dataclass
class Workflow:
    """Parsed workflow definition."""

    states: list[StateSpec]
    autonomy: AutonomySpec
    intervention: InterventionSpec
    _index: dict[str, StateSpec] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._index = {s.id: s for s in self.states}

    def get_state(self, state_id: str) -> StateSpec:
        if state_id not in self._index:
            raise WorkflowError(f"Unknown state: {state_id}")
        return self._index[state_id]

    def first_state(self) -> str:
        if not self.states:
            raise WorkflowError("Workflow has no states")
        return self.states[0].id

    def state_ids(self) -> list[str]:
        return [s.id for s in self.states]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_completion(raw: dict[str, Any] | None) -> CompletionSpec | None:
    if not raw:
        return None
    return CompletionSpec(
        artifact=raw.get("artifact", ""),
        required_fields=raw.get("required_fields", []),
    )


def _parse_error(raw: dict[str, Any] | None) -> ErrorSpec | None:
    if not raw:
        return None
    return ErrorSpec(
        max_retries=raw.get("max_retries", 0),
        retry_to=raw.get("retry_to"),
        on_exhaust=raw.get("on_exhaust", "skip_phase"),
    )


def _parse_condition(raw: dict[str, Any] | None) -> ConditionSpec | None:
    if not raw:
        return None
    return ConditionSpec(
        source=raw.get("source"),
        field=raw.get("field"),
        check=raw.get("check"),
    )


def _parse_state(raw: dict[str, Any]) -> StateSpec:
    return StateSpec(
        id=raw["id"],
        type=raw.get("type", "ai_session"),
        prompt=raw.get("prompt"),
        allowed_tools=raw.get("allowed_tools", []),
        allowed_write_globs=raw.get("allowed_write_globs", []),
        blocked_bash_patterns=raw.get("blocked_bash_patterns", []),
        context=raw.get("context", []),
        interactive=raw.get("interactive", False),
        interactive_fallback=raw.get("interactive_fallback", "self_answer"),
        mandatory=raw.get("mandatory", False),
        completion=_parse_completion(raw.get("completion")),
        error=_parse_error(raw.get("error")),
        condition=_parse_condition(raw.get("condition")),
        next=raw.get("next"),
    )


def _parse_autonomy(raw: dict[str, Any] | None) -> AutonomySpec:
    if not raw:
        return AutonomySpec()
    cb = raw.get("circuit_breaker", {})
    return AutonomySpec(
        mode=raw.get("mode", "autonomous"),
        max_iterations=raw.get("max_iterations", 5),
        allow_idea_mutation=raw.get("allow_idea_mutation", True),
        stop_on_target=raw.get("stop_on_target", True),
        max_consecutive_failures=cb.get("max_consecutive_failures", 3),
    )


def _parse_intervention(raw: dict[str, Any] | None) -> InterventionSpec:
    if not raw:
        return InterventionSpec()
    return InterventionSpec(
        checkpoint=raw.get("checkpoint", "between_phases"),
        timeout_seconds=raw.get("timeout_seconds", 3600),
    )


def load_workflow(path: Path) -> Workflow:
    """Load and parse a workflow YAML file."""
    if not path.exists():
        raise WorkflowError(f"Workflow file not found: {path}")

    data = json.loads(path.read_text())
    if not data or "states" not in data:
        raise WorkflowError("Workflow must have 'states' list")

    states = [_parse_state(s) for s in data["states"]]
    autonomy = _parse_autonomy(data.get("autonomy"))
    intervention = _parse_intervention(data.get("intervention"))

    wf = Workflow(states=states, autonomy=autonomy, intervention=intervention)
    validate_workflow(wf)
    return wf


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_workflow(wf: Workflow) -> None:
    """Validate workflow graph integrity."""
    errors: list[str] = []
    ids = set()

    for state in wf.states:
        # Duplicate check
        if state.id in ids:
            errors.append(f"Duplicate state id: {state.id}")
        ids.add(state.id)

        # Type check
        if state.type not in ("ai_session", "process", "checkpoint"):
            errors.append(f"State {state.id}: invalid type '{state.type}'")

        # ai_session with dict next must have condition (for conditional routing)
        # process/checkpoint with dict next must have condition
        if isinstance(state.next, dict) and state.condition is None:
            errors.append(f"State {state.id}: dict 'next' requires 'condition'")

        # Validate next references
        if isinstance(state.next, str) and state.next not in ids and state.next != "DONE":
            # Forward references are OK — check after all states parsed
            pass
        if isinstance(state.next, dict):
            for target in state.next.values():
                if target not in ("DONE",) and target not in ids:
                    pass  # forward reference, checked below

    # Check all next targets exist
    all_ids = wf.state_ids() + ["DONE"]
    for state in wf.states:
        targets = []
        if isinstance(state.next, str):
            targets = [state.next]
        elif isinstance(state.next, dict):
            targets = list(state.next.values())

        for t in targets:
            if t not in all_ids:
                errors.append(f"State {state.id}: next target '{t}' does not exist")

    if errors:
        raise WorkflowError("Workflow validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
