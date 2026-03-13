#!/bin/bash
# bump-version-reminder.sh
#
# Stop hook: src/tiny_lab/ 에 uncommitted 변경사항이 있는데
# pyproject.toml 버전이 올라가지 않았으면 Claude에게 다시 알린다.

set -uo pipefail

PROJ="${CLAUDE_PROJECT_DIR:-.}"

# src/tiny_lab/ 에 uncommitted 변경사항 있는지 확인
src_changed=$(git -C "$PROJ" diff HEAD -- src/tiny_lab/ 2>/dev/null | grep -c "^+[^+]" 2>/dev/null || true)
src_changed=${src_changed:-0}

# pyproject.toml 버전이 변경됐는지 확인
version_bumped=$(git -C "$PROJ" diff HEAD -- pyproject.toml 2>/dev/null | grep -c "^\+version" 2>/dev/null || true)
version_bumped=${version_bumped:-0}

if [ "$src_changed" -gt 0 ] && [ "$version_bumped" -eq 0 ]; then
    current=$(python3 -c "
import re, sys
content = open('$PROJ/pyproject.toml').read()
m = re.search(r'^version\s*=\s*\"([^\"]+)\"', content, re.M)
print(m.group(1) if m else '?')
" 2>/dev/null || echo "?")
    python3 -c "
import json
msg = 'src/tiny_lab/ 코드가 변경되었지만 pyproject.toml의 version이 아직 그대로입니다 (현재: $current). 작업이 완료됐다면 버전을 올려주세요.'
print(json.dumps({'decision': 'block', 'reason': msg}))
"
fi

# __init__.py에 하드코딩된 버전이 있으면 경고
if grep -q '__version__\s*=\s*"[0-9]' "$PROJ/src/tiny_lab/__init__.py" 2>/dev/null; then
    python3 -c "
import json
msg = '__init__.py에 하드코딩된 버전이 있습니다. importlib.metadata를 사용하세요.'
print(json.dumps({'decision': 'block', 'reason': msg}))
"
fi
