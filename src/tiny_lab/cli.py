"""tiny-lab v7 CLI — domain-agnostic adaptive loop."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .logging import log


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tiny-lab",
        description="Domain-agnostic adaptive loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Quick start:
  tiny-lab init                 Set up project (creates research/, prompts/, hooks)
  echo "my idea" > research/.user_idea.txt
  tiny-lab run                  Start the loop (full auto by default)
  tiny-lab run --max-steps 1    Smoke-test one state and pause
  tiny-lab run --timeout-seconds 300
  tiny-lab run --max-iterations 10
  tiny-lab board                View results

Workflow: Shape → Gather → [Execute → Reflect → Diversify]↺ → Synthesize → Evaluate
""",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize research project",
                            description="Set up directory structure, hooks, and prompt templates.")
    init_p.add_argument("--preset", default="ml-experiment",
                        choices=["ml-experiment", "review-paper", "novel-method",
                                 "data-analysis", "ideate", "ideate-deep", "custom"],
                        help="Workflow preset (default: ml-experiment). Use 'ideate' (lite) or "
                             "'ideate-deep' (with literature scan + gap analysis) for topic & "
                             "hypothesis exploration before committing to a research preset.")
    init_p.add_argument("--ideate-first", action="store_true",
                        help="Prepend ideate states to the chosen research preset, so the loop "
                             "first selects a hypothesis then runs the full preset workflow.")

    # run
    run_p = sub.add_parser("run", help="Start the research loop",
                           description="Run the full auto loop. Iterates until goal achieved or max iterations.")
    run_p.add_argument("idea", nargs="?", help="Research idea (also saved to research/.user_idea.txt)")
    run_p.add_argument("--max-iter", "--max-iterations", dest="max_iter", type=int, default=None,
                       help="Override max iterations (default: from preset)")
    run_p.add_argument("--max-steps", type=int, default=None,
                       help="Execute at most N state-machine states, then pause without marking DONE")
    run_p.add_argument("--timeout-seconds", type=float, default=None,
                       help="Override the per-ai-session backend timeout")
    run_p.add_argument("--model", default="sonnet",
                       choices=["sonnet", "haiku", "opus"],
                       help="Claude model (default: sonnet); ignored when --engine=codex")
    run_p.add_argument("--engine", default="claude",
                       choices=["claude", "codex"],
                       help="Default AI backend (default: claude). Per-state 'engine' field "
                            "in workflow JSON overrides this for individual states.")

    # step
    step_p = sub.add_parser("step", help="Advance exactly one state with engine handlers",
                            description="Native-runner helper: execute one deterministic/process/phase "
                                        "state using the same handlers as tiny-lab run.")
    step_p.add_argument("--run-ai", action="store_true",
                        help="Allow an ai_session state to invoke the configured backend once")
    step_p.add_argument("--wait-checkpoint", action="store_true",
                        help="Wait if the current checkpoint has no intervention yet")
    step_p.add_argument("--model", default="sonnet",
                        choices=["sonnet", "haiku", "opus"],
                        help="Claude model if --run-ai is used")
    step_p.add_argument("--engine", default="claude",
                        choices=["claude", "codex"],
                        help="Default AI backend if --run-ai is used")
    step_p.add_argument("--timeout-seconds", type=float, default=None,
                        help="Override the per-ai-session backend timeout if --run-ai is used")

    # prompt
    prompt_p = sub.add_parser("prompt", help="Render the current ai_session prompt",
                              description="Native-runner helper: print the exact prompt the CLI engine "
                                          "would send for the current ai_session state.")
    prompt_p.add_argument("--model", default="sonnet",
                          choices=["sonnet", "haiku", "opus"],
                          help="Claude model context used for prompt rendering")
    prompt_p.add_argument("--engine", default="claude",
                          choices=["claude", "codex"],
                          help="Default AI backend context used for prompt rendering")

    # brief
    brief_p = sub.add_parser("brief", help="Show current native-runner state contract",
                             description="Native-runner helper: print the current state, action, gates, "
                                         "and completion artifact from the engine's workflow parser.")
    brief_p.add_argument("--json", action="store_true",
                         help="Print the briefing as JSON")
    brief_p.add_argument("--model", default="sonnet",
                         choices=["sonnet", "haiku", "opus"],
                         help="Claude model context used for briefing")
    brief_p.add_argument("--engine", default="claude",
                         choices=["claude", "codex"],
                         help="Default AI backend context used for briefing")

    # status
    sub.add_parser("status", help="Show current state, iteration, phase")

    # ps
    sub.add_parser("ps", help="Show active Tiny-Lab backend subprocess")

    # doctor
    doctor_p = sub.add_parser("doctor", help="Check project and backend readiness")
    doctor_p.add_argument("--engine", default="claude",
                          choices=["claude", "codex"],
                          help="Backend command to check (default: claude)")
    doctor_p.add_argument("--probe-backend", action="store_true",
                          help="Run a minimal backend prompt to verify auth/login")
    doctor_p.add_argument("--repair-runner", action="store_true",
                          help="Repair native runner hooks/docs without rewriting workflow state")

    # stop
    sub.add_parser("stop", help="Send stop signal to running loop")

    # repair-state
    repair_state_p = sub.add_parser("repair-state", help="Repair research/.state.json with provenance")
    repair_state_p.add_argument("--to", required=True, dest="to_state",
                                help="State id to set, e.g. PHASE_RUN or SHAPE_FULL")
    repair_state_p.add_argument("--phase", dest="phase_id",
                                help="Optional current_phase_id to set")
    repair_state_p.add_argument("--clear-failures", action="store_true",
                                help="Reset consecutive_failures and phase_retries to 0")
    repair_state_p.add_argument("--clear-session", action="store_true",
                                help="Clear session_id")

    # resume
    resume_p = sub.add_parser("resume", help="Resume from last state",
                              description="Resume a stopped or failed loop.")
    resume_p.add_argument("--add-phase", help="Add a phase before resuming")
    resume_p.add_argument("--from", dest="from_phase", help="Resume from specific phase")

    # fork
    fork_p = sub.add_parser("fork", help="Fork to new iteration",
                            description="Create a new iteration, carrying over artifacts from a previous one.")
    fork_p.add_argument("--enter", help="State to enter (e.g., PLAN, IDEA_REFINE)")
    fork_p.add_argument("--idea", help="New idea for the fork")
    fork_p.add_argument("source_iter", nargs="?", type=int, help="Source iteration to fork from")

    # shape — write constraints.json directly (skip SHAPE_FULL state)
    shape_p = sub.add_parser("shape", help="Write constraints.json directly (skip interactive SHAPE_FULL)",
                             description="Create constraints.json from a JSON string or file, then set state to DOMAIN_RESEARCH.")
    shape_p.add_argument("constraints_file", help="Path to constraints JSON file, or '-' for stdin")

    # board
    board_p = sub.add_parser("board", help="Results dashboard with metrics")
    board_p.add_argument("--iter", type=int, help="Specific iteration")

    # audit
    audit_p = sub.add_parser("audit", help="Run research quality gates without advancing state")
    audit_scope = audit_p.add_mutually_exclusive_group()
    audit_scope.add_argument("--iter", type=int, help="Specific iteration (default: current)")
    audit_scope.add_argument("--all", action="store_true",
                             help="Audit all discovered iterations and references")
    audit_p.add_argument("--strict", action="store_true",
                         help="Exit non-zero if any audit issue is found")

    # intervene
    intervene_p = sub.add_parser("intervene", help="Send intervention to running loop",
                                 description="""\
Send an intervention while the loop is waiting at a checkpoint.

Actions:
  approve     Approve plan or phase result, continue execution
  skip        Skip current phase (requires phase_id arg)
  modify      Send plan back for revision
  stop        Stop the loop
  add-phase   Add a new phase to the plan""")
    intervene_p.add_argument("action", choices=["approve", "skip", "modify", "stop", "add-phase"])
    intervene_p.add_argument("args", nargs="*")

    # novelty
    nov_p = sub.add_parser("novelty", help="Estimate novelty of ideate candidates",
                           description="Query Semantic Scholar with each candidate's hypothesis and "
                                       "report how many recent (default 3-year window) papers match. "
                                       "Fewer matches → higher novelty score (0-10).")
    nov_p.add_argument("--iter", type=int, help="Iteration to read .diverge.json from (default: current)")
    nov_p.add_argument("--years", type=int, default=3, help="Recency window in years (default: 3)")
    nov_p.add_argument("--write", action="store_true",
                       help="Write per-candidate novelty into research/{iter}/.novelty.json")

    # verify-refs
    vr_p = sub.add_parser("verify-refs", help="Verify references in research artifacts",
                          description="Check that papers cited in domain_research, diverge, "
                                      "and other artifacts actually exist (arXiv/Crossref/Semantic Scholar). "
                                      "Writes .ref_verification.json sidecars next to each source file.")
    vr_p.add_argument("--iter", type=int, help="Verify a single iteration only")
    vr_p.add_argument("--file", help="Verify a single file by path (overrides --iter)")
    vr_p.add_argument("--no-write", action="store_true",
                      help="Print results only; do not write sidecar files")
    vr_p.add_argument("--strict", action="store_true",
                      help="Exit non-zero if any reference is not fully verified")

    # timeline
    tl_p = sub.add_parser("timeline", help="Retrospective timeline of all iterations",
                          description="Build a markdown table summarizing every iteration's "
                                      "topic, delta classification, trigger, decision, and best "
                                      "result. Reads each iter_*/reflect.json + the iteration's "
                                      "hypothesis_log if present. Use this for a one-glance view "
                                      "of how the research thinking has evolved.")
    tl_p.add_argument("--out", default="research/timeline.md",
                      help="Output path (default: research/timeline.md). Use '-' for stdout.")

    # report
    report_p = sub.add_parser("report", help="Report a bug/issue to GitHub",
                              description="Collect context (state, logs, errors) and create a GitHub issue.")
    report_p.add_argument("title", help="Issue title")
    report_p.add_argument("--body", default="", help="Additional description")
    report_p.add_argument("--label", default="bug", choices=["bug", "enhancement", "question"],
                          help="Issue label (default: bug)")

    args = parser.parse_args()
    project_dir = Path.cwd()

    if args.command == "init":
        _cmd_init(project_dir, args.preset, getattr(args, "ideate_first", False))
    elif args.command == "run":
        _cmd_run(
            project_dir,
            args.idea,
            max_iter=args.max_iter,
            model=args.model,
            engine_name=args.engine,
            max_steps=args.max_steps,
            backend_timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "step":
        ok = _cmd_step(
            project_dir,
            args.run_ai,
            args.wait_checkpoint,
            args.model,
            args.engine,
            args.timeout_seconds,
        )
        if not ok:
            sys.exit(1)
    elif args.command == "prompt":
        ok = _cmd_prompt(project_dir, args.model, args.engine)
        if not ok:
            sys.exit(1)
    elif args.command == "brief":
        ok = _cmd_brief(project_dir, args.model, args.engine, args.json)
        if not ok:
            sys.exit(1)
    elif args.command == "status":
        _cmd_status(project_dir)
    elif args.command == "ps":
        _cmd_ps(project_dir)
    elif args.command == "doctor":
        ok = _cmd_doctor(project_dir, args.engine, args.probe_backend, args.repair_runner)
        if not ok:
            sys.exit(1)
    elif args.command == "stop":
        _cmd_stop(project_dir)
    elif args.command == "repair-state":
        _cmd_repair_state(
            project_dir,
            args.to_state,
            phase_id=args.phase_id,
            clear_failures=args.clear_failures,
            clear_session=args.clear_session,
        )
    elif args.command == "resume":
        _cmd_resume(project_dir, args.add_phase, args.from_phase)
    elif args.command == "fork":
        _cmd_fork(project_dir, args.enter, args.idea, args.source_iter)
    elif args.command == "shape":
        _cmd_shape(project_dir, args.constraints_file)
    elif args.command == "board":
        _cmd_board(project_dir, args.iter)
    elif args.command == "audit":
        ok = _cmd_audit(project_dir, args.iter, args.all)
        if args.strict and not ok:
            sys.exit(1)
    elif args.command == "intervene":
        _cmd_intervene(project_dir, args.action, args.args)
    elif args.command == "report":
        _cmd_report(project_dir, args.title, args.body, args.label)
    elif args.command == "verify-refs":
        _cmd_verify_refs(project_dir, args.iter, args.file, args.no_write, args.strict)
    elif args.command == "novelty":
        _cmd_novelty(project_dir, args.iter, args.years, args.write)
    elif args.command == "timeline":
        _cmd_timeline(project_dir, args.out)
    else:
        parser.print_help()


def _register_hooks(project_dir: Path) -> None:
    """Register state-gate and state-advance hooks in .claude/settings.json."""
    import json
    from .runner_contract import claude_hooks_config

    settings_path = project_dir / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks
    _normalize_claude_hook_schema(hooks)
    desired_hooks = claude_hooks_config()

    # PreToolUse: state-gate blocks disallowed operations
    pre = hooks.setdefault("PreToolUse", [])
    # Remove old sh hook if present
    pre[:] = [e for e in pre if not _claude_hook_block_has_command(e, ".claude/hooks/state-gate.sh")]
    for desired in desired_hooks["PreToolUse"]:
        _upsert_claude_hook(pre, desired)

    # PostToolUse: state-advance detects artifacts and transitions
    post = hooks.setdefault("PostToolUse", [])
    # Remove old sh hook if present
    post[:] = [e for e in post if not _claude_hook_block_has_command(e, ".claude/hooks/state-advance.sh")]
    for desired in desired_hooks["PostToolUse"]:
        _upsert_claude_hook(post, desired)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


def _upsert_claude_hook(entries: list[dict], desired: dict) -> None:
    from .runner_contract import ensure_matcher_tools

    command = _single_hook_command(desired)
    if command is None:
        return
    entry = next((e for e in entries if _claude_hook_block_has_command(e, command)), None)
    if entry is None:
        entries.append(_copy_claude_hook_block(desired))
        return
    entry["matcher"] = ensure_matcher_tools(
        str(entry.get("matcher", "")),
        desired["matcher"].split("|"),
    )
    if not isinstance(entry.get("hooks"), list):
        entry.pop("command", None)
        entry["hooks"] = []
    hooks = entry["hooks"]
    hook = next(
        (
            h for h in hooks
            if isinstance(h, dict) and h.get("command") == command
        ),
        None,
    )
    desired_hook = _copy_claude_hook_block(desired)["hooks"][0]
    if hook is None:
        hooks.append(desired_hook)
    else:
        hook.update(desired_hook)


def _normalize_claude_hook_schema(hooks_root: dict) -> None:
    """Preserve existing Claude hooks while upgrading them to matcher+hooks[]."""
    for entries in hooks_root.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry.setdefault("matcher", "")
            if isinstance(entry.get("hooks"), list):
                continue
            command = entry.pop("command", None)
            if not isinstance(command, str):
                continue
            hook: dict[str, object] = {
                "type": entry.pop("type", "command"),
                "command": command,
            }
            timeout = entry.pop("timeout", None)
            if timeout is not None:
                hook["timeout"] = timeout
            entry["hooks"] = [hook]


def _copy_claude_hook_block(block: dict) -> dict:
    copied = {k: v for k, v in block.items() if k != "hooks"}
    copied["hooks"] = [dict(h) for h in block.get("hooks", []) if isinstance(h, dict)]
    return copied


def _single_hook_command(block: dict) -> str | None:
    if isinstance(block.get("command"), str):
        return str(block["command"])
    hooks = block.get("hooks")
    if not isinstance(hooks, list):
        return None
    commands = [
        hook.get("command")
        for hook in hooks
        if isinstance(hook, dict) and isinstance(hook.get("command"), str)
    ]
    return str(commands[0]) if len(commands) == 1 else None


def _claude_hook_block_has_command(block: object, command: str) -> bool:
    if not isinstance(block, dict):
        return False
    if block.get("command") == command:
        return True
    hooks = block.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(isinstance(hook, dict) and hook.get("command") == command for hook in hooks)


def _install_text_template(src: Path, dst: Path, *, overwrite: bool = False) -> bool:
    """Install a text template, rendering shared tiny-lab placeholders."""
    from .runner_contract import render_contract_template

    if not src.exists() or (dst.exists() and not overwrite):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = render_contract_template(src.read_text())
    dst.write_text(text)
    return True


def _install_runner_doc_template(src: Path, dst: Path) -> str | None:
    """Install or refresh a runner doc while preserving non-managed content."""
    from .runner_contract import (
        RUNNER_CONTRACT_END_MARKER,
        RUNNER_CONTRACT_START_MARKER,
        render_contract_template,
        render_runner_contract,
        render_runner_contract_block,
    )

    if not src.exists():
        return None
    rendered = render_contract_template(src.read_text())
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(rendered)
        return "installed"

    existing = dst.read_text()
    contract = render_runner_contract()
    block = render_runner_contract_block()
    if contract in existing:
        if RUNNER_CONTRACT_START_MARKER in existing and RUNNER_CONTRACT_END_MARKER in existing:
            return None
        updated = existing.replace(contract, block, 1)
        if updated != existing:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(updated)
            return "updated"
        return None

    if RUNNER_CONTRACT_START_MARKER in existing and RUNNER_CONTRACT_END_MARKER in existing:
        start = existing.index(RUNNER_CONTRACT_START_MARKER)
        end = existing.index(RUNNER_CONTRACT_END_MARKER, start) + len(RUNNER_CONTRACT_END_MARKER)
        updated = existing[:start] + block + existing[end:]
    elif "## Shared Runner Contract (SSOT)" in existing:
        # Legacy generated docs had no markers, so replace the managed file
        # instead of leaving a stale contract beside the current one.
        updated = rendered
    else:
        updated = existing.rstrip() + "\n\n" + rendered

    if updated != existing:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(updated)
        return "updated"
    return None


def _upgrade_codex_hooks(path: Path) -> None:
    """Upgrade known tiny-lab Codex hook registrations without replacing user config."""
    import json
    from .runner_contract import (
        REF_VERIFY_COMMAND,
        STATE_ADVANCE_COMMAND,
        codex_hooks_config,
        ensure_matcher_tools,
        render_codex_hooks_json,
    )

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_codex_hooks_json())
        return

    if not isinstance(data, dict):
        data = {}
    hooks_root = data.setdefault("hooks", {})
    if not isinstance(hooks_root, dict):
        hooks_root = {}
        data["hooks"] = hooks_root

    changed = False
    expected = codex_hooks_config()["hooks"]
    for event, desired_blocks in expected.items():
        blocks = hooks_root.setdefault(event, [])
        if not isinstance(blocks, list):
            blocks = []
            hooks_root[event] = blocks
            changed = True
        for desired_block in desired_blocks:
            desired_matcher = str(desired_block.get("matcher", ""))
            required_tools = desired_matcher.split("|")
            target = _codex_block_with_any_command(blocks, desired_block)
            for desired_hook in desired_block.get("hooks", []):
                command = desired_hook.get("command")
                block = _codex_block_with_command(blocks, command)
                if block is None:
                    if target is None:
                        target = {"matcher": desired_matcher, "hooks": []}
                        blocks.append(target)
                        changed = True
                    target_hooks = target.setdefault("hooks", [])
                    if not isinstance(target_hooks, list):
                        target_hooks = []
                        target["hooks"] = target_hooks
                    target_hooks.append(dict(desired_hook))
                    block = target
                    changed = True
                matcher = str(block.get("matcher", ""))
                upgraded = ensure_matcher_tools(matcher, required_tools)
                if upgraded != matcher:
                    block["matcher"] = upgraded
                    changed = True

    # Legacy repair for existing tiny-lab PostToolUse registrations that only
    # missed Bash before the generated matcher was expanded.
    for block in hooks_root.get("PostToolUse", []):
        if not isinstance(block, dict):
            continue
        hooks = block.get("hooks", [])
        if not isinstance(hooks, list):
            continue
        if not any(
            isinstance(hook, dict)
            and hook.get("command") in {STATE_ADVANCE_COMMAND, REF_VERIFY_COMMAND}
            for hook in hooks
        ):
            continue
        matcher = str(block.get("matcher", ""))
        upgraded = ensure_matcher_tools(matcher, ["Bash"])
        if upgraded != matcher:
            block["matcher"] = upgraded
            changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n")


