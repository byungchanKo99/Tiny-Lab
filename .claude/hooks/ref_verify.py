#!/usr/bin/env python3
"""PostToolUse hook — verify references in artifacts that contain citations.

Triggers when Claude writes a file matching a reference-bearing artifact
pattern (e.g., .domain_research.json, .diverge.json). Runs the verifier
in best-effort mode: errors do NOT block tool execution.

Output: .ref_verification.json sidecar next to the source file.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from command_paths import bash_write_target_paths  # noqa: E402
from hook_io import WRITE_TOOL_NAMES, read_hook_input  # noqa: E402

def main() -> int:
    hook = read_hook_input(event_name="PostToolUse")
    if hook.tool_name not in WRITE_TOOL_NAMES and hook.tool_name != "Bash":
        return 0

    written_files = list(hook.file_paths)
    if hook.tool_name == "Bash":
        written_files = bash_write_target_paths(hook.command)
    if not written_files:
        return 0

    for written_file in written_files:
        _verify_written_file(written_file)
    return 0


def _verify_written_file(written_file: str) -> None:
    if not _matches_trigger(written_file):
        return
    src = Path(written_file)
    if not src.exists():
        return

    # Late import — keep hook startup lean for non-matching writes.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from tiny_lab.refs import verify_file, write_verification
    except ImportError:
        # tiny-lab not on PYTHONPATH (e.g. user opened the project before
        # installing). Bail silently — verification is opt-in safety net.
        return

    try:
        result = verify_file(src)
    except Exception as e:
        print(f"ref_verify: skipped ({e})")
        return

    if result.total == 0:
        return  # nothing to verify in this artifact

    out = write_verification(src, result)
    summary = (
        f"references: {result.verified}/{result.total} verified  "
        f"(not_found={result.not_found}, unverified={result.unverified}, "
        f"error={result.error})"
    )
    print(f"ref_verify: {summary} → {out.name}")


def _matches_trigger(written_file: str) -> bool:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from tiny_lab.refs import is_reference_artifact_candidate_path

        return is_reference_artifact_candidate_path(written_file)
    except ImportError:
        return _fallback_reference_artifact_candidate_path(written_file)


def _fallback_reference_artifact_candidate_path(written_file: str) -> bool:
    candidate = Path(written_file)
    text = candidate.as_posix()
    if text.endswith(".ref_verification.json"):
        return False
    parts = candidate.parts
    if any(part in {".", ".."} for part in parts):
        return False
    return any(
        part == "research"
        and index + 2 == len(parts) - 1
        and re.fullmatch(r"iter_\d+", parts[index + 1]) is not None
        and parts[index + 2].endswith(".json")
        for index, part in enumerate(parts[:-2])
    )


if __name__ == "__main__":
    sys.exit(main())
