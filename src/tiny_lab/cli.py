"""CLI entry point for tiny-lab."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
from pathlib import Path
from typing import Any

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tiny-lab",
        description="Deterministic AI-driven research loop",
        epilog="""\
Lifecycle:
  tiny-lab init                          # scaffold project (once)
  tiny-lab discover "optimize accuracy"  # AI-guided setup → project.yaml + hypotheses
  CYCLE_SLEEP=1 tiny-lab run &           # start infinite loop in background
  tiny-lab status                        # confirm RUNNING
  tiny-lab board                         # check WIN/LOSS results
  tiny-lab stop                          # graceful shutdown when done

The loop is an INFINITE state machine:
  CHECK_QUEUE → SELECT → BUILD → RUN → EVALUATE → RECORD → CHECK_QUEUE
  When queue empties → GENERATE (AI creates new hypotheses) → CHECK_QUEUE

Environment variables:
  CYCLE_SLEEP     Seconds between experiment cycles (default: 30, recommend: 1)
  TINYLAB_PROVIDER  Force provider: "claude" or "codex" (default: auto-detect)
  CLAUDE_MAX_TURNS  Max turns for Claude provider (default: 20)

Key files (in research/):
  project.yaml          Experiment config: baseline, metric, levers, rules
  hypothesis_queue.yaml Hypothesis queue (pending/running/done/skipped)
  ledger.jsonl          Experiment results (append-only, DO NOT modify)
  loop.log              Loop execution log
  .loop-lock            PID lock file (use 'tiny-lab stop', not kill)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project-dir", default=".", help="Project root directory (default: cwd)")
    sub = parser.add_subparsers(dest="command")

    init_parser = sub.add_parser(
        "init",
        help="Scaffold project: create research/ dir, config templates, agent instructions",
        description="Creates research/ directory with project.yaml, hypothesis_queue.yaml, "
                    "questions.yaml, and provider-specific agent configs. Auto-detects "
                    "Claude Code or Codex CLI. Skips files that already exist.",
    )
    init_parser.add_argument("--global", dest="global_install", action="store_true",
                             help="Also install /research slash command to ~/.claude/ (Claude only)")

    sub.add_parser(
        "run",
        help="Start the experiment loop (INFINITE — run in background with &)",
        description="Starts the research loop state machine. This command NEVER exits on its own — "
                    "it runs experiments indefinitely until stopped via 'tiny-lab stop' or circuit "
                    "breaker (5 INVALID in last 20). MUST be run in background:\n\n"
                    "  CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &\n\n"
                    "The loop: picks hypothesis → builds command → runs experiment → evaluates "
                    "result → records to ledger.jsonl → repeats. When queue empties, AI generates "
                    "new hypotheses automatically (GENERATE phase).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub.add_parser(
        "status",
        help="Show loop state, queue counts, and last 5 experiment results",
        description="Outputs: RUNNING/STOPPED, current state (select/run/evaluate/generate), "
                    "queue breakdown (pending/done/skipped counts), and last 5 ledger entries "
                    "with verdict (WIN/LOSS/INVALID) and metric values. Use this to confirm "
                    "the loop is alive after starting, and to monitor progress.",
    )

    sub.add_parser(
        "stop",
        help="Send SIGTERM to running loop (graceful shutdown after current experiment)",
        description="Reads PID from research/.loop-lock and sends SIGTERM. The loop finishes "
                    "its current experiment, records the result, then exits cleanly. "
                    "If the process is already dead, removes the stale lock file.",
    )

    sub.add_parser(
        "generate",
        help="Manually trigger AI hypothesis generation (normally automatic in loop)",
        description="Calls the AI provider to analyze ledger.jsonl, diagnose research state "
                    "(EXPLORING/REFINING/SATURATED/STUCK), and generate 3-5 new hypotheses. "
                    "The AI may also modify project.yaml (add levers, extend search spaces, "
                    "raise baseline). Useful for manual intervention without restarting the loop. "
                    "Output: number of new hypotheses added to queue.",
    )

    board_parser = sub.add_parser(
        "board",
        help="Show experiment dashboard: best result, WIN/LOSS counts, metric trends",
        description="Displays project name, metric, baseline, best experiment found, "
                    "result class counts (WIN/LOSS/INVALID), queue status, last 10 experiments "
                    "with delta%%, and generation history (AI reasoning for each GENERATE cycle). "
                    "This is the primary way to understand research progress at a glance.",
    )
    board_parser.add_argument("--export", choices=["csv", "json"],
                              help="Export ledger as CSV or JSON (id, class, lever, value, metric, delta%%)")
    board_parser.add_argument("--plot", action="store_true",
                              help="Add ASCII sparklines: metric trend over time + per-lever WIN/LOSS bars")
    board_parser.add_argument("--html", metavar="FILE", nargs="?", const="research/report.html",
                              help="Generate self-contained HTML report with Chart.js visualizations")
    board_parser.add_argument("-o", "--output", help="Output file path (for --export)")

    discover_parser = sub.add_parser(
        "discover",
        help="AI-guided interactive setup: analyze data → propose metrics/levers → write configs",
        description="Starts an interactive AI session that: (1) scans for data/script files, "
                    "(2) analyzes columns to find metric and lever candidates, (3) asks user to "
                    "confirm choices, (4) writes project.yaml + hypothesis_queue.yaml + questions.yaml, "
                    "(5) verifies baseline command works. Works with any provider (Claude/Codex).",
    )
    discover_parser.add_argument("intent", nargs="*",
                                 help="Research intent in natural language (e.g. 'optimize hotel cancellation prediction')")

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "init":
        cmd_init(project_dir, global_install=args.global_install)
    elif args.command == "discover":
        cmd_discover(project_dir, " ".join(args.intent) if args.intent else "")
    elif args.command == "board":
        cmd_board(project_dir, args)
    else:
        commands = {
            "run": cmd_run,
            "status": cmd_status,
            "stop": cmd_stop,
            "generate": cmd_generate,
        }
        commands[args.command](project_dir)


