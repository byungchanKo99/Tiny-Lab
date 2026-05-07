"""Tests for shared visualization artifact gates."""
from __future__ import annotations

import json
from pathlib import Path

from tiny_lab.gates import completion_quality_issue
from tiny_lab.visualizations import data_visualization_manifest_issues


def _png_header(width: int = 640, height: int = 480) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )


def _write_data_analysis(project_dir: Path) -> None:
    idir = project_dir / "research" / "iter_1"
    idir.mkdir(parents=True, exist_ok=True)
    (idir / ".data_analysis.json").write_text(json.dumps({
        "data_status": "available",
        "files": [{"path": "data/train.csv", "rows": 100, "cols": 3}],
        "features": [
            {
                "name": "x1",
                "type": "numeric",
                "stats": {"mean": 0.0, "std": 1.0, "min": -2.0, "max": 2.0},
                "missing_pct": 0,
            },
            {
                "name": "x2",
                "type": "float",
                "stats": {"mean": 1.0, "std": 0.5, "min": 0.0, "max": 2.0},
                "missing_pct": 0,
            },
        ],
        "quality_issues": [],
        "target": {"name": "y", "task_type": "regression"},
        "visualization_brief": {
            "numeric_columns": ["x1", "x2"],
            "categorical_columns": [],
            "temporal_columns": [],
            "target_candidates": ["y"],
            "leakage_risks": [],
        },
    }))


def _manifest(generated_ids: list[str]) -> dict:
    generated = []
    for viz_id in generated_ids:
        generated.append({
            "id": viz_id,
            "filename": f"data_viz/{viz_id.lower()}.png",
            "visual_question": "Which visible data property affects the study design?",
            "what_it_shows": "The figure exposes a concrete data pattern.",
            "why_it_matters": "The pattern changes how the experiment should be interpreted.",
            "modeling_implication": "Use leakage-safe preprocessing and compare simple baselines first.",
            "domain_note": "Consistent with the domain notes.",
            "supported_decision": "Plan an explicit diagnostic phase.",
            "caveats": "Visual inspection does not prove causality.",
        })
    generated_set = set(generated_ids)
    skipped = [
        {"id": viz_id, "skip_reason": "not applicable from .data_analysis.json"}
        for viz_id in ("V1", "V2", "V3", "V4", "V5")
        if viz_id not in generated_set
    ]
    return {
        "generated": generated,
        "skipped": skipped,
        "researcher_readout": {
            "key_patterns": ["two numeric features are available"],
            "quality_risks": ["no missingness is reported in .data_analysis.json"],
            "modeling_implications": ["correlation and target plots should shape baselines"],
            "followup_checks": ["validate leakage-safe split before modeling"],
            "recommended_first_modeling_move": "run a simple baseline with leakage audit",
        },
        "summary": "The data has numeric predictors and an identifiable regression target.",
    }


def test_data_visualization_manifest_accepts_researcher_eda_packet(tmp_path: Path):
    _write_data_analysis(tmp_path)
    viz_dir = tmp_path / "research" / "iter_1" / "data_viz"
    viz_dir.mkdir()
    for name in ("v1.png", "v2.png", "v4.png"):
        (viz_dir / name).write_bytes(_png_header())

    issues = data_visualization_manifest_issues(tmp_path, 1, _manifest(["V1", "V2", "V4"]))

    assert issues == []


def test_data_visualization_manifest_rejects_skipped_applicable_plot(tmp_path: Path):
    _write_data_analysis(tmp_path)
    viz_dir = tmp_path / "research" / "iter_1" / "data_viz"
    viz_dir.mkdir()
    for name in ("v1.png", "v4.png"):
        (viz_dir / name).write_bytes(_png_header())

    issues = data_visualization_manifest_issues(tmp_path, 1, _manifest(["V1", "V4"]))

    assert "V2 is applicable from .data_analysis.json but was not generated" in issues


def test_data_visualization_manifest_rejects_tiny_png(tmp_path: Path):
    _write_data_analysis(tmp_path)
    viz_dir = tmp_path / "research" / "iter_1" / "data_viz"
    viz_dir.mkdir()
    (viz_dir / "v1.png").write_bytes(_png_header(width=1, height=1))
    (viz_dir / "v2.png").write_bytes(_png_header())
    (viz_dir / "v4.png").write_bytes(_png_header())

    issues = data_visualization_manifest_issues(tmp_path, 1, _manifest(["V1", "V2", "V4"]))

    assert any("PNG too small for legible EDA" in issue for issue in issues)


def test_visualize_data_completion_gate_blocks_weak_manifest(tmp_path: Path):
    _write_data_analysis(tmp_path)
    viz_dir = tmp_path / "research" / "iter_1" / "data_viz"
    viz_dir.mkdir()
    (viz_dir / "v1.png").write_bytes(_png_header())
    (viz_dir / "v4.png").write_bytes(_png_header())

    issue = completion_quality_issue(tmp_path, "VISUALIZE_DATA", _manifest(["V1", "V4"]), 1)

    assert issue is not None
    assert "data visualization issues" in issue
    assert "V2 is applicable" in issue
