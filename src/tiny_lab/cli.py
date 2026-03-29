"""tiny-lab v5 CLI — plan-driven phase executor."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .logging import log


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tiny-lab",
        description="Plan-driven AI research loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Quick start:
  tiny-lab init                 Set up project (creates research/, prompts/, hooks)
  echo "my idea" > research/.user_idea.txt
  tiny-lab run                  Start the loop (stops at PLAN_REVIEW for approval)
  tiny-lab intervene approve    Approve plan, start execution
  tiny-lab board                View results

Workflow: Understand → Plan → PLAN_REVIEW (stop) → Execute → Reflect → Iterate
""",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize research project",
                            description="Set up directory structure, hooks, and prompt templates.")
    init_p.add_argument("--preset", default="ml-experiment",
                        choices=["ml-experiment", "review-paper", "novel-method",
                                 "data-analysis", "custom"],
                        help="Workflow preset (default: ml-experiment)")

    # run
    run_p = sub.add_parser("run", help="Start the research loop",
                           description="Run the loop from current state. Stops at PLAN_REVIEW for approval.")
    run_p.add_argument("idea", nargs="?", help="Research idea (also saved to research/.user_idea.txt)")

    # status
    sub.add_parser("status", help="Show current state, iteration, phase")

    # stop
    sub.add_parser("stop", help="Send stop signal to running loop")

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

    # board
    board_p = sub.add_parser("board", help="Results dashboard with metrics")
    board_p.add_argument("--iter", type=int, help="Specific iteration")

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

    args = parser.parse_args()
    project_dir = Path.cwd()

    if args.command == "init":
        _cmd_init(project_dir, args.preset)
    elif args.command == "run":
        _cmd_run(project_dir, args.idea)
    elif args.command == "status":
        _cmd_status(project_dir)
    elif args.command == "stop":
        _cmd_stop(project_dir)
    elif args.command == "resume":
        _cmd_resume(project_dir, args.add_phase, args.from_phase)
    elif args.command == "fork":
        _cmd_fork(project_dir, args.enter, args.idea, args.source_iter)
    elif args.command == "board":
        _cmd_board(project_dir, args.iter)
    elif args.command == "intervene":
        _cmd_intervene(project_dir, args.action, args.args)
    else:
        parser.print_help()


def _register_hooks(project_dir: Path) -> None:
    """Register state-gate and state-advance hooks in .claude/settings.json."""
    import json

    settings_path = project_dir / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # PreToolUse: state-gate blocks disallowed operations
    pre = hooks.setdefault("PreToolUse", [])
    gate_entry = {
        "matcher": "Write|Edit|Bash",
        "command": ".claude/hooks/state-gate.sh",
    }
    if not any(e.get("command") == gate_entry["command"] for e in pre):
        pre.append(gate_entry)

    # PostToolUse: state-advance detects artifacts and transitions
    post = hooks.setdefault("PostToolUse", [])
    advance_entry = {
        "matcher": "Write|Edit",
        "command": ".claude/hooks/state-advance.sh",
    }
    if not any(e.get("command") == advance_entry["command"] for e in post):
        post.append(advance_entry)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


def _cmd_init(project_dir: Path, preset: str) -> None:
    """Initialize research project with a workflow preset."""
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
    shutil.copy2(preset_file, wf_path)
    print(f"Initialized with preset: {preset}")

    # Copy hooks
    hooks_src = Path(__file__).parent / "hooks"
    hooks_dst = project_dir / ".claude" / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for hook in hooks_src.glob("*.sh"):
        dst = hooks_dst / hook.name
        shutil.copy2(hook, dst)
        dst.chmod(0o755)

    # Register hooks in .claude/settings.json
    _register_hooks(project_dir)
    print(f"Hooks installed: {hooks_dst}")

    # Copy prompt templates
    prompts_src = Path(__file__).parent / "prompts"
    prompts_dst = project_dir / "prompts"
    if prompts_src.exists():
        shutil.copytree(prompts_src, prompts_dst, dirs_exist_ok=True)
        print(f"Prompts installed: {prompts_dst}")

    # Copy CLAUDE.md
    claude_md_src = Path(__file__).parent / "templates" / "CLAUDE.md"
    claude_md_dst = project_dir / "CLAUDE.md"
    if claude_md_src.exists() and not claude_md_dst.exists():
        shutil.copy2(claude_md_src, claude_md_dst)
        print("CLAUDE.md installed")

    # Copy .gitignore for research/
    gitignore_src = Path(__file__).parent / "templates" / "research.gitignore"
    gitignore_dst = rd / ".gitignore"
    if gitignore_src.exists() and not gitignore_dst.exists():
        shutil.copy2(gitignore_src, gitignore_dst)

    # Next steps
    print()
    print("Next steps:")
    print(f"  1. Write your idea:  echo \"your idea\" > research/.user_idea.txt")
    print(f"  2. Start the loop:   tiny-lab run")
    print(f"  3. Review the plan:  tiny-lab board")
    print(f"  4. Approve:          tiny-lab intervene approve")
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

    data = json.loads(wf_path.read_text())
    # If any state has phase-related IDs, use research registry
    state_ids = {s.get("id", "") for s in data.get("states", [])}
    if state_ids & {"PHASE_SELECT", "PHASE_RUN", "PHASE_EVALUATE", "PHASE_RECORD"}:
        return research_registry()
    return base_registry()


