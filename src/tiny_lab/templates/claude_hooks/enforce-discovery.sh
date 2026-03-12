#!/bin/bash
# enforce-discovery.sh — Gate discovery phases via state file
#
# Blocks Write/Edit to research config files unless the agent
# has progressed through the required phases in order.
#
# Phase order: SCAN → ANALYZE (or ASK_DATA) → CONCRETIZE → SETUP → CONFIRM
#
# The agent updates research/.discovery_state.yaml at the end of each phase.
# This hook reads that file and blocks premature actions.

set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name')
CWD=$(echo "$INPUT" | jq -r '.cwd')

STATE_FILE="$CWD/research/.discovery_state.yaml"

# --- Helper: read current phase from state file ---
get_phase() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "NONE"
    return
  fi
  grep "^phase:" "$STATE_FILE" 2>/dev/null | awk '{print $2}' || echo "NONE"
}

# --- Gate: Write/Edit to research config files ---
if [[ "$TOOL" == "Write" || "$TOOL" == "Edit" ]]; then
  FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
  [[ -z "$FILE" ]] && exit 0

  # Only gate research config files written during discovery
  case "$FILE" in
    */research/project.yaml|*/research/questions.yaml|*/research/hypothesis_queue.yaml)
      PHASE=$(get_phase)
      case "$PHASE" in
        SETUP|CONFIRM|DONE)
          # Allowed — agent is in the right phase
          exit 0
          ;;
        CONCRETIZE)
          echo "Phase is CONCRETIZE — project.yaml 작성은 SETUP Phase에서 해주세요. 먼저 7개 필드를 모두 확정하세요." >&2
          exit 2
          ;;
        ANALYZE|ASK_DATA)
          echo "Phase is $PHASE — 아직 데이터 분석/수집 중입니다. CONCRETIZE와 SETUP을 먼저 완료하세요." >&2
          exit 2
          ;;
        SCAN)
          echo "Phase is SCAN — 환경 스캔이 먼저 필요합니다. 디렉토리를 탐색하고 데이터/스크립트를 찾으세요." >&2
          exit 2
          ;;
        NONE)
          echo "Discovery가 시작되지 않았습니다. /research 명령으로 디스커버리를 시작하세요. SCAN Phase부터 진행해야 합니다." >&2
          exit 2
          ;;
        *)
          # Unknown phase — don't block, let agent proceed
          exit 0
          ;;
      esac
      ;;
    */research/.discovery_state.yaml)
      # Always allow updating the state file itself
      exit 0
      ;;
    *)
      # Not a gated file
      exit 0
      ;;
  esac
fi

# --- Gate: Bash running baseline command before SETUP ---
if [[ "$TOOL" == "Bash" ]]; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

  # Block tiny-lab run before CONFIRM
  if echo "$COMMAND" | grep -q "tiny-lab run"; then
    PHASE=$(get_phase)
    case "$PHASE" in
      CONFIRM|DONE)
        exit 0
        ;;
      NONE|SCAN|ANALYZE|ASK_DATA|CONCRETIZE|SETUP)
        echo "Phase is ${PHASE:-NONE} — tiny-lab run은 CONFIRM Phase에서만 실행할 수 있습니다. 모든 Phase를 순서대로 완료하세요." >&2
        exit 2
        ;;
    esac
  fi
fi

# Everything else — allow
exit 0
