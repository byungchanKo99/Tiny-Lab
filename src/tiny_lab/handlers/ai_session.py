"""AI session handler — runs the configured AI backend and checks for artifacts."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any, Iterable

from ..advancement import (
    apply_state_transition,
    resolve_runner_completion_advance,
    transition_starts_new_iteration,
)
from ..backends import BackendResult, get_backend
from ..errors import BackendUnavailableError, StateError
from ..evidence import render_evidence_contract
from ..final_paper import (
    render_final_paper_evidence_ledger,
    try_write_traceable_final_paper_for_problem,
    write_artifact_backed_paper_draft,
    write_traceable_final_paper,
)
from ..gates import (
    audit_final_artifacts,
    audit_research_completion,
    final_artifact_reference_iteration,
    final_artifact_reference_iterations,
)
from ..logging import log
from ..paths import constraints_path, knowledge_dir, research_result_json_files, results_dir
from ..phase_contract import (
    PHASE_SCRIPT_CONTRACT_MARKDOWN,
    default_phase_script_path,
    phase_name_slug,
)
from ..plan import load_plan, render_plan_quality_contract, repair_plan_quality_issues, validate_plan_quality
from ..quality import render_final_paper_contract
from ..refs import render_reference_verification_contract
from ..review import (
    REQUIRED_SCORE_KEYS,
    RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA,
    render_evaluation_contract,
)
from ..runner_contract import RunnerStateContract, load_quality_preamble, resolve_runner_state_contract
from ..state import LoopState, load_state, save_state, set_state
from ..workflow import StateSpec
from . import EngineContext, StateResult


class AiSessionHandler:
    """Spawn a Claude Code session, wait for completion artifact."""

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        prompt = render_ai_session_prompt(spec, ls, ctx)

        return self._run_noninteractive(spec, ls, ctx, prompt)

    def _run_noninteractive(
        self, spec: StateSpec, ls: LoopState, ctx: EngineContext, prompt: str,
    ) -> StateResult:
        """Run the configured AI backend — no user interaction."""
        contract = _current_runner_contract(spec, ls, ctx)

        if _try_deterministic_completion_artifact(spec, ls, ctx, contract):
            problem = _try_advance(contract, ls, ctx)
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()
            if problem:
                log(f"ENGINE: deterministic artifact failed validation: {problem}")

        # A previous native-runner hook or interrupted engine run may already
        # have written a valid completion artifact. Use the shared resolver
        # rather than a raw glob so phase-script naming cannot drift.
        if not (spec.id == "PHASE_CODE" and ls.phase_retries > 0):
            problem = _try_advance(contract, ls, ctx, ignore_missing=True)
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()
            if problem and contract.completion_artifact:
                if _try_fix_json(contract, ls, ctx):
                    problem = _try_advance(contract, ls, ctx)
                    new_ls = load_state(ctx.project_dir)
                    if new_ls.state != ls.state:
                        return StateResult()
                log(f"ENGINE: artifact validation issue: {problem}")
                if _try_fix_artifact(contract, ls, ctx, problem):
                    _try_advance(contract, ls, ctx)
                    new_ls = load_state(ctx.project_dir)
                    if new_ls.state != ls.state:
                        return StateResult()

        backend_name = contract.intended_engine
        backend = get_backend(backend_name)

        supports_resume = bool(getattr(backend, "supports_resume", True))
        if ls.session_id and supports_resume:
            log(f"ENGINE: resuming {backend.name} session {ls.session_id[:8]}…")
        elif ls.session_id:
            log(
                f"ENGINE: starting stateless {backend.name} session; "
                f"previous id {ls.session_id[:8]} is informational"
            )
        else:
            log(f"ENGINE: new {backend.name} session for {spec.id}")

        timeout = _backend_timeout_seconds(spec, ctx)
        attempt = 0
        current_prompt = prompt
        previous_failure_reason = _logged_previous_backend_failure_reason(ctx.project_dir, spec.id)
        if previous_failure_reason:
            current_prompt = _accelerated_retry_prompt(prompt, spec.id, previous_failure_reason)
            attempt = 1
            log(f"ENGINE: using accelerated prompt for {spec.id} after previous backend failure")
        last_result: BackendResult | None = None
        last_problem: str | None = None

        while attempt < 2:
            if attempt == 0:
                log(f"ENGINE: running {backend.name} session for {spec.id}")
            else:
                log(f"ENGINE: retrying {backend.name} session for {spec.id} with accelerated prompt")
            result = backend.invoke(
                current_prompt,
                cwd=ctx.project_dir,
                model=ctx.model if backend.name == "claude" else None,
                allowed_tools=list(contract.allowed_tools) or None,
                session_id=ls.session_id if supports_resume else None,
                timeout=timeout,
            )
            last_result = result

            # Persist resolved session id only after successful invocations. Some
            # backends include session-shaped ids in error envelopes.
            if result.exit_code == 0 and result.session_id and result.session_id != ls.session_id:
                ls.session_id = result.session_id
                save_state(ctx.project_dir, ls)

            log(f"ENGINE: {backend.name} session finished (exit={result.exit_code})")
            if result.exit_code != 0:
                for line in _backend_error_lines(result)[-5:]:
                    log(f"ENGINE: backend error: {line}")
                if ls.session_id and _backend_lost_session(result):
                    ls.session_id = None
                    save_state(ctx.project_dir, ls)
                    log(f"ENGINE: cleared stale {backend.name} session id")

            # Check if hook already advanced state.
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()

            # Try artifact detection before classifying backend failure. Slow
            # CLI clients can time out after writing a valid artifact.
            problem = _try_advance(contract, ls, ctx)
            last_problem = problem
            new_ls = load_state(ctx.project_dir)
            if new_ls.state != ls.state:
                return StateResult()

            if result.exit_code != 0:
                unavailable_reason = _backend_unavailable_reason(result)
                retry_reason = _accelerated_retry_reason(result, problem=None)
                if attempt == 0 and retry_reason:
                    current_prompt = _accelerated_retry_prompt(prompt, spec.id, retry_reason)
                    attempt += 1
                    continue
                if unavailable_reason:
                    raise BackendUnavailableError(
                        f"{backend.name} backend is unavailable for {spec.id}: {unavailable_reason}"
                    )
                message = _backend_error_summary(result)
                if attempt == 0:
                    current_prompt = _accelerated_retry_prompt(
                        prompt,
                        spec.id,
                        message or f"backend exited with code {result.exit_code}",
                    )
                    attempt += 1
                    continue
                raise StateError(
                    f"{backend.name} session for {spec.id} failed with exit code {result.exit_code}"
                    + (f": {message}" if message else "")
                )

            # Try fixing invalid JSON.
            if contract.completion_artifact and _try_fix_json(contract, ls, ctx):
                problem = _try_advance(contract, ls, ctx)
                last_problem = problem
                new_ls = load_state(ctx.project_dir)
                if new_ls.state != ls.state:
                    return StateResult()

            # Artifact exists but validation failed — ask backend to fix it.
            if problem and contract.completion_artifact:
                log(f"ENGINE: artifact validation issue: {problem}")
                if _try_fix_artifact(contract, ls, ctx, problem):
                    problem = _try_advance(contract, ls, ctx)
                    last_problem = problem
                    new_ls = load_state(ctx.project_dir)
                    if new_ls.state != ls.state:
                        return StateResult()

            if attempt == 0:
                current_prompt = _accelerated_retry_prompt(
                    prompt,
                    spec.id,
                    problem or "expected completion artifact was not produced",
                )
                attempt += 1
                continue
            break

        message = _backend_error_summary(last_result) if last_result else ""
        if last_result and last_result.exit_code != 0:
            raise StateError(
                f"{backend.name} session for {spec.id} failed with exit code {last_result.exit_code}"
                + (f": {message}" if message else "")
            )

        raise StateError(
            f"{backend.name} session for {spec.id} did not produce expected artifact"
            + (f" ({last_problem})" if last_problem else "")
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
        contract = _current_runner_contract(spec, ls, ctx)

        # Round 0: send initial prompt
        current_prompt = prompt
        for round_n in range(max_rounds + 1):
            cmd = [
                "claude", "-p", "--input-format", "text", "--output-format", "json",
                "--model", ctx.model,
            ]
            if contract.allowed_tools:
                cmd.extend(["--allowedTools", ",".join(contract.allowed_tools)])

            if round_n == 0 and not ls.phase_retries:
                cmd.extend(["--session-id", ls.session_id])
            else:
                cmd.extend(["--resume", ls.session_id])

            log(f"ENGINE: interactive round {round_n} for {spec.id}")
            result = subprocess.run(
                cmd,
                input=current_prompt,
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
            problem = _try_advance(contract, ls, ctx)
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


def render_ai_session_prompt(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> str:
    """Render the exact prompt used by engine-backed AI session states."""
    context = _build_context(spec, ls, ctx)
    return _render_prompt(spec, context, ctx)


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
    context_iteration = _prompt_context_iteration(spec, ls, ctx)
    iter_label = f"iter_{context_iteration}"
    d: dict[str, Any] = {
        "iter": iter_label,
        "iteration": context_iteration,
        "state_iteration": ls.current_iteration,
        "target_iter": iter_label,
        "target_iteration": context_iteration,
        "project_dir": str(ctx.project_dir),
        "knowledge_dir": str(knowledge_dir(ctx.project_dir)),
        "phase_script_contract": PHASE_SCRIPT_CONTRACT_MARKDOWN.strip(),
        "plan_quality_contract": render_plan_quality_contract(),
        "evidence_contract": render_evidence_contract(),
        "reference_verification_contract": render_reference_verification_contract(),
        "final_paper_contract": render_final_paper_contract(),
        "final_paper_evidence_ledger": _final_paper_evidence_ledger(spec, ctx, ls.current_iteration),
        "evaluation_contract": render_evaluation_contract(),
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
                d["current_phase_name_slug"] = phase_name_slug(name)
                d["phase_script_path"] = default_phase_script_path(iter_label, ls.current_phase_id, name)
                d["current_phase_type"] = phase.get("type", "script")
        except Exception:
            pass

    # File tree
    idir = ctx.project_dir / "research" / iter_label
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
    rdir = results_dir(ctx.project_dir, context_iteration)
    if rdir.exists():
        summaries = [
            f"- {f.stem}: {f.read_text()[:200]}"
            for f in _canonical_previous_result_files(ctx.project_dir, context_iteration)
        ]
        d["previous_results_summary"] = "\n".join(summaries) if summaries else "(none)"
    else:
        d["previous_results_summary"] = "(none)"

    d["review_feedback_summary"] = _load_review_feedback_summary(ctx.project_dir)

    # Phase error history
    error_file = ctx.project_dir / "research" / iter_label / ".phase_error.json"
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


def _canonical_previous_result_files(project_dir: Path, iteration: int) -> list[Path]:
    """Return previous result JSONs without duplicate phase aliases."""
    rdir = results_dir(project_dir, iteration)
    files = sorted(rdir.glob("*.json")) if rdir.exists() else []
    try:
        plan = load_plan(project_dir, iteration)
    except Exception:
        return files
    canonical: set[str] = set()
    for phase in plan.get("phases", []):
        if not isinstance(phase, dict):
            continue
        report = phase.get("expected_outputs", {}).get("report", {})
        if isinstance(report, dict) and isinstance(report.get("path"), str):
            canonical.add(report["path"].replace("{iter}", f"iter_{iteration}"))
    if not canonical:
        return files
    filtered: list[Path] = []
    for path in files:
        rel = path.relative_to(project_dir).as_posix()
        if path.name.startswith("phase_") and rel not in canonical:
            continue
        filtered.append(path)
    return filtered


def _prompt_context_iteration(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> int:
    """Return the completed iteration that an AI prompt should inspect."""
    if spec.id == "STORY_TELL":
        return final_artifact_reference_iteration(ctx.project_dir, ls.current_iteration)
    return ls.current_iteration


def _final_paper_evidence_ledger(spec: StateSpec, ctx: EngineContext, state_iteration: int) -> str:
    if spec.id != "STORY_TELL":
        return ""
    return render_final_paper_evidence_ledger(
        ctx.project_dir,
        final_artifact_reference_iterations(ctx.project_dir, state_iteration),
    )


def _load_review_feedback_summary(project_dir: Path) -> str:
    """Format previous professor feedback for revision/restart states."""
    path = project_dir / "research" / "evaluation.json"
    if not path.exists():
        return "(none)"
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"(could not read research/evaluation.json: {e})"
    if not isinstance(data, dict):
        return "(research/evaluation.json is not an object)"

    lines = ["Previous evaluation feedback from research/evaluation.json:"]
    verdict = data.get("verdict")
    if verdict:
        lines.append(f"- Verdict: {verdict}")
    summary = data.get("summary")
    if summary:
        lines.append(f"- Summary: {summary}")
    for key, label in (
        ("required_actions", "Required actions"),
        ("weaknesses", "Weaknesses"),
    ):
        values = data.get(key)
        if isinstance(values, list) and values:
            lines.append(f"- {label}:")
            lines.extend(f"  - {value}" for value in values if isinstance(value, str) and value.strip())

    feedback = data.get("feedback")
    if isinstance(feedback, list) and feedback:
        lines.append("- Criterion feedback:")
        for item in feedback:
            if not isinstance(item, dict):
                continue
            criterion = item.get("criterion", "unknown")
            issue = item.get("issue", "")
            suggestion = item.get("suggestion", "")
            lines.append(f"  - {criterion}: {issue} Suggestion: {suggestion}".strip())
    return "\n".join(lines)


def _render_prompt(spec: StateSpec, context: dict[str, Any], ctx: EngineContext) -> str:
    """Load and render a prompt template with manual substitution."""
    if not spec.prompt:
        template = f"You are in state {spec.id}. Complete the required artifact."
    else:
        prompt_path = ctx.project_dir / spec.prompt
        if not prompt_path.exists():
            # Try package prompt directory.
            prompt_path = Path(__file__).parent.parent / spec.prompt
        if not prompt_path.exists():
            template = f"You are in state {spec.id}. Complete the required artifact."
        else:
            template = prompt_path.read_text()

    preambles = []
    quality_preamble = load_quality_preamble(ctx.project_dir)
    if quality_preamble:
        preambles.append(quality_preamble)

    # Inject constraints preamble if constraints.json exists
    constraints_preamble = _load_constraints_preamble(ctx.project_dir)
    if constraints_preamble:
        preambles.append(constraints_preamble)
    if preambles:
        template = "\n\n".join(preambles + [template])

    render_context = {
        "phase_script_contract": PHASE_SCRIPT_CONTRACT_MARKDOWN.strip(),
        "plan_quality_contract": render_plan_quality_contract(),
        "evidence_contract": render_evidence_contract(),
        "reference_verification_contract": render_reference_verification_contract(),
        "final_paper_contract": render_final_paper_contract(),
        "evaluation_contract": render_evaluation_contract(),
        **context,
    }
    result = template
    for key, value in render_context.items():
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
    from ..constraints import constraints_validation_issues

    if constraints_validation_issues(data):
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


def _backend_error_lines(result: BackendResult) -> list[str]:
    stderr = result.stderr.strip()
    if stderr:
        return stderr.splitlines()

    message = _backend_error_summary(result)
    if message:
        return [message]

    stdout = result.stdout.strip()
    if stdout:
        return stdout.splitlines()
    return []


def _backend_timeout_seconds(spec: StateSpec, ctx: EngineContext) -> float:
    if ctx.backend_timeout_seconds is not None:
        return float(ctx.backend_timeout_seconds)
    if spec.timeout_seconds is not None:
        return float(spec.timeout_seconds)
    return 1800.0


def _backend_error_summary(result: BackendResult) -> str:
    stderr = result.stderr.strip()
    if stderr:
        return stderr.splitlines()[-1]

    stdout = result.stdout.strip()
    if not stdout:
        return ""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.splitlines()[-1]
    if not isinstance(data, dict):
        return ""

    for key in ("result", "error", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _backend_lost_session(result: BackendResult) -> bool:
    text = f"{result.stderr}\n{result.stdout}".lower()
    return "no conversation found" in text or "session not found" in text


def _backend_unavailable_reason(result: BackendResult) -> str:
    text = f"{result.stderr}\n{result.stdout}".lower()
    unavailable_markers = (
        "not logged in",
        "please run /login",
        "login required",
        "not authenticated",
        "authentication required",
        "api key",
        "backend command not found",
        "backend command timed out",
        "timed out after",
        "no such file or directory",
        "not inside a trusted directory",
        "skip-git-repo-check",
        "out of extra usage",
        "usage limit",
        "rate limit",
        "rate_limit",
        "quota",
        "too many requests",
    )
    if not any(marker in text for marker in unavailable_markers):
        return ""
    return _backend_error_summary(result) or "backend command is unavailable"


def _accelerated_retry_reason(result: BackendResult, problem: str | None) -> str:
    text = f"{result.stderr}\n{result.stdout}".lower()
    if result.exit_code == 124:
        return "the previous backend attempt reached its hard timeout"
    if "backend command timed out" in text or "timed out after" in text:
        return "the previous backend attempt reached its hard timeout"
    unavailable = _backend_unavailable_reason(result)
    if unavailable:
        return ""
    if result.exit_code != 0:
        return _backend_error_summary(result) or f"backend exited with code {result.exit_code}"
    return problem or ""


def _accelerated_retry_prompt(prompt: str, state_id: str, reason: str) -> str:
    return (
        prompt.rstrip()
        + "\n\n"
        + "## Accelerated retry instructions\n\n"
        + f"The previous attempt for state `{state_id}` failed: {reason}.\n"
        + "Think faster. Do not perform broad exploration, wait for perfect certainty, "
        + "or narrate your reasoning. Read only the files required for this state, make "
        + "the smallest conservative evidence-backed decision, write the required "
        + "completion artifact immediately, validate its schema, and stop.\n"
    )


def _logged_previous_backend_failure_reason(project_dir: Path, state_id: str) -> str:
    path = project_dir / "research" / "loop.log"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return ""
    if not lines:
        return ""

    lines = lines[-1000:]
    enter_marker = f"ENGINE: entering {state_id} "
    all_enter_indices = [
        idx for idx, line in enumerate(lines)
        if "ENGINE: entering " in line
    ]
    target_starts = [idx for idx in all_enter_indices if enter_marker in lines[idx]]
    if not target_starts:
        segments = [lines]
    else:
        segments = []
        for start in reversed(target_starts[-2:]):
            following_enters = [idx for idx in all_enter_indices if idx > start]
            end = following_enters[0] if following_enters else len(lines)
            segments.append(lines[start:end])

    if not segments:
        segments.append(lines)

    for segment in segments:
        reason = _backend_failure_reason_from_log_segment(segment, state_id)
        if reason:
            return reason
    return ""


def _backend_failure_reason_from_log_segment(lines: list[str], state_id: str) -> str:
    failure_idx = -1
    reason = ""
    for idx, line in enumerate(lines):
        if f"ENGINE: backend unavailable in {state_id}:" in line:
            failure_idx = idx
            reason = line.split(f"ENGINE: backend unavailable in {state_id}:", 1)[-1].strip()
        elif "ENGINE: backend error:" in line and "timed out" in line.lower():
            failure_idx = idx
            reason = line.split("ENGINE: backend error:", 1)[-1].strip()
        elif "session finished (exit=124)" in line:
            failure_idx = idx
            reason = "the previous backend attempt reached its hard timeout"
    if failure_idx < 0:
        return ""
    if any(f"ENGINE: advanced {state_id} " in line for line in lines[failure_idx + 1:]):
        return ""
    return reason


def _update_session_id(stdout: str, ctx: EngineContext) -> None:
    """Extract session_id from JSON output and persist it."""
    if not stdout:
        return
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and data.get("is_error"):
            return
        sid = data.get("session_id")
        if sid:
            ls = load_state(ctx.project_dir)
            if ls.session_id != sid:
                ls.session_id = sid
                save_state(ctx.project_dir, ls)
    except (json.JSONDecodeError, KeyError):
        pass


def _current_runner_contract(spec: StateSpec, ls: LoopState, ctx: EngineContext) -> RunnerStateContract:
    """Resolve the current AI-session contract from the runner SSOT."""
    return resolve_runner_state_contract(
        state_id=spec.id,
        iteration=ls.current_iteration,
        current_phase_id=ls.current_phase_id,
        spec=spec,
        default_engine=ctx.engine,
    )


def _completion_artifact_matches(project_dir: Path, contract: RunnerStateContract) -> list[str]:
    if not contract.completion_artifact:
        return []
    advance = resolve_runner_completion_advance(project_dir, contract)
    return [str(path) for path in advance.matches]


def _raw_completion_artifact_matches(project_dir: Path, contract: RunnerStateContract) -> list[Path]:
    """Return existing completion artifacts without running quality gates."""
    if not contract.completion_artifact:
        return []
    artifact_pattern = Path(contract.completion_artifact)
    if artifact_pattern.is_absolute():
        root = artifact_pattern
    else:
        root = project_dir / artifact_pattern
    pattern = root.as_posix()
    if any(ch in pattern for ch in "*?["):
        return sorted(path for path in project_dir.glob(contract.completion_artifact) if path.is_file())
    return [root] if root.is_file() else []


def _try_advance(
    contract_or_spec: RunnerStateContract | StateSpec,
    ls: LoopState,
    ctx: EngineContext,
    *,
    ignore_missing: bool = False,
) -> str | None:
    """Advance state if completion artifact exists and validates.

    Returns None on success, or a problem description if validation fails.
    """
    contract = (
        contract_or_spec
        if isinstance(contract_or_spec, RunnerStateContract)
        else _current_runner_contract(contract_or_spec, ls, ctx)
    )
    advance = resolve_runner_completion_advance(ctx.project_dir, contract)
    if not advance.relevant:
        return None
    if ignore_missing and not advance.matches and advance.problem == "artifact file not found":
        return None
    log(f"ENGINE: _try_advance — pattern={advance.pattern}, matches={len(advance.matches)}")
    if advance.problem:
        return advance.problem
    _verify_reference_sidecars(advance.matches, ctx)
    if advance.next_state:
        apply_state_transition(
            ctx.project_dir,
            advance.next_state,
            current_state=ls,
            new_iteration_on_entry=transition_starts_new_iteration(contract.state, advance.next_state),
        )
        suffix = " (conditional)" if isinstance(contract.next, dict) else ""
        log(f"ENGINE: advanced {contract.state} → {advance.next_state}{suffix}")
    return None


def _verify_reference_sidecars(matches: Iterable[Path], ctx: EngineContext) -> None:
    """Best-effort reference verification for CLI-engine artifact writes."""
    try:
        from ..refs import (
            is_reference_artifact_candidate_path,
            verify_file,
            write_verification,
        )
    except ImportError:
        return

    for artifact_path in matches:
        artifact = Path(artifact_path)
        if not is_reference_artifact_candidate_path(artifact):
            continue
        try:
            result = verify_file(artifact)
        except Exception as e:
            log(f"ENGINE: reference verification skipped for {artifact.name}: {e}")
            continue
        if result.total <= 0:
            continue
        try:
            out = write_verification(artifact, result)
        except Exception as e:
            log(f"ENGINE: reference verification write failed for {artifact.name}: {e}")
            continue
        try:
            rel = out.relative_to(ctx.project_dir)
        except ValueError:
            rel = out
        log(f"ENGINE: reference verification wrote {rel}")


def _try_fix_artifact(contract: RunnerStateContract, ls: LoopState, ctx: EngineContext, problem: str) -> bool:
    """Repair an artifact that has validation issues (e.g. missing fields)."""
    for artifact_path in _raw_completion_artifact_matches(ctx.project_dir, contract):
        if _try_traceable_final_paper_fallback(artifact_path, contract, ctx, problem):
            return True

    matches = _completion_artifact_matches(ctx.project_dir, contract)
    if not matches:
        return False

    artifact_path = Path(matches[0])

    if _try_traceable_final_paper_fallback(artifact_path, contract, ctx, problem):
        return True
    if _try_plan_quality_fallback(artifact_path, contract, ctx, problem):
        return True

    fix_prompt = _artifact_fix_prompt(artifact_path, contract, problem, ctx.project_dir)
    result = _invoke_artifact_fix_backend(contract, ls, ctx, fix_prompt, artifact_path, problem)
    if result.exit_code != 0:
        if _artifact_now_valid(contract, ctx):
            log("ENGINE: artifact fix produced valid artifact despite backend error")
            return True
        return False

    # Verify fix
    if _artifact_now_valid(contract, ctx):
        log("ENGINE: artifact fix successful")
        return True
    log("ENGINE: artifact fix failed")
    if _try_traceable_final_paper_fallback(artifact_path, contract, ctx, problem):
        return True
    if _try_plan_quality_fallback(artifact_path, contract, ctx, problem):
        return True
    return False


def _artifact_now_valid(contract: RunnerStateContract, ctx: EngineContext) -> bool:
    advance = resolve_runner_completion_advance(ctx.project_dir, contract)
    return bool(advance.relevant and not advance.problem)


def _invoke_artifact_fix_backend(
    contract: RunnerStateContract,
    ls: LoopState,
    ctx: EngineContext,
    prompt: str,
    artifact_path: Path,
    problem: str,
) -> BackendResult:
    backend = get_backend(contract.intended_engine)
    timeout = _artifact_fix_timeout_seconds(ctx, artifact_path, backend_name=backend.name)
    log(f"ENGINE: asking {backend.name} to fix artifact: {problem}")
    result = backend.invoke(
        prompt,
        cwd=ctx.project_dir,
        model=ctx.model if backend.name == "claude" else None,
        allowed_tools=["Read", "Write", "Edit"],
        session_id=ls.session_id,
        timeout=timeout,
    )
    if result.exit_code == 0 and result.session_id and result.session_id != ls.session_id:
        ls.session_id = result.session_id
        save_state(ctx.project_dir, ls)
    if result.exit_code == 124:
        log(f"ENGINE: artifact fix timed out after {timeout:g}s")
    elif result.exit_code != 0:
        for line in _backend_error_lines(result)[-5:]:
            log(f"ENGINE: artifact fix backend error: {line}")
    return result


def _try_traceable_final_paper_fallback(
    artifact_path: Path,
    contract: RunnerStateContract,
    ctx: EngineContext,
    problem: str,
) -> bool:
    if artifact_path.name != "final_paper.md":
        return False
    try:
        if not try_write_traceable_final_paper_for_problem(ctx.project_dir, contract.iteration, problem):
            return False
    except Exception as e:
        log(f"ENGINE: traceable final paper fallback failed to write: {e}")
        return False
    advance = resolve_runner_completion_advance(ctx.project_dir, contract)
    if advance.relevant and not advance.problem:
        log("ENGINE: traceable final paper fallback successful")
        return True
    log(f"ENGINE: traceable final paper fallback failed validation: {advance.problem}")
    return False


def _try_plan_quality_fallback(
    artifact_path: Path,
    contract: RunnerStateContract,
    ctx: EngineContext,
    problem: str,
) -> bool:
    if artifact_path.name != "research_plan.json":
        return False
    if "research plan quality issues" not in problem:
        return False
    try:
        data = json.loads(artifact_path.read_text())
    except Exception as e:
        log(f"ENGINE: plan quality fallback could not read plan: {e}")
        return False
    if not isinstance(data, dict):
        return False
    if not repair_plan_quality_issues(data, contract.iteration):
        return False
    try:
        artifact_path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError as e:
        log(f"ENGINE: plan quality fallback could not write plan: {e}")
        return False
    advance = resolve_runner_completion_advance(ctx.project_dir, contract)
    if advance.relevant and not advance.problem:
        log("ENGINE: plan quality fallback successful")
        return True
    log(f"ENGINE: plan quality fallback failed validation: {advance.problem}")
    return False


def _try_deterministic_completion_artifact(
    spec: StateSpec,
    ls: LoopState,
    ctx: EngineContext,
    contract: RunnerStateContract,
) -> bool:
    if spec.id == "PAPER_DRAFT":
        return _try_write_deterministic_paper_draft(ls, ctx)
    if spec.id == "REFLECT":
        return _try_write_deterministic_reflection(ls, ctx)
    if spec.id == "STORY_TELL":
        return _try_write_deterministic_final_paper(ls, ctx)
    if spec.id == "REVIEW":
        return _try_write_deterministic_review(ls, ctx)
    if spec.id != "VALIDATE_PLAN":
        return False
    artifact = ctx.project_dir / "research" / f"iter_{ls.current_iteration}" / ".plan_validation.json"
    if artifact.exists():
        return False
    try:
        plan = load_plan(ctx.project_dir, ls.current_iteration)
    except Exception as e:
        log(f"ENGINE: deterministic plan validation skipped: {e}")
        return False
    issues = validate_plan_quality(plan, ls.current_iteration)
    if issues:
        return False
    payload = {
        "verdict": "APPROVE",
        "checks": {
            "shared_plan_quality_contract": "pass",
            "deterministic_validator": "pass",
        },
        "issues": [],
        "required_fixes": [],
        "approval_rationale": {
            "shared_plan_quality_contract": (
                "tiny_lab.plan.validate_plan_quality returned no blocking issues."
            )
        },
    }
    artifact.write_text(json.dumps(payload, indent=2) + "\n")
    log("ENGINE: deterministic plan validation artifact written")
    return True


def _try_write_deterministic_paper_draft(ls: LoopState, ctx: EngineContext) -> bool:
    artifact = ctx.project_dir / "research" / f"iter_{ls.current_iteration}" / "paper_draft.md"
    if artifact.exists():
        return False
    if not research_result_json_files(ctx.project_dir, ls.current_iteration):
        return False
    try:
        write_artifact_backed_paper_draft(ctx.project_dir, ls.current_iteration)
    except Exception as e:
        log(f"ENGINE: deterministic paper draft skipped: {e}")
        return False
    log("ENGINE: deterministic paper draft artifact written")
    return True


def _try_write_deterministic_reflection(ls: LoopState, ctx: EngineContext) -> bool:
    artifact = ctx.project_dir / "research" / f"iter_{ls.current_iteration}" / "reflect.json"
    if artifact.exists():
        return False
    result_paths = _relative_result_json_paths(ctx.project_dir, (ls.current_iteration,))
    if not result_paths:
        return False

    max_iterations = ctx.workflow.autonomy.max_iterations
    continue_research = ls.current_iteration < max_iterations
    decision = "idea_mutation" if continue_research else "done"
    best_path = result_paths[0]
    payload: dict[str, Any] = {
        "decision": decision,
        "reason": (
            f"Deterministic reflection used saved result artifacts for iter_{ls.current_iteration}. "
            + (
                f"The configured max_iterations budget ({max_iterations}) is not exhausted, so the next "
                "iteration should deepen the artifact-backed direction."
                if continue_research
                else f"The configured max_iterations budget ({max_iterations}) has been reached, so the run should synthesize."
            )
        ),
        "best_result": {
            "phase_id": Path(best_path).stem,
            "metric_value": None,
            "config": "see saved result artifact",
            "artifact": best_path,
        },
        "diagnosis": [{
            "gap": "deterministic reflection did not infer unsupported root causes",
            "root_cause": "requires human or model interpretation beyond saved artifacts",
            "evidence": best_path,
            "suggested_fix": "add targeted follow-up phases only when within the configured iteration budget",
        }],
        "missing_experiments": (
            ["Add robustness, external validation, or deeper error-analysis phases if not already present."]
            if continue_research
            else []
        ),
        "contributions": [
            f"Artifact-backed empirical record captured in {best_path}.",
            "Traceability was preserved by basing reflection on saved result files.",
        ],
        "delta_from_previous_iter": "new_track" if ls.current_iteration == 1 else "deepened",
        "delta_evidence": f"Completed result artifact {best_path} is available for iteration synthesis.",
        "delta_trigger": "internal",
        "max_iterations": max_iterations,
    }
    if continue_research:
        portfolio = _deterministic_idea_portfolio(ls.current_iteration, best_path)
        selected = max(portfolio, key=lambda item: float(item.get("score", 0)))
        next_idea = str(selected["direction"])
        payload["idea_portfolio"] = portfolio
        payload["selected_direction"] = {
            "direction": next_idea,
            "reason": selected["rationale"],
            "evidence": selected["evidence"],
            "selection_rule": "highest deterministic expected_information_gain-adjusted score",
            "score": selected["score"],
        }
        payload["selection_rationale"] = (
            "Selected the candidate with the strongest balance of information gain, feasibility, "
            "and novelty while keeping artifact cost bounded."
        )
        payload["new_idea"] = next_idea
        payload["future_iteration_seeds"] = [{
            "status": "promote_next",
            "direction": next_idea,
            "idea": next_idea,
            "reason": selected["rationale"],
            "evidence": selected["evidence"],
            "score": selected["score"],
        }]
    else:
        payload["future_iteration_seeds"] = []

    try:
        artifact.write_text(json.dumps(payload, indent=2) + "\n")
    except OSError as e:
        log(f"ENGINE: deterministic reflection skipped: {e}")
        return False
    log("ENGINE: deterministic reflection artifact written")
    return True


def _deterministic_idea_portfolio(iteration: int, best_path: str) -> list[dict[str, Any]]:
    """Build a conservative follow-up idea portfolio from saved artifacts."""
    return [
        {
            "direction": (
                f"Stress-test iter_{iteration} conclusions with controlled robustness checks "
                f"grounded in {best_path}."
            ),
            "rationale": "Robustness checks can falsify whether the current result survives seeds, splits, and perturbations.",
            "evidence": best_path,
            "scores": {
                "novelty": 3,
                "feasibility": 5,
                "expected_information_gain": 4,
                "risk": 2,
                "artifact_cost": 2,
            },
            "score": 18,
            "status": "promote_next",
        },
        {
            "direction": (
                f"Run targeted error-slice analysis to explain where the strongest iter_{iteration} result fails."
            ),
            "rationale": "Error slices turn aggregate metrics into mechanistic hypotheses for the next phase plan.",
            "evidence": best_path,
            "scores": {
                "novelty": 3,
                "feasibility": 4,
                "expected_information_gain": 5,
                "risk": 2,
                "artifact_cost": 3,
            },
            "score": 17,
            "status": "defer",
        },
        {
            "direction": (
                f"Pivot to cross-dataset or held-out generalization for the iter_{iteration} hypothesis."
            ),
            "rationale": "A generalization check reveals whether the current finding is dataset-specific or transferable.",
            "evidence": best_path,
            "scores": {
                "novelty": 4,
                "feasibility": 3,
                "expected_information_gain": 5,
                "risk": 3,
                "artifact_cost": 4,
            },
            "score": 15,
            "status": "defer",
        },
    ]


def _try_write_deterministic_final_paper(ls: LoopState, ctx: EngineContext) -> bool:
    artifact = ctx.project_dir / "research" / "final_paper.md"
    if artifact.exists():
        return False
    reference_iterations = final_artifact_reference_iterations(ctx.project_dir, ls.current_iteration)
    if not _relative_result_json_paths(ctx.project_dir, reference_iterations):
        return False
    try:
        write_traceable_final_paper(ctx.project_dir, reference_iterations)
    except Exception as e:
        log(f"ENGINE: deterministic final paper skipped: {e}")
        return False
    log("ENGINE: deterministic final paper artifact written")
    return True


def _try_write_deterministic_review(ls: LoopState, ctx: EngineContext) -> bool:
    artifact = ctx.project_dir / "research" / "evaluation.json"
    if artifact.exists():
        return False
    reference_iterations = final_artifact_reference_iterations(ctx.project_dir, ls.current_iteration)
    result_paths = _relative_result_json_paths(ctx.project_dir, reference_iterations)
    if not result_paths:
        return False

    final_audit = audit_final_artifacts(
        ctx.project_dir,
        reference_iterations=reference_iterations,
        require_final_paper=True,
    )
    completion_issues = audit_research_completion(
        ctx.project_dir,
        max(reference_iterations),
        iterations=reference_iterations,
    )
    if (
        final_audit.paper_issues
        or final_audit.claim_issues
        or final_audit.reference_issues
        or final_audit.evaluation_issues
        or completion_issues
    ):
        return False

    result_citation = result_paths[0]
    scores = {key: 8 for key in REQUIRED_SCORE_KEYS}
    payload = {
        "verdict": "ACCEPT",
        "scores": scores,
        "total": sum(scores.values()),
        "summary": (
            "Deterministic audit accepted the run because final-paper, claim, "
            "reference, and research-completion gates passed."
        ),
        "feedback": [
            {
                "criterion": criterion,
                "score": score,
                "recommendation": (
                    f"Artifact-backed {criterion.replace('_', ' ')} evidence is traceable through "
                    f"{result_citation if criterion in RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA else 'research/final_paper.md'}."
                ),
            }
            for criterion, score in scores.items()
        ],
        "required_actions": [],
    }
    try:
        artifact.write_text(json.dumps(payload, indent=2) + "\n")
    except OSError as e:
        log(f"ENGINE: deterministic review skipped: {e}")
        return False
    log("ENGINE: deterministic review artifact written")
    return True


def _relative_result_json_paths(project_dir: Path, iterations: Iterable[int]) -> list[str]:
    return sorted({
        path.relative_to(project_dir).as_posix()
        for iteration in iterations
        for path in research_result_json_files(project_dir, iteration)
    })


def _artifact_fix_prompt(
    artifact_path: Path,
    contract: RunnerStateContract,
    problem: str,
    project_dir: Path,
) -> str:
    if artifact_path.name == "research_plan.json" or "research plan quality issues" in problem:
        return (
            f"The research plan {artifact_path} failed Tiny-Lab plan-quality validation:\n"
            f"{problem}\n\n"
            f"Required completion fields: {list(contract.completion_required_fields)}\n\n"
            f"Read the plan and revise it in place until it satisfies the shared plan contract below. "
            f"You may add, remove, rename, or restructure plan fields, phase schemas, checklist entries, "
            f"success criteria, and pending phases as needed. Keep the scientific intent faithful to the "
            f"existing plan and source artifacts, do not invent completed results, and keep executable "
            f"phase statuses as `pending` unless the phase was already completed. Report paths must remain "
            f"under `research/iter_{contract.iteration}/results/`.\n\n"
            f"{render_plan_quality_contract()}"
        )
    if artifact_path.suffix.lower() == ".json":
        return (
            f"The file {artifact_path} was created but has a validation problem:\n"
            f"{problem}\n\n"
            f"Required fields: {list(contract.completion_required_fields)}\n\n"
            f"Read the file and revise it in place so it satisfies the completion contract. "
            f"Preserve existing evidence-backed content, but you may add missing required fields "
            f"or minimally revise malformed fields when the validation problem requires it. "
            f"Do not invent completed experimental results.\n\n"
            f"Common issues:\n"
            f"- 'metrics' (plural) should be 'metric' (singular) or vice versa\n"
            f"- Missing a required top-level key\n"
            f"- Key exists under a nested object instead of top level\n"
            f"- Required summary/readout fields are missing and must be derived from existing artifact content"
        )
    if artifact_path.name == "final_paper.md":
        reference_iterations = final_artifact_reference_iterations(project_dir, contract.iteration)
        reference_iteration = max(reference_iterations)
        reference_iteration_list = ", ".join(f"iter_{iteration}" for iteration in reference_iterations)
        evidence_ledger = render_final_paper_evidence_ledger(project_dir, reference_iterations)
        return (
            f"The final paper {artifact_path} was created but failed deterministic quality gates:\n"
            f"{problem}\n\n"
            f"This final paper must close completed iterations "
            f"{reference_iteration_list}. "
            f"The engine state may currently be iter_{contract.iteration}; do not cite incomplete later "
            f"iteration folders unless they are explicitly discussed as future-work seeds.\n\n"
            f"Read the paper and the relevant research artifacts, then revise research/final_paper.md "
            f"in place until it satisfies the shared final-paper contract below. You may change content, "
            f"structure, citations, headings, and wording as needed, but every quantitative or comparison "
            f"claim must stay faithful to the saved artifacts. Prefer a concise, audit-passing paper over "
            f"a long paper: delete unsupported background prose instead of trying to preserve it.\n\n"
            f"{evidence_ledger}\n\n"
            f"{render_final_paper_contract()}\n\n"
            f"Before finishing, mentally run tiny-lab audit --strict --iter {reference_iteration} and fix "
            f"any remaining artifact citation, reference citation, or claim traceability issue."
        )
    return (
        f"The file {artifact_path} was created but has a validation problem:\n"
        f"{problem}\n\n"
        f"Read the file and revise it in place so it satisfies the current tiny-lab completion contract."
    )


def _artifact_fix_timeout_seconds(
    ctx: EngineContext,
    artifact_path: Path,
    *,
    backend_name: str | None = None,
) -> float:
    if artifact_path.name == "final_paper.md":
        default = 600.0
    elif (backend_name or ctx.engine) == "codex" and artifact_path.suffix.lower() == ".json":
        default = 300.0
    elif artifact_path.suffix.lower() == ".json":
        default = 120.0
    else:
        default = 120.0
    if ctx.backend_timeout_seconds is None:
        return default
    return max(1.0, min(float(ctx.backend_timeout_seconds), default))


def _try_fix_json(contract: RunnerStateContract, ls: LoopState, ctx: EngineContext) -> bool:
    """If artifact is invalid JSON, ask Claude to fix it."""
    matches = _completion_artifact_matches(ctx.project_dir, contract)
    if not matches:
        return False

    artifact_path = Path(matches[0])
    if artifact_path.suffix.lower() != ".json":
        return False
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
        result = _invoke_artifact_fix_backend(contract, ls, ctx, fix_prompt, artifact_path, "invalid JSON")
        if result.exit_code != 0:
            return False
        try:
            json.loads(artifact_path.read_text())
            log("ENGINE: JSON fixed successfully")
            return True
        except json.JSONDecodeError:
            log("ENGINE: JSON fix attempt failed")
            return False
