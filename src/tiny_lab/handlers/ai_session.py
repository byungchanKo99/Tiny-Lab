"""AI session handler — runs Claude Code with prompt and checks for artifacts."""
from __future__ import annotations

import glob as g
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from ..errors import StateError
from ..logging import log
from ..paths import results_dir, iter_dir, knowledge_dir, constraints_path
from ..plan import load_plan
from ..state import LoopState, load_state, save_state, set_state
from ..workflow import StateSpec
from . import EngineContext, StateResult


class AiSessionHandler:
    """Spawn a Claude Code session, wait for completion artifact."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        context = _build_context(spec, ls, ctx)
        prompt = _render_prompt(spec, context, ctx)

        return self._run_noninteractive(spec, ls, ctx, prompt)

    def _run_noninteractive(
        self, spec: StateSpec, ls: LoopState, ctx: EngineContext, prompt: str,
    ) -> StateResult:
        """Run Claude in pipe mode (-p) — no user interaction."""
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", ctx.model]
        if spec.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(spec.allowed_tools)])

        # Session resume: reuse within iteration
        if ls.session_id:
            cmd.extend(["--resume", ls.session_id])
            log(f"ENGINE: resuming session {ls.session_id[:8]}…")
        else:
            session_id = str(uuid.uuid4())
            cmd.extend(["--session-id", session_id])
            ls.session_id = session_id
            save_state(ctx.project_dir, ls)
            log(f"ENGINE: new session {session_id[:8]}…")

        log(f"ENGINE: running Claude session for {spec.id}")
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=str(ctx.project_dir),
            timeout=1800,
        )

        # Extract session_id from JSON output (may change on resume)
        _update_session_id(result.stdout, ctx)

        log(f"ENGINE: Claude session finished (exit={result.returncode})")
        if result.returncode != 0 and result.stderr:
            for line in result.stderr.strip().splitlines()[-5:]:
                log(f"ENGINE: stderr: {line}")

        # Check if hook already advanced state
        new_ls = load_state(ctx.project_dir)
        if new_ls.state != ls.state:
            return StateResult()  # already transitioned

        # Try advancing via artifact detection
        problem = _try_advance(spec, ls, ctx)
        new_ls = load_state(ctx.project_dir)
        if new_ls.state != ls.state:
            return StateResult()

        # Try fixing invalid JSON
        if spec.completion and _try_fix_json(spec, ls, ctx):
            problem = _try_advance(spec, ls, ctx)
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()

        # Artifact exists but validation failed — ask Claude to fix it
        if problem and spec.completion:
            log(f"ENGINE: artifact validation issue: {problem}")
            if _try_fix_artifact(spec, ls, ctx, problem):
                problem = _try_advance(spec, ls, ctx)
                new_ls = load_state(ctx.project_dir)
                if new_ls.state != ls.state:
                    return StateResult()

        raise StateError(
            f"Claude session for {spec.id} did not produce expected artifact"
            + (f" ({problem})" if problem else "")
        )

    def _run_interactive(
        self, spec: StateSpec, ls: LoopState, ctx: EngineContext, prompt: str,
    ) -> StateResult:
        """Run Claude with user-in-the-loop via repeated -p calls.

        1. Send initial prompt via -p → Claude asks questions
        2. Show Claude's response to user, get user's answer
        3. Send user's answer via -p --resume → Claude continues
        4. Repeat until artifact is produced (auto-detected)

        No /exit needed — engine detects artifact and moves on.
        """
        max_rounds = 5  # max user interaction rounds

        # Ensure session exists
        if not ls.session_id:
            session_id = str(uuid.uuid4())
            ls.session_id = session_id
            save_state(ctx.project_dir, ls)
            log(f"ENGINE: interactive new session {session_id[:8]}…")

        # Round 0: send initial prompt
        current_prompt = prompt
        for round_n in range(max_rounds + 1):
            cmd = [
                "claude", "-p", current_prompt, "--output-format", "json",
                "--model", ctx.model,
            ]
            if spec.allowed_tools:
                cmd.extend(["--allowedTools", ",".join(spec.allowed_tools)])

            if round_n == 0 and not ls.phase_retries:
                cmd.extend(["--session-id", ls.session_id])
            else:
                cmd.extend(["--resume", ls.session_id])

            log(f"ENGINE: interactive round {round_n} for {spec.id}")
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                cwd=str(ctx.project_dir),
                timeout=300,
            )

            _update_session_id(result.stdout, ctx)

            # Check if artifact was created
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()  # hook advanced
            problem = _try_advance(spec, ls, ctx)
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()  # artifact found

            # Extract Claude's text response for user
            claude_text = _extract_text(result.stdout)
            if not claude_text:
                claude_text = "(Claude produced no visible output this round)"

            # Show Claude's response and ask user
            print(f"\n{'─'*60}")
            print(f"  [{spec.id}] Claude asks:")
            print(f"{'─'*60}")
            print(claude_text)
            print(f"{'─'*60}")

            if round_n >= max_rounds:
                log(f"ENGINE: max interaction rounds reached, proceeding with defaults")
                current_prompt = (
                    "The user did not respond further. "
                    "Use your best judgment based on domain research to fill in remaining gaps. "
                    "Write the constraints.json and .shaped_input.json files now."
                )
                continue

            try:
                user_input = input("  Your answer (empty = let Claude decide): ").strip()
            except (EOFError, KeyboardInterrupt):
                user_input = ""

            if not user_input:
                current_prompt = (
                    "The user accepted your suggestions. "
                    "Proceed with your proposed defaults and write the output files now."
                )
            else:
                current_prompt = f"User's answer: {user_input}"

        # Final attempt — should not reach here normally
        raise StateError(
            f"Interactive session for {spec.id} did not produce artifact after {max_rounds} rounds"
        )


def _extract_text(stdout: str) -> str:
    """Extract readable text from Claude's JSON output."""
    if not stdout:
        return ""
    try:
        data = json.loads(stdout)
        # Claude --output-format json returns {"result": "text", ...}
        return data.get("result", "")
    except json.JSONDecodeError:
        return stdout.strip()


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def _build_context(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> dict[str, Any]:
    """Build template variable dict for prompt rendering."""
    d: dict[str, Any] = {
        "iter": f"iter_{ls.current_iteration}",
        "iteration": ls.current_iteration,
        "project_dir": str(ctx.project_dir),
        "knowledge_dir": str(knowledge_dir(ctx.project_dir)),
    }

    # Phase info
    if ls.current_phase_id:
        d["current_phase_id"] = ls.current_phase_id
        try:
            plan = load_plan(ctx.project_dir, ls.current_iteration)
            phase = next((p for p in plan["phases"] if p["id"] == ls.current_phase_id), None)
            if phase:
                d["current_phase"] = phase
                name = phase.get("name", "")
                d["current_phase_name"] = name
                d["current_phase_name_slug"] = name.lower().replace(" ", "_").replace("-", "_")
                d["current_phase_type"] = phase.get("type", "script")
        except Exception:
            pass

    # File tree
    idir = ctx.project_dir / "research" / f"iter_{ls.current_iteration}"
    tree_lines: list[str] = []
    for directory in [idir, idir / "phases", idir / "results"]:
        if directory.exists():
            tree_lines.append(f"{directory.relative_to(ctx.project_dir)}/")
            for f in sorted(directory.iterdir()):
                if f.is_file():
                    tree_lines.append(f"  {f.name} ({f.stat().st_size:,} bytes)")
    shared = ctx.project_dir / "shared" / "lib"
    if shared.exists():
        tree_lines.append("shared/lib/")
        for f in sorted(shared.iterdir()):
            if f.is_file():
                tree_lines.append(f"  {f.name}")
    d["project_tree"] = "\n".join(tree_lines) if tree_lines else "(empty)"

    # Previous results
    rdir = results_dir(ctx.project_dir, ls.current_iteration)
    if rdir.exists():
        summaries = [f"- {f.stem}: {f.read_text()[:200]}" for f in sorted(rdir.glob("*.json"))]
        d["previous_results_summary"] = "\n".join(summaries) if summaries else "(none)"
    else:
        d["previous_results_summary"] = "(none)"

    # Phase error history
    error_file = ctx.project_dir / "research" / f"iter_{ls.current_iteration}" / ".phase_error.json"
    d["phase_error_summary"] = ""
    if error_file.exists():
        try:
            err_data = json.loads(error_file.read_text())
            if isinstance(err_data, dict):
                err_data = [err_data]
            parts = []
            for attempt in err_data:
                n = attempt.get("attempt", "?")
                parts.append(
                    f"--- ATTEMPT {n} FAILED ---\n"
                    f"Script: {attempt.get('script', '?')}\n"
                    f"Exit code: {attempt.get('exit_code', '?')}\n"
                    f"Stderr:\n{attempt.get('stderr', '(none)')}\n"
                    f"Stdout tail:\n{attempt.get('stdout_tail', '(none)')}\n"
                    f"Script code (first 3000 chars):\n{attempt.get('script_snippet', '(not captured)')}"
                )
            d["phase_error_summary"] = (
                f"=== EXECUTION HISTORY ({len(err_data)} failed attempts) ===\n\n"
                + "\n\n".join(parts)
            )
        except Exception:
            pass

    return d


def _render_prompt(spec: StateSpec, context: dict[str, Any], ctx: EngineContext) -> str:
    """Load and render a prompt template with manual substitution."""
    if not spec.prompt:
        return f"You are in state {spec.id}. Complete the required artifact."

    prompt_path = ctx.project_dir / spec.prompt
    if not prompt_path.exists():
        # Try _shared/ prompts directory
        prompt_path = Path(__file__).parent.parent / spec.prompt
    if not prompt_path.exists():
        return f"You are in state {spec.id}. Complete the required artifact."

    template = prompt_path.read_text()

    # Inject constraints preamble if constraints.json exists
    constraints_preamble = _load_constraints_preamble(ctx.project_dir)
    if constraints_preamble:
        template = constraints_preamble + "\n\n" + template

    result = template
    for key, value in context.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _load_constraints_preamble(project_dir: Path) -> str:
    """Load constraints.json and format as a prompt preamble."""
    cpath = constraints_path(project_dir)
    if not cpath.exists():
        return ""
    try:
        data = json.loads(cpath.read_text())
    except (json.JSONDecodeError, OSError):
        return ""

    parts = ["## Constraints (MUST NOT VIOLATE)", ""]
    if data.get("objective"):
        parts.append(f"Objective: {data['objective']}")
    goal = data.get("goal", {})
    if goal.get("success_criteria"):
        parts.append(f"Goal: {goal['success_criteria']}")
    for inv in data.get("invariants", []):
        parts.append(f"- Invariant: {inv}")
    for fb in data.get("exploration_bounds", {}).get("forbidden", []):
        parts.append(f"- Forbidden: {fb}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Artifact detection and JSON repair
# ---------------------------------------------------------------------------


def _update_session_id(stdout: str, ctx: EngineContext) -> None:
    """Extract session_id from JSON output and persist it."""
    if not stdout:
        return
    try:
        data = json.loads(stdout)
        sid = data.get("session_id")
        if sid:
            ls = load_state(ctx.project_dir)
            if ls.session_id != sid:
                ls.session_id = sid
                save_state(ctx.project_dir, ls)
    except (json.JSONDecodeError, KeyError):
        pass


def _try_advance(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> str | None:
    """Advance state if completion artifact exists and validates.

    Returns None on success, or a problem description if validation fails.
    """
    if not spec.completion:
        return None

    pattern = spec.completion.artifact.replace("{iter}", f"iter_{ls.current_iteration}")
    full_pattern = str(ctx.project_dir / pattern)
    matches = g.glob(full_pattern)
    log(f"ENGINE: _try_advance — pattern={full_pattern}, matches={len(matches)}")
    if not matches:
        return "artifact file not found"

    if spec.completion.required_fields:
        try:
            data = json.loads(Path(matches[0]).read_text())
        except json.JSONDecodeError:
            # Advance even with bad JSON — engine will retry if needed
            if isinstance(spec.next, str):
                set_state(ctx.project_dir, spec.next)
                log(f"ENGINE: advanced {ls.state} → {spec.next} (with JSON warning)")
            elif isinstance(spec.next, dict) and spec.condition:
                try:
                    from ..conditions import resolve_condition
                    nxt = resolve_condition(spec.condition, spec.next, ctx.project_dir, ls.current_iteration)
                    set_state(ctx.project_dir, nxt)
                    log(f"ENGINE: advanced {ls.state} → {nxt} (conditional, JSON warning)")
                except Exception:
                    pass
            return None
        if not isinstance(data, dict):
            return f"artifact is not a JSON object (got {type(data).__name__})"
        missing = [f for f in spec.completion.required_fields if f not in data]
        if missing:
            actual_keys = list(data.keys())
            return f"missing required fields {missing}, file has: {actual_keys}"

    if isinstance(spec.next, str):
        set_state(ctx.project_dir, spec.next)
        log(f"ENGINE: advanced {ls.state} → {spec.next}")
    elif isinstance(spec.next, dict) and spec.condition:
        # Conditional transition: resolve condition from artifact
        from ..conditions import resolve_condition
        nxt = resolve_condition(spec.condition, spec.next, ctx.project_dir, ls.current_iteration)
        set_state(ctx.project_dir, nxt)
        log(f"ENGINE: advanced {ls.state} → {nxt} (conditional)")
    return None


def _try_fix_artifact(spec: StateSpec, ls: LoopState, ctx: EngineContext, problem: str) -> bool:
    """Ask Claude to fix an artifact that has validation issues (e.g. missing fields)."""
    pattern = spec.completion.artifact.replace("{iter}", f"iter_{ls.current_iteration}")
    full_pattern = str(ctx.project_dir / pattern)
    matches = g.glob(full_pattern)
    if not matches:
        return False

    artifact_path = Path(matches[0])
    fix_prompt = (
        f"The file {artifact_path} was created but has a validation problem:\n"
        f"{problem}\n\n"
        f"Required fields: {spec.completion.required_fields}\n\n"
        f"Read the file and fix it. Common issues:\n"
        f"- 'metrics' (plural) should be 'metric' (singular) or vice versa\n"
        f"- Missing a required top-level key\n"
        f"- Key exists under a nested object instead of top level\n\n"
        f"Fix the JSON file in place. Do NOT change the content — only rename/restructure keys."
    )
    log(f"ENGINE: asking Claude to fix artifact: {problem}")

    cmd = ["claude", "-p", fix_prompt, "--allowedTools", "Read,Write,Edit", "--model", ctx.model]
    if ls.session_id:
        cmd.extend(["--resume", ls.session_id])
    subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        cwd=str(ctx.project_dir),
        timeout=120,
    )

    # Verify fix
    try:
        data = json.loads(artifact_path.read_text())
        if isinstance(data, dict):
            missing = [f for f in spec.completion.required_fields if f not in data]
            if not missing:
                log("ENGINE: artifact fix successful")
                return True
    except Exception:
        pass
    log("ENGINE: artifact fix failed")
    return False


def _try_fix_json(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> bool:
    """If artifact is invalid JSON, ask Claude to fix it."""
    pattern = spec.completion.artifact.replace("{iter}", f"iter_{ls.current_iteration}")
    full_pattern = str(ctx.project_dir / pattern)
    matches = g.glob(full_pattern)
    if not matches:
        return False

    artifact_path = Path(matches[0])
    try:
        json.loads(artifact_path.read_text())
        return False
    except json.JSONDecodeError as e:
        log(f"ENGINE: artifact {artifact_path.name} has invalid JSON: {e}")
        fix_prompt = (
            f"The file {artifact_path} contains invalid JSON.\n"
            f"Error: {e}\n\n"
            f"Read the file, fix the JSON syntax error, and write it back as valid JSON.\n"
            f"Do NOT change the content — only fix the syntax."
        )
        subprocess.run(
            ["claude", "-p", fix_prompt, "--allowedTools", "Read,Write,Edit", "--model", ctx.model],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=str(ctx.project_dir),
            timeout=120,
        )
        try:
            json.loads(artifact_path.read_text())
            log("ENGINE: JSON fixed successfully")
            return True
        except json.JSONDecodeError:
            log("ENGINE: JSON fix attempt failed")
            return False
