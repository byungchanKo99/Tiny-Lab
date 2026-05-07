"""Tests for deterministic final-paper fallback."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from tiny_lab.claims import verify_paper_numeric_claims
from tiny_lab.final_paper import (
    render_final_paper_evidence_ledger,
    try_write_traceable_final_paper_for_problem,
    write_traceable_final_paper,
)
from tiny_lab.gates import audit_final_artifacts
from tiny_lab.quality import audit_final_paper


PNG_SIGNATURE = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_complete_plan_and_result(
    project_dir: Path,
    *,
    iteration: int,
    phase_id: str = "phase_0",
    mae_mean: float = 0.42,
) -> None:
    idir = project_dir / "research" / f"iter_{iteration}"
    rdir = idir / "results"
    pdir = idir / "phases"
    rdir.mkdir(parents=True)
    pdir.mkdir(parents=True)
    phase_script = pdir / f"{phase_id}.py"
    phase_script.write_text("print('ok')\n")
    script_sha = "sha256:" + hashlib.sha256(phase_script.read_bytes()).hexdigest()
    (idir / "research_plan.json").write_text(json.dumps({
        "name": "complete rigorous fixture",
        "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
        "phases": [{
            "id": phase_id,
            "type": "script",
            "status": "done",
            "expected_outputs": {
                "report": {"path": f"research/iter_{iteration}/results/{phase_id}.json"},
            },
            "visualization": [f"{phase_id}_error.png"],
        }],
    }))
    (rdir / f"{phase_id}.json").write_text(json.dumps({
        "mae_mean": mae_mean,
        "mae_std": 0.03,
        "mae_ci95": [round(mae_mean - 0.02, 10), round(mae_mean + 0.02, 10)],
        "p_value": 0.01,
        "baseline_results": [{"name": "baseline", "mae_mean": 0.50}],
        "improvement_over_baseline": round(0.50 - mae_mean, 10),
        "feature_importance": [{"feature": "x1", "importance": 0.7}],
        "fold_count": 2,
        "per_fold_metrics": [{"fold": 0, "mae_mean": mae_mean + 0.01}, {"fold": 1, "mae_mean": mae_mean - 0.01}],
        "error_analysis": [{"slice": "high", "mae_mean": 0.55}],
        "leakage_found": False,
        "train_test_overlap": 0,
        "target_achieved": True,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.12",
        "script_path": f"research/iter_{iteration}/phases/{phase_id}.py",
        "script_sha256": script_sha,
    }))
    (rdir / f"{phase_id}_error.png").write_bytes(PNG_SIGNATURE)


def test_traceable_final_paper_fallback_passes_final_paper_and_claim_audits(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    phase_script = tmp_path / "research" / "iter_1" / "phases" / "phase_0.py"
    phase_script.parent.mkdir(parents=True)
    phase_script.write_text("print('ok')\n")
    script_sha = "sha256:" + hashlib.sha256(phase_script.read_bytes()).hexdigest()
    (tmp_path / "research" / "iter_1" / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Random Forests", "doi": "10.1023/A:1010933404324"}],
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "mae_ci95": [0.40, 0.44],
        "p_value": 0.01,
        "baseline_results": [{"name": "baseline", "mae_mean": 0.50}],
        "improvement_over_baseline": 0.08,
        "feature_importance": [{"feature": "x1", "importance": 0.7}],
        "fold_count": 2,
        "per_fold_metrics": [{"fold": 0, "mae_mean": 0.43}, {"fold": 1, "mae_mean": 0.41}],
        "error_analysis": [{"slice": "high", "mae_mean": 0.55}],
        "leakage_found": False,
        "train_test_overlap": 0,
        "target_achieved": True,
        "random_seed": 7,
        "dataset_fingerprint": "sha256:" + "0" * 64,
        "split_id": "fold_0",
        "python_version": "3.12",
        "script_path": "research/iter_1/phases/phase_0.py",
        "script_sha256": script_sha,
    }))
    (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)

    write_traceable_final_paper(tmp_path, 1)

    assert audit_final_paper(tmp_path, iteration=1) == []
    assert verify_paper_numeric_claims(tmp_path) == []


def test_traceable_final_paper_fallback_closes_latest_planned_iteration_at_max_iter_tail(tmp_path: Path):
    _write_complete_plan_and_result(tmp_path, iteration=1, mae_mean=0.42)
    _write_complete_plan_and_result(tmp_path, iteration=2, mae_mean=0.38)

    wrote = try_write_traceable_final_paper_for_problem(
        tmp_path,
        state_iteration=3,
        problem="unsupported research claims",
    )

    assert wrote is True
    text = (tmp_path / "research" / "final_paper.md").read_text()
    assert "completed iterations `iter_2`" in text
    assert "research/iter_1/results/phase_0.json" not in text
    assert "research/iter_2/results/phase_0.json" in text
    assert "research/iter_1/results/phase_0_error.png" not in text
    assert "research/iter_2/results/phase_0_error.png" in text
    audit = audit_final_artifacts(tmp_path, reference_iterations=(2,))
    assert audit.paper_issues == ()
    assert audit.claim_issues == ()


def test_traceable_final_paper_skips_invalid_sibling_result_artifacts(tmp_path: Path):
    _write_complete_plan_and_result(tmp_path, iteration=1, mae_mean=0.42)
    _write_complete_plan_and_result(tmp_path, iteration=2, phase_id="valid_phase", mae_mean=0.38)
    bad_path = tmp_path / "research" / "iter_2" / "results" / "bad_phase.json"
    bad_path.write_text("{bad json")

    wrote = try_write_traceable_final_paper_for_problem(
        tmp_path,
        state_iteration=2,
        problem="final_paper.md cites invalid research result artifacts",
    )

    assert wrote is True
    text = (tmp_path / "research" / "final_paper.md").read_text()
    assert "research/iter_1/results/phase_0.json" not in text
    assert "research/iter_2/results/valid_phase.json" in text
    assert "research/iter_2/results/bad_phase.json" not in text
    audit = audit_final_artifacts(tmp_path, reference_iterations=(2,))
    assert audit.paper_issues == ()
    assert audit.claim_issues == ()


def test_final_paper_evidence_ledger_lists_artifacts_and_evidence_families(tmp_path: Path):
    rdir = tmp_path / "research" / "iter_1" / "results"
    rdir.mkdir(parents=True)
    (tmp_path / "research" / "iter_1" / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Random Forests", "doi": "10.1023/A:1010933404324"}],
    }))
    (rdir / "phase_0.json").write_text(json.dumps({
        "mae_mean": 0.42,
        "mae_std": 0.03,
        "baseline_results": [{"name": "baseline", "mae_mean": 0.50}],
        "feature_importance": [{"feature": "x1", "importance": 0.7}],
        "fold_count": 2,
        "per_fold_metrics": [{"fold": 0, "mae_mean": 0.43}],
        "error_analysis": [{"slice": "high", "mae_mean": 0.55}],
        "leakage_found": False,
        "train_test_overlap": 0,
        "target_achieved": True,
        "random_seed": 7,
    }))
    (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)

    ledger = render_final_paper_evidence_ledger(tmp_path, 1)

    assert "Final Paper Evidence Ledger" in ledger
    assert "research/iter_1/results/phase_0.json" in ledger
    assert "research/iter_1/results/phase_0_error.png" in ledger
    assert "research/iter_1/.domain_research.json" in ledger
    assert "Baseline comparison evidence is recorded" in ledger
    assert "Leakage evidence is recorded" in ledger
    assert "same-sentence citations" in ledger
