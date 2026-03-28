#!/bin/bash
# PreToolUse hook — enforces state constraints from workflow.yaml
# Blocks Write/Edit/Bash operations not allowed in current state.
#
# Reads workflow.yaml dynamically — no hardcoded state logic.

WORKFLOW="research/.workflow.yaml"
STATE_FILE="research/.state.json"

# Skip if no state file (not initialized yet)
[[ ! -f "$STATE_FILE" ]] && exit 0
[[ ! -f "$WORKFLOW" ]] && exit 0

STATE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('state','INIT'))" 2>/dev/null)
ITER=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('current_iteration',1))" 2>/dev/null)
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
FILE_PATH="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"
COMMAND="${CLAUDE_TOOL_INPUT_COMMAND:-}"

[[ "$STATE" == "INIT" ]] && exit 0

# Extract state rules from workflow.yaml
RULES=$(python3 << PYEOF
import yaml, json, sys

try:
    wf = yaml.safe_load(open("$WORKFLOW"))
    state = next((s for s in wf.get("states", []) if s["id"] == "$STATE"), None)
    if state:
        print(json.dumps(state))
    else:
        print("{}")
except Exception:
    print("{}")
PYEOF
)

STATE_TYPE=$(echo "$RULES" | python3 -c "import json,sys; print(json.load(sys.stdin).get('type',''))" 2>/dev/null)

# Checkpoint states: block all writes
if [[ "$STATE_TYPE" == "checkpoint" ]]; then
    if [[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]]; then
        echo "BLOCKED [$STATE]: checkpoint 상태에서는 쓰기 불가. intervention을 기다리세요."
        exit 1
    fi
fi

# Check allowed_write_globs for Write/Edit
if [[ ("$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit") && -n "$FILE_PATH" ]]; then
    python3 << PYEOF
import json, sys, fnmatch

rules = json.loads('''$RULES''')
globs = rules.get("allowed_write_globs", [])

# If no globs defined, allow all writes (permissive default)
if not globs:
    sys.exit(0)

target = "$FILE_PATH"
iter_str = "iter_$ITER"

for pattern in globs:
    resolved = pattern.replace("{iter}", iter_str)
    if fnmatch.fnmatch(target, resolved) or fnmatch.fnmatch(target, "*/" + resolved):
        sys.exit(0)

print(f"BLOCKED [$STATE]: {target} 는 이 상태에서 허용되지 않음")
print(f"허용 경로: {[p.replace('{iter}', iter_str) for p in globs]}")
sys.exit(1)
PYEOF
    [[ $? -ne 0 ]] && exit 1
fi

# Check blocked_bash_patterns for Bash
if [[ "$TOOL_NAME" == "Bash" && -n "$COMMAND" ]]; then
    python3 << PYEOF
import json, sys

rules = json.loads('''$RULES''')
patterns = rules.get("blocked_bash_patterns", [])

for pattern in patterns:
    if pattern in "$COMMAND":
        print(f"BLOCKED [$STATE]: 이 명령은 현재 상태에서 금지됨 ({pattern})")
        sys.exit(1)

sys.exit(0)
PYEOF
    [[ $? -ne 0 ]] && exit 1
fi
