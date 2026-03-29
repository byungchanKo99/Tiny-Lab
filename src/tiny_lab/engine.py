"""State machine engine — the thin outer loop.

Manages state transitions, dispatches to handlers, and handles errors.
All business logic lives in handlers/ — the engine just drives the loop.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import events
from .errors import TinyLabError
from .handlers import EngineContext, HandlerRegistry, StateResult
from .lock import Lock
from .logging import log
from .paths import (
    iter_dir, phases_dir, results_dir, research_dir,
    workflow_path, shared_dir, iterations_path, reflect_path,
)
from .plan import update_phase_status
from .state import LoopState, load_state, save_state, set_state
from .workflow import StateSpec, load_workflow


class Engine:
    """Tiny-lab state machine engine."""

    def __init__(self, project_dir: Path, registry: HandlerRegistry) -> None:
        self.project_dir = project_dir
        self.workflow = load_workflow(workflow_path(project_dir))
        self.registry = registry
        self.ctx = EngineContext(project_dir=project_dir, workflow=self.workflow)
        self._shutdown = False

    def run(self) -> None:
        with Lock(self.project_dir):
            self._init()
            self._loop()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self) -> None:
        research_dir(self.project_dir).mkdir(parents=True, exist_ok=True)
        shared_dir(self.project_dir).mkdir(parents=True, exist_ok=True)

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

    def _loop(self) -> None:
        while not self._shutdown:
            ls = load_state(self.project_dir)

            if ls.state == "DONE":
                log("ENGINE: reached DONE")
                events.loop_done(self.project_dir, "completed")
                break

            if ls.current_iteration > self.workflow.autonomy.max_iterations:
                log(f"ENGINE: max iterations ({self.workflow.autonomy.max_iterations}) reached")
                set_state(self.project_dir, "DONE", resumable=False)
                break

            try:
                spec = self.workflow.get_state(ls.state)
            except Exception:
                log(f"ENGINE: unknown state '{ls.state}', stopping")
                set_state(self.project_dir, "DONE")
                break

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

            except TinyLabError as e:
                log(f"ENGINE: error in {ls.state}: {e}")
                events.error_occurred(self.project_dir, ls.state, str(e))
                self._handle_error(spec, ls, e)

            except Exception as e:
                log(f"ENGINE: unexpected error in {ls.state}: {e}")
                events.error_occurred(self.project_dir, ls.state, str(e))
                self._handle_error(spec, ls, e)

    # ------------------------------------------------------------------
    # Result application
    # ------------------------------------------------------------------

    def _apply_result(self, result: StateResult, spec: StateSpec, ls: LoopState) -> None:
        """Apply handler result to state machine."""
        overrides = result.state_overrides

        if result.transition:
            # New iteration check
            if result.transition in ("IDEA_REFINE", "DOMAIN_RESEARCH"):
                new_iter = ls.current_iteration + 1
                self._create_iteration(new_iter)
                self._carry_over(ls.current_iteration, new_iter, result.transition)
                overrides["current_iteration"] = new_iter
            set_state(self.project_dir, result.transition, **overrides)
        else:
            # Save overrides first (e.g. PHASE_SELECT setting current_phase_id)
            if overrides:
                current_ls = load_state(self.project_dir)
                set_state(self.project_dir, current_ls.state, **overrides)
            # Then follow spec.next
            self._follow_next(spec, ls)

    def _follow_next(self, spec: StateSpec, ls: LoopState) -> None:
        """Evaluate and apply spec.next transition."""
        if isinstance(spec.next, str):
            set_state(self.project_dir, spec.next)
        elif isinstance(spec.next, dict) and spec.condition:
            from .conditions import resolve_condition
            current_ls = load_state(self.project_dir)
            nxt = resolve_condition(
                spec.condition, spec.next,
                self.project_dir, current_ls.current_iteration,
            )
            set_state(self.project_dir, nxt)

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
            set_state(self.project_dir, "PHASE_SELECT", current_phase_id=None, phase_retries=0, session_id=None)
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
        idir = iter_dir(self.project_dir, iteration)
        idir.mkdir(parents=True, exist_ok=True)
        phases_dir(self.project_dir, iteration).mkdir(exist_ok=True)
        results_dir(self.project_dir, iteration).mkdir(exist_ok=True)
        log(f"ENGINE: created iteration directory {idir.name}")

    def _carry_over(self, from_iter: int, to_iter: int, entry_state: str) -> None:
        src = iter_dir(self.project_dir, from_iter)
        dst = iter_dir(self.project_dir, to_iter)

        carry_map = {
            "DATA_DEEP_DIVE": [".domain_research.json"],
            "IDEA_REFINE": [".domain_research.json", ".data_analysis.json"],
            "PLAN": [".domain_research.json", ".data_analysis.json", ".idea_refined.json"],
        }
        for fname in carry_map.get(entry_state, []):
            src_file = src / fname
            if src_file.exists():
                shutil.copy2(src_file, dst / fname)
                log(f"ENGINE: carried over {fname} to iter_{to_iter}")

        self._update_iterations_log(from_iter)

    def _update_iterations_log(self, completed_iter: int) -> None:
        ipath = iterations_path(self.project_dir)
        data: dict[str, Any] = {"current_iteration": completed_iter + 1, "iterations": []}
        if ipath.exists():
            data = json.loads(ipath.read_text()) or data

        rpath = reflect_path(self.project_dir, completed_iter)
        reflect: dict[str, Any] = {}
        if rpath.exists():
            reflect = json.loads(rpath.read_text()) or {}

        data["iterations"].append({
            "id": completed_iter,
            "decision": reflect.get("decision", "unknown"),
            "reason": reflect.get("reason", ""),
        })
        data["current_iteration"] = completed_iter + 1
        ipath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