def _templates_dir() -> Path:
    """Get the templates directory bundled with the package."""
    return Path(__file__).parent / "templates"


def cmd_init(project_dir: Path, *, global_install: bool = False) -> None:
    """Initialize a new experiment project."""
    from .providers import detect_provider, get_provider

    templates = _templates_dir()
    provider_name = detect_provider()
    provider = get_provider(project_dir, provider_name)

    created = []
    skipped = []

    for src_rel, dst_rel in provider.get_template_files():
        src = templates / src_rel
        dst = project_dir / dst_rel

        if dst.exists():
            skipped.append(dst_rel)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst_rel.endswith(".sh"):
            dst.chmod(dst.stat().st_mode | 0o111)
        created.append(dst_rel)

    if created:
        print("Created:")
        for f in created:
            print(f"  {f}")
    if skipped:
        print("Skipped (already exists):")
        for f in skipped:
            print(f"  {f}")

    if not (project_dir / "research" / "ledger.jsonl").exists():
        (project_dir / "research" / "ledger.jsonl").touch()
        print("  research/ledger.jsonl (empty)")

    # Write detected provider into project.yaml
    project_yaml = project_dir / "research" / "project.yaml"
    if project_yaml.exists():
        content = project_yaml.read_text()
        content = content.replace("provider: claude", f"provider: {provider_name}")
        project_yaml.write_text(content)

    # --global: also install /research command to ~/.claude/ for all projects
    if global_install and provider_name == "claude":
        global_dst = Path.home() / ".claude" / "commands" / "research.md"
        global_src = templates / "claude" / "commands" / "research.md"
        global_dst.parent.mkdir(parents=True, exist_ok=True)
        if not global_dst.exists() or global_dst.read_text() != global_src.read_text():
            shutil.copy2(global_src, global_dst)
            print(f"  {global_dst} (global /research command)")

    print(f"\nProvider: {provider_name}")
    if provider_name == "claude":
        print("Start with: /research <what you want to research>")
        print("Or: tiny-lab discover <what you want to research>")
    else:
        print("Start with: tiny-lab discover <what you want to research>")



