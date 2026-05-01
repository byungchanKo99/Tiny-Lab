#!/usr/bin/env python3
"""PreToolUse hook — enforces state constraints from workflow.json.

Blocks Write/Edit/Bash operations not allowed in current state.
Reads workflow.json dynamically — no hardcoded state logic.

Dual-mode: works under both Claude Code (env vars + exit code) and
Codex CLI (stdin JSON + JSON response). Detection is automatic.
"""
import fnmatch
import json
import os
import sys
from pathlib import Path

# Allow this file to be invoked directly as a script — make sibling import work.
sys.path.insert(0, str(Path(__file__).parent))
from hook_io import deny, info, read_hook_input, allow  # noqa: E402, F401

WORKFLOW = Path("research/.workflow.json")
STATE_FILE = Path("research/.state.json")

# tiny-lab "owns" these top-level directories. Writes outside these paths
# are not the workflow's concern and pass through untouched even when a
# state is active. Critical for native skill mode where the same Claude/
# Codex session may interleave unrelated work.
_TINY_LAB_ROOTS = ("research/", "shared/")


def main() -> int:
    if not STATE_FILE.exists() or not WORKFLOW.exists():
        return 0

    try:
        state_data = json.loads(STATE_FILE.read_text())
        wf_data = json.loads(WORKFLOW.read_text())
    except (json.JSONDecodeError, OSError):
        return 0

    current_state = state_data.get("state", "INIT")
    iteration = state_data.get("current_iteration", 1)
    # Silent on terminal states — no enforcement needed and we must not
    # interfere with the user's parallel work in native skill mode.
    if current_state in ("INIT", "DONE"):
        return 0

    hook = read_hook_input(event_name="PreToolUse")
    tool_name = hook.tool_name
    file_path = hook.file_path
    command = hook.command

    # Find current state spec
    spec = next((s for s in wf_data.get("states", []) if s["id"] == current_state), None)
    if not spec:
        return 0

    # Checkpoint states: block writes inside tiny-lab territory only
    if spec.get("type") == "checkpoint" and tool_name in ("Write", "Edit"):
        if _is_tiny_lab_path(file_path):
            deny(hook, f"BLOCKED [{current_state}]: checkpoint 상태에서는 tiny-lab 영역 쓰기 불가. intervention을 기다리세요.")
        return 0

    # Check allowed_write_globs for Write/Edit
    if tool_name in ("Write", "Edit") and file_path:
        if not _is_tiny_lab_path(file_path):
            return 0  # Outside tiny-lab — not our concern.

        globs = spec.get("allowed_write_globs", [])
        if not globs:
            return 0  # No globs declared = allow all

        iter_str = f"iter_{iteration}"
        for pattern in globs:
            resolved = pattern.replace("{iter}", iter_str)
            if fnmatch.fnmatch(file_path, resolved) or fnmatch.fnmatch(file_path, "*/" + resolved):
                return 0

        resolved_globs = [p.replace("{iter}", iter_str) for p in globs]
        deny(
            hook,
            f"BLOCKED [{current_state}]: {file_path} 는 이 상태에서 허용되지 않음\n"
            f"허용 경로: {resolved_globs}",
        )

    # Check blocked_bash_patterns for Bash
    if tool_name == "Bash" and command:
        for pattern in spec.get("blocked_bash_patterns", []):
            if pattern in command:
                deny(hook, f"BLOCKED [{current_state}]: 이 명령은 현재 상태에서 금지됨 ({pattern})")

    return 0


def _is_tiny_lab_path(file_path: str) -> bool:
    if not file_path:
        return False
    p = file_path.lstrip("./")
    if any(p.startswith(root) for root in _TINY_LAB_ROOTS):
        return True
    cwd = os.getcwd().rstrip("/") + "/"
    if file_path.startswith(cwd):
        rel = file_path[len(cwd):]
        if any(rel.startswith(root) for root in _TINY_LAB_ROOTS):
            return True
    return any(f"/{root}" in file_path for root in _TINY_LAB_ROOTS)


if __name__ == "__main__":
    sys.exit(main())
