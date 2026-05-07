"""Validation helpers for phase code provenance."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .paths import normalize_project_relative_path


def audit_code_provenance(project_dir: Path, iteration: int, data: dict[str, Any]) -> list[str]:
    """Validate that result provenance points to the executed phase script."""
    path_entries = [
        (path, value)
        for path, value in _walk_named_values(data)
        if _leaf_key(path) in CODE_PATH_FIELDS
    ]
    hash_entries = [
        (path, value)
        for path, value in _walk_named_values(data)
        if _leaf_key(path) in CODE_HASH_FIELDS
    ]
    if not path_entries:
        if hash_entries:
            return ["code provenance hash requires script_path or code_path"]
        return []

    issues: list[str] = []
    rel_paths: list[tuple[str, Path]] = []
    for field, value in path_entries:
        try:
            rel_paths.append(
                (field, normalize_project_relative_path(project_dir, value, "code provenance path"))
            )
        except ValueError as e:
            issues.append(str(e))
    if issues:
        return issues
    unique_paths = {path.as_posix() for _, path in rel_paths}
    if len(unique_paths) > 1:
        issues.append(f"code provenance paths disagree: {sorted(unique_paths)}")

    path_field, rel_path = rel_paths[0]
    expected_prefix = Path("research") / f"iter_{iteration}" / "phases"
    try:
        rel_path.relative_to(expected_prefix)
    except ValueError:
        issues.append(f"code provenance path must be under {expected_prefix.as_posix()}/")
    if issues:
        return issues
    full_path = project_dir / rel_path
    if not full_path.exists():
        return [f"code provenance file not found: {path_entries[0][1]}"]
    try:
        expected_hash = "sha256:" + hashlib.sha256(full_path.read_bytes()).hexdigest()
    except OSError as e:
        return [f"could not read code provenance file {path_entries[0][1]}: {e}"]

    if not hash_entries:
        issues.append("code provenance must include at least one script/code hash")
    for field, value in hash_entries:
        if not isinstance(value, str) or _normalize_hash(value) != expected_hash:
            issues.append(f"{field} does not match {path_entries[0][1]}")
    return issues


def _normalize_hash(value: str) -> str:
    text = value.strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return "sha256:" + text
    return text


def _walk_named_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_walk_named_values(item, child_prefix))
        return out
    if isinstance(value, list):
        out: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.extend(_walk_named_values(item, child_prefix))
        return out
    return [(prefix, value)]


def _leaf_key(path: str) -> str:
    return path.split(".")[-1].split("[", 1)[0]


CODE_HASH_FIELDS = (
    "script_sha256",
    "script_sha",
    "script_hash",
    "code_sha256",
    "code_sha",
    "code_hash",
    "source_hash",
)


CODE_PATH_FIELDS = (
    "script_path",
    "code_path",
)