def cmd_run(project_dir: Path) -> None:
    """Start the research loop."""
    from .loop import ResearchLoop
    loop = ResearchLoop(project_dir)
    raise SystemExit(loop.run())


def cmd_status(project_dir: Path) -> None:
    """Show loop status."""
    state_path = project_dir / "research" / ".loop_state.json"
    lock_path = project_dir / "research" / ".loop-lock"
    queue_path = project_dir / "research" / "hypothesis_queue.yaml"
    ledger_path = project_dir / "research" / "ledger.jsonl"

    # Loop alive?
    alive = False
    pid = None
    if lock_path.exists():
        try:
            pid = int(lock_path.read_text().strip())
            os.kill(pid, 0)
            alive = True
        except (ValueError, OSError):
            pass

    print(f"Loop: {'RUNNING (pid={pid})' if alive else 'STOPPED'}")

    # State
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            print(f"State: {state.get('state', '?')} (updated: {state.get('updated_at', '?')})")
            ctx = state.get("context", {})
            if ctx.get("hypothesis_id"):
                print(f"Current hypothesis: {ctx['hypothesis_id']}")
        except json.JSONDecodeError:
            pass

    # Queue stats
    if queue_path.exists():
        data = yaml.safe_load(queue_path.read_text()) or {}
        hypotheses = data.get("hypotheses", [])
        counts = {}
        for h in hypotheses:
            s = h.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
        print(f"Queue: {', '.join(parts) if parts else 'empty'}")

    # Recent ledger
    if ledger_path.exists():
        lines = ledger_path.read_text().strip().splitlines()
        recent = lines[-5:] if lines else []
        if recent:
            print("\nRecent experiments:")
            for raw in recent:
                try:
                    row = json.loads(raw)
                    metric = row.get("primary_metric", {})
                    metric_val = {k: v for k, v in metric.items() if k not in ("baseline", "delta_pct")}
                    print(f"  {row['id']}: {row.get('class', '?')} | {metric_val} | {row.get('question', '')[:60]}")
                except json.JSONDecodeError:
                    pass


