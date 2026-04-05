#!/usr/bin/env python3
"""PreToolUse hook — enforces state constraints from workflow.json.

Blocks Write/Edit/Bash operations not allowed in current state.
Reads workflow.json dynamically — no hardcoded state logic.
"""
import fnmatch
import json
import os
import sys
from pathlib import Path

WORKFLOW = Path("research/.workflow.json")
STATE_FILE = Path("research/.state.json")


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
    if current_state == "INIT":
        return 0

    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
    file_path = os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", "")
    command = os.environ.get("CLAUDE_TOOL_INPUT_COMMAND", "")

    # Find current state spec
    spec = next((s for s in wf_data.get("states", []) if s["id"] == current_state), None)
    if not spec:
        return 0

    # Checkpoint states: block all writes
    if spec.get("type") == "checkpoint" and tool_name in ("Write", "Edit"):
        print(f"BLOCKED [{current_state}]: checkpoint 상태에서는 쓰기 불가. intervention을 기다리세요.")
        return 1

    # Check allowed_write_globs for Write/Edit
    if tool_name in ("Write", "Edit") and file_path:
        globs = spec.get("allowed_write_globs", [])
        if not globs:
            return 0  # No globs defined = allow all

        iter_str = f"iter_{iteration}"
        for pattern in globs:
            resolved = pattern.replace("{iter}", iter_str)
            if fnmatch.fnmatch(file_path, resolved) or fnmatch.fnmatch(file_path, "*/" + resolved):
                return 0

        resolved_globs = [p.replace("{iter}", iter_str) for p in globs]
        print(f"BLOCKED [{current_state}]: {file_path} 는 이 상태에서 허용되지 않음")
        print(f"허용 경로: {resolved_globs}")
        return 1

    # Check blocked_bash_patterns for Bash
    if tool_name == "Bash" and command:
        for pattern in spec.get("blocked_bash_patterns", []):
            if pattern in command:
                print(f"BLOCKED [{current_state}]: 이 명령은 현재 상태에서 금지됨 ({pattern})")
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
