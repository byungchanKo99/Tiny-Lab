"""Tests for shared runtime placeholder resolution."""
from __future__ import annotations

from tiny_lab.runtime_placeholders import resolve_runtime_placeholders


def test_resolves_iteration_and_current_phase_placeholders():
    assert (
        resolve_runtime_placeholders(
            "research/{iter}/results/{current_phase_id}_{iteration}.json",
            iteration=4,
            current_phase_id="phase_2",
        )
        == "research/iter_4/results/phase_2_4.json"
    )


def test_leaves_current_phase_placeholder_when_phase_is_unknown():
    assert (
        resolve_runtime_placeholders(
            "research/{iter}/results/{current_phase_id}.json",
            iteration=4,
            current_phase_id=None,
        )
        == "research/iter_4/results/{current_phase_id}.json"
    )
