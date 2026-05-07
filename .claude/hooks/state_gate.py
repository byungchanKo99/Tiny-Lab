#!/usr/bin/env python3
"""PreToolUse hook — enforces state constraints from RunnerStateContract.

Blocks Write/Edit/Bash operations not allowed in current state.
Consumes the shared runner contract dynamically — no hardcoded state logic.

Dual-mode: works under both Claude Code (env vars + exit code) and
Codex CLI (stdin JSON + JSON response). Detection is automatic.
"""
import sys
from pathlib import Path

# Allow this file to be invoked directly as a script — make sibling import work.
sys.path.insert(0, str(Path(__file__).parent))
from hook_io import deny, info, read_hook_input, allow  # noqa: E402, F401
from state_policy import evaluate_runner_state_gate  # noqa: E402

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tiny_lab.runner_contract import load_runner_state_snapshot  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover - hooks should fail open if package import is unavailable
    load_runner_state_snapshot = None

def main() -> int:
    if load_runner_state_snapshot is None:
        return 0

    snapshot = load_runner_state_snapshot(Path.cwd())
    if snapshot is None:
        return 0

    current_state = snapshot.contract.state
    # Silent on terminal states — no enforcement needed and we must not
    # interfere with the user's parallel work in native skill mode.
    if current_state in ("INIT", "DONE"):
        return 0

    hook = read_hook_input(event_name="PreToolUse")
    tool_name = hook.tool_name
    file_paths = hook.file_paths
    command = hook.command

    decision = evaluate_runner_state_gate(
        snapshot.contract.to_dict(),
        snapshot.state_data,
        tool_name=tool_name,
        file_paths=file_paths,
        command=command,
        root=Path.cwd(),
    )
    if not decision.allowed:
        deny(hook, decision.reason or f"BLOCKED [{current_state}]: state gate denied tool use")

    return 0


if __name__ == "__main__":
    sys.exit(main())