def _codex_block_with_any_command(blocks: list[object], desired_block: dict) -> dict | None:
    for desired_hook in desired_block.get("hooks", []):
        block = _codex_block_with_command(blocks, desired_hook.get("command"))
        if block is not None:
            return block
    return None


def _codex_block_with_command(blocks: list[object], command: object) -> dict | None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        hooks = block.get("hooks")
        if not isinstance(hooks, list):
            continue
        if any(isinstance(hook, dict) and hook.get("command") == command for hook in hooks):
            return block
    return None


def _merge_ideate_into_preset(ideate: dict, research: dict) -> dict:
    """Combine ideate's prefix states with a research preset's body.

    Result: SHAPE_LITE → DIVERGE → EVALUATE_MATRIX → SELECT → IDEATE_INLINE_HANDOFF
    → research preset's first non-SHAPE state (typically DOMAIN_RESEARCH).
    The research preset's SHAPE_FULL is dropped because the hypothesis
    already supplies the constraints.
    """
    import copy
    ideate_states = {s["id"]: s for s in ideate.get("states", [])}
    research_states = list(research.get("states", []))

    # SHAPE states to drop: only ai_session shapers (SHAPE_FULL, SHAPE_LITE).
    # SHAPE_SEED is a process state for convergence routing — keep it.
    drop_ids = {"SHAPE_FULL", "SHAPE_LITE"}

    # Find the first state in the research preset that we'd land on after
    # dropping SHAPE_FULL — this is what IDEATE_INLINE_HANDOFF jumps to.
    research_first = None
    for s in research_states:
        if s.get("id") in drop_ids:
            continue
        research_first = s.get("id")
        break
    if research_first is None:
        research_first = research_states[0]["id"] if research_states else "DONE"

    # Build the prefix states (everything except HANDOFF — replace with inline)
    prefix = []
    for sid in ("SHAPE_LITE", "DIVERGE", "EVALUATE_MATRIX",
                "VISUALIZE_CANDIDATES", "SELECT"):
        spec = ideate_states.get(sid)
        if not spec:
            continue
        spec = dict(spec)  # shallow copy; we'll mutate `next`
        if sid == "SELECT":
            spec["next"] = {
                "selected": "IDEATE_INLINE_HANDOFF",
                "redo": "DIVERGE",
                "reshape": "SHAPE_LITE",
            }
        prefix.append(spec)

    # Inline handoff: write constraints.json from hypothesis, then jump to research_first
    prefix.append({
        "id": "IDEATE_INLINE_HANDOFF",
        "type": "ai_session",
        "prompt": "prompts/ideate/handoff_inline.md",
        "allowed_tools": ["Read", "Write"],
        "allowed_write_globs": [
            "research/constraints.json",
            "research/.handoff_log.md",
        ],
        "completion": {
            "artifact": "research/constraints.json",
            "required_fields": ["objective", "ideated_from"],
        },
        "error": {"max_retries": 3, "on_exhaust": "stop"},
        "next": research_first,
    })

    # Carry research states verbatim, except dropped shapers.
    body = []
    for s in research_states:
        if s.get("id") in drop_ids:
            continue
        # Redirect any remaining references to dropped shapers (e.g.,
        # REVIEW_DONE.REJECT → SHAPE_FULL) to the inline handoff so the
        # workflow can recover without a dangling edge.
        s = copy.deepcopy(s)  # avoid mutating the preset dict held by caller
        nxt = s.get("next")
        if isinstance(nxt, str) and nxt in drop_ids:
            s["next"] = "IDEATE_INLINE_HANDOFF"
        elif isinstance(nxt, dict):
            s["next"] = {k: ("IDEATE_INLINE_HANDOFF" if v in drop_ids else v) for k, v in nxt.items()}
        body.append(s)

    # Keep the research preset's autonomy/exploration/intervention; merge boards
    merged = dict(research)
    merged["states"] = prefix + body

    # Board: union of sections, prepend ideate progress
    research_board = research.get("board", {})
    ideate_board = ideate.get("board", {})
    merged_board = dict(research_board)
    merged_board["title"] = f"Ideate + {research_board.get('title', 'Research')}"
    research_sections = research_board.get("sections", [])
    ideate_sections = ideate_board.get("sections", [])
    merged_board["sections"] = (
        ["constraints", "ideate_progress"]
        + [s for s in research_sections if s not in ("constraints", "ideate_progress")]
        + [s for s in ideate_sections if s not in research_sections and s != "constraints"]
    )
    merged_board["custom_sections"] = {
        **ideate_board.get("custom_sections", {}),
        **research_board.get("custom_sections", {}),
    }
    merged["board"] = merged_board

    return merged


