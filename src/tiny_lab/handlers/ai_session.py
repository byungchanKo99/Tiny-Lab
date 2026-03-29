"""AI session handler — runs Claude Code with prompt and checks for artifacts."""
from __future__ import annotations

import glob as g
import json
import subprocess
from pathlib import Path
from typing import Any

from ..errors import StateError
from ..logging import log
from ..paths import results_dir, iter_dir
from ..plan import load_plan
from ..state import LoopState, load_state, set_state
from ..workflow import StateSpec
from . import EngineContext, StateResult


class AiSessionHandler:
    """Spawn a Claude Code session, wait for completion artifact."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        context = _build_context(spec, ls, ctx)
        prompt = _render_prompt(spec, context, ctx)

        cmd = ["claude", "-p", prompt]
        if spec.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(spec.allowed_tools)])

        log(f"ENGINE: running Claude session for {spec.id}")
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=str(ctx.project_dir),
            timeout=1800,
        )

        log(f"ENGINE: Claude session finished (exit={result.returncode})")
        if result.returncode != 0 and result.stderr:
            for line in result.stderr.strip().splitlines()[-5:]:
                log(f"ENGINE: stderr: {line}")

        # Check if hook already advanced state
        new_ls = load_state(ctx.project_dir)
        if new_ls.state != ls.state:
            return StateResult()  # already transitioned

        # Try advancing via artifact detection
        _try_advance(spec, ls, ctx)
        new_ls = load_state(ctx.project_dir)
        if new_ls.state != ls.state:
            return StateResult()

        # Try fixing invalid JSON
        if spec.completion and _try_fix_json(spec, ls, ctx):
            _try_advance(spec, ls, ctx)
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()

        raise StateError(f"Claude session for {spec.id} did not produce expected artifact")


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def _build_context(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> dict[str, Any]:
    """Build template variable dict for prompt rendering."""
    d: dict[str, Any] = {
        "iter": f"iter_{ls.current_iteration}",
        "iteration": ls.current_iteration,
        "project_dir": str(ctx.project_dir),
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
        prompt_path = Path(__file__).parent.parent / spec.prompt
    if not prompt_path.exists():
        return f"You are in state {spec.id}. Complete the required artifact."

    template = prompt_path.read_text()
    result = template
    for key, value in context.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


# ---------------------------------------------------------------------------
# Artifact detection and JSON repair
# ---------------------------------------------------------------------------


def _try_advance(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> None:
    """Advance state if completion artifact exists and validates."""
    if not spec.completion:
        return

    pattern = spec.completion.artifact.replace("{iter}", f"iter_{ls.current_iteration}")
    full_pattern = str(ctx.project_dir / pattern)
    matches = g.glob(full_pattern)
    log(f"ENGINE: _try_advance — pattern={full_pattern}, matches={len(matches)}")
    if not matches:
        return

    if spec.completion.required_fields:
        try:
            data = json.loads(Path(matches[0]).read_text())
        except json.JSONDecodeError:
            if isinstance(spec.next, str):
                set_state(ctx.project_dir, spec.next)
                log(f"ENGINE: advanced {ls.state} → {spec.next} (with JSON warning)")
            return
        if not isinstance(data, dict):
            return
        missing = [f for f in spec.completion.required_fields if f not in data]
        if missing:
            return

    if isinstance(spec.next, str):
        set_state(ctx.project_dir, spec.next)
        log(f"ENGINE: advanced {ls.state} → {spec.next}")


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
            ["claude", "-p", fix_prompt, "--allowedTools", "Read,Write,Edit"],
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
