"""Shared visualization artifact checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import iter_dir, results_dir

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA_VIZ_REQUIRED_IDS = ("V1", "V2", "V3", "V4", "V5")
DATA_VIZ_MIN_WIDTH = 320
DATA_VIZ_MIN_HEIGHT = 240


def is_valid_png_artifact(path: Path) -> bool:
    """Return whether a path points to a non-empty PNG with a plausible header."""
    return _has_valid_png_header(path)


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Return PNG IHDR dimensions when the artifact has a plausible header."""
    try:
        with path.open("rb") as f:
            header = f.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:len(PNG_SIGNATURE)] != PNG_SIGNATURE:
        return None
    if header[12:16] != b"IHDR":
        return None
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def data_visualization_manifest_issues(
    project_dir: Path,
    iteration: int,
    manifest: dict[str, Any],
) -> list[str]:
    """Return blocking issues for the initial data-understanding visualization packet."""
    issues: list[str] = []
    generated = manifest.get("generated")
    skipped = manifest.get("skipped")
    if not isinstance(generated, list):
        issues.append("data viz manifest generated must be a list")
        generated = []
    if skipped is None:
        skipped = []
    if not isinstance(skipped, list):
        issues.append("data viz manifest skipped must be a list")
        skipped = []

    generated_ids = _manifest_ids(generated)
    skipped_ids = _manifest_ids(skipped)
    missing_accounting = [
        viz_id for viz_id in DATA_VIZ_REQUIRED_IDS
        if viz_id not in generated_ids and viz_id not in skipped_ids
    ]
    if missing_accounting:
        issues.append(f"data viz manifest must account for required ids: {missing_accounting}")

    duplicate_ids = _duplicate_ids([*generated_ids, *skipped_ids])
    if duplicate_ids:
        issues.append(f"data viz manifest has duplicate ids: {duplicate_ids}")

    data_analysis = _load_data_analysis(project_dir, iteration)
    data_available = _data_analysis_available(data_analysis)
    if data_available and not generated:
        issues.append("available data requires at least one generated data visualization")

    expected_ids = _expected_data_viz_ids(data_analysis)
    for viz_id in expected_ids:
        if viz_id not in generated_ids:
            issues.append(f"{viz_id} is applicable from .data_analysis.json but was not generated")

    issues.extend(_generated_data_viz_issues(project_dir, iteration, generated))
    issues.extend(_skipped_data_viz_issues(skipped))
    if data_available:
        issues.extend(_researcher_readout_issues(manifest.get("researcher_readout")))
    return issues


def phase_visualization_issues(project_dir: Path, iteration: int, phase: dict[str, Any]) -> list[str]:
    """Return blocking issues for a phase's requested PNG visualizations."""
    requested = phase.get("visualization")
    if not requested:
        return []

    phase_id = str(phase.get("id", "?"))
    rdir = results_dir(project_dir, iteration)
    existing_pngs = {p.name for p in rdir.glob("*.png")} if rdir.exists() else set()

    explicit = _requested_png_names(requested)
    if explicit:
        missing = [name for name in explicit if name not in existing_pngs]
        if missing:
            return [f"missing visualizations: {missing}"]
        empty = [name for name in explicit if _is_empty_file(rdir / name)]
        if empty:
            return [f"empty visualizations: {empty}"]
        invalid = [name for name in explicit if not is_valid_png_artifact(rdir / name)]
        if invalid:
            return [f"invalid PNG visualizations: {invalid}"]
        return []

    candidates = [name for name in existing_pngs if name.startswith(f"{phase_id}_")]
    if not candidates:
        return ["missing required PNG visualization"]
    empty = [name for name in candidates if _is_empty_file(rdir / name)]
    if empty:
        return [f"empty visualizations: {empty}"]
    invalid = [name for name in candidates if not is_valid_png_artifact(rdir / name)]
    if invalid:
        return [f"invalid PNG visualizations: {invalid}"]
    return []


