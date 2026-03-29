"""State machine engine — the outer loop.

Manages state transitions, delegates to AI sessions (Claude Code),
handles process states internally, and waits at checkpoints.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import json

from . import events
from .conditions import resolve_condition
from .errors import StateError, TinyLabError
from .lock import Lock
from .logging import log
from .paths import (
    iter_dir, phases_dir, results_dir, research_dir,
    workflow_path, intervention_path, shared_dir,
)
from .plan import load_plan, next_pending_phase, update_phase_status
from .state import LoopState, load_state, save_state, set_state
from .workflow import Workflow, StateSpec, load_workflow


class Engine:
    """Tiny-lab v5 state machine engine."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.workflow = load_workflow(workflow_path(project_dir))
        self._shutdown = False

    def run(self) -> None:
        """Main loop: INIT → states → DONE."""
        with Lock(self.project_dir):
            self._init()
            self._loop()

    # ------------------------------------------------------------------
    # INIT (hardcoded, outside workflow)
    # ------------------------------------------------------------------

    def _init(self) -> None:
        """Bootstrap: create dirs, load or recover state."""
        rd = research_dir(self.project_dir)
        rd.mkdir(parents=True, exist_ok=True)
        shared_dir(self.project_dir).mkdir(parents=True, exist_ok=True)

        ls = load_state(self.project_dir)

        if ls.state == "INIT":
            # First run — create iter_1, set first workflow state
            self._create_iteration(1)
            first = self.workflow.first_state()
            set_state(self.project_dir, first, current_iteration=1)
            log(f"ENGINE: initialized, starting at {first}")
        elif ls.state == "DONE" and not ls.resumable:
            log("ENGINE: previous run completed. Use 'tiny-lab fork' to start new iteration.")
            return
        else:
            log(f"ENGINE: resuming from {ls.state} (iter={ls.current_iteration})")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Execute states until DONE or shutdown."""
        while not self._shutdown:
            ls = load_state(self.project_dir)

            if ls.state == "DONE":
                log("ENGINE: reached DONE")
                events.loop_done(self.project_dir, "completed")
                break

            # Check max iterations
            if ls.current_iteration > self.workflow.autonomy.max_iterations:
                log(f"ENGINE: max iterations ({self.workflow.autonomy.max_iterations}) reached")
                set_state(self.project_dir, "DONE", resumable=False)
                break

            try:
                state_spec = self.workflow.get_state(ls.state)
            except Exception:
                log(f"ENGINE: unknown state '{ls.state}', stopping")
                set_state(self.project_dir, "DONE")
                break

            log(f"ENGINE: entering {ls.state} (type={state_spec.type}, iter={ls.current_iteration})")
            events.state_entered(self.project_dir, ls.state, ls.current_iteration)

            try:
                if state_spec.type == "ai_session":
                    self._handle_ai_session(state_spec, ls)
                elif state_spec.type == "process":
                    self._handle_process(state_spec, ls)
                elif state_spec.type == "checkpoint":
                    self._handle_checkpoint(state_spec, ls)

                # Reset failure counter on success
                ls = load_state(self.project_dir)
                if ls.consecutive_failures > 0:
                    save_state(self.project_dir, LoopState(
                        current_iteration=ls.current_iteration,
                        state=ls.state,
                        current_phase_id=ls.current_phase_id,
                        consecutive_failures=0,
                    ))

            except TinyLabError as e:
                log(f"ENGINE: error in {ls.state}: {e}")
                events.error_occurred(self.project_dir, ls.state, str(e))
                self._handle_error(state_spec, ls, e)

            except Exception as e:
                log(f"ENGINE: unexpected error in {ls.state}: {e}")
                events.error_occurred(self.project_dir, ls.state, str(e))
                self._handle_error(state_spec, ls, e)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_ai_session(self, spec: StateSpec, ls: LoopState) -> None:
        """Run a Claude Code session for this state."""
        context = self._build_context(spec, ls)
        prompt = self._render_prompt(spec, context)

        # Build claude command
        # claude -p "prompt" --allowedTools "Tool1,Tool2"
        cmd = ["claude", "-p", prompt]
        if spec.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(spec.allowed_tools)])

        log(f"ENGINE: running Claude session for {spec.id}")
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
            timeout=1800,  # 30 min max per state
        )

        log(f"ENGINE: Claude session finished (exit={result.returncode})")

        if result.returncode != 0:
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-5:]:
                    log(f"ENGINE: stderr: {line}")
            # Don't fail immediately — the artifact might still have been created
            # (Claude exits non-zero on warnings like missing stdin)

        # State transition happens via hook (PostToolUse detects artifact)
        # If hook didn't advance state, check if we need to advance manually
        new_ls = load_state(self.project_dir)
        if new_ls.state == ls.state:
            # Hook didn't fire — try advancing if completion artifact exists
            self._try_advance(spec, ls)
            new_ls = load_state(self.project_dir)
            if new_ls.state == ls.state:
                # Check if artifact exists but has invalid JSON — ask Claude to fix
                if spec.completion and self._try_fix_json(spec, ls):
                    self._try_advance(spec, ls)
                    new_ls = load_state(self.project_dir)

                if new_ls.state == ls.state:
                    raise StateError(f"Claude session for {spec.id} did not produce expected artifact")

    def _handle_process(self, spec: StateSpec, ls: LoopState) -> None:
        """Handle a process state (no AI needed)."""
        # State-specific logic
        if spec.id == "PHASE_SELECT":
            self._select_phase(ls)
        elif spec.id == "PHASE_RUN":
            self._run_phase(ls)
        elif spec.id == "PHASE_EVALUATE":
            self._evaluate_phase(ls)
        elif spec.id == "PHASE_RECORD":
            self._record_phase(ls)

        # Conditional transition
        if isinstance(spec.next, dict) and spec.condition:
            next_state = resolve_condition(
                spec.condition, spec.next,
                self.project_dir, ls.current_iteration,
            )
            if next_state in ("IDEA_REFINE", "DOMAIN_RESEARCH"):
                # New iteration
                new_iter = ls.current_iteration + 1
                self._create_iteration(new_iter)
                self._carry_over(ls.current_iteration, new_iter, next_state)
                set_state(self.project_dir, next_state, current_iteration=new_iter)
            else:
                set_state(self.project_dir, next_state)
        elif isinstance(spec.next, str):
            set_state(self.project_dir, spec.next)

    def _handle_checkpoint(self, spec: StateSpec, ls: LoopState) -> None:
        """Wait for intervention or auto-approve based on autonomy mode."""
        # Check for existing intervention first
        ipath = intervention_path(self.project_dir)
        if ipath.exists():
            self._process_intervention(spec, ls, ipath)
            return

        # Autonomous mode: auto-approve immediately
        if self.workflow.autonomy.mode == "autonomous":
            log(f"ENGINE: checkpoint {spec.id} — autonomous mode, auto-approving")
            self._advance_checkpoint(spec, "approve", ls)
            return

        # Supervised mode: wait for intervention or timeout
        timeout = self.workflow.intervention.timeout_seconds
        start = time.monotonic()
        log(f"ENGINE: checkpoint {spec.id}, waiting for intervention (timeout={timeout}s)")

        while time.monotonic() - start < timeout:
            if ipath.exists():
                self._process_intervention(spec, ls, ipath)
                return
            time.sleep(5)

        log(f"ENGINE: checkpoint timeout, auto-advancing")
        self._advance_checkpoint(spec, "approve", ls)

    def _process_intervention(self, spec: StateSpec, ls: LoopState, ipath: Path) -> None:
        """Read and apply an intervention file."""
        intervention = json.loads(ipath.read_text())
        ipath.unlink()
        action = intervention.get("action", "approve")
        log(f"ENGINE: intervention received: {action}")

        if action == "skip_phase" and ls.current_phase_id:
            update_phase_status(
                self.project_dir, ls.current_iteration,
                ls.current_phase_id, "skipped",
            )
        self._advance_checkpoint(spec, action, ls)

    def _advance_checkpoint(self, spec: StateSpec, action: str, ls: LoopState) -> None:
        """Advance from checkpoint based on action."""
        if isinstance(spec.next, dict):
            next_state = spec.next.get(action, spec.next.get("approve", "DONE"))
            set_state(self.project_dir, next_state)
        elif isinstance(spec.next, str):
            set_state(self.project_dir, spec.next)

    # ------------------------------------------------------------------
    # Phase execution helpers
    # ------------------------------------------------------------------

    def _select_phase(self, ls: LoopState) -> None:
        """Pick the next pending phase from research_plan and set current_phase_id."""
        try:
            plan = load_plan(self.project_dir, ls.current_iteration)
        except Exception:
            log("ENGINE: no plan found, nothing to select")
            return

        phase = next_pending_phase(plan)
        if phase:
            phase_id = phase["id"]
            reuse = phase.get("reuse_from")
            if reuse:
                # Copy reused script, skip PHASE_CODE
                import shutil
                src = self.project_dir / "research" / reuse
                dst = phases_dir(self.project_dir, ls.current_iteration) / src.name
                if src.exists():
                    shutil.copy2(src, dst)
                    log(f"ENGINE: reusing {reuse} for {phase_id}")
            set_state(self.project_dir, ls.state, current_phase_id=phase_id)
            events.phase_started(self.project_dir, phase_id, ls.current_iteration)
            log(f"ENGINE: selected phase {phase_id} — {phase.get('name', '')}")
        else:
            set_state(self.project_dir, ls.state, current_phase_id=None)
            log("ENGINE: no pending phases")

    def _run_phase(self, ls: LoopState) -> None:
        """Execute the current phase — script or optimize type."""
        phase_id = ls.current_phase_id
        if not phase_id:
            raise StateError("PHASE_RUN but no current_phase_id")

        plan = load_plan(self.project_dir, ls.current_iteration)
        phase = next((p for p in plan["phases"] if p["id"] == phase_id), None)
        if not phase:
            raise StateError(f"Phase {phase_id} not found in plan")

        update_phase_status(self.project_dir, ls.current_iteration, phase_id, "running")

        phase_type = phase.get("type", "script")
        if phase_type == "optimize":
            self._run_phase_optimize(phase, ls)
        elif phase_type == "manual":
            log(f"ENGINE: phase {phase_id} is manual — waiting for intervention")
            # Write a marker so the intervention knows what phase is waiting
            marker = {"phase_id": phase_id, "phase_name": phase.get("name", ""), "waiting_for": "manual input"}
            (intervention_path(self.project_dir).parent / ".manual_wait.json").write_text(
                json.dumps(marker, indent=2)
            )
            # Transition to CHECKPOINT to wait for intervention
            set_state(self.project_dir, "CHECKPOINT")
            return  # Don't continue to normal PHASE_RUN transition
        else:
            self._run_phase_script(phase, ls)

    def _run_phase_script(self, phase: dict[str, Any], ls: LoopState) -> None:
        """Run a script-type phase."""
        phase_id = phase["id"]
        pdir = phases_dir(self.project_dir, ls.current_iteration)
        scripts = list(pdir.glob(f"*{phase_id}*"))
        if not scripts:
            raise StateError(f"No script found for phase {phase_id} in {pdir}")

        script = scripts[0]
        log(f"ENGINE: running {script.name}")

        rdir = results_dir(self.project_dir, ls.current_iteration)
        rdir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["python", str(script)],
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
            env={
                **__import__("os").environ,
                "TINYLAB_PHASE_ID": phase_id,
                "TINYLAB_PROJECT_DIR": str(self.project_dir),
                "TINYLAB_RESULTS_DIR": str(rdir),
                "TINYLAB_ITERATION": str(ls.current_iteration),
            },
        )

        if result.returncode != 0:
            log(f"ENGINE: phase script failed (exit={result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-10:]:
                    log(f"ENGINE: stderr: {line}")
            raise StateError(f"Phase {phase_id} script failed")

        log(f"ENGINE: phase {phase_id} script completed")

    def _run_phase_optimize(self, phase: dict[str, Any], ls: LoopState) -> None:
        """Run an optimize-type phase using the optimizer inner loop."""
        from .optimize import run_optimize

        phase_id = phase["id"]
        opt_config = phase.get("optimize", {})
        plan = load_plan(self.project_dir, ls.current_iteration)
        metric = plan.get("metric", {})
        metric_name = metric.get("name", "metric")
        direction = metric.get("direction", "minimize")

        # Find the phase script (train script)
        pdir = phases_dir(self.project_dir, ls.current_iteration)
        scripts = list(pdir.glob(f"*{phase_id}*"))
        if not scripts:
            raise StateError(f"No script found for optimize phase {phase_id}")

        base_command = f"python {scripts[0]}"

        # Get levers from plan or phase config
        levers = plan.get("levers", {})

        log(f"ENGINE: running optimize phase {phase_id} ({opt_config.get('type', 'random')})")
        result = run_optimize(
            base_command=base_command,
            phase_config=opt_config,
            metric_name=metric_name,
            direction=direction,
            project_dir=self.project_dir,
            levers=levers,
        )

        # Write results
        rdir = results_dir(self.project_dir, ls.current_iteration)
        rdir.mkdir(parents=True, exist_ok=True)
        result_data = {
            metric_name: result.best_value,
            "best_params": result.best_params,
            "n_trials": result.n_trials,
            "total_seconds": result.total_seconds,
            "all_trials": result.all_trials,
        }
        (rdir / f"{phase_id}.json").write_text(json.dumps(result_data, indent=2, default=str))
        log(f"ENGINE: optimize phase {phase_id} done — best {metric_name}={result.best_value}")

    def _evaluate_phase(self, ls: LoopState) -> None:
        """Validate phase output against plan schema."""
        phase_id = ls.current_phase_id
        if not phase_id:
            raise StateError("PHASE_EVALUATE but no current_phase_id")

        plan = load_plan(self.project_dir, ls.current_iteration)
        phase = next((p for p in plan["phases"] if p["id"] == phase_id), None)
        if not phase:
            raise StateError(f"Phase {phase_id} not found")

        expected = phase.get("expected_outputs", {})
        report_spec = expected.get("report", {})
        if not report_spec:
            log(f"ENGINE: no expected_outputs.report for {phase_id}, skipping validation")
            return

        report_path = self.project_dir / report_spec["path"]
        if not report_path.exists():
            raise StateError(f"Expected report not found: {report_path}")

        schema = report_spec.get("schema", {})
        if schema:
            data = json.loads(report_path.read_text())
            missing = [k for k in schema if k not in data]
            if missing:
                raise StateError(f"Report missing fields: {missing}")

        log(f"ENGINE: phase {phase_id} output validated")

    def _record_phase(self, ls: LoopState) -> None:
        """Mark phase as done in plan."""
        if ls.current_phase_id:
            update_phase_status(
                self.project_dir, ls.current_iteration,
                ls.current_phase_id, "done",
            )
            events.phase_completed(self.project_dir, ls.current_phase_id, ls.current_iteration, "done")
            log(f"ENGINE: phase {ls.current_phase_id} recorded as done")

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error(self, spec: StateSpec, ls: LoopState, error: Exception) -> None:
        """Handle errors based on state's error spec."""
        err = spec.error
        ls = load_state(self.project_dir)
        ls.consecutive_failures += 1
        save_state(self.project_dir, ls)

        # Circuit breaker
        if ls.consecutive_failures >= self.workflow.autonomy.max_consecutive_failures:
            log(f"ENGINE: circuit breaker ({ls.consecutive_failures} consecutive failures)")
            set_state(self.project_dir, "DONE", resumable=True)
            self._shutdown = True
            return

        if err and ls.consecutive_failures <= err.max_retries:
            retry_to = err.retry_to or spec.id
            log(f"ENGINE: retrying ({ls.consecutive_failures}/{err.max_retries}) → {retry_to}")
            set_state(self.project_dir, retry_to)
            return

        # Exhausted retries
        on_exhaust = err.on_exhaust if err else "stop"
        if on_exhaust == "skip_phase" and ls.current_phase_id:
            log(f"ENGINE: skipping phase {ls.current_phase_id}")
            update_phase_status(
                self.project_dir, ls.current_iteration,
                ls.current_phase_id, "skipped",
            )
            set_state(self.project_dir, "PHASE_SELECT", current_phase_id=None)
        elif on_exhaust == "ask":
            log(f"ENGINE: waiting for intervention after error")
            set_state(self.project_dir, "CHECKPOINT")
        else:
            log(f"ENGINE: stopping after error")
            set_state(self.project_dir, "DONE", resumable=True)
            self._shutdown = True

    # ------------------------------------------------------------------
    # Context & prompt building
    # ------------------------------------------------------------------

    def _build_context(self, spec: StateSpec, ls: LoopState) -> dict[str, Any]:
        """Build context dict for prompt template rendering."""
        ctx: dict[str, Any] = {
            "iter": f"iter_{ls.current_iteration}",
            "iteration": ls.current_iteration,
            "project_dir": str(self.project_dir),
        }

        if ls.current_phase_id:
            ctx["current_phase_id"] = ls.current_phase_id
            try:
                plan = load_plan(self.project_dir, ls.current_iteration)
                phase = next((p for p in plan["phases"] if p["id"] == ls.current_phase_id), None)
                if phase:
                    ctx["current_phase"] = phase
                    name = phase.get("name", "")
                    ctx["current_phase_name"] = name
                    ctx["current_phase_name_slug"] = name.lower().replace(" ", "_").replace("-", "_")
                    ctx["current_phase_type"] = phase.get("type", "script")
            except Exception:
                pass

        # Previous results summary
        rdir = results_dir(self.project_dir, ls.current_iteration)
        if rdir.exists():
            summaries = []
            for f in sorted(rdir.glob("*.json")):
                summaries.append(f"- {f.stem}: {f.read_text()[:200]}")
            ctx["previous_results_summary"] = "\n".join(summaries) if summaries else "(none)"
        else:
            ctx["previous_results_summary"] = "(none)"

        return ctx

    def _render_prompt(self, spec: StateSpec, context: dict[str, Any]) -> str:
        """Load and render a prompt template."""
        if not spec.prompt:
            return f"You are in state {spec.id}. Complete the required artifact."

        prompt_path = self.project_dir / spec.prompt
        if not prompt_path.exists():
            # Try relative to package
            prompt_path = Path(__file__).parent / spec.prompt
        if not prompt_path.exists():
            return f"You are in state {spec.id}. Complete the required artifact."

        template = prompt_path.read_text()
        # Safe format — missing keys stay as {key}
        class SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return f"{{{key}}}"
        return template.format_map(SafeDict(context))

    def _try_fix_json(self, spec: StateSpec, ls: LoopState) -> bool:
        """If artifact exists but is invalid JSON, ask Claude to fix it. Returns True if fixed."""
        import glob as g
        pattern = spec.completion.artifact.replace("{iter}", f"iter_{ls.current_iteration}")
        full_pattern = str(self.project_dir / pattern)
        matches = g.glob(full_pattern)
        if not matches:
            return False

        artifact_path = Path(matches[0])
        try:
            json.loads(artifact_path.read_text())
            return False  # Already valid JSON
        except json.JSONDecodeError as e:
            log(f"ENGINE: artifact {artifact_path.name} has invalid JSON: {e}")
            log(f"ENGINE: asking Claude to fix...")

            fix_prompt = (
                f"The file {artifact_path} contains invalid JSON.\n"
                f"Error: {e}\n\n"
                f"Read the file, fix the JSON syntax error, and write it back as valid JSON.\n"
                f"Do NOT change the content — only fix the syntax."
            )

            fix_result = subprocess.run(
                ["claude", "-p", fix_prompt, "--allowedTools", "Read,Write,Edit"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=120,
            )

            # Check if fixed
            try:
                json.loads(artifact_path.read_text())
                log(f"ENGINE: JSON fixed successfully")
                return True
            except json.JSONDecodeError:
                log(f"ENGINE: JSON fix attempt failed")
                return False

    def _try_advance(self, spec: StateSpec, ls: LoopState) -> None:
        """Try to advance state if completion artifact exists."""
        if not spec.completion:
            log(f"ENGINE: _try_advance — no completion spec for {spec.id}")
            return

        import glob as g
        pattern = spec.completion.artifact.replace("{iter}", f"iter_{ls.current_iteration}")
        full_pattern = str(self.project_dir / pattern)
        matches = g.glob(full_pattern)
        log(f"ENGINE: _try_advance — pattern={full_pattern}, matches={len(matches)}")
        if not matches:
            return

        # Validate required fields
        if spec.completion.required_fields:
            try:
                data = json.loads(Path(matches[0]).read_text())
            except json.JSONDecodeError:
                # AI-generated YAML may have syntax errors — advance anyway
                # since the artifact file exists (content will be consumed by next state)
                log(f"ENGINE: _try_advance — YAML parse warning in {matches[0]}, advancing anyway")
                if isinstance(spec.next, str):
                    set_state(self.project_dir, spec.next)
                    log(f"ENGINE: advanced {ls.state} → {spec.next} (with YAML warning)")
                return
            if not isinstance(data, dict):
                return
            missing = [f for f in spec.completion.required_fields if f not in data]
            if missing:
                return

        # Advance
        if isinstance(spec.next, str):
            set_state(self.project_dir, spec.next)
            log(f"ENGINE: advanced {ls.state} → {spec.next}")

    # ------------------------------------------------------------------
    # Iteration management
    # ------------------------------------------------------------------

    def _create_iteration(self, iteration: int) -> None:
        """Create iter_N directory structure."""
        idir = iter_dir(self.project_dir, iteration)
        idir.mkdir(parents=True, exist_ok=True)
        phases_dir(self.project_dir, iteration).mkdir(exist_ok=True)
        results_dir(self.project_dir, iteration).mkdir(exist_ok=True)
        log(f"ENGINE: created iteration directory {idir.name}")

    def _carry_over(self, from_iter: int, to_iter: int, entry_state: str) -> None:
        """Copy artifacts from previous iteration based on entry state."""
        import shutil
        src = iter_dir(self.project_dir, from_iter)
        dst = iter_dir(self.project_dir, to_iter)

        carry_map = {
            "DATA_DEEP_DIVE": [".domain_research.json"],
            "IDEA_REFINE": [".domain_research.json", ".data_analysis.json"],
            "PLAN": [".domain_research.json", ".data_analysis.json", ".idea_refined.json"],
        }

        files = carry_map.get(entry_state, [])
        for fname in files:
            src_file = src / fname
            if src_file.exists():
                shutil.copy2(src_file, dst / fname)
                log(f"ENGINE: carried over {fname} to iter_{to_iter}")

        # Update iterations.json
        self._update_iterations_log(from_iter)

    def _update_iterations_log(self, completed_iter: int) -> None:
        """Append completed iteration to .iterations.json."""
        from .paths import iterations_path
        ipath = iterations_path(self.project_dir)

        data = {"current_iteration": completed_iter + 1, "iterations": []}
        if ipath.exists():
            data = json.loads(ipath.read_text()) or data

        # Read reflect.json for the completed iteration
        from .paths import reflect_path
        rpath = reflect_path(self.project_dir, completed_iter)
        reflect: dict[str, Any] = {}
        if rpath.exists():
            reflect = json.loads(rpath.read_text()) or {}

        entry = {
            "id": completed_iter,
            "decision": reflect.get("decision", "unknown"),
            "reason": reflect.get("reason", ""),
        }
        data["iterations"].append(entry)
        data["current_iteration"] = completed_iter + 1
        ipath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
