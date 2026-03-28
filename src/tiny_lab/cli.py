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
    )
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize research project")
    init_p.add_argument("--preset", default="ml-experiment",
                        choices=["ml-experiment", "review-paper", "novel-method",
                                 "data-analysis", "custom"],
                        help="Workflow preset (default: ml-experiment)")

    # run
    run_p = sub.add_parser("run", help="Start the research loop")
    run_p.add_argument("idea", nargs="?", help="Research idea (natural language)")

    # status
    sub.add_parser("status", help="Show current state")

    # stop
    sub.add_parser("stop", help="Stop the running loop")

    # resume
    resume_p = sub.add_parser("resume", help="Resume from last state")
    resume_p.add_argument("--add-phase", help="Add a phase before resuming")
    resume_p.add_argument("--from", dest="from_phase", help="Resume from specific phase")

    # fork
    fork_p = sub.add_parser("fork", help="Fork to new iteration")
    fork_p.add_argument("--enter", help="State to enter (e.g., PLAN, IDEA_REFINE)")
    fork_p.add_argument("--idea", help="New idea for the fork")
    fork_p.add_argument("source_iter", nargs="?", type=int, help="Source iteration to fork from")

    # board
    board_p = sub.add_parser("board", help="Show results dashboard")
    board_p.add_argument("--iter", type=int, help="Specific iteration")

    # intervene
    intervene_p = sub.add_parser("intervene", help="Send intervention")
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


def _cmd_init(project_dir: Path, preset: str) -> None:
    """Initialize research project with a workflow preset."""
    from .paths import research_dir, workflow_path, shared_dir

    rd = research_dir(project_dir)
    rd.mkdir(parents=True, exist_ok=True)
    shared_dir(project_dir).mkdir(parents=True, exist_ok=True)

    # Copy preset to .workflow.yaml
    preset_file = Path(__file__).parent / "presets" / f"{preset}.yaml"
    if not preset_file.exists():
        print(f"Preset not found: {preset}")
        sys.exit(1)

    wf_path = workflow_path(project_dir)
    shutil.copy2(preset_file, wf_path)
    print(f"Initialized with preset: {preset}")
    print(f"Workflow: {wf_path}")
    print(f"Edit research/.workflow.yaml to customize.")

    # Copy hooks
    hooks_src = Path(__file__).parent / "hooks"
    hooks_dst = project_dir / ".claude" / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for hook in hooks_src.glob("*.sh"):
        dst = hooks_dst / hook.name
        shutil.copy2(hook, dst)
        dst.chmod(0o755)
    print(f"Hooks installed: {hooks_dst}")

    # Copy prompt templates
    prompts_src = Path(__file__).parent / "prompts"
    prompts_dst = project_dir / "prompts"
    if prompts_src.exists():
        shutil.copytree(prompts_src, prompts_dst, dirs_exist_ok=True)
        print(f"Prompts installed: {prompts_dst}")


def _cmd_run(project_dir: Path, idea: str | None) -> None:
    """Start the research loop."""
    from .engine import Engine
    from .paths import workflow_path

    if not workflow_path(project_dir).exists():
        print("Not initialized. Run 'tiny-lab init' first.")
        sys.exit(1)

    if idea:
        # Store idea for IDEA_REFINE to pick up
        idea_file = project_dir / "research" / ".user_idea.txt"
        idea_file.write_text(idea)
        log(f"User idea: {idea}")

    engine = Engine(project_dir)
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
    import yaml
    from .paths import intervention_path

    ipath = intervention_path(project_dir)
    ipath.parent.mkdir(parents=True, exist_ok=True)
    ipath.write_text(yaml.dump({"action": "stop"}))
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
    engine = Engine(project_dir)
    engine.run()


def _cmd_fork(project_dir: Path, enter: str | None, idea: str | None, source_iter: int | None) -> None:
    """Fork to new iteration."""
    from .state import load_state, set_state
    from .paths import iter_dir

    ls = load_state(project_dir)
    source = source_iter or ls.current_iteration
    new_iter = source + 1

    # Create new iteration
    from .engine import Engine
    engine = Engine(project_dir)
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
    from .paths import results_dir, iterations_path
    import json

    ls = load_state(project_dir)
    target_iter = iteration or ls.current_iteration

    print(f"=== Iteration {target_iter} ===")
    rdir = results_dir(project_dir, target_iter)
    if rdir.exists():
        for f in sorted(rdir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                print(f"\n{f.stem}:")
                for k, v in data.items():
                    print(f"  {k}: {v}")
            except Exception:
                print(f"\n{f.stem}: (parse error)")
    else:
        print("No results yet.")

    # Show iterations history
    ipath = iterations_path(project_dir)
    if ipath.exists():
        import yaml
        data = yaml.safe_load(ipath.read_text())
        iters = data.get("iterations", [])
        if iters:
            print(f"\n=== Iteration History ===")
            for it in iters:
                print(f"  iter_{it['id']}: {it.get('decision', '?')} — {it.get('reason', '')[:80]}")


def _cmd_intervene(project_dir: Path, action: str, extra_args: list[str]) -> None:
    """Write intervention file."""
    import yaml
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
    ipath.write_text(yaml.dump(intervention))
    print(f"Intervention sent: {action}")