def _cmd_init(project_dir: Path, preset: str, ideate_first: bool = False) -> None:
    """Initialize research project with a workflow preset."""
    import json
    from .paths import research_dir, workflow_path, shared_dir

    rd = research_dir(project_dir)
    rd.mkdir(parents=True, exist_ok=True)
    shared_dir(project_dir).mkdir(parents=True, exist_ok=True)

    # Copy preset to .workflow.json
    preset_file = Path(__file__).parent / "presets" / f"{preset}.json"
    if not preset_file.exists():
        print(f"Preset not found: {preset}")
        sys.exit(1)

    wf_path = workflow_path(project_dir)

    if ideate_first:
        if preset in ("ideate", "ideate-deep", "custom"):
            print(f"--ideate-first ignored: preset is already {preset}")
            shutil.copy2(preset_file, wf_path)
        else:
            ideate_file = Path(__file__).parent / "presets" / "ideate.json"
            ideate_data = json.loads(ideate_file.read_text())
            research_data = json.loads(preset_file.read_text())
            merged = _merge_ideate_into_preset(ideate_data, research_data)
            wf_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
            print(f"Initialized with preset: ideate + {preset} (--ideate-first)")
    else:
        shutil.copy2(preset_file, wf_path)
        print(f"Initialized with preset: {preset}")

    # Copy hooks
    hooks_src = Path(__file__).parent / "hooks"
    hooks_dst = project_dir / ".claude" / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for hook in hooks_src.glob("*.py"):
        dst = hooks_dst / hook.name
        shutil.copy2(hook, dst)
        dst.chmod(0o755)

    # Register hooks in .claude/settings.json
    _register_hooks(project_dir)
    print(f"Hooks installed: {hooks_dst}")

    # Reset state (so re-init works cleanly)
    from .paths import state_path
    sp = state_path(project_dir)
    if sp.exists():
        sp.unlink()
        print("State reset: .state.json cleared")

    # Copy prompt templates
    prompts_src = Path(__file__).parent / "prompts"
    prompts_dst = project_dir / "prompts"
    if prompts_src.exists():
        shutil.copytree(prompts_src, prompts_dst, dirs_exist_ok=True)
        print(f"Prompts installed: {prompts_dst}")

    # Copy CLAUDE.md
    claude_md_src = Path(__file__).parent / "templates" / "CLAUDE.md"
    claude_md_dst = project_dir / "CLAUDE.md"
    claude_action = _install_runner_doc_template(claude_md_src, claude_md_dst)
    if claude_action:
        print(f"CLAUDE.md {claude_action}")

    # Copy the tiny-lab skill into .claude/skills/tiny-lab/
    skill_src = Path(__file__).parent / "templates" / "skill" / "SKILL.md"
    skill_dst_dir = project_dir / ".claude" / "skills" / "tiny-lab"
    skill_dst = skill_dst_dir / "SKILL.md"
    if _install_text_template(skill_src, skill_dst, overwrite=True):
        print(f"Skill installed: {skill_dst.relative_to(project_dir)}")

    # Codex CLI counterparts: AGENTS.md (auto-loaded from cwd) and
    # .codex/hooks.json (project-local hook registration).
    agents_src = Path(__file__).parent / "templates" / "codex" / "AGENTS.md"
    agents_dst = project_dir / "AGENTS.md"
    agents_action = _install_runner_doc_template(agents_src, agents_dst)
    if agents_action:
        print(f"AGENTS.md {agents_action} (Codex native runner)")

    codex_hooks_dst = project_dir / ".codex" / "hooks.json"
    if not codex_hooks_dst.exists():
        from .runner_contract import render_codex_hooks_json

        codex_hooks_dst.parent.mkdir(parents=True, exist_ok=True)
        codex_hooks_dst.write_text(render_codex_hooks_json())
        print(f"Codex hooks installed: {codex_hooks_dst.relative_to(project_dir)}")
        print("  ⚠ Codex hooks require `[features] codex_hooks = true` in your codex config")
    elif codex_hooks_dst.exists():
        _upgrade_codex_hooks(codex_hooks_dst)

    # Copy .gitignore for research/
    gitignore_src = Path(__file__).parent / "templates" / "research.gitignore"
    gitignore_dst = rd / ".gitignore"
    if gitignore_src.exists() and not gitignore_dst.exists():
        shutil.copy2(gitignore_src, gitignore_dst)

    # Next steps
    print()
    print("Next steps:")
    print(f"  1. Write your idea:  echo \"your idea\" > research/.user_idea.txt")
    print(f"  2. Check readiness:  tiny-lab doctor --probe-backend")
    print(f"  3. Start the loop:   tiny-lab run")
    print(f"  4. Review the plan:  tiny-lab board")
    print(f"  5. Approve:          tiny-lab intervene approve")
    print()
    print("See CLAUDE.md for full guide.")


def _load_registry(project_dir: Path) -> "HandlerRegistry":  # type: ignore[name-defined]  # noqa: F821
    """Load handler registry based on workflow preset."""
    from .handlers.defaults import base_registry, research_registry
    from .paths import workflow_path
    import json

    wf_path = workflow_path(project_dir)
    if not wf_path.exists():
        return base_registry()

    try:
        data = json.loads(wf_path.read_text())
    except json.JSONDecodeError:
        return base_registry()
    # If any state has phase-related IDs, use research registry
    states = data.get("states", []) if isinstance(data, dict) else []
    if not isinstance(states, list):
        return base_registry()
    state_ids = {s.get("id", "") for s in states if isinstance(s, dict)}
    if state_ids & {"PHASE_SELECT", "PHASE_RUN", "PHASE_EVALUATE", "PHASE_RECORD"}:
        return research_registry()
    return base_registry()


def _cmd_run(
    project_dir: Path,
    idea: str | None,
    max_iter: int | None = None,
    model: str = "sonnet",
    engine_name: str = "claude",
    max_steps: int | None = None,
    backend_timeout_seconds: float | None = None,
) -> None:
    """Start the research loop."""
    from .engine import Engine
    from .paths import workflow_path

    if not workflow_path(project_dir).exists():
        print("Not initialized. Run 'tiny-lab init' first.")
        sys.exit(1)

    if max_steps is not None and max_steps < 1:
        print("--max-steps must be a positive integer")
        sys.exit(1)
    if max_iter is not None and max_iter < 1:
        print("--max-iter/--max-iterations must be a positive integer")
        sys.exit(1)
    if backend_timeout_seconds is not None and backend_timeout_seconds <= 0:
        print("--timeout-seconds must be positive")
        sys.exit(1)

    if idea:
        idea_file = project_dir / "research" / ".user_idea.txt"
        idea_file.write_text(idea)
        log(f"User idea: {idea}")

    constraints_issue = _constraints_file_issue(project_dir)
    if constraints_issue:
        print(constraints_issue)
        sys.exit(1)

    idea_issue = _initial_research_idea_issue(project_dir)
    if idea_issue:
        print(idea_issue)
        sys.exit(1)

    engine = Engine(
        project_dir,
        _load_registry(project_dir),
        model=model,
        engine=engine_name,
        backend_timeout_seconds=backend_timeout_seconds,
    )

    if max_iter is not None:
        engine.workflow.autonomy.max_iterations = max_iter
        log(f"Max iterations overridden: {max_iter}")

    log(f"Engine: {engine_name}  Model: {model}")
    ok = engine.run(max_steps=max_steps) if max_steps is not None else engine.run()
    if not ok:
        sys.exit(1)


def _initial_research_idea_issue(project_dir: Path) -> str | None:
    from .errors import TinyLabError
    from .paths import constraints_path, iter_dir, workflow_path
    from .state import load_state
    from .workflow import load_workflow

    ls = load_state(project_dir)
    shape_states = {"SHAPE_FULL", "SHAPE_LITE"}
    active_state = ls.state
    if active_state == "INIT":
        try:
            active_state = load_workflow(workflow_path(project_dir)).first_state()
        except TinyLabError:
            return None

    if active_state not in shape_states:
        return None
    if constraints_path(project_dir).exists():
        return None

    idea_file = project_dir / "research" / ".user_idea.txt"
    if idea_file.exists() and idea_file.read_text().strip():
        return None

    if ls.state != "INIT":
        idir = iter_dir(project_dir, ls.current_iteration)
        seed_files = (idir / ".iteration_seed.json", idir / ".explore_seed.json")
        if any(path.exists() and path.read_text().strip() for path in seed_files):
            return None

    return (
        "No research idea found. Provide one with `tiny-lab run \"your idea\"`, "
        "write research/.user_idea.txt, or use `tiny-lab shape <constraints.json>`."
    )