def _requested_png_names(requested: Any) -> list[str]:
    """Extract requested PNG artifact names from legacy and structured plan shapes."""
    if isinstance(requested, str):
        return [Path(requested).name] if requested.lower().endswith(".png") else []
    if isinstance(requested, dict):
        names: list[str] = []
        for key in ("path", "file", "filename", "artifact"):
            value = requested.get(key)
            if isinstance(value, str) and value.lower().endswith(".png"):
                names.append(Path(value).name)
        for value in requested.values():
            if isinstance(value, (dict, list)):
                names.extend(_requested_png_names(value))
        return list(dict.fromkeys(names))
    if isinstance(requested, list):
        names: list[str] = []
        for item in requested:
            names.extend(_requested_png_names(item))
        return list(dict.fromkeys(names))
    return []


def _manifest_ids(items: list[Any]) -> list[str]:
    ids: list[str] = []
    for item in items:
        if isinstance(item, dict):
            raw = item.get("id")
            if isinstance(raw, str) and raw.strip():
                ids.append(raw.strip().upper())
    return ids


def _duplicate_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in ids:
        if item in seen and item not in duplicates:
            duplicates.append(item)
        seen.add(item)
    return duplicates


def _load_data_analysis(project_dir: Path, iteration: int) -> dict[str, Any]:
    path = iter_dir(project_dir, iteration) / ".data_analysis.json"
    if not path.exists():
        return {}
    try:
        import json

        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _data_analysis_available(data: dict[str, Any]) -> bool:
    status = str(data.get("data_status", "")).strip().lower()
    if status == "not_available":
        return False
    files = data.get("files")
    if isinstance(files, list) and files:
        return True
    return status == "available"


def _expected_data_viz_ids(data: dict[str, Any]) -> list[str]:
    if not _data_analysis_available(data):
        return []
    numeric_count = _numeric_feature_count(data)
    expected: list[str] = []
    if numeric_count > 0:
        expected.append("V1")
    if numeric_count >= 2:
        expected.append("V2")
    if _has_missing_values(data):
        expected.append("V3")
    if _has_target(data) and numeric_count > 0:
        expected.append("V4")
    if _has_temporal_axis(data):
        expected.append("V5")
    return expected


def _numeric_feature_count(data: dict[str, Any]) -> int:
    features = data.get("features")
    if not isinstance(features, list):
        return 0
    return sum(1 for item in features if _feature_is_numeric(item))


def _feature_is_numeric(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    text = " ".join(
        str(item.get(key, ""))
        for key in ("type", "dtype", "kind", "role")
    ).lower()
    if any(token in text for token in ("number", "numeric", "float", "double", "int", "integer")):
        return True
    stats = item.get("stats")
    return isinstance(stats, dict) and any(key in stats for key in ("mean", "std", "min", "max"))


def _has_missing_values(data: dict[str, Any]) -> bool:
    features = data.get("features")
    if isinstance(features, list):
        for item in features:
            if not isinstance(item, dict):
                continue
            for key in ("missing_pct", "missing_percent", "missing_rate"):
                value = item.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                    return True
            stats = item.get("stats")
            if isinstance(stats, dict):
                value = stats.get("missing_pct", stats.get("missing_rate"))
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                    return True
    quality_text = " ".join(str(item) for item in data.get("quality_issues", [])).lower()
    return any(token in quality_text for token in ("missing", "nan", "null"))


def _has_target(data: dict[str, Any]) -> bool:
    target = data.get("target")
    if isinstance(target, str):
        return bool(target.strip()) and target.strip().lower() not in {"none", "null", "unknown"}
    if isinstance(target, dict):
        return any(
            isinstance(target.get(key), str) and target[key].strip()
            for key in ("name", "column", "variable", "description")
        )
    return target is not None


def _has_temporal_axis(data: dict[str, Any]) -> bool:
    brief = data.get("visualization_brief")
    if isinstance(brief, dict):
        temporal = brief.get("temporal_columns")
        if isinstance(temporal, list) and temporal:
            return True
    features = data.get("features")
    if not isinstance(features, list):
        return False
    for item in features:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(key, "")) for key in ("name", "type", "dtype", "role")).lower()
        if any(token in text for token in ("time", "date", "datetime", "timestamp", "temporal")):
            return True
    return False


