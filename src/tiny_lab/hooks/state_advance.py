#!/usr/bin/env python3
"""PostToolUse hook — detects artifact creation and advances state.

When AI writes the completion artifact for the current state,
this hook validates required fields and transitions to the next state.
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

    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    written_file = os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", "")
    if not written_file:
        return 0

    try:
        state_data = json.loads(STATE_FILE.read_text())
        wf_data = json.loads(WORKFLOW.read_text())
    except (json.JSONDecodeError, OSError):
        return 0

    current_state = state_data.get("state", "INIT")
    iteration = state_data.get("current_iteration", 1)

    # Find current state spec
    spec = next((s for s in wf_data.get("states", []) if s["id"] == current_state), None)
    if not spec or "completion" not in spec:
        return 0

    # Only ai_session states auto-advance via hook
    if spec.get("type") != "ai_session":
        return 0

    comp = spec["completion"]
    artifact_pattern = comp.get("artifact", "")
    if not artifact_pattern:
        return 0

    iter_str = f"iter_{iteration}"
    resolved = artifact_pattern.replace("{iter}", iter_str)

    # Check if written file matches completion artifact pattern
    if not (fnmatch.fnmatch(written_file, resolved) or
            fnmatch.fnmatch(written_file, "*/" + resolved)):
        return 0

    # Validate required fields
    required = comp.get("required_fields", [])
    if required:
        try:
            data = json.loads(Path(written_file).read_text())
            if not isinstance(data, dict):
                print(f"Completion artifact is not a dict: {written_file}")
                return 0
            missing = [f for f in required if f not in data]
            if missing:
                print(f"Missing required fields: {missing}")
                return 0
        except Exception as e:
            print(f"Could not validate artifact: {e}")
            return 0

    # Resolve next state
    next_state = spec.get("next")
    if isinstance(next_state, str):
        resolved_next = next_state
    elif isinstance(next_state, dict) and "condition" in spec:
        resolved_next = _resolve_conditional_next(spec, next_state, iter_str)
        if not resolved_next:
            return 0  # Let engine handle
    else:
        return 0

    # Advance state
    state_data["state"] = resolved_next
    STATE_FILE.write_text(json.dumps(state_data, indent=2) + "\n")
    print(f"State: {current_state} → {resolved_next}")
    return 0


def _resolve_conditional_next(spec: dict, next_map: dict, iter_str: str) -> str | None:
    """Resolve conditional next from artifact field."""
    cond = spec["condition"]
    source = cond.get("source")
    field = cond.get("field")

    if not source or not field:
        return None  # Builtin check conditions handled by engine

    try:
        cond_path = Path("research") / source.replace("{iter}", iter_str)
        cond_data = json.loads(cond_path.read_text())
        value = str(cond_data.get(field, ""))
        return next_map.get(value)
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