def _cmd_step(
    project_dir: Path,
    run_ai: bool = False,
    wait_checkpoint: bool = False,
    model: str = "sonnet",
    engine_name: str = "claude",
    backend_timeout_seconds: float | None = None,
) -> bool:
    """Execute a single state-machine step."""
    from .engine import Engine
    from .errors import TinyLabError
    from .paths import workflow_path

    if not workflow_path(project_dir).exists():
        print("Not initialized. Run 'tiny-lab init' first.")
        return False

    if backend_timeout_seconds is not None and backend_timeout_seconds <= 0:
        print("--timeout-seconds must be positive")
        return False

    if run_ai:
        constraints_issue = _constraints_file_issue(project_dir)
        if constraints_issue:
            print(constraints_issue)
            return False
        idea_issue = _initial_research_idea_issue(project_dir)
        if idea_issue:
            print(idea_issue)
            return False

    try:
        engine = Engine(
            project_dir,
            _load_registry(project_dir),
            model=model,
            engine=engine_name,
            backend_timeout_seconds=backend_timeout_seconds,
        )
        outcome = engine.step_once(run_ai=run_ai, wait_checkpoint=wait_checkpoint)
    except TinyLabError as e:
        print(f"Cannot execute step: {e}")
        return False
    print(f"State: {outcome.message}")
    return outcome.executed or outcome.state_after == "DONE"


def _cmd_prompt(
    project_dir: Path,
    model: str = "sonnet",
    engine_name: str = "claude",
) -> bool:
    """Print the current ai_session prompt rendered by the engine path."""
    from .engine import Engine
    from .errors import TinyLabError
    from .paths import workflow_path

    if not workflow_path(project_dir).exists():
        print("Not initialized. Run 'tiny-lab init' first.")
        return False

    constraints_issue = _constraints_file_issue(project_dir)
    if constraints_issue:
        print(constraints_issue)
        return False

    idea_issue = _initial_research_idea_issue(project_dir)
    if idea_issue:
        print(idea_issue)
        return False

    try:
        import contextlib
        import io

        engine = Engine(project_dir, _load_registry(project_dir), model=model, engine=engine_name)
        with contextlib.redirect_stdout(io.StringIO()):
            outcome = engine.render_current_prompt()
    except TinyLabError as e:
        print(f"Cannot render prompt: {e}")
        return False

    print(outcome.prompt)
    return True


def _cmd_brief(
    project_dir: Path,
    model: str = "sonnet",
    engine_name: str = "claude",
    as_json: bool = False,
) -> bool:
    """Print the current state contract resolved by the engine path."""
    import json

    from .engine import Engine
    from .errors import TinyLabError
    from .paths import workflow_path

    if not workflow_path(project_dir).exists():
        print("Not initialized. Run 'tiny-lab init' first.")
        return False

    try:
        import contextlib
        import io

        engine = Engine(project_dir, _load_registry(project_dir), model=model, engine=engine_name)
        with contextlib.redirect_stdout(io.StringIO()):
            briefing = engine.current_state_briefing()
    except TinyLabError as e:
        print(f"Cannot render briefing: {e}")
        return False

    data = briefing.to_dict()
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return True

    phase = f" phase={briefing.current_phase_id}" if briefing.current_phase_id else ""
    print(f"state: iter_{briefing.iteration} {briefing.state} ({briefing.state_type}){phase}")
    print(f"action: {briefing.action}")
    if briefing.runner_command:
        print(f"command: {briefing.runner_command}")
    print(f"engine: {briefing.intended_engine}")
    if briefing.prompt_path:
        print(f"prompt: {briefing.prompt_path}")
    _print_brief_list("allowed tools", briefing.allowed_tools)
    _print_brief_list("allowed writes", briefing.allowed_write_globs)
    _print_brief_list("blocked writes", briefing.blocked_write_globs)
    _print_brief_list("blocked bash", briefing.blocked_bash_patterns)
    if briefing.completion_artifact:
        print(f"completion: {briefing.completion_artifact}")
        _print_brief_list("required fields", briefing.completion_required_fields)
    if briefing.condition:
        print(f"condition: {json.dumps(briefing.condition, ensure_ascii=False)}")
    if briefing.next:
        print(f"next: {json.dumps(briefing.next, ensure_ascii=False)}")
    return True


def _print_brief_list(label: str, values: tuple[str, ...]) -> None:
    if values:
        print(f"{label}: {', '.join(values)}")


def _constraints_file_issue(project_dir: Path) -> str | None:
    import json

    from .constraints import constraints_validation_issues
    from .paths import constraints_path

    cpath = constraints_path(project_dir)
    if not cpath.exists():
        return None
    try:
        data = json.loads(cpath.read_text())
    except json.JSONDecodeError as e:
        return f"research/constraints.json is invalid JSON: {e}"
    except OSError as e:
        return f"research/constraints.json cannot be read: {e}"

    issues = constraints_validation_issues(data)
    if issues:
        return "research/constraints.json is invalid: " + "; ".join(issues)
    return None


def _cmd_shape(project_dir: Path, constraints_file: str) -> None:
    """Write constraints.json and advance past SHAPE_FULL."""
    import json
    from .constraints import constraints_validation_issues
    from .errors import TinyLabError
    from .paths import research_dir, constraints_path, iter_dir, workflow_path
    from .state import load_state, set_state
    from .workflow import load_workflow

    rd = research_dir(project_dir)
    rd.mkdir(parents=True, exist_ok=True)

    # Read constraints from file or stdin
    try:
        if constraints_file == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(constraints_file).read_text()
    except OSError as e:
        print(f"Error: cannot read constraints: {e}")
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: invalid constraints JSON: {e}")
        sys.exit(1)

    issues = constraints_validation_issues(data)
    if issues:
        print("Error: invalid constraints")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)

    ls = load_state(project_dir)
    next_state: str | None = None
    if ls.state in ("INIT", "SHAPE_FULL"):
        next_state = "DOMAIN_RESEARCH"  # default fallback
        wp = workflow_path(project_dir)
        if wp.exists():
            try:
                wf = load_workflow(wp)
            except TinyLabError as e:
                print(f"Error: cannot read workflow: {e}")
                sys.exit(1)
            for state in wf.states:
                if state.id == "SHAPE_FULL":
                    if isinstance(state.next, str):
                        next_state = state.next
                    break
            else:
                # No SHAPE_FULL — use first state
                next_state = wf.first_state()

    # Write constraints.json
    cpath = constraints_path(project_dir)
    cpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Constraints written: {cpath}")

    # Ensure iter_1 exists
    idir = iter_dir(project_dir, 1)
    idir.mkdir(parents=True, exist_ok=True)
    (idir / "phases").mkdir(exist_ok=True)
    (idir / "results").mkdir(exist_ok=True)

    # Set state past SHAPE_FULL — read next state from workflow
    if next_state is not None:
        set_state(project_dir, next_state, current_iteration=1)
        print(f"State: → {next_state} (skipped SHAPE_FULL)")
    else:
        print(f"State unchanged: {ls.state} (not in INIT/SHAPE_FULL)")


def _cmd_status(project_dir: Path) -> None:
    """Show current state — concise one-screen summary."""
    import json
    from .state import load_state
    from .paths import (
        constraints_path, convergence_log_path, iter_dir,
        plan_path, results_dir, iterations_path,
    )

    ls = load_state(project_dir)

    # One-line header
    phase_str = f" → {ls.current_phase_id}" if ls.current_phase_id else ""
    session_str = f"  session={ls.session_id[:8]}…" if ls.session_id else ""
    print(f"iter_{ls.current_iteration}  {ls.state}{phase_str}{session_str}")

    # Objective from constraints
    cpath = constraints_path(project_dir)
    if cpath.exists():
        constraints_issue = _constraints_file_issue(project_dir)
        if constraints_issue:
            print(f"  constraints: invalid ({constraints_issue})")
        else:
            c = json.loads(cpath.read_text())
            print(f"  objective: {c.get('objective', '?')[:80]}")

    # Phase progress
    pp = plan_path(project_dir, ls.current_iteration)
    if pp.exists():
        plan = json.loads(pp.read_text())
        phases = plan.get("phases", [])
        done = sum(1 for p in phases if p.get("status") == "done")
        total = len(phases)
        bar = "█" * done + "░" * (total - done)
        print(f"  phases: [{bar}] {done}/{total}")

    # Results count
    rdir = results_dir(project_dir, ls.current_iteration)
    if rdir.exists():
        n_results = len(list(rdir.glob("*.json")))
        n_plots = len(list(rdir.glob("*.png")))
        if n_results or n_plots:
            print(f"  results: {n_results} json, {n_plots} plots")

    # Errors
    if ls.consecutive_failures > 0:
        print(f"  ⚠ failures: {ls.consecutive_failures} consecutive")
    if ls.phase_retries > 0:
        print(f"  ⚠ retries: {ls.phase_retries}")

    # Iteration history (compact)
    ipath = iterations_path(project_dir)
    if ipath.exists():
        data = json.loads(ipath.read_text()) or {}
        iters = data.get("iterations", [])
        if iters:
            decisions = " → ".join(f"iter_{i['id']}:{i.get('decision', '?')[:4]}" for i in iters)
            print(f"  history: {decisions}")

    _print_active_backend(project_dir, prefix="  ")


def _cmd_ps(project_dir: Path) -> None:
    """Show the active Tiny-Lab backend child process, if any."""
    active = _active_backend_status(project_dir)
    if active is None:
        print("No active Tiny-Lab backend process recorded.")
        return
    state = "alive" if active["alive"] else "stale"
    print(
        f"{state} backend={active.get('backend', '?')} "
        f"pid={active.get('pid', '?')} started_at={active.get('started_at', '?')}"
    )
    command = active.get("command")
    if isinstance(command, list) and command:
        print("command: " + " ".join(str(part) for part in command))


def _print_active_backend(project_dir: Path, prefix: str = "") -> None:
    active = _active_backend_status(project_dir)
    if active is None:
        return
    state = "alive" if active["alive"] else "stale"
    print(
        f"{prefix}backend: {state} {active.get('backend', '?')} "
        f"pid={active.get('pid', '?')}"
    )


def _active_backend_status(project_dir: Path) -> dict | None:
    from .processes import pid_is_alive, read_active_backend

    active = read_active_backend(project_dir)
    if not active:
        return None
    pid = active.get("pid")
    active["alive"] = isinstance(pid, int) and pid_is_alive(pid)
    return active


