"""Tests for reference verification audits."""
from __future__ import annotations

import json
from pathlib import Path

from tiny_lab.refs import (
    RefCheck,
    VerificationResult,
    audit_reference_sidecars,
    discover_artifacts,
    extract_references,
    is_reference_artifact_candidate_path,
    render_reference_verification_contract,
    write_verification,
)


def _ref_checks(summary: dict) -> list[dict]:
    refs: list[dict] = []
    for status in ("verified", "unverified", "not_found", "error"):
        for _ in range(int(summary.get(status, 0) or 0)):
            record = {"raw": {"title": "Some Paper", "doi": "10.1234/example"}, "status": status}
            if status == "verified":
                record.update({
                    "title": "Some Paper",
                    "doi": "10.1234/example",
                    "method": "crossref",
                    "canonical_title": "Some Paper",
                })
            refs.append(record)
    return refs


def _write_domain_research(project_dir: Path, summary: dict) -> None:
    idir = project_dir / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "references": [{"title": "Some Paper", "doi": "10.1234/example"}]
    }))
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": summary,
        "refs": _ref_checks(summary),
    }))


def _write_domain_research_sidecar(
    project_dir: Path,
    *,
    source_file: str = "research/iter_1/.domain_research.json",
    summary: dict | None = None,
    references: list[dict] | None = None,
) -> None:
    idir = project_dir / "research" / "iter_1"
    idir.mkdir(parents=True)
    refs = references if references is not None else [{"title": "Some Paper", "doi": "10.1234/example"}]
    (idir / ".domain_research.json").write_text(json.dumps({"references": refs}))
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": source_file,
        "summary": summary or {
            "total": len(refs),
            "verified": len(refs),
            "unverified": 0,
            "not_found": 0,
            "error": 0,
        },
        "refs": _ref_checks(summary or {
            "total": len(refs),
            "verified": len(refs),
            "unverified": 0,
            "not_found": 0,
            "error": 0,
        }),
    }))


def test_reference_verification_contract_renders_refs_ssot():
    text = render_reference_verification_contract()

    assert "Reference Verification Contract" in text
    assert "tiny_lab.refs" in text
    assert "research/iter_1/.diverge.ref_verification.json" in text
    assert "research/iter_1/.lit_scan.ref_verification.json" in text
    assert "tiny-lab verify-refs --strict" in text
    assert "not_found" in text
    assert "unverified" in text
    assert "error" in text
    assert "research/iter_1/.ref_verification.json" not in text


def test_reference_audit_accepts_all_verified(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )

    assert audit_reference_sidecars(tmp_path, 1) == []


def test_write_verification_uses_research_relative_source_file(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    artifact = idir / ".domain_research.json"
    raw_ref = {"title": "Some Paper", "doi": "10.1234/example"}
    artifact.write_text(json.dumps({"references": [raw_ref]}))
    result = VerificationResult(
        source_file=str(artifact),
        total=1,
        verified=1,
        refs=[
            RefCheck(
                raw=raw_ref,
                title="Some Paper",
                doi="10.1234/example",
                status="verified",
                method="crossref",
                canonical_title="Some Paper",
            )
        ],
    )

    sidecar = write_verification(artifact, result)
    data = json.loads(sidecar.read_text())

    assert data["source_file"] == "research/iter_1/.domain_research.json"
    assert result.source_file == str(artifact)
    assert audit_reference_sidecars(tmp_path, 1) == []


def test_reference_audit_rejects_unverified_refs(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 0, "unverified": 1, "not_found": 0, "error": 0},
    )

    issues = audit_reference_sidecars(tmp_path, 1)

    assert len(issues) == 1
    assert "unverified references" in issues[0]


def test_reference_audit_rejects_sidecar_source_file_mismatch(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        source_file="research/iter_1/.other.json",
    )

    issues = audit_reference_sidecars(tmp_path, 1)

    assert len(issues) == 1
    assert "source_file" in issues[0]
    assert ".other.json" in issues[0]


