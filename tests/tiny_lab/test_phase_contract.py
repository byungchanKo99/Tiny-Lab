"""Tests for the shared phase artifact contract."""
from __future__ import annotations

import pytest

from tiny_lab.phase_contract import (
    default_phase_script_filename,
    default_phase_script_path,
    phase_script_stem_matches,
    select_phase_script,
)


def test_default_phase_script_path_uses_phase_id_prefix():
    assert (
        default_phase_script_path("iter_1", "phase_0", "Leakage-Safe Baseline Audit")
        == "research/iter_1/phases/phase_0_leakage_safe_baseline_audit.py"
    )


def test_default_phase_script_filename_has_fallback_slug():
    assert default_phase_script_filename("phase_2", "!!!") == "phase_2_script.py"


def test_phase_script_matching_requires_exact_or_delimited_phase_id():
    assert phase_script_stem_matches("phase_1", "phase_1")
    assert phase_script_stem_matches("phase_1_train", "phase_1")
    assert phase_script_stem_matches("phase_1-train", "phase_1")
    assert not phase_script_stem_matches("phase_10_train", "phase_1")


def test_select_phase_script_rejects_extra_match_even_with_exact_script(tmp_path):
    (tmp_path / "phase_0.py").write_text("print('exact')")
    (tmp_path / "phase_0_train.py").write_text("print('train')")

    with pytest.raises(ValueError, match="Multiple Python scripts found"):
        select_phase_script(tmp_path, "phase_0")


def test_select_phase_script_rejects_ambiguous_matches(tmp_path):
    (tmp_path / "phase_0_train.py").write_text("print('train')")
    (tmp_path / "phase_0_eval.py").write_text("print('eval')")

    with pytest.raises(ValueError, match="Multiple Python scripts found"):
        select_phase_script(tmp_path, "phase_0")