def _cmd_doctor(
    project_dir: Path,
    engine_name: str = "claude",
    probe_backend: bool = False,
    repair_runner: bool = False,
) -> bool:
    """Check whether the current project can run the selected backend."""
    import os
    import shutil
    from .errors import TinyLabError
    from .paths import workflow_path
    from .state import load_state
    from .workflow import Workflow, load_workflow

    ok = True
    workflow: Workflow | None = None

    def check(label: str, passed: bool, detail: str) -> None:
        nonlocal ok
        status = "PASS" if passed else "FAIL"
        print(f"{status} {label}: {detail}")
        ok = ok and passed

    def info(label: str, detail: str) -> None:
        print(f"INFO {label}: {detail}")

    print("tiny-lab doctor")
    if repair_runner:
        repaired = _repair_runner_artifacts(project_dir)
        detail = ", ".join(repaired) if repaired else "nothing changed"
        print(f"INFO repair runner: {detail}")

    wf_path = workflow_path(project_dir)
    if not wf_path.exists():
        check("workflow", False, "research/.workflow.json not found; run tiny-lab init")
    else:
        try:
            workflow = load_workflow(wf_path)
        except TinyLabError as e:
            check("workflow", False, str(e))
        else:
            check("workflow", True, f"{len(workflow.states)} states loaded")

    ls = load_state(project_dir)
    info("state", f"iter_{ls.current_iteration} {ls.state}")
    constraints_issue = _constraints_file_issue(project_dir)
    check(
        "constraints",
        constraints_issue is None,
        "valid or not present" if constraints_issue is None else constraints_issue,
    )
    idea_issue = _initial_research_idea_issue(project_dir)
    check("initial idea", idea_issue is None, "available" if idea_issue is None else idea_issue)
    if workflow is not None:
        if ls.state == "INIT":
            check("current state", True, f"will start at {workflow.first_state()}")
        elif ls.state == "DONE":
            check("current state", True, "DONE")
        else:
            try:
                spec = workflow.get_state(ls.state)
            except TinyLabError as e:
                check("current state", False, str(e))
            else:
                check("current state", True, f"{spec.id} ({spec.type})")
                _doctor_prompt_template(project_dir, spec.prompt, check)

    prompt_source_issues = _doctor_prompt_template_source_issues(project_dir)
    check(
        "prompt template sources",
        not prompt_source_issues,
        "in sync" if not prompt_source_issues else "; ".join(prompt_source_issues),
    )

    required_hooks = (
        project_dir / ".claude" / "hooks" / "state_gate.py",
        project_dir / ".claude" / "hooks" / "state_advance.py",
        project_dir / ".claude" / "hooks" / "ref_verify.py",
    )
    missing_hooks = [path.relative_to(project_dir).as_posix() for path in required_hooks if not path.exists()]
    check(
        "claude hooks",
        not missing_hooks,
        "installed" if not missing_hooks else "missing " + ", ".join(missing_hooks),
    )

    hook_source_issues = _doctor_claude_hook_source_issues(project_dir)
    check(
        "claude hook sources",
        not hook_source_issues,
        "in sync" if not hook_source_issues else "; ".join(hook_source_issues),
    )

    claude_config_issue = _doctor_claude_hook_config_issue(project_dir)
    check(
        "claude hook config",
        claude_config_issue is None,
        "registered" if claude_config_issue is None else claude_config_issue,
    )

    codex_hooks = project_dir / ".codex" / "hooks.json"
    check(
        "codex hooks",
        codex_hooks.exists(),
        codex_hooks.relative_to(project_dir).as_posix() if codex_hooks.exists() else "missing .codex/hooks.json",
    )
    codex_config_issue = _doctor_codex_hook_config_issue(project_dir)
    check(
        "codex hook config",
        codex_config_issue is None,
        "registered" if codex_config_issue is None else codex_config_issue,
    )

    runner_doc_issues = _doctor_runner_doc_issues(project_dir)
    check(
        "runner docs",
        not runner_doc_issues,
        "current" if not runner_doc_issues else "; ".join(runner_doc_issues),
    )

    command = _doctor_backend_command(engine_name, os.environ.get("TINYLAB_CODEX_CMD"))
    command_path = shutil.which(command)
    check(
        "backend command",
        command_path is not None,
        f"{command} -> {command_path}" if command_path else f"{command} not found on PATH",
    )

    if probe_backend:
        if command_path is None:
            check("backend probe", False, "skipped because backend command is missing")
        else:
            check("backend probe", *_doctor_probe_backend(project_dir, engine_name))
    else:
        info("backend probe", "not run; use --probe-backend to verify login/auth")

    return ok


def _doctor_prompt_template(project_dir: Path, prompt: str | None, check) -> None:
    if not prompt:
        return
    package_prompt = Path(__file__).parent / prompt
    project_prompt = project_dir / prompt
    exists = project_prompt.exists() or package_prompt.exists()
    detail = prompt if exists else f"{prompt} not found"
    check("prompt template", exists, detail)


def _doctor_prompt_template_source_issues(project_dir: Path) -> list[str]:
    issues: list[str] = []
    source_dir = Path(__file__).parent / "prompts"
    installed_dir = project_dir / "prompts"
    if not source_dir.exists():
        return issues
    if not installed_dir.exists():
        return ["missing prompts/"]

    for source in sorted(path for path in source_dir.rglob("*") if path.is_file()):
        installed = installed_dir / source.relative_to(source_dir)
        rel = installed.relative_to(project_dir).as_posix()
        if not installed.exists():
            issues.append(f"missing {rel}")
            continue
        try:
            if installed.read_bytes() != source.read_bytes():
                issues.append(f"stale {rel}")
        except OSError as e:
            issues.append(f"cannot read {rel}: {e}")
    return issues


def _repair_runner_artifacts(project_dir: Path) -> list[str]:
    """Repair native runner artifacts without changing workflow/state."""
    repaired: list[str] = []

    hooks_src = Path(__file__).parent / "hooks"
    hooks_dst = project_dir / ".claude" / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for hook in sorted(hooks_src.glob("*.py")):
        dst = hooks_dst / hook.name
        before = dst.read_text() if dst.exists() else None
        text = hook.read_text()
        if before != text:
            dst.write_text(text)
            repaired.append(dst.relative_to(project_dir).as_posix())
        dst.chmod(0o755)

    settings_path = project_dir / ".claude" / "settings.json"
    before_settings = settings_path.read_text() if settings_path.exists() else None
    _register_hooks(project_dir)
    after_settings = settings_path.read_text() if settings_path.exists() else None
    if after_settings != before_settings:
            repaired.append(".claude/settings.json")

    repaired.extend(_repair_prompt_templates(project_dir))

    docs = (
        (Path(__file__).parent / "templates" / "CLAUDE.md", project_dir / "CLAUDE.md"),
        (Path(__file__).parent / "templates" / "codex" / "AGENTS.md", project_dir / "AGENTS.md"),
        (
            Path(__file__).parent / "templates" / "skill" / "SKILL.md",
            project_dir / ".claude" / "skills" / "tiny-lab" / "SKILL.md",
        ),
    )
    for src, dst in docs:
        action = _install_runner_doc_template(src, dst)
        if action:
            repaired.append(dst.relative_to(project_dir).as_posix())

    codex_hooks = project_dir / ".codex" / "hooks.json"
    before_codex = codex_hooks.read_text() if codex_hooks.exists() else None
    _upgrade_codex_hooks(codex_hooks)
    after_codex = codex_hooks.read_text() if codex_hooks.exists() else None
    if after_codex != before_codex:
        repaired.append(".codex/hooks.json")

    return repaired


def _repair_prompt_templates(project_dir: Path) -> list[str]:
    repaired: list[str] = []
    prompts_src = Path(__file__).parent / "prompts"
    prompts_dst = project_dir / "prompts"
    if not prompts_src.exists():
        return repaired

    for source in sorted(path for path in prompts_src.rglob("*") if path.is_file()):
        rel = source.relative_to(prompts_src)
        dst = prompts_dst / rel
        before = dst.read_bytes() if dst.exists() else None
        data = source.read_bytes()
        if before != data:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            repaired.append(dst.relative_to(project_dir).as_posix())
    return repaired


def _doctor_claude_hook_source_issues(project_dir: Path) -> list[str]:
    issues: list[str] = []
    source_dir = Path(__file__).parent / "hooks"
    installed_dir = project_dir / ".claude" / "hooks"
    for source in sorted(source_dir.glob("*.py")):
        installed = installed_dir / source.name
        rel = installed.relative_to(project_dir).as_posix()
        if not installed.exists():
            issues.append(f"missing {rel}")
            continue
        try:
            if installed.read_text() != source.read_text():
                issues.append(f"stale {rel}")
        except OSError as e:
            issues.append(f"cannot read {rel}: {e}")
    return issues


def _doctor_claude_hook_config_issue(project_dir: Path) -> str | None:
    import json

    from .runner_contract import claude_hooks_config

    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return "missing .claude/settings.json"
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError as e:
        return f"invalid .claude/settings.json: {e}"
    except OSError as e:
        return f"cannot read .claude/settings.json: {e}"

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return ".claude/settings.json must contain hooks object"

    for event, desired_entries in claude_hooks_config().items():
        entries = hooks.get(event)
        if not isinstance(entries, list):
            return f"missing hooks.{event}"
        for desired in desired_entries:
            command = _single_hook_command(desired)
            if command is None:
                return f"invalid desired {event} hook"
            entry = next(
                (
                    item for item in entries
                    if _claude_hook_block_has_command(item, command)
                ),
                None,
            )
            if entry is None:
                return f"missing {event} command {command}"
            if not isinstance(entry.get("hooks"), list):
                return f"{event} command {command} must use hooks array"
            matcher = str(entry.get("matcher", ""))
            missing_tools = [
                tool for tool in desired["matcher"].split("|")
                if tool not in matcher.split("|")
            ]
            if missing_tools:
                return f"{event} command {command} matcher missing {', '.join(missing_tools)}"
    return None


def _doctor_codex_hook_config_issue(project_dir: Path) -> str | None:
    import json

    from .runner_contract import codex_hooks_config

    hooks_path = project_dir / ".codex" / "hooks.json"
    if not hooks_path.exists():
        return "missing .codex/hooks.json"
    try:
        data = json.loads(hooks_path.read_text())
    except json.JSONDecodeError as e:
        return f"invalid .codex/hooks.json: {e}"
    except OSError as e:
        return f"cannot read .codex/hooks.json: {e}"

    hooks = data.get("hooks") if isinstance(data, dict) else None
    expected_hooks = codex_hooks_config()["hooks"]
    if not isinstance(hooks, dict):
        return ".codex/hooks.json must contain hooks object"

    for event, desired_blocks in expected_hooks.items():
        blocks = hooks.get(event)
        if not isinstance(blocks, list):
            return f"missing hooks.{event}"
        for desired_block in desired_blocks:
            for desired_hook in desired_block.get("hooks", []):
                command = desired_hook.get("command")
                block = _codex_hook_block_for_command(blocks, command)
                if block is None:
                    return f"missing {event} command {command}"
                matcher = str(block.get("matcher", ""))
                missing_tools = [
                    tool for tool in str(desired_block.get("matcher", "")).split("|")
                    if tool not in matcher.split("|")
                ]
                if missing_tools:
                    return f"{event} command {command} matcher missing {', '.join(missing_tools)}"
    return None


def _codex_hook_block_for_command(blocks: list[object], command: object) -> dict | None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        hooks = block.get("hooks")
        if not isinstance(hooks, list):
            continue
        if any(isinstance(hook, dict) and hook.get("command") == command for hook in hooks):
            return block
    return None


def _doctor_runner_doc_issues(project_dir: Path) -> list[str]:
    from .runner_contract import (
        RUNNER_CONTRACT_END_MARKER,
        RUNNER_CONTRACT_START_MARKER,
        render_runner_contract,
    )

    contract = render_runner_contract()
    docs = (
        project_dir / "CLAUDE.md",
        project_dir / "AGENTS.md",
        project_dir / ".claude" / "skills" / "tiny-lab" / "SKILL.md",
    )
    issues: list[str] = []
    for path in docs:
        rel = path.relative_to(project_dir).as_posix()
        if not path.exists():
            issues.append(f"missing {rel}")
            continue
        try:
            text = path.read_text()
        except OSError as e:
            issues.append(f"cannot read {rel}: {e}")
            continue
        if contract not in text:
            issues.append(f"stale {rel}")
            continue
        if RUNNER_CONTRACT_START_MARKER not in text or RUNNER_CONTRACT_END_MARKER not in text:
            issues.append(f"unmanaged {rel}")
    return issues


