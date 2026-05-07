"""Reference verification — detect hallucinated citations.

Verifies references found in research artifacts (.domain_research.json,
.diverge.json, .papers_collected.json, etc.) against public APIs:
arXiv, Crossref, Semantic Scholar.

Pure stdlib (urllib) — no external deps to keep tiny-lab dependency-free.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .paths import is_safe_research_artifact_path, iteration_dirs

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

VERIFIED = "verified"
UNVERIFIED = "unverified"
NOT_FOUND = "not_found"
ERROR = "error"

REFERENCE_VERIFICATION_CONTRACT_MARKDOWN = f"""## Reference Verification Contract

This section is generated from `tiny_lab.refs`. Update that module, not individual prompt copies.

Reference-bearing iteration artifacts write sidecars next to the source artifact as
`<source-stem>.ref_verification.json`, for example:

- `research/iter_1/.domain_research.json` -> `research/iter_1/.domain_research.ref_verification.json`
- `research/iter_1/.lit_scan.json` -> `research/iter_1/.lit_scan.ref_verification.json`
- `research/iter_1/.diverge.json` -> `research/iter_1/.diverge.ref_verification.json`

Status semantics:

- `{VERIFIED}`: identity was verified through arXiv, Crossref, or Semantic Scholar; URL HEAD checks only prove the URL is reachable.
- `{UNVERIFIED}`: the verifier lacked enough identifiers or evidence to confirm the work.
- `{NOT_FOUND}`: the verifier searched but could not find the work.
- `{ERROR}`: the verifier hit an API, network, or parsing error.

Strict completion means every reference is `{VERIFIED}` and the sidecar audit has no structural issues.
`tiny-lab verify-refs --strict` exits non-zero for any `{NOT_FOUND}`, `{UNVERIFIED}`, or `{ERROR}` reference.

For candidate scoring and literature-gap reasoning, treat `{UNVERIFIED}`, `{NOT_FOUND}`, and `{ERROR}` as weak evidence. Apply `ref_verification_penalty` to candidate ideas whose `grounded_in` citations are not fully verified, and do not build novelty, SOTA, or superiority claims on them."""


def render_reference_verification_contract() -> str:
    """Return the shared reference verification contract for prompts and runners."""
    return REFERENCE_VERIFICATION_CONTRACT_MARKDOWN.strip()


@dataclass
class RefCheck:
    """One reference's verification result."""

    raw: dict[str, Any]
    title: str | None = None
    url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    status: str = UNVERIFIED  # verified | unverified | not_found | error
    method: str | None = None  # arxiv | crossref | semantic_scholar | url_head
    canonical_title: str | None = None
    canonical_url: str | None = None
    notes: str | None = None


@dataclass
class VerificationResult:
    """Aggregated verification for a single source artifact."""

    source_file: str
    total: int = 0
    verified: int = 0
    unverified: int = 0
    not_found: int = 0
    error: int = 0
    refs: list[RefCheck] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "summary": {
                "total": self.total,
                VERIFIED: self.verified,
                UNVERIFIED: self.unverified,
                NOT_FOUND: self.not_found,
                ERROR: self.error,
            },
            "refs": [asdict(r) for r in self.refs],
        }


# ---------------------------------------------------------------------------
# Reference extraction — handle multiple artifact schemas
# ---------------------------------------------------------------------------

# Field names that commonly hold reference lists across tiny-lab artifacts.
_REF_FIELD_CANDIDATES = (
    "references",
    "literature_notes",
    "papers",
    "grounded_in",
    "citations",
    "bibliography",
    "works_cited",
    "related_work",
    "sources",
    "evidence",
)


