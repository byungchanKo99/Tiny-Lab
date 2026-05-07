"""Centralized path definitions for tiny-lab."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

RESEARCH_ARTIFACT_PATH_RE = re.compile(
    r"\bresearch/(?:final_paper\.md|iter_\d+/[A-Za-z0-9_./-]+\.(?:json|png|md))\b"
)
RESEARCH_RESULT_JSON_PATH_RE = re.compile(
    r"\bresearch/iter_\d+/results/[A-Za-z0-9_./-]+\.json\b"
)
RESEARCH_RESULT_PNG_PATH_RE = re.compile(
    r"\bresearch/iter_\d+/results/[A-Za-z0-9_./-]+\.png\b"
)


def research_dir(project_dir: Path) -> Path:
    return project_dir / "research"


def shared_dir(project_dir: Path) -> Path:
    return project_dir / "shared"


def knowledge_dir(project_dir: Path) -> Path:
    return shared_dir(project_dir) / "knowledge"


def constraints_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "constraints.json"


def convergence_log_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / "convergence_log.json"


def workflow_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".workflow.json"


def state_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".state.json"


def intervention_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".intervention.json"


def iterations_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".iterations.json"


def lock_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".loop-lock"


def active_backend_path(project_dir: Path) -> Path:
    return research_dir(project_dir) / ".active_backend.json"


def iter_dir(project_dir: Path, iteration: int) -> Path:
    return research_dir(project_dir) / f"iter_{iteration}"


def iteration_number_from_dir_name(name: str) -> int | None:
    match = re.fullmatch(r"iter_(\d+)", name)
    if match is None:
        return None
    return int(match.group(1))


def is_iteration_dir_name(name: str) -> bool:
    return iteration_number_from_dir_name(name) is not None


def iteration_dirs(project_dir: Path) -> list[Path]:
    """Return official numeric research iteration directories."""
    return [
        path
        for path in sorted(research_dir(project_dir).glob("iter_*"))
        if path.is_dir() and is_iteration_dir_name(path.name)
    ]


def research_plan_files(project_dir: Path) -> list[Path]:
    """Return research_plan.json files from official numeric iteration directories."""
    return [
        path
        for path in (root / "research_plan.json" for root in iteration_dirs(project_dir))
        if path.is_file()
    ]


def research_result_json_files(project_dir: Path, iteration: int | None = None) -> list[Path]:
    """Return result JSON files from official numeric iteration directories."""
    roots = [iter_dir(project_dir, iteration)] if iteration is not None else iteration_dirs(project_dir)
    return [
        path
        for root in roots
        for path in sorted((root / "results").glob("*.json"))
        if path.is_file()
    ]


def research_result_png_files(project_dir: Path, iteration: int | None = None) -> list[Path]:
    """Return result PNG files from official numeric iteration directories."""
    roots = [iter_dir(project_dir, iteration)] if iteration is not None else iteration_dirs(project_dir)
    return [
        path
        for root in roots
        for path in sorted((root / "results").glob("*.png"))
        if path.is_file()
    ]


def phases_dir(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "phases"


def results_dir(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "results"


def plan_path(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "research_plan.json"


def reflect_path(project_dir: Path, iteration: int) -> Path:
    return iter_dir(project_dir, iteration) / "reflect.json"


def research_relative_path_issue(path_value: Any, field_name: str = "path") -> str | None:
    """Return a validation issue when a plan path escapes the research tree."""
    if not isinstance(path_value, str) or not path_value.strip():
        return f"{field_name} must be a non-empty relative path"
    candidate = Path(path_value)
    if candidate.is_absolute():
        return f"{field_name} must be relative to project_dir"
    parts = _raw_relative_path_parts(path_value)
    if ".." in parts:
        return f"{field_name} must not contain '..'"
    if "." in parts:
        return f"{field_name} must not contain '.'"
    if not parts or parts[0] != "research":
        return f"{field_name} must be under research/"
    return None


def _raw_relative_path_parts(path_value: str | Path) -> tuple[str, ...]:
    text = path_value if isinstance(path_value, str) else path_value.as_posix()
    return tuple(part for part in str(text).replace("\\", "/").split("/") if part)


def is_safe_research_artifact_path(path_value: Any) -> bool:
    """Return whether a project-relative artifact path stays inside research/."""
    if not isinstance(path_value, (str, Path)):
        return False
    candidate = Path(path_value)
    if candidate.is_absolute():
        return False
    parts = _raw_relative_path_parts(path_value)
    return bool(parts) and parts[0] == "research" and all(part not in {".", ".."} for part in parts)


def is_safe_research_result_artifact_path(path_value: Any, suffix: str | None = None) -> bool:
    """Return whether a path is a safe research/iter_N/results artifact path."""
    if not is_safe_research_artifact_path(path_value):
        return False
    parts = _raw_relative_path_parts(path_value)
    if len(parts) < 4 or re.fullmatch(r"iter_\d+", parts[1]) is None or parts[2] != "results":
        return False
    return suffix is None or parts[-1].endswith(suffix)


def research_artifact_paths_in_text(text: str) -> list[str]:
    """Return unique research artifact path mentions in text, preserving order."""
    return list(dict.fromkeys(RESEARCH_ARTIFACT_PATH_RE.findall(text)))


def research_result_json_paths_in_text(text: str) -> list[str]:
    """Return unique research result JSON path mentions in text, preserving order."""
    return list(dict.fromkeys(RESEARCH_RESULT_JSON_PATH_RE.findall(text)))


def research_result_png_paths_in_text(text: str) -> list[str]:
    """Return unique research result PNG path mentions in text, preserving order."""
    return list(dict.fromkeys(RESEARCH_RESULT_PNG_PATH_RE.findall(text)))


def safe_research_artifact_paths_in_text(text: str) -> list[str]:
    """Return safe research artifact path mentions in text."""
    return [
        path
        for path in research_artifact_paths_in_text(text)
        if is_safe_research_artifact_path(path)
    ]


def unsafe_research_artifact_paths_in_text(text: str) -> list[str]:
    """Return syntactically unsafe research artifact path mentions in text."""
    return [
        path
        for path in research_artifact_paths_in_text(text)
        if not is_safe_research_artifact_path(path)
    ]


def safe_research_result_json_paths_in_text(text: str) -> list[str]:
    """Return safe research result JSON path mentions in text."""
    return [
        path
        for path in research_result_json_paths_in_text(text)
        if is_safe_research_result_artifact_path(path, ".json")
    ]


def resolve_research_path(project_dir: Path, path_value: Any, field_name: str = "path") -> Path:
    """Resolve a validated path that is required to stay under research/."""
    issue = research_relative_path_issue(path_value, field_name)
    if issue:
        raise ValueError(issue)
    return project_dir / Path(path_value)


def research_results_path_issue(
    path_value: Any,
    iteration: int | None = None,
    field_name: str = "path",
) -> str | None:
    """Return a validation issue when a phase result path is outside results/."""
    issue = research_relative_path_issue(path_value, field_name)
    if issue:
        return issue
    parts = _raw_relative_path_parts(path_value)
    if len(parts) < 4 or re.fullmatch(r"iter_\d+", parts[1]) is None or parts[2] != "results":
        return f"{field_name} must be under research/iter_<n>/results/"
    if iteration is not None and parts[1] != f"iter_{iteration}":
        return f"{field_name} must be under research/iter_{iteration}/results/"
    return None


def resolve_research_results_path(
    project_dir: Path,
    path_value: Any,
    iteration: int | None = None,
    field_name: str = "path",
) -> Path:
    """Resolve a phase result path that is required to stay under results/."""
    issue = research_results_path_issue(path_value, iteration, field_name)
    if issue:
        raise ValueError(issue)
    return project_dir / Path(path_value)


def normalize_project_relative_path(project_dir: Path, path_value: Any, field_name: str = "path") -> Path:
    """Normalize a tool-supplied path to a project-relative path."""
    if isinstance(path_value, Path):
        candidate = path_value
    elif isinstance(path_value, str) and path_value.strip():
        candidate = Path(path_value)
    else:
        raise ValueError(f"{field_name} must be a non-empty path")

    root = project_dir.resolve(strict=False)
    absolute = candidate if candidate.is_absolute() else root / candidate
    try:
        return absolute.resolve(strict=False).relative_to(root)
    except ValueError as e:
        raise ValueError(f"{field_name} must be inside project_dir") from e
