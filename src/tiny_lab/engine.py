"""State machine engine — the thin outer loop.

Manages state transitions, dispatches to handlers, and handles errors.
All business logic lives in handlers/ — the engine just drives the loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import events
from .advancement import (
    apply_state_transition,
    carry_over_iteration,
    create_iteration_dirs,
    resolve_next_state,
    transition_starts_new_iteration,
    update_iterations_log,
)
from .errors import BackendUnavailableError, StateError, TinyLabError
from .handlers import EngineContext, HandlerRegistry, StateResult
from .lock import Lock
from .logging import log
from .paths import (
    iter_dir, research_dir,
    workflow_path, shared_dir, knowledge_dir,
    intervention_path,
)
from .plan import update_phase_status
from .runner_contract import RunnerStateContract, resolve_runner_state_contract
from .state import LoopState, load_state, save_state, set_state
from .workflow import StateSpec, load_workflow


@dataclass(frozen=True)
class StepOutcome:
    """Result of executing at most one state-machine step."""

    executed: bool
    state_before: str
    state_after: str
    message: str


@dataclass(frozen=True)
class PromptOutcome:
    """Rendered prompt for the current native-runner AI session state."""

    state: str
    prompt: str


class Engine:
    """Tiny-lab state machine engine."""

    def __init__(
        self,
        project_dir: Path,
        registry: HandlerRegistry,
        model: str = "sonnet",
        engine: str = "claude",
        backend_timeout_seconds: float | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.workflow = load_workflow(workflow_path(project_dir))
        self.registry = registry
        self.ctx = EngineContext(
            project_dir=project_dir,
            workflow=self.workflow,
            model=model,
            engine=engine,
            backend_timeout_seconds=backend_timeout_seconds,
        )
        self._shutdown = False
        self._last_error: str | None = None

    def run(self, max_steps: int | None = None) -> bool:
        with Lock(self.project_dir):
            self._init()
            return self._loop(max_steps=max_steps)

    def step_once(
        self,
        *,
        run_ai: bool = False,
        wait_checkpoint: bool = False,
    ) -> StepOutcome:
        """Execute at most one state-machine step.

        Native runners use this to delegate deterministic process, phase,
        and checkpoint transitions to the same handlers as the CLI engine
        without starting the full autonomous loop.
        """
        with Lock(self.project_dir):
            state_before_init = load_state(self.project_dir).state
            self._init()
            ls = load_state(self.project_dir)
            if state_before_init == "INIT" and ls.state != "INIT":
                return StepOutcome(True, "INIT", ls.state, f"initialized → {ls.state}")

            state_before = ls.state
            if ls.state == "DONE":
                return StepOutcome(False, state_before, state_before, "already DONE")

            try:
                spec = self.workflow.get_state(ls.state)
            except TinyLabError:
                log(f"ENGINE: unknown state '{ls.state}', stopping without marking DONE")
                return StepOutcome(
                    False,
                    state_before,
                    state_before,
                    f"{state_before} is missing from workflow; repair research/.workflow.json or research/.state.json",
                )

            if spec.type == "ai_session" and not run_ai:
                return StepOutcome(
                    False,
                    state_before,
                    state_before,
                    f"{state_before} is an ai_session; complete its artifact natively or run with --run-ai",
                )

            if spec.type == "checkpoint" and not wait_checkpoint:
                ipath = intervention_path(self.project_dir)
                if not ipath.exists() and (spec.mandatory or self.ctx.autonomy.mode != "autonomous"):
                    return StepOutcome(
                        False,
                        state_before,
                        state_before,
                        f"{state_before} is waiting for intervention",
                    )

            self._execute_current_state(ls)
            state_after = load_state(self.project_dir).state
            if self._shutdown:
                detail = f": {self._last_error}" if self._last_error else ""
                return StepOutcome(
                    False,
                    state_before,
                    state_after,
                    f"{state_before} failed{detail}",
                )
            return StepOutcome(
                True,
                state_before,
                state_after,
                f"{state_before} → {state_after}" if state_after != state_before else f"{state_before} completed",
            )

    def render_current_prompt(self) -> PromptOutcome:
        """Render the current ai_session prompt through the same path used by the engine."""
        with Lock(self.project_dir):
            self._init()
            ls = load_state(self.project_dir)
            if ls.state == "DONE":
                raise StateError("DONE has no prompt")

            spec = self.workflow.get_state(ls.state)
            if spec.type != "ai_session":
                raise StateError(f"{ls.state} is a {spec.type} state; use tiny-lab step")

            from .handlers.ai_session import render_ai_session_prompt

            return PromptOutcome(
                state=ls.state,
                prompt=render_ai_session_prompt(spec, ls, self.ctx),
            )

    def current_state_briefing(self) -> RunnerStateContract:
        """Return the current state contract resolved for the active iteration."""
        with Lock(self.project_dir):
            self._init()
            ls = load_state(self.project_dir)
            if ls.state == "DONE":
                return resolve_runner_state_contract(
                    state_id=ls.state,
                    iteration=ls.current_iteration,
                    current_phase_id=ls.current_phase_id,
                    spec=None,
                    default_engine=self.ctx.engine,
                )

            try:
                spec = self.workflow.get_state(ls.state)
            except TinyLabError:
                spec = None
            return resolve_runner_state_contract(
                state_id=ls.state,
                iteration=ls.current_iteration,
                current_phase_id=ls.current_phase_id,
                spec=spec,
                default_engine=self.ctx.engine,
            )

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self) -> None:
        research_dir(self.project_dir).mkdir(parents=True, exist_ok=True)
        shared_dir(self.project_dir).mkdir(parents=True, exist_ok=True)
        knowledge_dir(self.project_dir).mkdir(parents=True, exist_ok=True)

        ls = load_state(self.project_dir)
        if ls.state == "INIT":
            self._create_iteration(1)
            first = self.workflow.first_state()
            set_state(self.project_dir, first, current_iteration=1)
            log(f"ENGINE: initialized, starting at {first}")
        elif ls.state == "DONE" and not ls.resumable:
            log("ENGINE: previous run completed. Use 'tiny-lab fork' to start new iteration.")
        else:
            log(f"ENGINE: resuming from {ls.state} (iter={ls.current_iteration})")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self, max_steps: int | None = None) -> bool:
        steps_executed = 0
        while not self._shutdown:
            ls = load_state(self.project_dir)

            if ls.state == "DONE":
                log("ENGINE: reached DONE")
                events.loop_done(self.project_dir, "completed")
                return True

            if ls.current_iteration > self.workflow.autonomy.max_iterations:
                # Don't cut off if we're in the synthesis/evaluation tail
                if ls.state not in ("STORY_TELL", "REVIEW", "REVIEW_DONE"):
                    log(f"ENGINE: max iterations ({self.workflow.autonomy.max_iterations}) reached → STORY_TELL")
                    if "STORY_TELL" in self.workflow._index:
                        set_state(self.project_dir, "STORY_TELL")
                        continue
                    else:
                        set_state(self.project_dir, "DONE", resumable=False)
                        return True

            try:
                spec = self.workflow.get_state(ls.state)
            except TinyLabError:
                log(f"ENGINE: unknown state '{ls.state}', stopping without marking DONE")
                return False

            self._execute_current_state(ls)
            if self._shutdown:
                break

            steps_executed += 1
            if max_steps is not None and steps_executed >= max_steps:
                current = load_state(self.project_dir)
                log(f"ENGINE: max steps ({max_steps}) reached, pausing at {current.state}")
                return True

        return False

    def _execute_current_state(self, ls: LoopState) -> None:
        """Execute the current state once using the registered handler."""
        spec = self.workflow.get_state(ls.state)
        log(f"ENGINE: entering {ls.state} (type={spec.type}, iter={ls.current_iteration})")
        events.state_entered(self.project_dir, ls.state, ls.current_iteration)

        try:
            handler = self.registry.get(spec)
            result = handler.execute(spec, ls, self.ctx)
            self._apply_result(result, spec, ls)

            # Reset consecutive failure counter on success
            ls = load_state(self.project_dir)
            if ls.consecutive_failures > 0:
                ls.consecutive_failures = 0
                save_state(self.project_dir, ls)

        except BackendUnavailableError as e:
            self._last_error = str(e)
            log(f"ENGINE: backend unavailable in {ls.state}: {e}")
            events.error_occurred(self.project_dir, ls.state, str(e))
            self._shutdown = True

        except TinyLabError as e:
            self._last_error = str(e)
            log(f"ENGINE: error in {ls.state}: {e}")
            events.error_occurred(self.project_dir, ls.state, str(e))
            self._handle_error(spec, ls, e)

        except Exception as e:
            self._last_error = str(e)
            log(f"ENGINE: unexpected error in {ls.state}: {e}")
            events.error_occurred(self.project_dir, ls.state, str(e))
            self._handle_error(spec, ls, e)

    # ------------------------------------------------------------------
    # Result application
    # ------------------------------------------------------------------

    def _apply_result(self, result: StateResult, spec: StateSpec, ls: LoopState) -> None:
        """Apply handler result to state machine."""
        overrides = dict(result.state_overrides)

        if result.transition:
            next_state = self._cap_review_transition_after_max_iterations(ls, result.transition, overrides)
            apply_state_transition(
                self.project_dir,
                next_state,
                current_state=ls,
                state_overrides=overrides,
                new_iteration_on_entry=transition_starts_new_iteration(ls.state, next_state),
            )
        else:
            # Save overrides first (e.g. PHASE_SELECT setting current_phase_id)
            if overrides:
                current_ls = load_state(self.project_dir)
                set_state(self.project_dir, current_ls.state, **overrides)
            # Then follow spec.next
            self._follow_next(spec, ls)

    def _follow_next(self, spec: StateSpec, ls: LoopState) -> None:
        """Evaluate and apply spec.next transition."""
        current_ls = load_state(self.project_dir)
        nxt, problem = resolve_next_state(
            spec,
            self.project_dir,
            current_ls.current_iteration,
            current_phase_id=current_ls.current_phase_id,
        )
        if problem:
            raise StateError(problem)
        if not nxt:
            return

        overrides: dict[str, object] = {}
        nxt = self._cap_review_transition_after_max_iterations(current_ls, nxt, overrides)
        apply_state_transition(
            self.project_dir,
            nxt,
            current_state=current_ls,
            state_overrides=overrides,
        )

    def _cap_review_transition_after_max_iterations(
        self,
        ls: LoopState,
        next_state: str,
        overrides: dict[str, object],
    ) -> str:
        """Stop after final review when the configured iteration budget is exhausted."""
        if (
            ls.current_iteration >= self.workflow.autonomy.max_iterations
            and ls.state == "REVIEW_DONE"
            and next_state != "DONE"
        ):
            log(
                "ENGINE: max iterations "
                f"({self.workflow.autonomy.max_iterations}) reached; "
                f"review requested {next_state}, stopping at DONE"
            )
            overrides["resumable"] = False
            overrides["session_id"] = None
            return "DONE"
        return next_state

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error(self, spec: StateSpec, ls: LoopState, error: Exception) -> None:
        err = spec.error
        ls = load_state(self.project_dir)
        ls.consecutive_failures += 1
        ls.phase_retries += 1
        save_state(self.project_dir, ls)

        # Circuit breaker
        if ls.consecutive_failures >= self.workflow.autonomy.max_consecutive_failures:
            log(f"ENGINE: circuit breaker ({ls.consecutive_failures} consecutive failures)")
            set_state(self.project_dir, "DONE", resumable=True)
            self._shutdown = True
            return

        # Phase-level retry
        if err and ls.phase_retries <= err.max_retries:
            retry_to = err.retry_to or spec.id
            log(f"ENGINE: retrying ({ls.phase_retries}/{err.max_retries}) → {retry_to}")
            set_state(self.project_dir, retry_to)
            return

        # Exhausted
        on_exhaust = err.on_exhaust if err else "stop"
        if on_exhaust == "skip_phase" and ls.current_phase_id:
            log(f"ENGINE: skipping phase {ls.current_phase_id}")
            update_phase_status(self.project_dir, ls.current_iteration, ls.current_phase_id, "skipped")
            set_state(self.project_dir, "PHASE_SELECT", current_phase_id=None, phase_retries=0)
        elif on_exhaust == "ask":
            log("ENGINE: waiting for intervention after error")
            set_state(self.project_dir, "CHECKPOINT")
        else:
            log("ENGINE: stopping after error")
            set_state(self.project_dir, "DONE", resumable=True)
            self._shutdown = True

    # ------------------------------------------------------------------
    # Iteration management
    # ------------------------------------------------------------------

    def _create_iteration(self, iteration: int) -> None:
        create_iteration_dirs(self.project_dir, iteration)
        log(f"ENGINE: created iteration directory {iter_dir(self.project_dir, iteration).name}")

    def _carry_over(self, from_iter: int, to_iter: int, entry_state: str) -> None:
        carry_over_iteration(self.project_dir, from_iter, to_iter, entry_state)

    def _update_iterations_log(self, completed_iter: int) -> None:
        update_iterations_log(self.project_dir, completed_iter)