def extract_references(data: Any, _path: str = "") -> list[dict[str, Any]]:
    """Walk a JSON document and pull out reference-like dicts.

    A 'reference-like' value is:
    - a dict with at least one of: title, url, doi, arxiv_id
    - or a string that looks like a URL or DOI (wrapped into a dict)
    - or a list of either
    """
    out: list[dict[str, Any]] = []

    if isinstance(data, list):
        for i, item in enumerate(data):
            out.extend(extract_references(item, f"{_path}[{i}]"))
        return out

    if not isinstance(data, dict):
        return out

    # Direct hits: known field names
    for field_name in _REF_FIELD_CANDIDATES:
        if field_name in data:
            value = data[field_name]
            if isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict) and _looks_like_ref(item):
                        out.append(item)
                    elif isinstance(item, str):
                        wrapped = _wrap_string_ref(item)
                        if wrapped:
                            out.append(wrapped)

    # Recurse into nested structures (candidates[].grounded_in, etc.)
    for k, v in data.items():
        if k in _REF_FIELD_CANDIDATES:
            continue  # already handled
        if isinstance(v, (dict, list)):
            out.extend(extract_references(v, f"{_path}.{k}"))

    # De-duplicate by (title, url, doi, arxiv_id) tuple
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for r in out:
        key = (
            (r.get("title") or "").strip().lower(),
            (r.get("url") or "").strip().lower(),
            (r.get("doi") or "").strip().lower(),
            (r.get("arxiv_id") or "").strip().lower(),
        )
        if key == ("", "", "", "") or key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def _looks_like_ref(d: dict[str, Any]) -> bool:
    return any(d.get(k) for k in ("title", "url", "doi", "arxiv_id"))


_URL_RE = re.compile(r"https?://[^\s)\]]+")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def _wrap_string_ref(s: str) -> dict[str, Any] | None:
    s = s.strip()
    if not s:
        return None
    url_match = _URL_RE.search(s)
    doi_match = _DOI_RE.search(s)
    if url_match:
        return {"url": url_match.group(0)}
    if doi_match:
        return {"doi": doi_match.group(0)}
    return None


# ---------------------------------------------------------------------------
# Identifier extraction
# ---------------------------------------------------------------------------

_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)
_DOI_URL_RE = re.compile(r"(?:doi\.org/|dx\.doi\.org/)(10\.\d{4,9}/\S+)", re.IGNORECASE)


def _extract_arxiv_id(ref: dict[str, Any]) -> str | None:
    if ref.get("arxiv_id"):
        return str(ref["arxiv_id"]).strip()
    url = str(ref.get("url") or "")
    m = _ARXIV_URL_RE.search(url)
    return m.group(1) if m else None


def _extract_doi(ref: dict[str, Any]) -> str | None:
    if ref.get("doi"):
        return str(ref["doi"]).strip()
    url = str(ref.get("url") or "")
    m = _DOI_URL_RE.search(url)
    if m:
        return m.group(1)
    text = " ".join(str(v) for v in (ref.get("url"), ref.get("title")) if v)
    m2 = _DOI_RE.search(text)
    return m2.group(0) if m2 else None


# ---------------------------------------------------------------------------
# API clients (stdlib only)
# ---------------------------------------------------------------------------

_USER_AGENT = "tiny-lab/7.4 (reference-verifier; https://github.com/byungchanKo99/Tiny-Lab)"
_TIMEOUT = 8.0


def _http_get(url: str, accept: str | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    if accept:
        req.add_header("Accept", accept)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def _check_arxiv(arxiv_id: str) -> tuple[str, str | None]:
    """Returns (status, canonical_title)."""
    url = f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    code, body = _http_get(url, accept="application/atom+xml")
    if code == 0:
        return ERROR, None
    if code != 200:
        return NOT_FOUND, None
    if "<entry>" not in body:
        return NOT_FOUND, None
    m = re.search(r"<title>([^<]+)</title>", body)
    title = None
    if m:
        # arXiv API returns a generic <title> first (the feed title), then per-entry.
        titles = re.findall(r"<title>([^<]+)</title>", body)
        if len(titles) >= 2:
            title = titles[1].strip()
    return VERIFIED, title


def _check_crossref(doi: str) -> tuple[str, str | None]:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}"
    code, body = _http_get(url, accept="application/json")
    if code == 0:
        return ERROR, None
    if code == 404:
        return NOT_FOUND, None
    if code != 200:
        return NOT_FOUND, None
    try:
        data = json.loads(body)
        title_list = data.get("message", {}).get("title", [])
        title = title_list[0] if title_list else None
        return VERIFIED, title
    except (json.JSONDecodeError, KeyError, IndexError):
        return ERROR, None


