#!/usr/bin/env python3
"""PostToolUse hook — detects artifact creation and advances state.

When AI writes the completion artifact for the current state,
this hook validates required fields and transitions to the next state.

Dual-mode: works under both Claude Code and Codex CLI.
"""
import sys
from pathlib import Path

# Sibling import — same trick as state_gate.py
sys.path.insert(0, str(Path(__file__).parent))
from command_paths import bash_write_target_paths  # noqa: E402
from hook_io import WRITE_TOOL_NAMES, read_hook_input  # noqa: E402

# Source-tree import when hooks are run directly from src/tiny_lab/hooks.
# Installed-package imports still work when hooks are copied into .claude/hooks.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tiny_lab.advancement import (  # type: ignore  # noqa: E402
        apply_state_transition,
        resolve_runner_completion_advance,
        transition_starts_new_iteration,
    )
    from tiny_lab.final_paper import try_write_traceable_final_paper_for_problem  # type: ignore  # noqa: E402
    from tiny_lab.runner_contract import load_runner_state_snapshot  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover - hooks should fail open if package import is unavailable
    apply_state_transition = None
    resolve_runner_completion_advance = None
    try_write_traceable_final_paper_for_problem = None
    load_runner_state_snapshot = None
    transition_starts_new_iteration = None


def main() -> int:
    hook = read_hook_input(event_name="PostToolUse")
    if hook.tool_name not in WRITE_TOOL_NAMES and hook.tool_name != "Bash":
        return 0

    written_files = hook.file_paths
    if hook.tool_name == "Bash":
        written_files = tuple(bash_write_target_paths(hook.command))
    if not written_files:
        return 0

    if (
        load_runner_state_snapshot is None
        or resolve_runner_completion_advance is None
        or apply_state_transition is None
        or transition_starts_new_iteration is None
    ):
        return 0

    snapshot = load_runner_state_snapshot(Path.cwd())
    if snapshot is None:
        return 0

    contract = snapshot.contract
    # Silent on terminal states — same reasoning as state_gate.py
    if contract.state in ("INIT", "DONE"):
        return 0

    if not snapshot.state_spec or not contract.completion_artifact:
        return 0

    # Only ai_session states auto-advance via hook
    if contract.state_type != "ai_session":
        return 0

    for written_file in written_files:
        advance = resolve_runner_completion_advance(
            Path.cwd(),
            contract,
            written_file=written_file,
        )
        if not advance.relevant:
            continue
        if advance.problem:
            fallback_advance = _try_final_paper_fallback(Path.cwd(), contract, written_file, advance.problem)
            if fallback_advance is not None:
                advance = fallback_advance
            else:
                print(advance.problem[:1].upper() + advance.problem[1:])
                return 0
        if advance.problem:
            print(advance.problem[:1].upper() + advance.problem[1:])
            return 0
        if not advance.next_state:
            return 0

        apply_state_transition(
            Path.cwd(),
            advance.next_state,
            current_state=snapshot.state_data,
            new_iteration_on_entry=transition_starts_new_iteration(contract.state, advance.next_state),
        )
        print(f"State: {contract.state} → {advance.next_state}")
        return 0
    return 0


def _try_final_paper_fallback(project_dir: Path, contract, written_file: str | Path, problem: str):
    if try_write_traceable_final_paper_for_problem is None:
        return None
    if not str(written_file).endswith("research/final_paper.md"):
        return None
    try:
        wrote = try_write_traceable_final_paper_for_problem(project_dir, contract.iteration, problem)
    except Exception:
        return None
    if not wrote:
        return None
    fallback_advance = resolve_runner_completion_advance(
        project_dir,
        contract,
        written_file=written_file,
    )
    if not fallback_advance.relevant or fallback_advance.problem:
        return None
    print("Traceable final paper fallback applied")
    return fallback_advance


if __name__ == "__main__":
    sys.exit(main())