def _doctor_backend_command(engine_name: str, codex_override: str | None) -> str:
    import shlex

    if engine_name == "codex" and codex_override:
        parts = shlex.split(codex_override)
        if parts:
            return parts[0]
    return engine_name


def _doctor_probe_backend(project_dir: Path, engine_name: str) -> tuple[bool, str]:
    from .backends import get_backend
    from .handlers.ai_session import _backend_error_summary, _backend_unavailable_reason

    backend = get_backend(engine_name)
    result = backend.invoke(
        "Reply with exactly: tiny-lab-ok",
        cwd=project_dir,
        model="haiku" if engine_name == "claude" else None,
        allowed_tools=[],
        timeout=60.0,
    )
    unavailable = _backend_unavailable_reason(result)
    if unavailable:
        return False, unavailable
    if result.exit_code != 0:
        return False, _backend_error_summary(result) or f"exit code {result.exit_code}"
    return True, "backend invocation succeeded"


def _cmd_stop(project_dir: Path) -> None:
    """Stop by writing intervention and signaling the active backend child."""
    import json
    from .paths import intervention_path
    from .processes import read_active_backend, signal_pid

    ipath = intervention_path(project_dir)
    ipath.parent.mkdir(parents=True, exist_ok=True)
    ipath.write_text(json.dumps({"action": "stop"}, indent=2))
    print("Stop signal sent.")

    active = read_active_backend(project_dir)
    pid = active.get("pid") if active else None
    if isinstance(pid, int):
        if signal_pid(pid):
            print(f"Interrupted active backend pid {pid}.")
        else:
            print(f"Active backend pid {pid} was not running.")


def _cmd_repair_state(
    project_dir: Path,
    to_state: str,
    *,
    phase_id: str | None = None,
    clear_failures: bool = False,
    clear_session: bool = False,
) -> None:
    """Repair research/.state.json without hand-editing it."""
    from . import events
    from .state import load_state, set_state

    before = load_state(project_dir)
    overrides: dict[str, object] = {}
    if phase_id is not None:
        overrides["current_phase_id"] = phase_id
    if clear_failures:
        overrides["consecutive_failures"] = 0
        overrides["phase_retries"] = 0
    if clear_session:
        overrides["session_id"] = None

    after = set_state(project_dir, to_state, **overrides)
    events.emit(project_dir, "manual_state_repair", {
        "before": {
            "state": before.state,
            "iteration": before.current_iteration,
            "phase_id": before.current_phase_id,
            "consecutive_failures": before.consecutive_failures,
            "phase_retries": before.phase_retries,
            "session_id": before.session_id,
        },
        "after": {
            "state": after.state,
            "iteration": after.current_iteration,
            "phase_id": after.current_phase_id,
            "consecutive_failures": after.consecutive_failures,
            "phase_retries": after.phase_retries,
            "session_id": after.session_id,
        },
    })
    print(
        f"State repaired: {before.state} -> {after.state}"
        + (f" ({after.current_phase_id})" if after.current_phase_id else "")
    )


def _cmd_resume(project_dir: Path, add_phase: str | None, from_phase: str | None) -> None:
    """Resume from last state."""
    from .state import load_state, set_state

    ls = load_state(project_dir)
    if ls.state == "DONE":
        if add_phase:
            set_state(project_dir, "PLAN", resumable=True)
            log(f"Resuming with new phase: {add_phase}")
        else:
            print("Loop is DONE. Use --add-phase or 'tiny-lab fork'.")
            return
    elif from_phase:
        set_state(project_dir, "PHASE_SELECT", current_phase_id=None)
        log(f"Resuming from phase {from_phase}")

    from .engine import Engine
    engine = Engine(project_dir, _load_registry(project_dir))
    engine.run()


def _cmd_fork(project_dir: Path, enter: str | None, idea: str | None, source_iter: int | None) -> None:
    """Fork to new iteration."""
    from .state import load_state, set_state
    from .paths import iter_dir

    ls = load_state(project_dir)
    source = source_iter or ls.current_iteration
    new_iter = source + 1

    from .engine import Engine
    engine = Engine(project_dir, _load_registry(project_dir))
    engine._create_iteration(new_iter)

    entry_state = enter or "PLAN"
    engine._carry_over(source, new_iter, entry_state)

    if idea:
        idea_file = iter_dir(project_dir, new_iter) / ".user_idea.txt"
        idea_file.write_text(idea)

    set_state(project_dir, entry_state, current_iteration=new_iter)
    print(f"Forked iter_{source} → iter_{new_iter}, entering {entry_state}")

    engine.run()