def cmd_stop(project_dir: Path) -> None:
    """Stop the running loop."""
    lock_path = project_dir / "research" / ".loop-lock"
    if not lock_path.exists():
        print("No running loop found.")
        return

    try:
        pid = int(lock_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to pid {pid}")
    except ValueError:
        print("Invalid lock file")
    except OSError as e:
        print(f"Could not stop loop: {e}")
        lock_path.unlink(missing_ok=True)
        print("Removed stale lock file")


def cmd_generate(project_dir: Path) -> None:
    """Manually trigger hypothesis generation."""
    from .project import load_project
    from .generate import generate_hypotheses, load_queue, pending_hypotheses
    from .providers import get_provider

    project = load_project(project_dir)
    provider = get_provider(project_dir)

    before = len(pending_hypotheses(load_queue(project_dir)))
    generate_hypotheses(project, project_dir, provider)
    after = len(pending_hypotheses(load_queue(project_dir)))

    added = after - before
    if added > 0:
        print(f"Generated {added} new hypotheses.")
    else:
        print("No new hypotheses generated.")


def cmd_discover(project_dir: Path, intent: str = "") -> None:
    """Interactive research setup using AI provider.

    Portable alternative to /research slash command — works with any provider.
    Reads research.md discovery instructions and runs the AI interactively.
    """
    from .providers import get_provider

    templates = _templates_dir()
    research_md = templates / "claude" / "commands" / "research.md"

    # Read the discovery mode instructions
    instructions = research_md.read_text()

    provider = get_provider(project_dir)

    prompt = f"""You are running the /research discovery mode.

USER INTENT: {intent if intent else "(user will describe interactively)"}

Follow the Discovery Mode instructions below EXACTLY. Execute phases in order.
The working directory is: {project_dir}

{instructions}

Start with Phase 1: SCAN. Scan the current directory and proceed through the phases."""

    print(f"Starting discovery mode (provider: {provider.name})...")
    print(f"Project directory: {project_dir}")
    if intent:
        print(f"Intent: {intent}")
    print()

    result = provider.run_interactive(prompt, cwd=str(project_dir))
    raise SystemExit(result.returncode)


def _build_board_data(project_dir: Path) -> dict[str, Any] | None:
    """Load and compute all data needed for the experiment dashboard."""
    from .project import load_project
    from .ledger import load_ledger, get_baseline_metric
    from .generate import load_queue, load_generate_history

    try:
        project = load_project(project_dir)
    except FileNotFoundError:
        return None

    metric_name = project["metric"]["name"]
    direction = project["metric"].get("direction", "minimize")
    ledger = load_ledger(project_dir)
    baseline = get_baseline_metric(project_dir, metric_name)
    queue = load_queue(project_dir)

    # Best result
    best_row = None
    for row in ledger:
        if row.get("class") == "BASELINE":
            continue
        val = row.get("primary_metric", {}).get(metric_name)
        if val is None:
            continue
        if best_row is None:
            best_row = row
        else:
            best_val = best_row.get("primary_metric", {}).get(metric_name)
            if direction == "maximize" and val > best_val:
                best_row = row
            elif direction == "minimize" and val < best_val:
                best_row = row

    # Class counts
    counts: dict[str, int] = {}
    for row in ledger:
        c = row.get("class", "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1

    # Queue counts
    queue_counts: dict[str, int] = {}
    for h in queue:
        s = h.get("status", "unknown")
        queue_counts[s] = queue_counts.get(s, 0) + 1

    return {
        "project": project,
        "metric_name": metric_name,
        "direction": direction,
        "ledger": ledger,
        "baseline": baseline,
        "best_row": best_row,
        "counts": counts,
        "queue_counts": queue_counts,
        "gen_history": load_generate_history(project_dir),
    }


def _format_value(value: Any) -> str:
    """Format a hypothesis value for display. Handles both str and dict (multi-lever)."""
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def _format_board(data: dict[str, Any]) -> None:
    """Print the experiment dashboard from pre-computed data."""
    metric_name = data["metric_name"]
    direction = data["direction"]
    baseline = data["baseline"]
    ledger = data["ledger"]
    best_row = data["best_row"]
    counts = data["counts"]
    queue_counts = data["queue_counts"]
    gen_history = data["gen_history"]

    print(f"Project: {data['project']['name']}")
    print(f"Metric: {metric_name} (direction: {direction})")
    print(f"Baseline {metric_name}: {baseline}")
    print()

    if best_row:
        bpm = best_row.get("primary_metric", {})
        value_display = _format_value(best_row.get("value"))
        print(f"Best: {best_row['id']} — {metric_name}={bpm.get(metric_name)} (delta={bpm.get('delta_pct')}%) "
              f"[{best_row.get('changed_variable')}={value_display}]")
    print()

    print("Results: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    print("Queue: " + ", ".join(f"{k}: {v}" for k, v in sorted(queue_counts.items())))
    print()

    recent = ledger[-10:]
    if recent:
        print(f"{'ID':<10} {'Verdict':<12} {metric_name:<15} {'Delta%':<10} {'Description'}")
        print("-" * 80)
        for row in recent:
            pm = row.get("primary_metric", {})
            val = pm.get(metric_name, "N/A")
            delta = pm.get("delta_pct", "N/A")
            desc = row.get("question", "")[:40]
            print(f"{row.get('id', '?'):<10} {row.get('class', '?'):<12} {str(val):<15} {str(delta):<10} {desc}")
    else:
        print("No experiments yet.")

    if gen_history:
        print()
        print("Generation History:")
        print("-" * 80)
        for entry in gen_history[-5:]:
            ts = entry.get("timestamp", "?")[:19]
            state = entry.get("state", "?")
            added = entry.get("hypotheses_added_count", 0)
            reasoning = entry.get("reasoning", "")[:60]
            hyp_ids = ", ".join(entry.get("hypotheses_added", []))
            print(f"  [{ts}] {state} — +{added} hypotheses")
            if reasoning:
                print(f"    Why: {reasoning}")
            if hyp_ids:
                print(f"    Added: {hyp_ids}")
            changes = entry.get("changes_made", [])
            if changes:
                print(f"    Changes: {'; '.join(changes)}")


def _export_board(data: dict[str, Any], fmt: str, output_path: str | None) -> None:
    """Export board data as CSV or JSON."""
    import csv
    import io

    metric_name = data["metric_name"]
    ledger = data["ledger"]

    if fmt == "json":
        rows = []
        for row in ledger:
            pm = row.get("primary_metric", {})
            rows.append({
                "id": row.get("id"),
                "class": row.get("class"),
                "changed_variable": row.get("changed_variable"),
                "value": row.get("value"),
                metric_name: pm.get(metric_name),
                "baseline": pm.get("baseline"),
                "delta_pct": pm.get("delta_pct"),
                "question": row.get("question"),
            })
        text = json.dumps(rows, indent=2, ensure_ascii=False)
    else:
        buf = io.StringIO()
        fields = ["id", "class", "changed_variable", "value", metric_name, "baseline", "delta_pct", "question"]
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for row in ledger:
            pm = row.get("primary_metric", {})
            writer.writerow({
                "id": row.get("id"),
                "class": row.get("class"),
                "changed_variable": row.get("changed_variable"),
                "value": row.get("value"),
                metric_name: pm.get(metric_name),
                "baseline": pm.get("baseline"),
                "delta_pct": pm.get("delta_pct"),
                "question": row.get("question"),
            })
        text = buf.getvalue()

    if output_path:
        Path(output_path).write_text(text)
        print(f"Exported to {output_path}")
    else:
        print(text)


def _format_sparklines(data: dict[str, Any]) -> None:
    """Print ASCII sparkline charts for metric trends and lever win/loss ratios."""
    metric_name = data["metric_name"]
    ledger = data["ledger"]
    blocks = " ▁▂▃▄▅▆▇█"

    # Metric trend sparkline
    values = []
    for row in ledger:
        if row.get("class") == "BASELINE":
            continue
        val = row.get("primary_metric", {}).get(metric_name)
        if val is not None:
            values.append(val)

    if values:
        lo, hi = min(values), max(values)
        span = hi - lo if hi != lo else 1
        spark = "".join(blocks[min(8, int((v - lo) / span * 8))] for v in values)
        print(f"Metric trend ({metric_name}): {spark}  [{lo:.4g} .. {hi:.4g}]")
    else:
        print(f"Metric trend ({metric_name}): (no data)")

    # Per-lever win/loss ratio
    lever_stats: dict[str, dict[str, int]] = {}
    for row in ledger:
        if row.get("class") in ("BASELINE", None):
            continue
        lever = row.get("changed_variable", "?")
        if lever not in lever_stats:
            lever_stats[lever] = {"WIN": 0, "LOSS": 0, "INVALID": 0, "INCONCLUSIVE": 0}
        cls = row.get("class", "INVALID")
        if cls in lever_stats[lever]:
            lever_stats[lever][cls] += 1

    if lever_stats:
        print()
        print("Lever stats:")
        for lever, stats in sorted(lever_stats.items()):
            total = stats["WIN"] + stats["LOSS"]
            ratio = f"{stats['WIN']}/{total}" if total else "0/0"
            bar_len = min(stats["WIN"], 20)
            bar = "█" * bar_len + "░" * (min(total, 20) - bar_len) if total else ""
            print(f"  {lever:<20} W/L: {ratio:<8} {bar}  (+{stats['INVALID']} invalid)")


def cmd_board(project_dir: Path, args: argparse.Namespace | None = None) -> None:
    """Show experiment dashboard."""
    data = _build_board_data(project_dir)
    if data is None:
        print("No project.yaml found. Run 'tiny-lab init' first.")
        return

    export_fmt = getattr(args, "export", None) if args else None
    do_plot = getattr(args, "plot", False) if args else False
    html_path = getattr(args, "html", None) if args else None
    output_path = getattr(args, "output", None) if args else None

    if export_fmt:
        _export_board(data, export_fmt, output_path)
    elif do_plot:
        _format_board(data)
        print()
        _format_sparklines(data)
    elif html_path:
        from .report import generate_html_report
        out = project_dir / html_path
        generate_html_report(data, out)
        print(f"Report written to {out}")
    else:
        _format_board(data)
