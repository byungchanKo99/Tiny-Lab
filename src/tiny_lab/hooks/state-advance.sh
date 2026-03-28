#!/bin/bash
# PostToolUse hook — detects artifact creation and advances state.
#
# When AI writes the completion artifact for the current state,
# this hook validates required fields and transitions to the next state.

WORKFLOW="research/.workflow.yaml"
STATE_FILE="research/.state.json"

# Skip if not initialized
[[ ! -f "$STATE_FILE" ]] && exit 0
[[ ! -f "$WORKFLOW" ]] && exit 0

# Only trigger on Write/Edit
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0

STATE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('state','INIT'))" 2>/dev/null)
ITER=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('current_iteration',1))" 2>/dev/null)
WRITTEN_FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"

[[ -z "$WRITTEN_FILE" ]] && exit 0

python3 << PYEOF
import yaml, json, sys, glob as g
from pathlib import Path

try:
    wf = yaml.safe_load(open("$WORKFLOW"))
except Exception:
    sys.exit(0)

state = next((s for s in wf.get("states", []) if s["id"] == "$STATE"), None)
if not state or "completion" not in state:
    sys.exit(0)

# Only ai_session states auto-advance via hook
if state.get("type") != "ai_session":
    sys.exit(0)

comp = state["completion"]
artifact_pattern = comp.get("artifact", "")
if not artifact_pattern:
    sys.exit(0)

resolved = artifact_pattern.replace("{iter}", "iter_$ITER")

# Check if the written file matches the completion artifact pattern
import fnmatch
written = "$WRITTEN_FILE"
if not (fnmatch.fnmatch(written, resolved) or
        fnmatch.fnmatch(written, "*/" + resolved)):
    sys.exit(0)

# Validate required fields
required = comp.get("required_fields", [])
if required:
    try:
        data = yaml.safe_load(Path(written).read_text())
        if not isinstance(data, dict):
            print(f"Completion artifact is not a dict: {written}")
            sys.exit(0)  # Don't block, just don't advance
        missing = [f for f in required if f not in data]
        if missing:
            print(f"Missing required fields: {missing}")
            sys.exit(0)  # Don't advance until all fields present
    except Exception as e:
        print(f"Could not validate artifact: {e}")
        sys.exit(0)

# Advance state
next_state = state.get("next")
if not isinstance(next_state, str):
    sys.exit(0)  # Conditional next handled by process, not hook

state_data = json.load(open("$STATE_FILE"))
old_state = state_data.get("state", "?")
state_data["state"] = next_state
with open("$STATE_FILE", "w") as f:
    json.dump(state_data, f, indent=2)

print(f"✅ State: {old_state} → {next_state}")
PYEOF