def _generated_data_viz_issues(project_dir: Path, iteration: int, generated: list[Any]) -> list[str]:
    issues: list[str] = []
    base = iter_dir(project_dir, iteration)
    for idx, item in enumerate(generated):
        if not isinstance(item, dict):
            issues.append(f"data viz generated[{idx}] must be an object")
            continue
        viz_id = str(item.get("id", "")).strip().upper() or f"generated[{idx}]"
        for key in ("filename", "visual_question", "what_it_shows", "why_it_matters", "modeling_implication"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                issues.append(f"data viz {viz_id} missing non-empty {key}")
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            continue
        rel_issue = _data_viz_filename_issue(filename)
        if rel_issue:
            issues.append(f"data viz {viz_id} unsafe filename: {rel_issue}")
            continue
        path = base / filename
        if not path.exists():
            issues.append(f"data viz {viz_id} missing PNG artifact: {filename}")
            continue
        if _is_empty_file(path):
            issues.append(f"data viz {viz_id} empty PNG artifact: {filename}")
            continue
        if not is_valid_png_artifact(path):
            issues.append(f"data viz {viz_id} invalid PNG artifact: {filename}")
            continue
        dims = png_dimensions(path)
        if dims is None:
            issues.append(f"data viz {viz_id} invalid PNG dimensions: {filename}")
        elif dims[0] < DATA_VIZ_MIN_WIDTH or dims[1] < DATA_VIZ_MIN_HEIGHT:
            issues.append(
                f"data viz {viz_id} PNG too small for legible EDA: "
                f"{filename} is {dims[0]}x{dims[1]}, minimum is {DATA_VIZ_MIN_WIDTH}x{DATA_VIZ_MIN_HEIGHT}"
            )
    return issues


def _skipped_data_viz_issues(skipped: list[Any]) -> list[str]:
    issues: list[str] = []
    for idx, item in enumerate(skipped):
        if not isinstance(item, dict):
            issues.append(f"data viz skipped[{idx}] must be an object")
            continue
        viz_id = str(item.get("id", "")).strip().upper() or f"skipped[{idx}]"
        if viz_id not in DATA_VIZ_REQUIRED_IDS:
            issues.append(f"data viz skipped entry has unknown id: {viz_id}")
        reason = item.get("skip_reason")
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"data viz {viz_id} skip entry requires non-empty skip_reason")
    return issues


def _researcher_readout_issues(readout: Any) -> list[str]:
    if not isinstance(readout, dict):
        return ["available data requires researcher_readout object"]
    issues: list[str] = []
    for key in ("key_patterns", "quality_risks", "modeling_implications", "followup_checks"):
        value = readout.get(key)
        if not isinstance(value, list) or not any(isinstance(item, str) and item.strip() for item in value):
            issues.append(f"researcher_readout requires non-empty {key} list")
    first_move = readout.get("recommended_first_modeling_move")
    if not isinstance(first_move, str) or not first_move.strip():
        issues.append("researcher_readout requires recommended_first_modeling_move")
    return issues


def _data_viz_filename_issue(filename: str) -> str | None:
    path = Path(filename)
    parts = path.parts
    if path.is_absolute():
        return "must be relative"
    if any(part in {"", ".", ".."} for part in parts):
        return "must not contain empty, '.', or '..' path segments"
    if len(parts) != 2 or parts[0] != "data_viz":
        return "must be under data_viz/"
    if path.suffix.lower() != ".png":
        return "must end with .png"
    return None


def _is_empty_file(path: Path) -> bool:
    try:
        return path.stat().st_size == 0
    except OSError:
        return True


def _has_valid_png_header(path: Path) -> bool:
    return png_dimensions(path) is not None
