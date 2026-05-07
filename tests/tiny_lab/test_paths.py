"""Tests for centralized project-relative path helpers."""
from __future__ import annotations

from tiny_lab.paths import (
    iteration_dirs,
    iteration_number_from_dir_name,
    research_artifact_paths_in_text,
    research_plan_files,
    research_result_json_paths_in_text,
    research_result_json_files,
    research_result_png_paths_in_text,
    research_result_png_files,
    safe_research_artifact_paths_in_text,
    safe_research_result_json_paths_in_text,
    unsafe_research_artifact_paths_in_text,
    is_safe_research_artifact_path,
    is_safe_research_result_artifact_path,
)


def test_safe_research_artifact_path_rejects_traversal_segments():
    assert is_safe_research_artifact_path("research/iter_1/results/phase_0.json") is True
    assert is_safe_research_artifact_path("research/iter_1/results/./phase_0.json") is False
    assert is_safe_research_artifact_path("research/iter_1/results/../phase_0.json") is False
    assert is_safe_research_artifact_path("research/iter_1/results/../../evaluation.json") is False
    assert is_safe_research_artifact_path("/tmp/research/iter_1/results/phase_0.json") is False
    assert is_safe_research_artifact_path("shared/results/phase_0.json") is False


def test_safe_research_result_artifact_path_requires_results_scope_and_suffix():
    assert is_safe_research_result_artifact_path("research/iter_1/results/phase_0.json", ".json") is True
    assert is_safe_research_result_artifact_path("research/iter_1/results/plots/phase_0.png", ".png") is True
    assert is_safe_research_result_artifact_path("research/iter_1/results/./phase_0.json", ".json") is False
    assert is_safe_research_result_artifact_path("research/iter_1/.domain_research.json", ".json") is False
    assert is_safe_research_result_artifact_path("research/iter_x/results/phase_0.json", ".json") is False
    assert is_safe_research_result_artifact_path("research/iter_1/results/phase_0.png", ".json") is False


def test_iteration_number_from_dir_name_requires_numeric_suffix():
    assert iteration_number_from_dir_name("iter_1") == 1
    assert iteration_number_from_dir_name("iter_001") == 1
    assert iteration_number_from_dir_name("iter_x") is None
    assert iteration_number_from_dir_name("notes_iter_1") is None


def test_iteration_file_discovery_ignores_non_numeric_iter_dirs(tmp_path):
    iter1 = tmp_path / "research" / "iter_1"
    iterx = tmp_path / "research" / "iter_x"
    (iter1 / "results").mkdir(parents=True)
    (iterx / "results").mkdir(parents=True)
    (iter1 / "research_plan.json").write_text("{}")
    (iterx / "research_plan.json").write_text("{}")
    (iter1 / "results" / "phase_0.json").write_text("{}")
    (iterx / "results" / "noise.json").write_text("{}")
    (iter1 / "results" / "phase_0.png").write_bytes(b"png")
    (iterx / "results" / "noise.png").write_bytes(b"png")

    assert [path.name for path in iteration_dirs(tmp_path)] == ["iter_1"]
    assert [path.relative_to(tmp_path).as_posix() for path in research_plan_files(tmp_path)] == [
        "research/iter_1/research_plan.json"
    ]
    assert [path.relative_to(tmp_path).as_posix() for path in research_result_json_files(tmp_path)] == [
        "research/iter_1/results/phase_0.json"
    ]
    assert [path.relative_to(tmp_path).as_posix() for path in research_result_png_files(tmp_path)] == [
        "research/iter_1/results/phase_0.png"
    ]


def test_research_artifact_path_extractors_preserve_order_and_safety_filters():
    text = (
        "See research/iter_1/results/phase_0.json and "
        "research/iter_1/results/phase_0.png. "
        "Unsafe: research/iter_1/results/../../evaluation.json. "
        "Also research/final_paper.md and research/iter_1/results/phase_0.json."
    )

    assert research_artifact_paths_in_text(text) == [
        "research/iter_1/results/phase_0.json",
        "research/iter_1/results/phase_0.png",
        "research/iter_1/results/../../evaluation.json",
        "research/final_paper.md",
    ]
    assert safe_research_artifact_paths_in_text(text) == [
        "research/iter_1/results/phase_0.json",
        "research/iter_1/results/phase_0.png",
        "research/final_paper.md",
    ]
    assert unsafe_research_artifact_paths_in_text(text) == [
        "research/iter_1/results/../../evaluation.json"
    ]
    assert research_result_json_paths_in_text(text) == [
        "research/iter_1/results/phase_0.json",
        "research/iter_1/results/../../evaluation.json",
    ]
    assert safe_research_result_json_paths_in_text(text) == [
        "research/iter_1/results/phase_0.json"
    ]
    assert research_result_png_paths_in_text(text) == [
        "research/iter_1/results/phase_0.png"
    ]
