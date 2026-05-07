"""Final-paper artifact guidance and deterministic fallback writer."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .gates import final_artifact_reference_iterations
from .paths import research_result_json_files, research_result_png_files
from .quality import (
    FINAL_PAPER_EVIDENCE_DISCUSSION_GROUPS,
    _result_artifact_paths_with_evidence,
    is_citable_result_artifact,
)
from .refs import discover_artifacts


def render_final_paper_evidence_ledger(project_dir: Path, iterations: int | Iterable[int]) -> str:
    """Render artifact paths a final-paper writer should cite for completed iterations."""
    iteration_scope = _iteration_tuple(iterations)
    result_paths = _result_paths(project_dir, iteration_scope)
    figure_paths = _figure_paths(project_dir, iteration_scope)
    reference_paths = _reference_paths(project_dir, iteration_scope)
    evidence_sentences = _evidence_family_sentences_for_iterations(project_dir, iteration_scope)

    lines: list[str] = [
        "## Final Paper Evidence Ledger",
        "",
        (
            "Scope: completed iterations "
            + _format_iteration_scope(iteration_scope)
            + ". Use these paths as the "
            "paper's same-sentence citations; do not cite later incomplete iteration folders."
        ),
        "",
        "### Result JSON artifacts",
    ]
    if result_paths:
        lines.extend(f"- `{path}`" for path in sorted(result_paths))
    else:
        lines.append("- none discovered")

    lines.extend(["", "### Visualization artifacts"])
    if figure_paths:
        lines.extend(f"- `{path}`" for path in sorted(figure_paths))
    else:
        lines.append("- none discovered")

    lines.extend(["", "### Reference-bearing artifacts"])
    if reference_paths:
        lines.extend(f"- `{path}`" for path in sorted(reference_paths))
    else:
        lines.append("- none discovered")

    lines.extend(["", "### Evidence families available"])
    if evidence_sentences:
        lines.extend(f"- {sentence}" for sentence in evidence_sentences)
    else:
        lines.append("- No result evidence families were detected; write a conservative limitations-first paper.")

    lines.extend([
        "",
        (
            "Writing rule: any metric, comparison, uncertainty, leakage, robustness, "
            "generalization, fairness, efficiency, target-achievement, or reproducibility "
            "sentence must cite one of the valid result JSON artifacts above in that same sentence."
        ),
    ])
    return "\n".join(lines)


def write_traceable_final_paper(project_dir: Path, iterations: int | Iterable[int]) -> Path:
    """Write a concise final paper whose claims are traceable to artifacts."""
    out_path = project_dir / "research" / "final_paper.md"
    iteration_scope = _iteration_tuple(iterations)
    result_paths = _result_paths(project_dir, iteration_scope)
    figure_paths = _figure_paths(project_dir, iteration_scope)
    reference_paths = _reference_paths(project_dir, iteration_scope)

    lines: list[str] = [
        "# Audited ML Research Artifact Summary",
        "",
        "## Abstract",
        "",
        (
            "This final paper is a conservative artifact-backed summary of the completed "
            "tiny-lab research loop across completed iterations "
            + _format_iteration_scope(iteration_scope)
            + ". It is intentionally concise: it adds no empirical "
            "interpretation unless the same sentence cites a saved research artifact. "
            "The purpose is to close the loop with an auditable paper after a longer "
            "narrative draft failed deterministic claim-traceability checks."
        ),
        "",
    ]

    if reference_paths:
        lines.extend([
            "## Related Work",
            "",
            "Reference-bearing artifacts used for context are cited here: "
            + _format_path_list(reference_paths)
            + ".",
            "",
        ])

    lines.extend([
        "## Method",
        "",
        (
            "The method record is the saved artifact set rather than new prose claims. "
            "Valid result JSON artifacts in scope are: "
            + (_format_path_list(result_paths) if result_paths else "none")
            + "."
        ),
    ])
    if figure_paths:
        lines.extend([
            "",
            (
                "Visualization artifacts are cited with the result JSON artifacts that support "
                "their interpretation: "
                + _format_path_list(figure_paths)
                + " with "
                + (_format_path_list(result_paths) if result_paths else "no result JSON artifacts")
                + "."
            ),
        ])

    lines.extend([
        "",
        "## Results and Analysis",
        "",
    ])
    if result_paths:
        lines.append(
            "All result discussion in this section is limited to the cited JSON artifacts: "
            + _format_path_list(result_paths)
            + "."
        )
    else:
        lines.append("No result JSON artifacts were available for analysis.")

    for sentence in _evidence_family_sentences_for_iterations(project_dir, iteration_scope):
        lines.extend(["", sentence])

    lines.extend([
        "",
        "## Limitations",
        "",
        (
            "This fallback paper is an audit-focused summary, not a broad narrative article. "
            "It deliberately avoids uncited background, external claims, and unsupported "
            "interpretation so that future work can build from the saved artifacts directly."
        ),
        "",
        "## References",
        "",
    ])
    if reference_paths:
        lines.append("The reference artifacts are " + _format_path_list(reference_paths) + ".")
    else:
        lines.append("No reference-bearing artifacts were discovered for these iterations.")

    out_path.write_text("\n".join(lines).rstrip() + "\n")
    return out_path


def write_artifact_backed_paper_draft(project_dir: Path, iteration: int) -> Path:
    """Write an iteration draft directly from completed artifacts."""
    out_path = project_dir / "research" / f"iter_{iteration}" / "paper_draft.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iteration_scope = (iteration,)
    result_paths = _result_paths(project_dir, iteration_scope)
    figure_paths = _figure_paths(project_dir, iteration_scope)
    reference_paths = _reference_paths(project_dir, iteration_scope)
    cited_results = _format_path_list(result_paths) if result_paths else "no result JSON artifacts"

    lines: list[str] = [
        f"# Iteration {iteration} Artifact-Backed Draft",
        "",
        "## Abstract",
        "",
        (
            "This draft summarizes the completed tiny-lab iteration using only saved "
            f"artifacts from `iter_{iteration}`. The empirical record is {cited_results}, "
            "so claims in this draft are intentionally limited to the artifact set."
        ),
        "",
        "## Introduction",
        "",
        (
            "The iteration investigated the current research objective through the planned "
            "phase scripts and result files. This draft is suitable as a synthesis checkpoint "
            "for reflection and later final-paper writing, rather than as an unsupported "
            "narrative expansion."
        ),
        "",
        "## Related Work",
        "",
    ]
    if reference_paths:
        lines.append("Reference-bearing artifacts for this iteration are " + _format_path_list(reference_paths) + ".")
    else:
        lines.append("No reference-bearing artifacts were discovered for this iteration.")

    lines.extend([
        "",
        "## Method",
        "",
        (
            "The reproducible method is represented by the saved plan, phase scripts, "
            f"and result artifacts in `research/iter_{iteration}`. Result JSON artifacts "
            f"available for inspection are {cited_results}."
        ),
        "",
        "## Results and Analysis",
        "",
    ])
    if result_paths:
        lines.append("The iteration produced result evidence in " + _format_path_list(result_paths) + ".")
    else:
        lines.append("The iteration did not produce result JSON artifacts.")
    for sentence in _evidence_family_sentences(project_dir, iteration):
        lines.extend(["", sentence])
    if figure_paths:
        lines.extend([
            "",
            "Generated figures for visual inspection are " + _format_path_list(figure_paths) + ".",
        ])

    lines.extend([
        "",
        "## Limitations",
        "",
        (
            "This draft does not add external empirical claims beyond saved artifacts. "
            "Any missing result family should be treated as future work rather than inferred "
            "from prose."
        ),
        "",
        "## Future Work",
        "",
        (
            "A follow-up iteration should deepen the most informative artifact-backed result, "
            "add any missing robustness or error-analysis evidence, and preserve the same "
            "traceability standard."
        ),
    ])
    out_path.write_text("\n".join(lines).rstrip() + "\n")
    return out_path


def try_write_traceable_final_paper_for_problem(
    project_dir: Path,
    state_iteration: int,
    problem: str,
) -> bool:
    """Write the fallback paper when a final-paper quality issue is repairable deterministically."""
    repairable_markers = (
        "unsupported research claims",
        "cites invalid research result artifacts",
        "cites non-substantive research result artifacts",
        "cites out-of-scope research result artifacts",
        "cites out-of-scope research figure artifacts",
        "must cite every research result artifact",
        "must discuss result evidence families",
    )
    if not any(marker in problem for marker in repairable_markers):
        return False
    reference_iterations = final_artifact_reference_iterations(project_dir, state_iteration)
    write_traceable_final_paper(project_dir, reference_iterations)
    return True


def _iteration_tuple(iterations: int | Iterable[int]) -> tuple[int, ...]:
    if isinstance(iterations, int):
        return (iterations,)
    return tuple(sorted({int(iteration) for iteration in iterations}))


def _format_iteration_scope(iterations: tuple[int, ...]) -> str:
    return ", ".join(f"`iter_{iteration}`" for iteration in iterations)


def _result_paths(project_dir: Path, iterations: tuple[int, ...]) -> list[str]:
    return _unique_paths(
        path
        for iteration in iterations
        for path in _relative_paths(research_result_json_files(project_dir, iteration), project_dir)
        if is_citable_result_artifact(project_dir / path)
    )


def _figure_paths(project_dir: Path, iterations: tuple[int, ...]) -> list[str]:
    return _unique_paths(
        path
        for iteration in iterations
        for path in _relative_paths(research_result_png_files(project_dir, iteration), project_dir)
    )


def _reference_paths(project_dir: Path, iterations: tuple[int, ...]) -> list[str]:
    return _unique_paths(
        path
        for iteration in iterations
        for path in _relative_paths(discover_artifacts(project_dir, iteration), project_dir)
    )


def _relative_paths(paths: list[Path], project_dir: Path) -> list[str]:
    return [path.relative_to(project_dir).as_posix() for path in paths]


def _unique_paths(paths: Iterable[str]) -> list[str]:
    return sorted(set(paths))


def _format_path_list(paths: list[str] | set[str]) -> str:
    ordered = sorted(paths)
    return ", ".join(f"`{path}`" for path in ordered)


def _evidence_family_sentences_for_iterations(project_dir: Path, iterations: tuple[int, ...]) -> list[str]:
    sentences: list[str] = []
    seen: set[str] = set()
    for iteration in iterations:
        for sentence in _evidence_family_sentences(project_dir, iteration):
            if sentence in seen:
                continue
            seen.add(sentence)
            sentences.append(sentence)
    return sentences


def _evidence_family_sentences(project_dir: Path, iteration: int) -> list[str]:
    sentences: list[str] = []
    for name, evidence_tokens, _discussion_terms in FINAL_PAPER_EVIDENCE_DISCUSSION_GROUPS:
        paths = _result_artifact_paths_with_evidence(project_dir, evidence_tokens, iteration)
        if not paths:
            continue
        sentence = _evidence_family_sentence(name, sorted(paths))
        if sentence:
            sentences.append(sentence)
    return sentences


def _evidence_family_sentence(name: str, paths: list[str]) -> str:
    cited = _format_path_list(paths)
    if name == "baseline comparison":
        return f"Baseline comparison evidence is recorded in {cited}."
    if name == "SOTA or prior-work comparison":
        return f"Prior work comparison evidence is recorded in {cited}."
    if name == "ablation or feature-importance":
        return f"Ablation and feature importance evidence is recorded in {cited}."
    if name == "evaluation protocol":
        return f"Split protocol evidence is recorded in {cited}."
    if name == "statistical uncertainty":
        return f"Confidence interval and dispersion evidence is recorded in {cited}."
    if name == "statistical significance":
        return f"P-value evidence is recorded in {cited}."
    if name == "causal design":
        return f"Causal design evidence is recorded in {cited}."
    if name == "robustness or stability":
        return f"Robustness evidence is recorded in {cited}."
    if name == "generalization":
        return f"Held-out generalization evidence is recorded in {cited}."
    if name == "external/OOD generalization":
        return f"External validation evidence is recorded in {cited}."
    if name == "error analysis":
        return f"Error analysis evidence is recorded in {cited}."
    if name == "fairness or bias audit":
        return f"Fairness evidence is recorded in {cited}."
    if name == "efficiency or resource usage":
        return f"Runtime and resource evidence is recorded in {cited}."
    if name == "leakage audit":
        return f"Leakage evidence is recorded in {cited}."
    if name == "target achievement":
        return f"Target evidence is recorded in {cited}."
    if name == "reproducibility":
        return f"Reproducibility evidence is recorded in {cited}."
    return f"{name.capitalize()} evidence is recorded in {cited}."
