#!/usr/bin/env python3
"""PostToolUse hook — verify references in artifacts that contain citations.

Triggers when Claude writes a file matching a reference-bearing artifact
pattern (e.g., .domain_research.json, .diverge.json). Runs the verifier
in best-effort mode: errors do NOT block tool execution.

Output: .ref_verification.json sidecar next to the source file.
"""
import fnmatch
import json
import os
import sys
from pathlib import Path

# Patterns of files whose writes should trigger verification.
# Matches the discovery globs in tiny_lab/refs.py.
_TRIGGER_PATTERNS = (
    "*/.domain_research.json",
    "*/.diverge.json",
    "*/.papers_collected.json",
    "*/.paper_analysis.json",
    "*/.related_work.json",
    "*/.evaluation_matrix.json",
)


def main() -> int:
    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    written_file = os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", "")
    if not written_file:
        return 0

    # Match against trigger patterns
    matches = any(
        fnmatch.fnmatch(written_file, p) or fnmatch.fnmatch(written_file, "*/" + p)
        for p in _TRIGGER_PATTERNS
    )
    if not matches:
        return 0

    src = Path(written_file)
    if not src.exists():
        return 0

    # Late import — keep hook startup lean for non-matching writes.
    try:
        from tiny_lab.refs import verify_file, write_verification
    except ImportError:
        # tiny-lab not on PYTHONPATH (e.g. user opened the project before
        # installing). Bail silently — verification is opt-in safety net.
        return 0

    try:
        result = verify_file(src)
    except Exception as e:
        print(f"ref_verify: skipped ({e})")
        return 0

    if result.total == 0:
        return 0  # nothing to verify in this artifact

    out = write_verification(src, result)
    summary = (
        f"references: {result.verified}/{result.total} verified  "
        f"(not_found={result.not_found}, unverified={result.unverified}, "
        f"error={result.error})"
    )
    print(f"ref_verify: {summary} → {out.name}")

    # Non-blocking: even if some refs are not_found, return 0 so the engine
    # can decide what to do (e.g., evaluate_matrix.md applies a penalty).
    return 0


if __name__ == "__main__":
    sys.exit(main())
