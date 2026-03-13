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
  CHECK_QUEUE → SELECT → BUILD → OPTIMIZE → EVALUATE → RECORD → CHECK_QUEUE
  When queue empties → GENERATE (AI creates new hypotheses) → CHECK_QUEUE
  OPTIMIZE runs inner loop (optuna/grid/random) if search_space defined, else single RUN

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
    init_parser.add_argument("--update", action="store_true",
                             help="Overwrite existing template files (backs up to .bak first)")

    run_parser = sub.add_parser(
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
    run_parser.add_argument("--until-idle", action="store_true",
        help="Stop the loop when the initial queue is exhausted instead of generating new hypotheses. "
             "Use for finite comparisons (e.g. 'compare 5 models').")
    run_parser.add_argument("--on-event", metavar="CMD",
        help="Shell command to execute on loop events. "
             "Receives TINYLAB_EVENT and TINYLAB_EVENT_DATA env vars. "
             "Example: --on-event 'tiny-lab status --json >> /tmp/lab.log'")

    status_parser = sub.add_parser(
        "status",
        help="Show loop state, queue counts, and last 5 experiment results",
        description="Outputs: RUNNING/STOPPED, current state (select/run/evaluate/generate), "
                    "queue breakdown (pending/done/skipped counts), and last 5 ledger entries "
                    "with verdict (WIN/LOSS/INVALID) and metric values. Use this to confirm "
                    "the loop is alive after starting, and to monitor progress.",
    )
    status_parser.add_argument("--json", dest="as_json", action="store_true",
                                help="Output structured JSON with action_needed field")

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
    board_parser.add_argument("--live", action="store_true",
                              help="Start live dashboard on localhost (auto-refreshing HTML, default port 8505)")
    board_parser.add_argument("--port", type=int, default=8505,
                              help="Port for live dashboard (default: 8505)")
    board_parser.add_argument("--refresh", type=int, default=5,
                              help="Auto-refresh interval in seconds for live dashboard (default: 5)")
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
        cmd_init(project_dir, global_install=args.global_install, update=args.update)
    elif args.command == "discover":
        cmd_discover(project_dir, " ".join(args.intent) if args.intent else "")
    elif args.command == "board":
        cmd_board(project_dir, args)
    elif args.command == "run":
        cmd_run(project_dir, on_event_cmd=getattr(args, "on_event", None),
                until_idle=getattr(args, "until_idle", False))
    elif args.command == "status":
        cmd_status(project_dir, as_json=getattr(args, "as_json", False))
    else:
        commands = {
            "stop": cmd_stop,
            "generate": cmd_generate,
        }
        commands[args.command](project_dir)


def _templates_dir() -> Path:
    """Get the templates directory bundled with the package."""
    return Path(__file__).parent / "templates"


def cmd_init(project_dir: Path, *, global_install: bool = False, update: bool = False) -> None:
    """Initialize a new experiment project."""
    from .providers import detect_provider, get_provider

    templates = _templates_dir()
    provider_name = detect_provider()
    provider = get_provider(project_dir, provider_name)

    created = []
    skipped = []
    updated = []

    for src_rel, dst_rel in provider.get_template_files():
        src = templates / src_rel
        dst = project_dir / dst_rel

        if dst.exists():
            if update:
                backup = dst.with_suffix(dst.suffix + ".bak")
                shutil.copy2(dst, backup)
                shutil.copy2(src, dst)
                if dst_rel.endswith(".sh"):
                    dst.chmod(dst.stat().st_mode | 0o111)
                updated.append(dst_rel)
            else:
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
    if updated:
        print("Updated (backup → .bak):")
        for f in updated:
            print(f"  {f}")
    if skipped:
        print("Skipped (already exists):")
        for f in skipped:
            print(f"  {f}")

    from .paths import ledger_path, project_yaml_path
    if not ledger_path(project_dir).exists():
        ledger_path(project_dir).touch()
        print("  research/ledger.jsonl (empty)")

    # Write detected provider into project.yaml
    project_yaml = project_yaml_path(project_dir)
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

    print("\n" + "=" * 60)
    print("AGENT RULES:")
    print("1. NEVER run `tiny-lab stop` unless the user explicitly asks.")
    print("2. Always run in background: tiny-lab run > research/tiny_lab_run.out 2>&1 &")
    print("3. For finite comparisons: tiny-lab run --until-idle")
    print("4. The loop auto-generates new hypotheses. Do NOT stop it early.")
    print("=" * 60)



def cmd_run(project_dir: Path, *, on_event_cmd: str | None = None, until_idle: bool = False) -> None:
    """Start the research loop."""
    from .loop import ResearchLoop
    loop = ResearchLoop(project_dir, on_event_cmd=on_event_cmd, until_idle=until_idle)
    raise SystemExit(loop.run())


def _build_status_data(project_dir: Path) -> dict[str, Any]:
    """Build structured status data."""
    from .dashboard import build_status_data
    return build_status_data(project_dir)


def _format_status(data: dict[str, Any]) -> None:
    """Print human-readable status from data dict."""
    pid = data.get("pid")
    print(f"Loop: {data['loop']}" + (f" (pid={pid})" if pid else ""))
    if data["loop"] == "RUNNING":
        print("Reminder: Do NOT run `tiny-lab stop` unless the user explicitly asks.")

    if data.get("state"):
        print(f"State: {data['state']} (updated: {data.get('updated_at', '?')})")
    if data.get("current_hypothesis"):
        print(f"Current hypothesis: {data['current_hypothesis']}")

    queue = data.get("queue", {})
    parts = [f"{k}: {v}" for k, v in sorted(queue.items())]
    print(f"Queue: {', '.join(parts) if parts else 'empty'}")

    recent = data.get("recent_experiments", [])
    if recent:
        print("\nRecent experiments:")
        for row in recent:
            print(f"  {row['id']}: {row.get('class', '?')} | {row.get('metric', {})} | {row.get('description', '')}")


def cmd_status(project_dir: Path, *, as_json: bool = False) -> None:
    """Show loop status."""
    data = _build_status_data(project_dir)
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        _format_status(data)


def cmd_stop(project_dir: Path) -> None:
    """Stop the running loop."""
    from .paths import lock_path as _lock_path
    lock_path = _lock_path(project_dir)
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
    from .generate import generate_hypotheses
    from .queue import load_queue, pending_hypotheses
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
    from .dashboard import build_board_data
    return build_board_data(project_dir)


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
    baseline_cmd = data.get("baseline_command", "")
    if baseline_cmd:
        print(f"Baseline {metric_name}: {baseline} | {baseline_cmd}")
    else:
        print(f"Baseline {metric_name}: {baseline}")
    print()

    if best_row:
        bpm = best_row.get("primary_metric", {})
        value_display = _format_value(best_row.get("value"))
        best_line = f"Best: {best_row['id']} — {metric_name}={bpm.get(metric_name)} (delta={bpm.get('delta_pct')}%)"
        if best_row.get("approach"):
            best_line += f" [{best_row['approach']}]"
        else:
            best_line += f" [{best_row.get('changed_variable')}={value_display}]"
        opt = best_row.get("optimize_result")
        if opt:
            best_line += f" ({opt.get('n_trials', '?')} trials, {opt.get('total_seconds', '?')}s)"
        print(best_line)
    print()

    print("Results: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    print("Queue: " + ", ".join(f"{k}: {v}" for k, v in sorted(queue_counts.items())))
    print()

    recent = ledger[-10:]
    if recent:
        print(f"{'ID':<10} {'Verdict':<12} {metric_name:<15} {'Delta%':<10} {'Config':<30} {'Reasoning'}")
        print("-" * 120)
        for row in recent:
            pm = row.get("primary_metric", {})
            val = pm.get(metric_name, "N/A")
            delta = pm.get("delta_pct", "N/A")
            # Config: use approach for v2, else ledger config dict, else changed_variable=value
            if row.get("approach"):
                config_str = row["approach"]
                opt = row.get("optimize_result")
                if opt:
                    config_str += f" ({opt.get('n_trials', '?')}T, {opt.get('total_seconds', '?')}s)"
            else:
                config = row.get("config", {})
                if config and "baseline_command" not in config:
                    config_str = ", ".join(f"{k}={v}" for k, v in config.items())
                elif row.get("changed_variable") and row.get("value"):
                    config_str = f"{row['changed_variable']}={_format_value(row['value'])}"
                else:
                    config_str = ""
            # Reasoning: use reasoning field, fallback to question
            reasoning = row.get("reasoning", "") or row.get("question", "")
            reasoning = reasoning[:60]
            print(f"{row.get('id', '?'):<10} {row.get('class', '?'):<12} {str(val):<15} {str(delta):<10} {config_str:<30} {reasoning}")
    else:
        print("No experiments yet.")

    recent_events = data.get("recent_events", [])
    if recent_events:
        print()
        print("Events:")
        for ev in recent_events:
            ts = ev.get("timestamp", "")
            # Show HH:MM:SS from ISO timestamp
            time_part = ts[11:19] if len(ts) >= 19 else ts
            event_name = ev.get("event", "?")
            ev_data = ev.get("data", {})
            detail_parts = []
            for k, v in ev_data.items():
                detail_parts.append(f"{k}={v}")
            detail = " ".join(detail_parts)
            line = f"  [{time_part}] {event_name}"
            if detail:
                line += f" ({detail})"
            print(line)

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
    do_live = getattr(args, "live", False) if args else False
    output_path = getattr(args, "output", None) if args else None

    if do_live:
        from .server import serve_dashboard
        port = getattr(args, "port", 8505)
        refresh = getattr(args, "refresh", 5)
        serve_dashboard(project_dir, port=port, refresh=refresh)
    elif export_fmt:
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