def test_reference_audit_rejects_stale_sidecar_total(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        references=[
            {"title": "Some Paper", "doi": "10.1234/example"},
            {"title": "Another Paper", "doi": "10.1234/another"},
        ],
        summary={"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )

    issues = audit_reference_sidecars(tmp_path, 1)

    assert len(issues) == 1
    assert "total 1 does not match" in issues[0]
    assert "references 2" in issues[0]


def test_reference_audit_reports_malformed_summary_counts(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        summary={"total": "many", "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json summary.total must be an integer count"
    ]


def test_reference_audit_rejects_negative_summary_counts(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        summary={"total": 1, "verified": -1, "unverified": 2, "not_found": 0, "error": 0},
    )

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "summary.verified must be a non-negative integer count"
    ]


def test_reference_audit_accepts_numeric_string_summary_counts(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        summary={"total": "1", "verified": "1", "unverified": "0", "not_found": "0", "error": "0"},
    )

    assert audit_reference_sidecars(tmp_path, 1) == []


def test_reference_audit_rejects_empty_refs_for_verified_summary(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"] = []
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json refs length 0 does not match summary.total 1"
    ]


def test_reference_audit_rejects_refs_status_count_mismatch(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"][0]["status"] = "unverified"
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert len(issues) == 1
    assert "refs status counts" in issues[0]
    assert "summary counts" in issues[0]


def test_reference_audit_rejects_verified_ref_without_method(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"][0].pop("method")
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "refs[0] verified reference must include a valid verification method"
    ]


def test_reference_audit_rejects_verified_crossref_without_doi(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"][0].pop("doi")
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "refs[0] crossref verification must include doi"
    ]


def test_reference_audit_accepts_verified_url_head_with_url(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        references=[{"title": "Some Paper", "url": "https://example.com/paper"}],
        summary={"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"] = [{
        "raw": {"title": "Some Paper", "url": "https://example.com/paper"},
        "title": "Some Paper",
        "url": "https://example.com/paper",
        "method": "url_head",
        "status": "verified",
    }]
    sidecar.write_text(json.dumps(data))

    assert audit_reference_sidecars(tmp_path, 1) == []


def test_reference_audit_rejects_url_head_when_identity_verification_required(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        references=[{"title": "Some Paper", "url": "https://example.com/paper"}],
        summary={"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"] = [{
        "raw": {"title": "Some Paper", "url": "https://example.com/paper"},
        "title": "Some Paper",
        "url": "https://example.com/paper",
        "method": "url_head",
        "status": "verified",
    }]
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1, require_identity_verified=True)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "refs[0] url_head verification only proves URL reachability; identity verification required"
    ]


def test_reference_audit_rejects_refs_raw_mismatch(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"][0]["raw"] = {"title": "Different Paper", "doi": "10.1234/different"}
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json refs raw references do not match source artifact references"
    ]


def test_reference_audit_rejects_refs_missing_raw_object(tmp_path: Path):
    _write_domain_research(
        tmp_path,
        {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
    )
    sidecar = tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json"
    data = json.loads(sidecar.read_text())
    data["refs"][0].pop("raw")
    sidecar.write_text(json.dumps(data))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json refs[0].raw must be an object matching the source reference"
    ]


def test_reference_audit_requires_sidecar_for_bibliography_only_refs(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({
        "bibliography": [{"title": "Title Only Paper"}]
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == ["research/iter_1/.domain_research.json missing ref verification sidecar"]


def test_reference_audit_requires_sidecar_for_literature_scan_refs(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    lit_scan = idir / ".lit_scan.json"
    lit_scan.write_text(json.dumps({
        "papers": [{"title": "Grounding Paper", "doi": "10.1234/grounding"}]
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert discover_artifacts(tmp_path, 1) == [lit_scan]
    assert issues == ["research/iter_1/.lit_scan.json missing ref verification sidecar"]


def test_reference_discovery_ignores_non_numeric_iteration_dirs(tmp_path: Path):
    valid = tmp_path / "research" / "iter_1" / ".lit_scan.json"
    noise = tmp_path / "research" / "iter_x" / ".lit_scan.json"
    valid.parent.mkdir(parents=True)
    noise.parent.mkdir(parents=True)
    valid.write_text(json.dumps({
        "papers": [{"title": "Grounding Paper", "doi": "10.1234/grounding"}]
    }))
    noise.write_text(json.dumps({
        "papers": [{"title": "Noise Paper", "doi": "10.1234/noise"}]
    }))

    assert discover_artifacts(tmp_path) == [valid]
    assert audit_reference_sidecars(tmp_path) == [
        "research/iter_1/.lit_scan.json missing ref verification sidecar"
    ]


def test_reference_audit_rejects_stale_sidecar_missing_source_file(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [{
            "raw": {"title": "Some Paper", "doi": "10.1234/example"},
            "title": "Some Paper",
            "doi": "10.1234/example",
            "method": "crossref",
            "status": "verified",
        }],
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "source_file 'research/iter_1/.domain_research.json' is missing"
    ]


def test_reference_audit_rejects_stale_sidecar_when_source_no_longer_has_refs(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.json").write_text(json.dumps({"notes": "references removed"}))
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [{
            "raw": {"title": "Some Paper", "doi": "10.1234/example"},
            "title": "Some Paper",
            "doi": "10.1234/example",
            "method": "crossref",
            "status": "verified",
        }],
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "source_file 'research/iter_1/.domain_research.json' no longer contains references"
    ]


def test_reference_audit_rejects_stale_sidecar_with_invalid_source_path(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "../outside.json",
        "summary": {"total": 0, "verified": 0, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [],
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "source_file '../outside.json' is not a reference artifact path"
    ]


def test_reference_audit_rejects_stale_sidecar_with_unsafe_research_source_path(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "../research/iter_1/.domain_research.json",
        "summary": {"total": 0, "verified": 0, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [],
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.domain_research.ref_verification.json "
        "source_file '../research/iter_1/.domain_research.json' is not a reference artifact path"
    ]


def test_reference_audit_rejects_unexpected_sidecar_filename(tmp_path: Path):
    _write_domain_research_sidecar(tmp_path)
    idir = tmp_path / "research" / "iter_1"
    (idir / ".old_domain_research.ref_verification.json").write_text(json.dumps({
        "source_file": "research/iter_1/.domain_research.json",
        "summary": {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
        "refs": [{
            "raw": {"title": "Some Paper", "doi": "10.1234/example"},
            "title": "Some Paper",
            "doi": "10.1234/example",
            "method": "crossref",
            "status": "verified",
        }],
    }))

    issues = audit_reference_sidecars(tmp_path, 1)

    assert issues == [
        "research/iter_1/.old_domain_research.ref_verification.json "
        "sidecar path does not match source_file; expected "
        "research/iter_1/.domain_research.ref_verification.json"
    ]


def test_reference_artifact_candidate_ignores_sidecars():
    assert is_reference_artifact_candidate_path("research/iter_1/.lit_scan.json") is True
    assert is_reference_artifact_candidate_path("research/iter_1/.lit_scan.ref_verification.json") is False
    assert is_reference_artifact_candidate_path("../research/iter_1/.lit_scan.json") is False
    assert is_reference_artifact_candidate_path("research/iter_x/.lit_scan.json") is False
    assert is_reference_artifact_candidate_path("research/iter_1/results/phase_0.json") is False


def test_extract_references_from_bibliography_and_sources_fields():
    refs = extract_references({
        "bibliography": [{"title": "Paper A", "doi": "10.1234/a"}],
        "works_cited": ["https://arxiv.org/abs/2401.12345"],
        "related_work": [{"title": "Paper B", "url": "https://example.com/b"}],
        "nested": {
            "sources": [{"title": "Paper C", "arxiv_id": "2402.00001"}],
        },
    })

    assert len(refs) == 4
    assert {ref.get("title") for ref in refs if ref.get("title")} == {"Paper A", "Paper B", "Paper C"}
    assert any(ref.get("url") == "https://arxiv.org/abs/2401.12345" for ref in refs)


def test_reference_audit_rejects_unaccounted_refs(tmp_path: Path):
    _write_domain_research_sidecar(
        tmp_path,
        references=[
            {"title": "Some Paper", "doi": "10.1234/example"},
            {"title": "Another Paper", "doi": "10.1234/another"},
        ],
        summary={"total": 2, "verified": 1, "not_found": 0, "error": 0},
    )

    issues = audit_reference_sidecars(tmp_path, 1)

    assert len(issues) == 1
    assert "unverified references" in issues[0]