def _cmd_board(project_dir: Path, iteration: int | None) -> None:
    """Show results dashboard."""
    from .state import load_state
    from .paths import results_dir, iterations_path, iter_dir, plan_path, workflow_path
    from .events import load_events
    import json

    ls = load_state(project_dir)
    target_iter = iteration or ls.current_iteration

    from .paths import constraints_path, convergence_log_path

    # Load board config from workflow
    board_cfg: dict = {}
    wp = workflow_path(project_dir)
    if wp.exists():
        wf_data = json.loads(wp.read_text())
        board_cfg = wf_data.get("board", {})

    board_title = board_cfg.get("title", "Research")
    board_sections = board_cfg.get("sections", [
        "constraints", "convergence", "plan", "validation", "results",
        "understanding", "reflect", "history", "paper", "events",
    ])
    preset_metric_keys = board_cfg.get("metric_keys", [])
    preset_flag_keys = set(board_cfg.get("flag_keys", []))
    custom_sections = board_cfg.get("custom_sections", {})

    # Header
    print(f"tiny-lab v7 [{board_title}] — Iteration {target_iter}")
    print(f"State: {ls.state}")
    if ls.current_phase_id:
        print(f"Current phase: {ls.current_phase_id}")
    if ls.session_id:
        print(f"Session: {ls.session_id[:8]}…")

    # Constraints
    cpath = constraints_path(project_dir)
    if cpath.exists():
        import json as _json
        c = _json.loads(cpath.read_text())
        print(f"\nObjective: {c.get('objective', '?')}")
        goal = c.get("goal", {})
        if goal.get("success_criteria"):
            print(f"Goal: {goal['success_criteria']}")

    # Convergence
    clpath = convergence_log_path(project_dir)
    if clpath.exists():
        import json as _json
        cl = _json.loads(clpath.read_text())
        entries = cl.get("log", cl.get("entries", []))
        if entries:
            print(f"\nConvergence ({len(entries)} entries):")
            for e in entries:
                print(f"  iter_{e.get('iteration', '?')}: {e.get('seed_summary', '')[:60]} [{e.get('approach_category', '')}]")

    print()

    # Plan summary
    pp = plan_path(project_dir, target_iter)
    if pp.exists():
        import json
        plan = json.loads(pp.read_text())
        print(f"Plan: {plan.get('name', '?')}")
        metric = plan.get("metric", {})
        if metric:
            print(f"Metric: {metric.get('name', '?')} ({metric.get('direction', '?')}, target: {metric.get('target', '?')})")
        phases = plan.get("phases", [])
        print(f"\nPhases ({len(phases)}):")
        for p in phases:
            status_icon = {"done": "+", "running": ">", "pending": " ", "skipped": "-", "failed": "!"}.get(p.get("status", "?"), "?")
            print(f"  [{status_icon}] {p['id']}: {p.get('name', '')} ({p.get('type', 'script')})")
        print()

    # Plan validation
    idir = iter_dir(project_dir, target_iter)
    pv_file = idir / ".plan_validation.json" if idir.exists() else None
    if pv_file and pv_file.exists():
        pv = json.loads(pv_file.read_text())
        verdict = pv.get("verdict", "?")
        checks = pv.get("checks", {})
        check_summary = " ".join(
            f"{'✓' if v in ('pass', 'sufficient', 'complete', 'rigorous', 'clear', 'adequate', 'acceptable') else '✗'}{k[:8]}"
            for k, v in checks.items()
        )
        print(f"Validation: {verdict}  [{check_summary}]")
        issues = pv.get("issues", [])
        blockers = [i for i in issues if i.get("severity") == "blocker"]
        if blockers:
            for b in blockers:
                print(f"  ✗ {b.get('criterion', '?')}: {b.get('description', '')[:70]}")
        print()

    # Ideate — candidate comparison table
    eval_matrix_file = idir / ".evaluation_matrix.json" if idir.exists() else None
    diverge_file = idir / ".diverge.json" if idir.exists() else None
    if eval_matrix_file and eval_matrix_file.exists():
        try:
            em = json.loads(eval_matrix_file.read_text())
            scored = em.get("scored_candidates", [])
            ranking = em.get("ranking", [])
            pareto = set(em.get("pareto_optimal_ids", []))
            recommendation = em.get("recommendation", {})
            top_id = recommendation.get("top_id")

            # Optional: candidate labels from diverge.json
            label_by_id = {}
            if diverge_file and diverge_file.exists():
                try:
                    dv = json.loads(diverge_file.read_text())
                    for c in dv.get("candidates", []):
                        label_by_id[c.get("id", "")] = c.get("label", "")
                except Exception:
                    pass

            print("Candidates:")
            print(f"  {'id':<5s}{'label':<22s}{'nov':>5s}{'feas':>6s}{'falsi':>7s}"
                  f"{'total':>7s}  flags")
            print(f"  {'─'*5}{'─'*22}{'─'*5}{'─'*6}{'─'*7}{'─'*7}")
            # Order by ranking if available, else by scored_candidates order
            order = [r.get("id") for r in ranking] if ranking else [c.get("id") for c in scored]
            score_by_id = {c.get("id"): c for c in scored}
            for cid in order:
                c = score_by_id.get(cid, {})
                if not c:
                    continue
                nov = c.get("novelty", {}).get("score", "?")
                feas = c.get("feasibility", {}).get("score", "?")
                fals = c.get("falsifiability", {}).get("score", "?")
                tot = c.get("weighted_total", "?")
                label = (label_by_id.get(cid, "") or "")[:20]
                flags = []
                if cid in pareto:
                    flags.append("⌬pareto")
                if cid == top_id:
                    flags.append("★top")
                penalty = c.get("ref_verification_penalty", 0)
                if penalty:
                    flags.append(f"⚠refs(-{penalty})")
                tot_s = f"{tot:.2f}" if isinstance(tot, (int, float)) else str(tot)
                print(f"  {cid:<5s}{label:<22s}{str(nov):>5s}{str(feas):>6s}"
                      f"{str(fals):>7s}{tot_s:>7s}  {' '.join(flags)}")
            if recommendation:
                runner = recommendation.get("runner_up_id")
                print(f"  Recommendation: {top_id} (runner-up: {runner or '—'})")
            print()
        except Exception as e:
            print(f"  (could not render candidates: {e})")
            print()

    # Visualization manifests (data + ideate)
    for manifest_name, viz_dirname, label in (
        (".data_viz_manifest.json", "data_viz", "Data Visualizations"),
        (".candidate_viz_manifest.json", "ideate_viz", "Candidate Visualizations"),
    ):
        manifest_file = idir / manifest_name if idir.exists() else None
        viz_dir = idir / viz_dirname if idir.exists() else None
        png_count = len(list(viz_dir.glob("*.png"))) if viz_dir and viz_dir.exists() else 0
        if not manifest_file or not manifest_file.exists():
            continue
        try:
            mf = json.loads(manifest_file.read_text())
            generated = mf.get("generated", [])
            skipped = mf.get("skipped", [])
            summary = mf.get("summary") or mf.get("viewer_summary", "")
            print(f"{label}: {png_count} PNG ({len(generated)} generated, {len(skipped)} skipped)")
            for g in generated:
                fname = g.get("filename", "?")
                what = g.get("what_it_shows") or g.get("key_takeaway", "")
                print(f"  ✓ {fname}: {what[:70]}")
            for s in skipped:
                print(f"  ○ {s.get('id', '?')} skipped — {s.get('skip_reason', '')[:70]}")
            if summary:
                print(f"  Summary: {summary[:120]}")
            print()
        except Exception:
            pass

    # Selected hypothesis
    hyp_file = idir / "hypothesis.json" if idir.exists() else None
    if hyp_file and hyp_file.exists():
        try:
            h = json.loads(hyp_file.read_text())
            verdict = h.get("verdict", "?")
            print(f"Hypothesis [{verdict}]")
            if verdict == "selected":
                print(f"  H1: {h.get('hypothesis', '?')[:90]}")
                print(f"  H0: {h.get('null_hypothesis', '?')[:90]}")
                np = h.get("next_preset", "?")
                print(f"  Next preset: {np}")
            print()
        except Exception:
            pass

    # Results — auto-extract numeric metrics for comparison table
    rdir = results_dir(project_dir, target_iter)
    if rdir.exists() and list(rdir.glob("*.json")):
        _SKIP_KEYS = {"phase", "status", "n_features", "n_parameters", "train_time_seconds",
                       "rows_raw", "rows_after_dedup", "rows_hourly", "n_duplicates_removed",
                       "n_sentinel_wv_fixed", "n_sentinel_maxwv_fixed", "nan_rows_before_interp",
                       "nan_rows_after_interp", "target_col_index"}
        _FLAG_KEYS = preset_flag_keys or {"beats_naive", "beats_ma", "target_achieved"}
        rows: list[tuple[str, dict, list[str]]] = []
        for f in sorted(rdir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                if not isinstance(data, dict):
                    continue
                model = data.get("model_id", data.get("model", f.stem))
                metrics = {}
                flags = []
                for k, v in data.items():
                    if k in _SKIP_KEYS:
                        continue
                    if k in _FLAG_KEYS and v is True:
                        flags.append(f"✓{k.replace('beats_', '').replace('target_', '')}")
                    elif isinstance(v, float):
                        metrics[k] = v
                if metrics:
                    rows.append((str(model), metrics, flags))
            except Exception:
                pass

        if rows:
            # Use preset metric_keys if specified, otherwise auto-detect
            if preset_metric_keys:
                all_row_keys = set(k for _, m, _ in rows for k in m)
                display_keys = [k for k in preset_metric_keys if k in all_row_keys][:4]
            if not preset_metric_keys or not display_keys:
                from collections import Counter
                key_counts = Counter(k for _, m, _ in rows for k in m)
                shared_keys = [k for k, c in key_counts.most_common() if c >= 2]
                if not shared_keys:
                    shared_keys = list(dict.fromkeys(k for _, m, _ in rows for k in m))
                display_keys = shared_keys[:4]

            print("Results:")
            header = f"  {'Model':<25s}"
            for k in display_keys:
                header += f" {k:>14s}"
            print(header)
            print(f"  {'─'*25}" + "─" * (15 * len(display_keys)))

            for model, metrics, flags in rows:
                row = f"  {model:<25s}"
                for k in display_keys:
                    v = metrics.get(k)
                    if isinstance(v, float):
                        row += f" {v:>14.4f}"
                    else:
                        row += f" {'—':>14s}"
                if flags:
                    row += f"  [{', '.join(flags)}]"
                print(row)
            print()
        else:
            print("Results: (no numeric metrics found)")
            print()

    # Understanding artifacts
    artifacts = [".domain_research.json", ".data_analysis.json", ".idea_refined.json"]
    present = [a for a in artifacts if idir.exists() and (idir / a).exists()]
    if present:
        print(f"Understanding: {', '.join(a.replace('.json', '').lstrip('.') for a in present)}")

    # Custom sections from preset board config
    for sec_name, sec_cfg in custom_sections.items():
        files = sec_cfg.get("files", [])
        labels = sec_cfg.get("labels", files)
        items = []
        for fname, label in zip(files, labels):
            fpath = idir / fname if idir.exists() else None
            if fpath and fpath.exists():
                try:
                    data = json.loads(fpath.read_text())
                    # Show key counts for dicts/lists
                    if isinstance(data, dict):
                        summary_parts = []
                        for k, v in data.items():
                            if isinstance(v, list):
                                summary_parts.append(f"{k}: {len(v)}")
                            elif isinstance(v, (int, float)):
                                summary_parts.append(f"{k}: {v}")
                            elif isinstance(v, str) and len(v) < 60:
                                summary_parts.append(f"{k}: {v}")
                        items.append(f"  ✓ {label}: {', '.join(summary_parts[:4])}")
                    else:
                        items.append(f"  ✓ {label}")
                except Exception:
                    items.append(f"  ✓ {label} (exists)")
            else:
                items.append(f"  ○ {label} (pending)")
        if items:
            print(f"\n{sec_name.replace('_', ' ').title()}:")
            for item in items:
                print(item)

    # Reflect (current iter)
    reflect_file = idir / "reflect.json" if idir.exists() else None
    if reflect_file and reflect_file.exists():
        reflect = json.loads(reflect_file.read_text())
        delta = reflect.get("delta_from_previous_iter")
        drift = reflect.get("drift_warning")
        delta_str = f"  delta={delta}" if delta else ""
        drift_str = "  ⚠drift" if drift else ""
        print(f"Reflect: {reflect.get('decision', '?')}{delta_str}{drift_str} — "
              f"{reflect.get('reason', '')[:90]}")

    # Framing log — scan every iter's reflect.json for framing_change entries
    if "framing_log" in board_sections:
        from .paths import iteration_dirs, research_dir as _research_dir
        framing_entries = []
        rd = _research_dir(project_dir)
        if rd.exists():
            for d in iteration_dirs(project_dir):
                rfile = d / "reflect.json"
                if not rfile.exists():
                    continue
                try:
                    r = json.loads(rfile.read_text())
                except (json.JSONDecodeError, OSError):
                    continue
                fc = r.get("framing_change")
                if fc and isinstance(fc, dict):
                    framing_entries.append((d.name, fc))
        if framing_entries:
            print("\nFraming Log:")
            for iter_name, fc in framing_entries:
                axis = fc.get("axis", "?")
                from_f = (fc.get("from_frame") or "")[:60]
                to_f = (fc.get("to_frame") or "")[:60]
                print(f"  {iter_name} [{axis}]: {from_f}")
                print(f"            → {to_f}")

    # Iterations history
    ipath = iterations_path(project_dir)
    if ipath.exists():
        data = json.loads(ipath.read_text()) or {}
        iters = data.get("iterations", [])
        if iters:
            print(f"\nIteration History:")
            for it in iters:
                print(f"  iter_{it['id']}: {it.get('decision', '?')} — {it.get('reason', '')[:80]}")

    # Final paper & evaluation
    final_paper = project_dir / "research" / "final_paper.md"
    eval_file = project_dir / "research" / "evaluation.json"
    if final_paper.exists():
        print(f"\nFinal Paper: {final_paper} ({final_paper.stat().st_size:,} bytes)")
    if eval_file.exists():
        ev = json.loads(eval_file.read_text())
        scores = ev.get("scores", {})
        score_str = " | ".join(f"{k[:8]}={v}" for k, v in scores.items())
        print(f"Review: {ev.get('verdict', '?')} (total={ev.get('total', '?')}) [{score_str}]")

    # Recent events
    evts = load_events(project_dir, last_n=5)
    if evts:
        print(f"\nRecent Events:")
        for e in evts:
            ts = e.get("timestamp", "?")[:19]
            print(f"  [{ts}] {e.get('event', '?')}: {e.get('data', {})}")


def _cmd_audit(project_dir: Path, iteration: int | None = None, all_iterations: bool = False) -> bool:
    """Run quality checks against current research artifacts."""
    from .gates import audit_final_artifacts
    from .state import load_state

    ls = load_state(project_dir)
    target_iters = _audit_target_iterations(project_dir, ls.current_iteration, iteration, all_iterations)
    issues: list[str] = []

    if all_iterations:
        iter_label = ", ".join(f"iter_{num}" for num in target_iters)
        print(f"tiny-lab audit — all iterations ({iter_label})")
    else:
        print(f"tiny-lab audit — iter_{target_iters[0]}")

    for target_iter in target_iters:
        iter_issues = _audit_iteration_plan_outputs(project_dir, target_iter)
        issues.extend(iter_issues)

    final_audit = audit_final_artifacts(
        project_dir,
        reference_iteration=None if all_iterations else target_iters[0],
    )

    # Final paper claims
    if final_audit.final_paper_exists:
        if final_audit.paper_issues:
            print(f"Final paper: FAIL ({len(final_audit.paper_issues)} issues)")
            for issue in final_audit.paper_issues:
                print(f"  - {issue}")
            issues.extend(f"paper: {issue}" for issue in final_audit.paper_issues)
        else:
            print("Final paper: PASS")

        if final_audit.claim_issues:
            print(f"Paper claims: FAIL ({len(final_audit.claim_issues)} issues)")
            for issue in final_audit.claim_issues[:10]:
                print(f"  - {issue}")
            issues.extend(f"claim: {issue}" for issue in final_audit.claim_issues)
        else:
            print("Paper claims: PASS")
    else:
        if final_audit.missing_final_paper_issue:
            print(f"Final paper: FAIL ({final_audit.missing_final_paper_issue})")
            issues.append("paper: final_paper.md missing despite evaluation.json")
        else:
            print("Final paper: SKIP (final_paper.md not found)")
        print("Paper claims: SKIP (final_paper.md not found)")

    # Reference verification sidecars
    if final_audit.reference_issues:
        print(f"References: FAIL ({len(final_audit.reference_issues)} issues)")
        for issue in final_audit.reference_issues:
            print(f"  - {issue}")
        issues.extend(f"references: {issue}" for issue in final_audit.reference_issues)
    else:
        print("References: PASS")

    # Professor review consistency
    if final_audit.evaluation_exists:
        if final_audit.evaluation_issues:
            print(f"Evaluation: FAIL ({len(final_audit.evaluation_issues)} issues)")
            for issue in final_audit.evaluation_issues:
                print(f"  - {issue}")
            issues.extend(f"evaluation: {issue}" for issue in final_audit.evaluation_issues)
        else:
            print("Evaluation: PASS")
    else:
        print("Evaluation: SKIP (evaluation.json not found)")

    print(f"\nAudit: {'PASS' if not issues else 'FAIL'}")
    return not issues


def _audit_target_iterations(
    project_dir: Path,
    current_iteration: int,
    iteration: int | None,
    all_iterations: bool,
) -> list[int]:
    from .paths import iteration_number_from_dir_name, iteration_dirs

    if not all_iterations:
        return [iteration or current_iteration]

    found: set[int] = set()
    for path in iteration_dirs(project_dir):
        iter_num = iteration_number_from_dir_name(path.name)
        if iter_num is None:
            continue
        found.add(iter_num)
    return sorted(found) or [iteration or current_iteration]


def _audit_iteration_plan_outputs(project_dir: Path, target_iter: int) -> list[str]:
    """Audit one iteration's plan and phase outputs."""
    from .gates import audit_iteration_completion

    issues: list[str] = []
    print(f"\niter_{target_iter}")
    audit = audit_iteration_completion(project_dir, target_iter)
    if not audit.plan_exists:
        print("Plan: FAIL (research_plan.json is missing)")
        issues.append(f"iter_{target_iter}: research_plan.json is missing")
        return issues
    if audit.load_issue:
        print(f"Plan: FAIL ({audit.load_issue})")
        issues.append(f"iter_{target_iter}: {audit.load_issue}")
        return issues

    if audit.plan_issues:
        print(f"Plan: FAIL ({len(audit.plan_issues)} issues)")
        for issue in audit.plan_issues:
            print(f"  - {issue}")
        issues.extend(f"iter_{target_iter} plan: {issue}" for issue in audit.plan_issues)
    else:
        print("Plan: PASS")

    if audit.phase_issues:
        print(f"Phase outputs: FAIL ({len(audit.phase_issues)} issues)")
        for issue in audit.phase_issues:
            print(f"  - {issue}")
        issues.extend(f"iter_{target_iter} phase: {issue}" for issue in audit.phase_issues)
    else:
        print("Phase outputs: PASS")
    return issues


def _cmd_intervene(project_dir: Path, action: str, extra_args: list[str]) -> None:
    """Write intervention file."""
    import json
    from .paths import intervention_path

    intervention: dict = {"action": action}

    if action == "skip" and extra_args:
        intervention["action"] = "skip_phase"
        intervention["skip_phase"] = {"phase_id": extra_args[0]}
    elif action == "modify" and len(extra_args) >= 2:
        intervention["action"] = "modify_plan"
        intervention["modify_plan"] = {"phase_id": extra_args[0], "changes": extra_args[1:]}

    ipath = intervention_path(project_dir)
    ipath.parent.mkdir(parents=True, exist_ok=True)
    ipath.write_text(json.dumps(intervention, indent=2))
    print(f"Intervention sent: {action}")


def _cmd_verify_refs(
    project_dir: Path,
    iteration: int | None,
    single_file: str | None,
    no_write: bool,
    strict: bool,
) -> None:
    """Verify references in research artifacts."""
    from .refs import (
        verify_file, verify_all, write_verification, format_summary,
    )

    write_files = not no_write

    if single_file:
        path = Path(single_file)
        if not path.is_absolute():
            path = project_dir / path
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(2)
        result = verify_file(path)
        results = [result]
        if write_files and result.total > 0:
            out = write_verification(path, result)
            print(f"Wrote: {out.relative_to(project_dir)}")
    else:
        results = verify_all(project_dir, iteration=iteration, write_files=write_files)
        if write_files:
            for r in results:
                if r.total > 0:
                    sidecar = (
                        Path(r.source_file).parent
                        / (Path(r.source_file).stem + ".ref_verification.json")
                    )
                    print(f"Wrote: {sidecar.relative_to(project_dir)}")

    print()
    print(format_summary(results))

    if strict:
        not_found = sum(r.not_found for r in results)
        unverified = sum(r.unverified for r in results)
        errors = sum(r.error for r in results)
        if not_found or unverified or errors:
            print(
                "\nstrict mode: references not fully verified "
                f"(not_found={not_found}, unverified={unverified}, error={errors}) - exiting 1"
            )
            sys.exit(1)


def _cmd_novelty(
    project_dir: Path,
    iteration: int | None,
    years: int,
    write: bool,
) -> None:
    """Estimate novelty for each candidate in .diverge.json."""
    import json
    from .refs import novelty_estimate
    from .state import load_state
    from .paths import iter_dir

    if iteration is None:
        ls = load_state(project_dir)
        iteration = ls.current_iteration

    diverge_file = iter_dir(project_dir, iteration) / ".diverge.json"
    if not diverge_file.exists():
        print(f"No .diverge.json at {diverge_file}")
        sys.exit(2)

    try:
        dv = json.loads(diverge_file.read_text())
    except json.JSONDecodeError as e:
        print(f"Cannot read {diverge_file}: {e}")
        sys.exit(2)

    candidates = dv.get("candidates", [])
    if not candidates:
        print("No candidates in .diverge.json")
        sys.exit(2)

    print(f"Querying Semantic Scholar for {len(candidates)} candidates "
          f"(window: last {years} years)\n")
    print(f"  {'id':<5s}{'label':<22s}{'matches':>9s}{'score':>7s}")
    print(f"  {'─'*5}{'─'*22}{'─'*9}{'─'*7}")

    results = []
    for c in candidates:
        cid = c.get("id", "?")
        label = (c.get("label") or "")[:20]
        hypothesis = c.get("hypothesis", "")
        result = novelty_estimate(hypothesis, year_window=years)
        results.append({
            "id": cid,
            "label": c.get("label"),
            "hypothesis": hypothesis,
            **result,
        })
        score = result.get("novelty_score")
        score_s = str(score) if score is not None else "?"
        count = result.get("count", 0)
        err = result.get("error")
        marker = f" ({err})" if err else ""
        print(f"  {cid:<5s}{label:<22s}{count:>9d}{score_s:>7s}{marker}")

    if write:
        out_path = iter_dir(project_dir, iteration) / ".novelty.json"
        out_path.write_text(json.dumps({
            "iteration": iteration,
            "year_window": years,
            "candidates": results,
        }, indent=2, ensure_ascii=False) + "\n")
        print(f"\nWrote: {out_path.relative_to(project_dir)}")


def _cmd_timeline(project_dir: Path, out: str) -> None:
    """Build the retrospective timeline table (v7.10).

    Walks every iter_*/reflect.json (and the iteration's
    .hypothesis_log.json if present) and emits a markdown table with
    one row per iteration: topic / delta / trigger / decision / best
    result / cycle length.
    """
    import json
    from datetime import datetime
    from .paths import iteration_dirs, iteration_number_from_dir_name, research_dir

    rd = research_dir(project_dir)
    if not rd.exists():
        print("No research/ directory — run `tiny-lab init` first.")
        sys.exit(2)

    rows: list[dict] = []
    for d in iteration_dirs(project_dir):
        iter_num = iteration_number_from_dir_name(d.name)
        if iter_num is None:
            continue
        rfile = d / "reflect.json"
        if not rfile.exists():
            continue
        try:
            r = json.loads(rfile.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Hypothesis log (optional — only present if HYPOTHESIS_UPDATE state ran)
        hlog_file = d / "phases" / ".hypothesis_log.json"
        n_phases = 0
        cycle_len = ""
        if hlog_file.exists():
            try:
                hlog = json.loads(hlog_file.read_text())
                entries = hlog.get("entries", [])
                n_phases = len(entries)
                if len(entries) >= 2:
                    first_ts = entries[0].get("ran_at")
                    last_ts = entries[-1].get("ran_at")
                    if first_ts and last_ts:
                        try:
                            t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                            t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                            cycle_len = f"{(t1 - t0).total_seconds() / 3600:.1f}h"
                        except (ValueError, AttributeError):
                            pass
            except (json.JSONDecodeError, OSError):
                pass

        best = r.get("best_result") or {}
        metric_v = best.get("metric_value", "—")
        if isinstance(metric_v, float):
            metric_v = f"{metric_v:.4f}"

        pivot = r.get("pivot_trigger") or {}
        trigger_src = pivot.get("trigger_source", r.get("delta_trigger", "—"))

        rows.append({
            "iter": iter_num,
            "delta": r.get("delta_from_previous_iter", "—"),
            "trigger": trigger_src,
            "decision": r.get("decision", "—"),
            "best": str(metric_v)[:30],
            "phases": n_phases,
            "cycle": cycle_len or "—",
            "drift": "⚠" if r.get("drift_warning") else "",
            "framing": "✓" if r.get("framing_change") else "",
            "reason": (r.get("reason") or "")[:80].replace("\n", " ").replace("|", "/"),
        })

    if not rows:
        print("No iterations with reflect.json found yet.")
        sys.exit(0)

    lines = [
        "# Research Timeline",
        "",
        f"_Generated from {len(rows)} iteration(s) — `tiny-lab timeline`_",
        "",
        "| iter | delta | trigger | decision | best | phases | cycle | flags | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        flags = (r["drift"] + r["framing"]).strip() or " "
        lines.append(
            f"| {r['iter']} | {r['delta']} | {r['trigger']} | {r['decision']} | "
            f"{r['best']} | {r['phases']} | {r['cycle']} | {flags} | {r['reason']} |"
        )
    text = "\n".join(lines) + "\n"

    if out == "-":
        print(text)
        return

    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = project_dir / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"Wrote: {out_path.relative_to(project_dir)}")
    print(f"  {len(rows)} iteration(s) summarized")


_REPO = "byungchanKo99/Tiny-Lab"


def _cmd_report(project_dir: Path, title: str, body: str, label: str) -> None:
    """Collect context and create a GitHub issue."""
    import json
    import subprocess
    from .state import load_state
    from .paths import research_dir

    # Collect context
    sections = [body] if body else []

    # State
    ls = load_state(project_dir)
    sections.append(
        f"## Environment\n"
        f"- **State**: `{ls.state}` (iter={ls.current_iteration})\n"
        f"- **Phase**: `{ls.current_phase_id or 'none'}`\n"
        f"- **Retries**: {ls.phase_retries}, failures: {ls.consecutive_failures}"
    )

    # Version
    try:
        from . import __version__
        sections.append(f"- **Version**: {__version__}")
    except Exception:
        pass

    # Last 20 log lines
    log_file = research_dir(project_dir) / "loop.log"
    if log_file.exists():
        lines = log_file.read_text().strip().splitlines()[-20:]
        sections.append(f"## Recent Log\n```\n" + "\n".join(lines) + "\n```")

    # Phase error if exists
    error_file = (
        research_dir(project_dir) / f"iter_{ls.current_iteration}" / ".phase_error.json"
    )
    if error_file.exists():
        try:
            err = json.loads(error_file.read_text())
            last = err[-1] if isinstance(err, list) else err
            sections.append(
                f"## Last Phase Error\n"
                f"- Script: `{last.get('script', '?')}`\n"
                f"- Exit code: {last.get('exit_code', '?')}\n"
                f"```\n{last.get('stderr', '')[:500]}\n```"
            )
        except Exception:
            pass

    # Constraints
    cpath = research_dir(project_dir) / "constraints.json"
    if cpath.exists():
        try:
            c = json.loads(cpath.read_text())
            sections.append(f"## Constraints\n- Objective: {c.get('objective', '?')}")
        except Exception:
            pass

    full_body = "\n\n".join(sections)

    # Create issue via gh
    cmd = [
        "gh", "issue", "create",
        "--repo", _REPO,
        "--title", title,
        "--body", full_body,
        "--label", label,
    ]

    print(f"Creating issue: {title}")
    print(f"Label: {label}")
    print(f"Context: state={ls.state}, iter={ls.current_iteration}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        url = result.stdout.strip()
        print(f"Issue created: {url}")
    else:
        print(f"Failed to create issue: {result.stderr.strip()}")
        print("Make sure 'gh' CLI is installed and authenticated.")
        print(f"\nFull body (copy to GitHub manually):\n{'─'*40}\n{full_body}")