def _check_semantic_scholar_title(title: str) -> tuple[str, str | None]:
    """Title-only fuzzy match against Semantic Scholar."""
    if not title or len(title.strip()) < 10:
        return UNVERIFIED, None
    q = urllib.parse.quote(title.strip())
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=3&fields=title,externalIds"
    code, body = _http_get(url, accept="application/json")
    if code == 0 or code == 429:
        return ERROR, None
    if code != 200:
        return UNVERIFIED, None
    try:
        data = json.loads(body)
        papers = data.get("data", [])
        if not papers:
            return NOT_FOUND, None
        # Fuzzy title match: case/punct-insensitive token overlap
        norm_query = _normalize_title(title)
        for p in papers:
            cand = _normalize_title(p.get("title", ""))
            if cand and _title_match(norm_query, cand):
                return VERIFIED, p.get("title")
        return NOT_FOUND, None
    except (json.JSONDecodeError, KeyError):
        return ERROR, None


def _normalize_title(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def _title_match(a: str, b: str) -> bool:
    """Token-set jaccard ≥ 0.7 → match."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    union = len(ta | tb)
    return (len(ta & tb) / union) >= 0.7


def _check_url_head(url: str) -> str:
    """Fallback: just check the URL responds 2xx/3xx."""
    code, _ = _http_get(url)
    if code == 0:
        return ERROR
    if 200 <= code < 400:
        return VERIFIED
    return NOT_FOUND


# ---------------------------------------------------------------------------
# Per-reference verification
# ---------------------------------------------------------------------------


def verify_reference(ref: dict[str, Any]) -> RefCheck:
    """Run identifier-aware verification on one reference."""
    check = RefCheck(
        raw=ref,
        title=ref.get("title"),
        url=ref.get("url"),
        doi=ref.get("doi"),
        arxiv_id=_extract_arxiv_id(ref),
    )

    # 1. arXiv (most reliable when applicable)
    if check.arxiv_id:
        status, canonical_title = _check_arxiv(check.arxiv_id)
        check.status = status
        check.method = "arxiv"
        check.canonical_title = canonical_title
        if status == VERIFIED:
            return check

    # 2. Crossref via DOI
    doi = _extract_doi(ref)
    if doi:
        check.doi = doi
        status, canonical_title = _check_crossref(doi)
        if status == VERIFIED or check.status != VERIFIED:
            check.status = status
            check.method = "crossref"
            check.canonical_title = canonical_title
        if status == VERIFIED:
            return check

    # 3. Semantic Scholar by title
    if check.title:
        status, canonical_title = _check_semantic_scholar_title(check.title)
        if status == VERIFIED or check.status not in (VERIFIED,):
            check.status = status
            check.method = "semantic_scholar"
            if canonical_title:
                check.canonical_title = canonical_title
        if status == VERIFIED:
            return check

    # 4. Fallback: bare URL HEAD
    if check.url and check.status not in (VERIFIED,):
        status = _check_url_head(check.url)
        check.status = status
        check.method = "url_head"
        if status == VERIFIED:
            check.notes = "URL reachable; identity not verified via metadata"

    if check.status == VERIFIED and check.method != "url_head":
        check.canonical_url = check.url

    return check


# ---------------------------------------------------------------------------
# File-level verification
# ---------------------------------------------------------------------------


def verify_file(source_file: Path) -> VerificationResult:
    """Read a JSON artifact, extract refs, verify each, return aggregated result."""
    result = VerificationResult(source_file=str(source_file))

    try:
        data = json.loads(source_file.read_text())
    except (OSError, json.JSONDecodeError):
        return result

    refs = extract_references(data)
    result.total = len(refs)

    for ref in refs:
        check = verify_reference(ref)
        result.refs.append(check)
        if check.status == VERIFIED:
            result.verified += 1
        elif check.status == NOT_FOUND:
            result.not_found += 1
        elif check.status == ERROR:
            result.error += 1
        else:
            result.unverified += 1

    return result


def write_verification(source_file: Path, result: VerificationResult) -> Path:
    """Write .ref_verification.json next to the source artifact.

    For source `iter_1/.domain_research.json`, output is
    `iter_1/.domain_research.ref_verification.json`.
    """
    if source_file.name.startswith("."):
        out_name = source_file.stem + ".ref_verification.json"
        # source.stem on a hidden file like ".domain_research.json" is ".domain_research"
        # which still starts with a dot — that's fine, mirrors source
    else:
        out_name = source_file.stem + ".ref_verification.json"

    out_path = source_file.parent / out_name
    payload = result.to_json()
    payload["source_file"] = _sidecar_source_file(source_file)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _sidecar_source_file(source_file: Path) -> str:
    parts = source_file.as_posix().split("/")
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "research":
            return "/".join(parts[index:])
    return source_file.as_posix()


# ---------------------------------------------------------------------------
# Discovery — find all reference-bearing artifacts in a project
# ---------------------------------------------------------------------------

def discover_artifacts(project_dir: Path, iteration: int | None = None) -> list[Path]:
    """Return JSON artifacts that actually contain references."""
    found: list[Path] = []
    roots = _iteration_dirs(project_dir, iteration)
    for root in roots:
        for artifact in sorted({*root.glob("*.json"), *root.glob(".*.json")}):
            if not is_reference_artifact_candidate_path(artifact):
                continue
            count = _artifact_reference_count(artifact)
            if count:
                found.append(artifact)
    return sorted(found)


def is_reference_artifact_candidate_path(path: str | Path) -> bool:
    """Return whether a path may be a reference-bearing iteration JSON artifact."""
    candidate = Path(path)
    text = candidate.as_posix()
    if text.endswith(".ref_verification.json"):
        return False
    if not candidate.is_absolute() and not is_safe_research_artifact_path(candidate):
        return False
    parts = candidate.parts
    return any(
        part == "research"
        and index + 2 == len(parts) - 1
        and re.fullmatch(r"iter_\d+", parts[index + 1]) is not None
        and parts[index + 2].endswith(".json")
        for index, part in enumerate(parts[:-2])
    )


def _iteration_dirs(project_dir: Path, iteration: int | None) -> list[Path]:
    if iteration is not None:
        root = project_dir / "research" / f"iter_{iteration}"
        return [root] if root.exists() else []
    return iteration_dirs(project_dir)


def verify_all(
    project_dir: Path,
    iteration: int | None = None,
    write_files: bool = True,
) -> list[VerificationResult]:
    """Verify every reference-bearing artifact. Writes .ref_verification.json sidecars."""
    results: list[VerificationResult] = []
    for artifact in discover_artifacts(project_dir, iteration):
        result = verify_file(artifact)
        if write_files and result.total > 0:
            write_verification(artifact, result)
        results.append(result)
    return results


def audit_reference_sidecars(
    project_dir: Path,
    iteration: int | None = None,
    *,
    require_identity_verified: bool = False,
) -> list[str]:
    """Check existing reference verification sidecars without network calls."""
    issues: list[str] = []
    audited_sidecars: set[Path] = set()
    for artifact in discover_artifacts(project_dir, iteration=iteration):
        sidecar = artifact.parent / (artifact.stem + ".ref_verification.json")
        audited_sidecars.add(sidecar)
        if not sidecar.exists():
            actual_total = _artifact_reference_count(artifact)
            if actual_total:
                issues.append(f"{artifact.relative_to(project_dir)} missing ref verification sidecar")
            continue
        try:
            data = json.loads(sidecar.read_text())
            summary = data.get("summary", {})
        except Exception as e:
            issues.append(f"{sidecar.relative_to(project_dir)} invalid JSON: {e}")
            continue
        rel_artifact = artifact.relative_to(project_dir).as_posix()
        source_file = data.get("source_file")
        if source_file != rel_artifact:
            issues.append(
                f"{sidecar.relative_to(project_dir)} source_file {source_file!r} "
                f"does not match {rel_artifact!r}"
            )
        count_issue, counts = _sidecar_summary_counts(summary)
        if count_issue:
            issues.append(f"{sidecar.relative_to(project_dir)} {count_issue}")
            continue
        total = counts["total"]
        actual_total = _artifact_reference_count(artifact)
        if actual_total is not None and total != actual_total:
            issues.append(
                f"{sidecar.relative_to(project_dir)} total {total} does not match "
                f"{rel_artifact} references {actual_total}"
            )
        verified = counts["verified"]
        unverified = counts["unverified"]
        not_found = counts["not_found"]
        error = counts["error"]
        accounted = verified + unverified + not_found + error
        if accounted == total:
            refs_issue, ref_status_counts = _sidecar_ref_status_counts(data.get("refs"), total)
            if refs_issue:
                issues.append(f"{sidecar.relative_to(project_dir)} {refs_issue}")
            elif ref_status_counts:
                expected_counts = {
                    VERIFIED: verified,
                    UNVERIFIED: unverified,
                    NOT_FOUND: not_found,
                    ERROR: error,
                }
                if ref_status_counts != expected_counts:
                    issues.append(
                        f"{sidecar.relative_to(project_dir)} refs status counts "
                        f"{ref_status_counts} do not match summary counts {expected_counts}"
                    )
                else:
                    verified_evidence_issue = _sidecar_verified_ref_evidence_issue(
                        data.get("refs"),
                        require_identity_verified=require_identity_verified,
                    )
                    if verified_evidence_issue:
                        issues.append(f"{sidecar.relative_to(project_dir)} {verified_evidence_issue}")
                if actual_total is not None and total == actual_total:
                    signature_issue = _sidecar_ref_signature_issue(data.get("refs"), artifact)
                    if signature_issue:
                        issues.append(f"{sidecar.relative_to(project_dir)} {signature_issue}")
        unaccounted = max(0, total - accounted)
        unverified_total = unverified + unaccounted
        if unverified_total:
            issues.append(f"{sidecar.relative_to(project_dir)} has {unverified_total} unverified references")
        if not_found:
            issues.append(f"{sidecar.relative_to(project_dir)} has {not_found} not_found references")
        if error:
            issues.append(f"{sidecar.relative_to(project_dir)} has {error} verification errors")
    for sidecar in _existing_reference_sidecars(project_dir, iteration):
        if sidecar in audited_sidecars:
            continue
        stale_issue = _stale_sidecar_issue(project_dir, sidecar)
        if stale_issue:
            issues.append(f"{sidecar.relative_to(project_dir)} {stale_issue}")
    return issues


def _existing_reference_sidecars(project_dir: Path, iteration: int | None) -> list[Path]:
    sidecars: set[Path] = set()
    for root in _iteration_dirs(project_dir, iteration):
        sidecars.update(root.glob("*.ref_verification.json"))
        sidecars.update(root.glob(".*.ref_verification.json"))
    return sorted(sidecars)


def _stale_sidecar_issue(project_dir: Path, sidecar: Path) -> str | None:
    try:
        data = json.loads(sidecar.read_text())
    except Exception as e:
        return f"invalid JSON: {e}"
    source_file = data.get("source_file")
    if not isinstance(source_file, str) or not source_file.strip():
        return "source_file is required"
    if (
        not is_safe_research_artifact_path(source_file)
        or not is_reference_artifact_candidate_path(source_file)
    ):
        return f"source_file {source_file!r} is not a reference artifact path"
    source_path = project_dir / source_file
    if not source_path.is_file():
        return f"source_file {source_file!r} is missing"
    expected_sidecar = source_path.parent / (source_path.stem + ".ref_verification.json")
    if sidecar != expected_sidecar:
        expected_rel = expected_sidecar.relative_to(project_dir)
        return f"sidecar path does not match source_file; expected {expected_rel}"
    actual_total = _artifact_reference_count(source_path)
    if actual_total is None:
        return f"source_file {source_file!r} cannot be read as JSON"
    if actual_total == 0:
        return f"source_file {source_file!r} no longer contains references"
    return None


def _artifact_reference_count(artifact: Path) -> int | None:
    refs = _artifact_references(artifact)
    if refs is None:
        return None
    return len(refs)


def _artifact_references(artifact: Path) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(artifact.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return extract_references(data)


def _sidecar_ref_signature_issue(refs: Any, artifact: Path) -> str | None:
    if not isinstance(refs, list):
        return None
    expected_refs = _artifact_references(artifact)
    if expected_refs is None:
        return None
    expected = Counter(_reference_signature(ref) for ref in expected_refs)
    observed: Counter[tuple[str, str, str, str]] = Counter()
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            return None
        raw = ref.get("raw")
        if not isinstance(raw, dict):
            return f"refs[{i}].raw must be an object matching the source reference"
        observed[_reference_signature(raw)] += 1
    if observed != expected:
        return "refs raw references do not match source artifact references"
    return None


def _reference_signature(ref: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("title") or "").strip().lower(),
        str(ref.get("url") or "").strip().lower(),
        str(ref.get("doi") or "").strip().lower(),
        str(ref.get("arxiv_id") or "").strip().lower(),
    )


def _sidecar_ref_status_counts(refs: Any, total: int) -> tuple[str | None, dict[str, int]]:
    if refs is None:
        if total == 0:
            return None, {}
        return f"refs must list {total} verification records", {}
    if not isinstance(refs, list):
        return "refs must be a list", {}
    if len(refs) != total:
        return f"refs length {len(refs)} does not match summary.total {total}", {}

    counts = {VERIFIED: 0, UNVERIFIED: 0, NOT_FOUND: 0, ERROR: 0}
    valid = set(counts)
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            return f"refs[{i}] must be an object", {}
        status = ref.get("status")
        if status not in valid:
            return (
                f"refs[{i}].status must be one of "
                f"{', '.join(sorted(valid))}"
            ), {}
        counts[status] += 1
    return None, counts


_VERIFICATION_METHODS = frozenset({"arxiv", "crossref", "semantic_scholar", "url_head"})


def _sidecar_verified_ref_evidence_issue(
    refs: Any,
    *,
    require_identity_verified: bool = False,
) -> str | None:
    if not isinstance(refs, list):
        return None
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict) or ref.get("status") != VERIFIED:
            continue
        method = ref.get("method")
        if method not in _VERIFICATION_METHODS:
            return f"refs[{i}] verified reference must include a valid verification method"
        if method == "arxiv" and not _non_empty_ref_field(ref, "arxiv_id"):
            return f"refs[{i}] arxiv verification must include arxiv_id"
        if method == "crossref" and not _non_empty_ref_field(ref, "doi"):
            return f"refs[{i}] crossref verification must include doi"
        if method == "semantic_scholar" and not _non_empty_ref_field(ref, "canonical_title"):
            return f"refs[{i}] semantic_scholar verification must include canonical_title"
        if method == "url_head" and not _non_empty_ref_field(ref, "url"):
            return f"refs[{i}] url_head verification must include url"
        if method == "url_head" and require_identity_verified:
            return (
                f"refs[{i}] url_head verification only proves URL reachability; "
                "identity verification required"
            )
    return None


def _non_empty_ref_field(ref: dict[str, Any], key: str) -> bool:
    value = ref.get(key)
    return isinstance(value, str) and bool(value.strip())


def _sidecar_summary_counts(summary: Any) -> tuple[str | None, dict[str, int]]:
    if not isinstance(summary, dict):
        return "summary must be an object", {}
    counts: dict[str, int] = {}
    for key in ("total", "verified", "unverified", "not_found", "error"):
        value = summary.get(key, 0) or 0
        if isinstance(value, bool):
            return f"summary.{key} must be an integer count", {}
        if isinstance(value, int):
            count = value
        elif isinstance(value, str) and value.strip().isdigit():
            count = int(value.strip())
        else:
            return f"summary.{key} must be an integer count", {}
        if count < 0:
            return f"summary.{key} must be a non-negative integer count", {}
        counts[key] = count
    return None, counts


def novelty_estimate(
    hypothesis: str,
    year_window: int = 3,
    limit: int = 50,
) -> dict[str, Any]:
    """Estimate hypothesis novelty by counting recent similar papers.

    Uses Semantic Scholar's paper search. The score is a coarse proxy:
    fewer recent matches → higher novelty.

    Returns:
        {
          "query": "...",
          "matches": [{"title": "...", "year": 2024, "url": "..."}, ...],
          "count": N,
          "novelty_score": 0-10,  # 10 = no matches (high novelty), 0 = many
          "method": "semantic_scholar",
          "error": null | "string",
        }
    """
    import datetime

    out: dict[str, Any] = {
        "query": hypothesis,
        "matches": [],
        "count": 0,
        "novelty_score": None,
        "method": "semantic_scholar",
        "error": None,
    }
    if not hypothesis or len(hypothesis.strip()) < 10:
        out["error"] = "hypothesis too short for search"
        return out

    cutoff_year = datetime.datetime.now().year - year_window
    q = urllib.parse.quote(hypothesis.strip())
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={q}&limit={limit}&fields=title,year,externalIds,url"
    )
    code, body = _http_get(url, accept="application/json")
    if code in (0, 429):
        out["error"] = f"API unavailable (http {code})"
        return out
    if code != 200:
        out["error"] = f"http {code}"
        return out

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        out["error"] = f"invalid response: {e}"
        return out

    papers = data.get("data", [])
    recent = []
    for p in papers:
        year = p.get("year")
        if year is None or year < cutoff_year:
            continue
        ext = p.get("externalIds", {}) or {}
        arxiv = ext.get("ArXiv")
        recent.append({
            "title": p.get("title"),
            "year": year,
            "url": p.get("url") or (
                f"https://arxiv.org/abs/{arxiv}" if arxiv else None
            ),
        })
    out["matches"] = recent[:10]  # cap displayed list
    out["count"] = len(recent)

    # Score: 0 matches → 10, 1-2 → 8, 3-5 → 6, 6-10 → 4, 11-20 → 2, >20 → 1
    n = len(recent)
    if n == 0:
        score = 10
    elif n <= 2:
        score = 8
    elif n <= 5:
        score = 6
    elif n <= 10:
        score = 4
    elif n <= 20:
        score = 2
    else:
        score = 1
    out["novelty_score"] = score
    return out


def format_summary(results: Iterable[VerificationResult]) -> str:
    """Compact human-readable summary."""
    lines: list[str] = []
    total = verified = not_found = unverified = error = 0
    for r in results:
        if r.total == 0:
            continue
        lines.append(
            f"  {r.source_file}: {r.verified}/{r.total} verified  "
            f"(not_found={r.not_found}, unverified={r.unverified}, error={r.error})"
        )
        total += r.total
        verified += r.verified
        not_found += r.not_found
        unverified += r.unverified
        error += r.error
    if total == 0:
        return "  No references found in any artifact."
    header = (
        f"References: {verified}/{total} verified  "
        f"(not_found={not_found}, unverified={unverified}, error={error})"
    )
    return header + "\n" + "\n".join(lines)