def _cmd_run(project_dir: Path, idea: str | None) -> None:
    """Start the research loop."""
    from .engine import Engine
    from .paths import workflow_path

    if not workflow_path(project_dir).exists():
        print("Not initialized. Run 'tiny-lab init' first.")
        sys.exit(1)

    if idea:
        idea_file = project_dir / "research" / ".user_idea.txt"
        idea_file.write_text(idea)
        log(f"User idea: {idea}")

    engine = Engine(project_dir, _load_registry(project_dir))
    engine.run()


def _cmd_status(project_dir: Path) -> None:
    """Show current state."""
    from .state import load_state

    ls = load_state(project_dir)
    print(f"Iteration: {ls.current_iteration}")
    print(f"State: {ls.state}")
    if ls.current_phase_id:
        print(f"Phase: {ls.current_phase_id}")
    print(f"Resumable: {ls.resumable}")
    if ls.consecutive_failures > 0:
        print(f"Consecutive failures: {ls.consecutive_failures}")


def _cmd_stop(project_dir: Path) -> None:
    """Stop by writing intervention."""
    import json
    from .paths import intervention_path

    ipath = intervention_path(project_dir)
    ipath.parent.mkdir(parents=True, exist_ok=True)
    ipath.write_text(json.dumps({"action": "stop"}, indent=2))
    print("Stop signal sent.")


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
    from .paths import results_dir, iterations_path, iter_dir, plan_path
    from .events import load_events
    import json

    ls = load_state(project_dir)
    target_iter = iteration or ls.current_iteration

    # Header
    print(f"tiny-lab v5 — Iteration {target_iter}")
    print(f"State: {ls.state}")
    if ls.current_phase_id:
        print(f"Current phase: {ls.current_phase_id}")
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

    # Results
    rdir = results_dir(project_dir, target_iter)
    if rdir.exists() and list(rdir.glob("*.json")):
        print("Results:")
        for f in sorted(rdir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                # Show key metrics, not full dump
                summary_keys = [k for k in data if k not in ("all_trials",) and not isinstance(data[k], (list, dict)) or k == "best_params"]
                parts = []
                for k in summary_keys:
                    v = data[k]
                    if isinstance(v, float):
                        parts.append(f"{k}={v:.4f}")
                    elif isinstance(v, dict):
                        inner = ", ".join(f"{ik}={iv}" for ik, iv in list(v.items())[:3])
                        parts.append(f"{k}=({inner})")
                    else:
                        parts.append(f"{k}={v}")
                print(f"  {f.stem}: {', '.join(parts)}")
            except Exception:
                print(f"  {f.stem}: (parse error)")
        print()

    # Understanding artifacts
    idir = iter_dir(project_dir, target_iter)
    artifacts = [".domain_research.json", ".data_analysis.json", ".idea_refined.json"]
    present = [a for a in artifacts if (idir / a).exists()]
    if present:
        print(f"Understanding: {', '.join(a.replace('.json', '').lstrip('.') for a in present)}")

    # Reflect
    reflect_file = idir / "reflect.json" if idir.exists() else None
    if reflect_file and reflect_file.exists():
        import json
        reflect = json.loads(reflect_file.read_text())
        print(f"Reflect: {reflect.get('decision', '?')} — {reflect.get('reason', '')[:100]}")

    # Iterations history
    ipath = iterations_path(project_dir)
    if ipath.exists():
        import json
        data = json.loads(ipath.read_text()) or {}
        iters = data.get("iterations", [])
        if iters:
            print(f"\nIteration History:")
            for it in iters:
                print(f"  iter_{it['id']}: {it.get('decision', '?')} — {it.get('reason', '')[:80]}")

    # Recent events
    evts = load_events(project_dir, last_n=5)
    if evts:
        print(f"\nRecent Events:")
        for e in evts:
            ts = e.get("timestamp", "?")[:19]
            print(f"  [{ts}] {e.get('event', '?')}: {e.get('data', {})}")


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
