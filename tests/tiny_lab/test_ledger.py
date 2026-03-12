"""Tests for ledger read/write utilities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiny_lab.ledger import load_ledger, append_ledger, get_baseline_metric, next_experiment_id
from tiny_lab.schemas import ValidationError


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "ledger.jsonl").touch()
    return tmp_path


def _make_entry(exp_id: str = "EXP-001", cls: str = "WIN", metric_val: float = 1.0) -> dict:
    return {
        "id": exp_id, "question": "q", "family": "f",
        "changed_variable": "x", "value": "v",
        "status": "done", "class": cls,
        "primary_metric": {"loss": metric_val, "baseline": 2.0, "delta_pct": -50.0},
        "decision": cls.lower(), "control": "EXP-001",
    }


class TestLoadLedger:
    def test_empty_file(self, project_dir: Path):
        assert load_ledger(project_dir) == []

    def test_missing_file(self, tmp_path: Path):
        assert load_ledger(tmp_path) == []

    def test_reads_valid_entries(self, project_dir: Path):
        ledger_path = project_dir / "research" / "ledger.jsonl"
        ledger_path.write_text(json.dumps(_make_entry()) + "\n")
        rows = load_ledger(project_dir)
        assert len(rows) == 1
        assert rows[0]["id"] == "EXP-001"

    def test_skips_invalid_json(self, project_dir: Path):
        ledger_path = project_dir / "research" / "ledger.jsonl"
        ledger_path.write_text("not json\n" + json.dumps(_make_entry()) + "\n")
        rows = load_ledger(project_dir)
        assert len(rows) == 1

    def test_blank_lines_ignored(self, project_dir: Path):
        ledger_path = project_dir / "research" / "ledger.jsonl"
        ledger_path.write_text("\n" + json.dumps(_make_entry()) + "\n\n")
        assert len(load_ledger(project_dir)) == 1


class TestAppendLedger:
    def test_appends_valid_entry(self, project_dir: Path):
        append_ledger(project_dir, _make_entry())
        rows = load_ledger(project_dir)
        assert len(rows) == 1

    def test_multiple_appends(self, project_dir: Path):
        append_ledger(project_dir, _make_entry("EXP-001"))
        append_ledger(project_dir, _make_entry("EXP-002"))
        assert len(load_ledger(project_dir)) == 2

    def test_rejects_invalid_entry(self, project_dir: Path):
        with pytest.raises(ValidationError):
            append_ledger(project_dir, {"id": "bad"})


class TestGetBaselineMetric:
    def test_returns_none_when_no_baseline(self, project_dir: Path):
        append_ledger(project_dir, _make_entry("EXP-001", "WIN"))
        assert get_baseline_metric(project_dir, "loss") is None

    def test_returns_baseline_value(self, project_dir: Path):
        baseline = _make_entry("EXP-001", "BASELINE", 2.5)
        append_ledger(project_dir, baseline)
        assert get_baseline_metric(project_dir, "loss") == 2.5

    def test_returns_none_for_wrong_metric(self, project_dir: Path):
        baseline = _make_entry("EXP-001", "BASELINE", 2.5)
        append_ledger(project_dir, baseline)
        assert get_baseline_metric(project_dir, "accuracy") is None

    def test_empty_ledger(self, project_dir: Path):
        assert get_baseline_metric(project_dir, "loss") is None


class TestNextExperimentId:
    def test_empty_ledger(self):
        assert next_experiment_id([]) == "EXP-001"

    def test_sequential(self):
        ledger = [{"id": "EXP-001"}, {"id": "EXP-002"}]
        assert next_experiment_id(ledger) == "EXP-003"

    def test_gap_in_ids(self):
        ledger = [{"id": "EXP-001"}, {"id": "EXP-005"}]
        assert next_experiment_id(ledger) == "EXP-006"

    def test_non_exp_ids_ignored(self):
        ledger = [{"id": "BASELINE"}, {"id": "EXP-003"}]
        assert next_experiment_id(ledger) == "EXP-004"
