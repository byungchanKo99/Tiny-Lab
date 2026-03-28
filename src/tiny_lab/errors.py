"""Exception hierarchy for tiny-lab v5."""


class TinyLabError(Exception):
    """Base exception for all tiny-lab errors."""


class WorkflowError(TinyLabError):
    """Invalid workflow definition."""


class StateError(TinyLabError):
    """State machine transition error."""


class PhaseError(TinyLabError):
    """Phase execution error."""


class PlanError(TinyLabError):
    """Research plan parsing or validation error."""


class InterventionError(TinyLabError):
    """Intervention protocol error."""
