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
  tiny-lab run --max-iter 10    Override max iterations
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
                                 "data-analysis", "custom"],
                        help="Workflow preset (default: ml-experiment)")

    # run
    run_p = sub.add_parser("run", help="Start the research loop",
                           description="Run the full auto loop. Iterates until goal achieved or max iterations.")
    run_p.add_argument("idea", nargs="?", help="Research idea (also saved to research/.user_idea.txt)")
    run_p.add_argument("--max-iter", type=int, default=None,
                       help="Override max iterations (default: from preset)")
    run_p.add_argument("--model", default="sonnet",
                       choices=["sonnet", "haiku", "opus"],
                       help="Claude model (default: sonnet)")

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

    # shape — write constraints.json directly (skip SHAPE_FULL state)
    shape_p = sub.add_parser("shape", help="Write constraints.json directly (skip interactive SHAPE_FULL)",
                             description="Create constraints.json from a JSON string or file, then set state to DOMAIN_RESEARCH.")
    shape_p.add_argument("constraints_file", help="Path to constraints JSON file, or '-' for stdin")

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
        _cmd_run(project_dir, args.idea, args.max_iter, args.model)
    elif args.command == "status":
        _cmd_status(project_dir)
    elif args.command == "stop":
        _cmd_stop(project_dir)
    elif args.command == "resume":
        _cmd_resume(project_dir, args.add_phase, args.from_phase)
    elif args.command == "fork":
        _cmd_fork(project_dir, args.enter, args.idea, args.source_iter)
    elif args.command == "shape":
        _cmd_shape(project_dir, args.constraints_file)
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
    gate_cmd = "python3 .claude/hooks/state_gate.py"
    # Remove old sh hook if present
    pre[:] = [e for e in pre if e.get("command") != ".claude/hooks/state-gate.sh"]
    if not any(e.get("command") == gate_cmd for e in pre):
        pre.append({"matcher": "Write|Edit|Bash", "command": gate_cmd})

    # PostToolUse: state-advance detects artifacts and transitions
    post = hooks.setdefault("PostToolUse", [])
    advance_cmd = "python3 .claude/hooks/state_advance.py"
    # Remove old sh hook if present
    post[:] = [e for e in post if e.get("command") != ".claude/hooks/state-advance.sh"]
    if not any(e.get("command") == advance_cmd for e in post):
        post.append({"matcher": "Write|Edit", "command": advance_cmd})

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
    for hook in hooks_src.glob("*.py"):
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


def _cmd_run(
    project_dir: Path,
    idea: str | None,
    max_iter: int | None = None,
    model: str = "sonnet",
) -> None:
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

    engine = Engine(project_dir, _load_registry(project_dir), model=model)

    if max_iter is not None:
        engine.workflow.autonomy.max_iterations = max_iter
        log(f"Max iterations overridden: {max_iter}")

    log(f"Model: {model}")
    engine.run()


def _cmd_shape(project_dir: Path, constraints_file: str) -> None:
    """Write constraints.json and advance past SHAPE_FULL."""
    import json
    from .paths import research_dir, constraints_path, iter_dir
    from .state import load_state, set_state

    rd = research_dir(project_dir)
    rd.mkdir(parents=True, exist_ok=True)

    # Read constraints from file or stdin
    if constraints_file == "-":
        data = json.loads(sys.stdin.read())
    else:
        data = json.loads(Path(constraints_file).read_text())

    # Validate required fields
    for field in ("objective", "goal", "invariants"):
        if field not in data:
            print(f"Error: constraints must have '{field}' field")
            sys.exit(1)

    # Write constraints.json
    cpath = constraints_path(project_dir)
    cpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Constraints written: {cpath}")

    # Ensure iter_1 exists
    idir = iter_dir(project_dir, 1)
    idir.mkdir(parents=True, exist_ok=True)
    (idir / "phases").mkdir(exist_ok=True)
    (idir / "results").mkdir(exist_ok=True)

    # Set state past SHAPE_FULL
    ls = load_state(project_dir)
    if ls.state in ("INIT", "SHAPE_FULL"):
        set_state(project_dir, "DOMAIN_RESEARCH", current_iteration=1)
        print("State: → DOMAIN_RESEARCH (skipped SHAPE_FULL)")
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

    # Reflect
    reflect_file = idir / "reflect.json" if idir.exists() else None
    if reflect_file and reflect_file.exists():
        reflect = json.loads(reflect_file.read_text())
        print(f"Reflect: {reflect.get('decision', '?')} — {reflect.get('reason', '')[:100]}")

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
