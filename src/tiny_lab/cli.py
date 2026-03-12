"""CLI entry point for tiny-lab."""
from __future__ import annotations

import argparse
import importlib.resources
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(prog="tiny-lab", description="Deterministic AI-driven research loop")
    parser.add_argument("--project-dir", default=".", help="Project root directory")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize a new experiment project")
    sub.add_parser("run", help="Start the research loop")
    sub.add_parser("status", help="Show loop status")
    sub.add_parser("stop", help="Stop the running loop")
    sub.add_parser("generate", help="Generate new hypotheses")
    sub.add_parser("board", help="Show experiment dashboard")
    discover_parser = sub.add_parser("discover", help="Interactive research setup (works with any AI provider)")
    discover_parser.add_argument("intent", nargs="*", help="What you want to research (natural language)")
    setup_parser = sub.add_parser("setup", help="Install /research command for Claude Code")
    setup_parser.add_argument("--global", dest="global_install", action="store_true",
                              help="Install globally to ~/.claude/ instead of project-level")

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "status": cmd_status,
        "stop": cmd_stop,
        "generate": cmd_generate,
        "board": cmd_board,
        "setup": cmd_setup,
    }
    if args.command == "setup":
        cmd_setup(project_dir, global_install=args.global_install)
    elif args.command == "discover":
        cmd_discover(project_dir, " ".join(args.intent) if args.intent else "")
    else:
        commands[args.command](project_dir)


def _templates_dir() -> Path:
    """Get the templates directory bundled with the package."""
    return Path(__file__).parent / "templates"


def cmd_init(project_dir: Path) -> None:
    """Copy template files into the project directory."""
    templates = _templates_dir()

    copies = [
        ("project.yaml", "research/project.yaml"),
        ("hypothesis_queue.yaml", "research/hypothesis_queue.yaml"),
        ("questions.yaml", "research/questions.yaml"),
        ("claude_agents/hypothesis-generator.md", ".claude/agents/hypothesis-generator.md"),
        ("claude_agents/code-modifier.md", ".claude/agents/code-modifier.md"),
        ("claude_agents/ux-evaluator.md", ".claude/agents/ux-evaluator.md"),
        ("claude_commands/research.md", ".claude/commands/research.md"),
        ("claude_hooks/enforce-discovery.sh", ".claude/hooks/enforce-discovery.sh"),
        ("claude_settings.json", ".claude/settings.json"),
        ("CLAUDE.md", "CLAUDE.md"),
    ]

    created = []
    skipped = []

    for src_rel, dst_rel in copies:
        src = templates / src_rel
        dst = project_dir / dst_rel

        if dst.exists():
            skipped.append(dst_rel)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # Make hook scripts executable
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

    print("\nEdit research/project.yaml to configure your experiment, then run: tiny-lab run")


def cmd_setup(project_dir: Path, *, global_install: bool = False) -> None:
    """Install /research command for Claude Code."""
    templates = _templates_dir()

    if global_install:
        target_dir = Path.home() / ".claude"
        scope = "globally"
    else:
        target_dir = project_dir / ".claude"
        scope = f"for this project ({project_dir})"

    copies = [
        ("claude_commands/research.md", "commands/research.md"),
    ]

    created = []
    updated = []

    for src_rel, dst_rel in copies:
        src = templates / src_rel
        dst = target_dir / dst_rel

        dst.parent.mkdir(parents=True, exist_ok=True)

        if dst.exists():
            if dst.read_text() != src.read_text():
                shutil.copy2(src, dst)
                updated.append(str(dst))
            else:
                print(f"  Already up to date: {dst}")
        else:
            shutil.copy2(src, dst)
            created.append(str(dst))

    if created:
        print("Installed:")
        for f in created:
            print(f"  {f}")
    if updated:
        print("Updated:")
        for f in updated:
            print(f"  {f}")

    print(f"""
Setup complete {scope}! You can now use /research in Claude Code.

Quick start:
  /research 하고 싶은 연구를 자연어로 설명

Or manually:
  tiny-lab init          # Scaffold full project files
  tiny-lab run           # Start the research loop

Tip: Use --global to install for all projects (~/.claude/).
""")


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
    from .loop import ResearchLoop

    project = load_project(project_dir)
    loop = ResearchLoop(project_dir)

    before = len(pending_hypotheses(load_queue(project_dir)))
    generate_hypotheses(project, project_dir, loop._run_ai)
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
    from .loop import ResearchLoop, CLAUDE_BIN, CODEX_BIN

    templates = _templates_dir()
    research_md = templates / "claude_commands" / "research.md"

    # Read the discovery mode instructions
    instructions = research_md.read_text()

    # Determine provider
    project_yaml = project_dir / "research" / "project.yaml"
    if project_yaml.exists():
        data = yaml.safe_load(project_yaml.read_text()) or {}
        provider = data.get("agent", {}).get("provider", "claude")
    else:
        provider = os.environ.get("TINYLAB_PROVIDER", "claude")

    prompt = f"""You are running the /research discovery mode.

USER INTENT: {intent if intent else "(user will describe interactively)"}

Follow the Discovery Mode instructions below EXACTLY. Execute phases in order.
The working directory is: {project_dir}

{instructions}

Start with Phase 1: SCAN. Scan the current directory and proceed through the phases."""

    print(f"Starting discovery mode (provider: {provider})...")
    print(f"Project directory: {project_dir}")
    if intent:
        print(f"Intent: {intent}")
    print()

    if provider == "codex":
        if not shutil.which(CODEX_BIN):
            print(f"Error: codex CLI not found. Install it or set agent.provider: claude")
            return
        cmd = [CODEX_BIN, "exec", prompt, "-s", "workspace-write", "-a", "on-request"]
    else:
        if not shutil.which(CLAUDE_BIN):
            print(f"Error: claude CLI not found. Install it or set agent.provider: codex")
            return
        env_key = "CLAUDECODE"
        cmd = [CLAUDE_BIN, "-p", prompt,
               "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
               "--max-turns", "50", "--output-format", "text"]

    # Run interactively (not captured — user sees output directly)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(cmd, cwd=str(project_dir), env=env)
    raise SystemExit(result.returncode)


def cmd_board(project_dir: Path) -> None:
    """Show experiment dashboard."""
    from .project import load_project
    from .ledger import load_ledger, get_baseline_metric
    from .generate import load_queue

    try:
        project = load_project(project_dir)
    except FileNotFoundError:
        print("No project.yaml found. Run 'tiny-lab init' first.")
        return

    metric_name = project["metric"]["name"]
    ledger = load_ledger(project_dir)
    baseline = get_baseline_metric(project_dir, metric_name)
    queue = load_queue(project_dir)

    print(f"Project: {project['name']}")
    print(f"Metric: {metric_name} (direction: {project['metric'].get('direction', 'minimize')})")
    print(f"Baseline {metric_name}: {baseline}")
    print()

    # Win/Loss/Invalid counts
    counts: dict[str, int] = {}
    for row in ledger:
        c = row.get("class", "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1
    print("Results: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))

    # Queue
    queue_counts: dict[str, int] = {}
    for h in queue:
        s = h.get("status", "unknown")
        queue_counts[s] = queue_counts.get(s, 0) + 1
    print("Queue: " + ", ".join(f"{k}: {v}" for k, v in sorted(queue_counts.items())))
    print()

    # Last 10 experiments
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
