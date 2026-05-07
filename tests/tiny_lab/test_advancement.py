"""Tests for shared engine/native completion advancement."""
from __future__ import annotations

import json
from pathlib import Path

from tiny_lab.advancement import (
    apply_state_transition,
    carry_over_iteration,
    resolve_completion_advance,
    resolve_runner_completion_advance,
    resolve_next_state,
    resolve_next_state_from_value,
    transition_starts_new_iteration,
)
from tiny_lab.runner_contract import resolve_runner_state_contract
from tiny_lab.workflow import _parse_state


def test_resolve_next_state_supports_engine_and_native_specs(tmp_path: Path):
    decision_path = tmp_path / "research" / "iter_1" / "decision.json"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(json.dumps({"verdict": "accept"}))
    raw_spec = {
        "id": "REVIEW_DONE",
        "type": "process",
        "condition": {"source": "{iter}/decision.json", "field": "verdict"},
        "next": {"accept": "DONE", "revise": "PLAN"},
    }

    engine_next, engine_problem = resolve_next_state(_parse_state(raw_spec), tmp_path, 1)
    native_next, native_problem = resolve_next_state(raw_spec, tmp_path, 1)

    assert engine_problem is None
    assert native_problem is None
    assert engine_next == native_next == "DONE"


def test_resolve_next_state_resolves_current_phase_condition_source(tmp_path: Path):
    decision_path = tmp_path / "research" / "iter_2" / "results" / "phase_1.json"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(json.dumps({"verdict": "accept"}))
    raw_spec = {
        "id": "PHASE_DECIDE",
        "type": "process",
        "condition": {"source": "{iter}/results/{current_phase_id}.json", "field": "verdict"},
        "next": {"accept": "DONE", "revise": "PHASE_CODE"},
    }

    next_state, problem = resolve_next_state(
        raw_spec,
        tmp_path,
        2,
        current_phase_id="phase_1",
    )

    assert problem is None
    assert next_state == "DONE"


def test_resolve_next_state_from_value_supports_engine_and_native_specs():
    raw_spec = {
        "id": "CHECKPOINT",
        "type": "checkpoint",
        "next": {
            "approve": "PHASE_SELECT",
            "modify_plan": "PLAN",
            "stop": "DONE",
        },
    }

    engine_next, engine_problem = resolve_next_state_from_value(
        _parse_state(raw_spec),
        "modify_plan",
        fallback_values=("approve",),
        default_state="DONE",
    )
    native_next, native_problem = resolve_next_state_from_value(
        raw_spec,
        "unknown_action",
        fallback_values=("approve",),
        default_state="DONE",
    )

    assert engine_problem is None
    assert native_problem is None
    assert engine_next == "PLAN"
    assert native_next == "PHASE_SELECT"


def test_transition_starts_new_iteration_only_for_iteration_entry_sources():
    assert transition_starts_new_iteration("EXPLORE", "DOMAIN_RESEARCH")
    assert transition_starts_new_iteration("ROUTE", "IDEA_REFINE")
    assert transition_starts_new_iteration("ROUTE", "DOMAIN_RESEARCH")
    assert transition_starts_new_iteration("REVIEW_DONE", "IDEA_REFINE")
    assert not transition_starts_new_iteration("SHAPE_FULL", "DOMAIN_RESEARCH")
    assert not transition_starts_new_iteration("VISUALIZE_DATA", "IDEA_REFINE")
    assert not transition_starts_new_iteration("EXPLORE", "PLAN")


def test_carry_over_iteration_keeps_data_viz_for_idea_refine_entry(tmp_path: Path):
    src = tmp_path / "research" / "iter_1"
    src.mkdir(parents=True)
    (src / ".domain_research.json").write_text(json.dumps({"domain_type": "tabular"}))
    (src / ".data_analysis.json").write_text(json.dumps({"data_status": "available"}))
    (src / ".data_viz_manifest.json").write_text(json.dumps({"generated": [], "summary": "no data"}))
    (src / "data_viz").mkdir()
    (src / "data_viz" / "v1_distributions.png").write_bytes(b"png")

    carry_over_iteration(tmp_path, 1, 2, "IDEA_REFINE")

    dst = tmp_path / "research" / "iter_2"
    assert (dst / ".domain_research.json").exists()
    assert (dst / ".data_analysis.json").exists()
    assert (dst / ".data_viz_manifest.json").exists()
    assert (dst / "data_viz" / "v1_distributions.png").exists()


def test_apply_state_transition_writes_iteration_seed_from_reflect_new_idea(tmp_path: Path):
    idir = tmp_path / "research" / "iter_1"
    idir.mkdir(parents=True)
    (idir / "reflect.json").write_text(json.dumps({
        "decision": "idea_mutation",
        "reason": "The residual error analysis suggests a new causal framing.",
        "new_idea": "Test causal representation learning for the hard residual slices.",
        "future_iteration_seeds": [{
            "direction": "Causal representation learning",
            "status": "promote_next",
            "reason": "Targets the observed residual failure mode.",
        }],
        "idea_portfolio": [{
            "direction": "Causal representation learning",
            "rationale": "Targets the observed residual failure mode.",
            "evidence": "research/iter_1/results/phase_0.json",
            "scores": {
                "novelty": 4,
                "feasibility": 3,
                "expected_information_gain": 5,
                "risk": 3,
                "artifact_cost": 3,
            },
            "score": 16,
            "status": "promote_next",
        }],
        "selected_direction": {
            "direction": "Causal representation learning",
            "reason": "Highest information gain against the observed failure mode.",
            "evidence": "research/iter_1/results/phase_0.json",
        },
        "selection_rationale": "Causal representation learning best targets the hard residual slices.",
    }))

    applied = apply_state_transition(
        tmp_path,
        "IDEA_REFINE",
        current_state={"state": "ROUTE", "current_iteration": 1, "session_id": "old-session"},
        new_iteration_on_entry=transition_starts_new_iteration("ROUTE", "IDEA_REFINE"),
    )

    seed = json.loads((tmp_path / "research" / "iter_2" / ".iteration_seed.json").read_text())
    state = json.loads((tmp_path / "research" / ".state.json").read_text())
    assert applied.created_iteration
    assert seed["source_artifact"] == "research/iter_1/reflect.json"
    assert seed["new_idea"] == "Test causal representation learning for the hard residual slices."
    assert seed["selected_direction"]["direction"] == "Causal representation learning"
    assert seed["idea_portfolio"][0]["status"] == "promote_next"
    assert seed["future_iteration_seed"]["status"] == "promote_next"
    assert state["state"] == "IDEA_REFINE"
    assert state["current_iteration"] == 2
    assert state["session_id"] is None


def test_completion_advance_supports_engine_and_native_specs(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_1" / "reflect.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"decision": "done", "reason": "target met"}))
    raw_spec = {
        "id": "REFLECT",
        "type": "ai_session",
        "completion": {
            "artifact": "research/{iter}/reflect.json",
            "required_fields": ["decision", "reason"],
        },
        "condition": {"check": "has_pending_phases"},
        "next": {"true": "PHASE_CODE", "false": "PAPER_DRAFT"},
    }

    engine_advance = resolve_completion_advance(
        tmp_path,
        _parse_state(raw_spec),
        "REFLECT",
        1,
    )
    native_advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "REFLECT",
        1,
        written_file=artifact,
    )

    assert engine_advance.problem is None
    assert native_advance.problem is None
    assert engine_advance.next_state == native_advance.next_state == "PAPER_DRAFT"


def test_hypothesis_update_completion_requires_current_phase_entry(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_1" / "phases" / ".hypothesis_log.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "iteration": 1,
        "entries": [{"phase_id": "phase_1", "outgoing_hypothesis": "old"}],
    }))
    raw_spec = {
        "id": "HYPOTHESIS_UPDATE",
        "type": "ai_session",
        "completion": {
            "artifact": "research/{iter}/phases/.hypothesis_log.json",
            "required_fields": ["iteration", "entries"],
        },
        "next": "CHECKPOINT",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "HYPOTHESIS_UPDATE",
        1,
        current_phase_id="phase_2",
    )

    assert advance.problem is not None
    assert "stale hypothesis log" in advance.problem


def test_hypothesis_update_completion_accepts_latest_current_phase_entry(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_1" / "phases" / ".hypothesis_log.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "iteration": 1,
        "entries": [
            {"phase_id": "phase_1", "outgoing_hypothesis": "old"},
            {"phase_id": "phase_2", "outgoing_hypothesis": "new"},
        ],
    }))
    raw_spec = {
        "id": "HYPOTHESIS_UPDATE",
        "type": "ai_session",
        "completion": {
            "artifact": "research/{iter}/phases/.hypothesis_log.json",
            "required_fields": ["iteration", "entries"],
        },
        "next": "CHECKPOINT",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "HYPOTHESIS_UPDATE",
        1,
        current_phase_id="phase_2",
    )

    assert advance.problem is None
    assert advance.next_state == "CHECKPOINT"


def test_reflect_completion_blocks_mutation_without_idea_selection(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_1" / "reflect.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "decision": "idea_mutation",
        "reason": "Need a new direction.",
        "new_idea": "Try a different model family.",
        "future_iteration_seeds": [{"direction": "Try a different model family.", "status": "promote_next"}],
    }))
    raw_spec = {
        "id": "REFLECT",
        "type": "ai_session",
        "completion": {
            "artifact": "research/{iter}/reflect.json",
            "required_fields": ["decision", "reason"],
        },
        "next": "SHAPE_SEED",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "REFLECT",
        1,
        written_file=artifact,
    )

    assert advance.problem is not None
    assert "reflection strategy issues" in advance.problem
    assert "idea_portfolio" in advance.problem


def test_story_tell_completion_blocks_weak_final_paper(tmp_path: Path):
    artifact = tmp_path / "research" / "final_paper.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Paper\n\nToo short.")
    raw_spec = {
        "id": "STORY_TELL",
        "type": "ai_session",
        "completion": {"artifact": "research/final_paper.md"},
        "next": "REVIEW",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "STORY_TELL",
        1,
    )

    assert advance.problem is not None
    assert "final paper issues" in advance.problem
    assert "too short" in advance.problem


def test_runner_completion_advance_uses_resolved_state_contract(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_3" / "reflect.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"decision": "done", "reason": "target met"}))
    raw_spec = {
        "id": "REFLECT",
        "type": "ai_session",
        "completion": {
            "artifact": "research/{iter}/reflect.json",
            "required_fields": ["decision", "reason"],
        },
        "condition": {"check": "has_pending_phases"},
        "next": {"true": "PHASE_CODE", "false": "PAPER_DRAFT"},
    }
    contract = resolve_runner_state_contract(
        state_id="REFLECT",
        iteration=3,
        current_phase_id=None,
        spec=raw_spec,
        default_engine="claude",
    )

    advance = resolve_runner_completion_advance(tmp_path, contract, written_file=artifact)

    assert advance.problem is None
    assert advance.next_state == "PAPER_DRAFT"
    assert advance.pattern.endswith("research/iter_3/reflect.json")


def test_constraints_completion_advance_rejects_invalid_constraints_for_engine_and_native(tmp_path: Path):
    artifact = tmp_path / "research" / "constraints.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "objective": " ",
        "goal": "reduce error somehow",
        "invariants": [],
    }))
    raw_spec = {
        "id": "SHAPE_FULL",
        "type": "ai_session",
        "completion": {"artifact": "research/constraints.json"},
        "next": "DOMAIN_RESEARCH",
    }

    engine_advance = resolve_completion_advance(
        tmp_path,
        _parse_state(raw_spec),
        "SHAPE_FULL",
        1,
    )
    contract = resolve_runner_state_contract(
        state_id="SHAPE_FULL",
        iteration=1,
        current_phase_id=None,
        spec=raw_spec,
        default_engine="claude",
    )
    native_advance = resolve_runner_completion_advance(
        tmp_path,
        contract,
        written_file=artifact,
    )

    assert engine_advance.next_state is None
    assert native_advance.next_state is None
    assert engine_advance.problem == native_advance.problem
    assert "invalid constraints" in engine_advance.problem
    assert "'objective' must be a non-empty string" in engine_advance.problem
    assert "'goal' must be an object" in engine_advance.problem


def test_constraints_completion_advance_accepts_valid_constraints_without_required_fields(tmp_path: Path):
    artifact = tmp_path / "research" / "constraints.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "objective": "Build a leakage-safe model comparison.",
        "goal": {
            "metric": "mae",
            "direction": "minimize",
            "target": 0.5,
        },
        "invariants": ["No data leakage."],
    }))
    raw_spec = {
        "id": "SHAPE_FULL",
        "type": "ai_session",
        "completion": {"artifact": "research/constraints.json"},
        "next": "DOMAIN_RESEARCH",
    }

    engine_advance = resolve_completion_advance(
        tmp_path,
        _parse_state(raw_spec),
        "SHAPE_FULL",
        1,
    )
    native_advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "SHAPE_FULL",
        1,
        written_file=artifact,
    )

    assert engine_advance.problem is None
    assert native_advance.problem is None
    assert engine_advance.next_state == native_advance.next_state == "DOMAIN_RESEARCH"


def test_completion_advance_resolves_runtime_path_placeholders(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_4" / "results" / "phase_2.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"ok": True}))
    raw_spec = {
        "id": "PHASE_SUMMARY",
        "type": "ai_session",
        "completion": {
            "artifact": "research/{iter}/results/{current_phase_id}.json",
            "required_fields": ["ok"],
        },
        "next": "DONE",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "PHASE_SUMMARY",
        4,
        current_phase_id="phase_2",
        written_file=artifact,
    )

    assert advance.problem is None
    assert advance.next_state == "DONE"
    assert advance.pattern.endswith("research/iter_4/results/phase_2.json")


def test_completion_advance_ignores_unrelated_native_write(tmp_path: Path):
    raw_spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/.domain_research.json"},
        "next": "DATA_DEEP_DIVE",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "DOMAIN_RESEARCH",
        1,
        written_file=tmp_path / "research" / "iter_1" / "other.json",
    )

    assert not advance.relevant


def test_completion_advance_ignores_outside_native_write_with_matching_suffix(tmp_path: Path):
    project_dir = tmp_path / "project"
    outside_dir = tmp_path / "outside" / "research" / "iter_1"
    outside_dir.mkdir(parents=True)
    outside_artifact = outside_dir / "reflect.json"
    outside_artifact.write_text(json.dumps({"decision": "done", "reason": "target met"}))
    raw_spec = {
        "id": "REFLECT",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/reflect.json"},
        "next": "PAPER_DRAFT",
    }

    advance = resolve_completion_advance(
        project_dir,
        raw_spec,
        "REFLECT",
        1,
        written_file=outside_artifact,
    )

    assert not advance.relevant


def test_completion_advance_rejects_unsafe_completion_artifact(tmp_path: Path):
    raw_spec = {
        "id": "REFLECT",
        "type": "ai_session",
        "completion": {"artifact": "../reflect.json"},
        "next": "PAPER_DRAFT",
    }

    advance = resolve_completion_advance(tmp_path, raw_spec, "REFLECT", 1)

    assert advance.relevant
    assert advance.problem == "unsafe completion artifact: completion.artifact must not contain '..'"


def test_completion_advance_runs_quality_gate_without_required_fields(tmp_path: Path):
    artifact = tmp_path / "research" / "iter_1" / "research_plan.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "name": "weak",
        "metric": {"name": "mae"},
        "phases": [{
            "id": "phase_0",
            "type": "script",
            "depends_on": [],
            "status": "pending",
            "methodology": "train one model",
            "expected_outputs": {"report": {"path": "research/iter_1/results/phase_0.json", "schema": {"mae": {}}}},
            "visualization": ["phase_0_loss.png"],
        }],
    }))
    raw_spec = {
        "id": "PLAN",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/research_plan.json"},
        "next": "VALIDATE_PLAN",
    }

    engine_advance = resolve_completion_advance(
        tmp_path,
        _parse_state(raw_spec),
        "PLAN",
        1,
    )
    native_advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "PLAN",
        1,
        written_file=artifact,
    )

    assert engine_advance.problem is not None
    assert native_advance.problem is not None
    assert "research plan quality issues" in engine_advance.problem
    assert engine_advance.problem == native_advance.problem


def test_phase_code_completion_requires_current_phase_script_for_engine(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    pdir.mkdir(parents=True)
    (pdir / "phase_0_baseline.py").write_text("print('old phase')\n")
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
        "next": "PHASE_RUN",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "PHASE_CODE",
        1,
        current_phase_id="phase_1",
    )

    assert advance.next_state is None
    assert advance.problem is not None
    assert "No Python script found for phase phase_1" in advance.problem


def test_phase_code_completion_advances_for_current_phase_script(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    pdir.mkdir(parents=True)
    (pdir / "phase_0_baseline.py").write_text("print('old phase')\n")
    current_script = pdir / "phase_1_model.py"
    current_script.write_text("print('current phase')\n")
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
        "next": "PHASE_RUN",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "PHASE_CODE",
        1,
        current_phase_id="phase_1",
        written_file=current_script,
    )

    assert advance.problem is None
    assert advance.artifact_path == current_script
    assert advance.next_state == "PHASE_RUN"


def test_phase_code_completion_rejects_write_for_different_phase(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    pdir.mkdir(parents=True)
    wrong_script = pdir / "phase_0_baseline.py"
    wrong_script.write_text("print('wrong phase')\n")
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
        "next": "PHASE_RUN",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "PHASE_CODE",
        1,
        current_phase_id="phase_1",
        written_file=wrong_script,
    )

    assert advance.next_state is None
    assert advance.problem is not None
    assert "does not match current_phase_id phase_1" in advance.problem


def test_phase_code_completion_rejects_ambiguous_current_phase_scripts(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    pdir.mkdir(parents=True)
    current_script = pdir / "phase_1_model.py"
    current_script.write_text("print('current phase')\n")
    (pdir / "phase_1_eval.py").write_text("print('also current phase')\n")
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
        "next": "PHASE_RUN",
    }

    advance = resolve_completion_advance(
        tmp_path,
        raw_spec,
        "PHASE_CODE",
        1,
        current_phase_id="phase_1",
        written_file=current_script,
    )

    assert advance.next_state is None
    assert advance.problem is not None
    assert "Multiple Python scripts found for phase phase_1" in advance.problem


def test_phase_code_completion_requires_current_phase_id(tmp_path: Path):
    pdir = tmp_path / "research" / "iter_1" / "phases"
    pdir.mkdir(parents=True)
    (pdir / "phase_0_baseline.py").write_text("print('phase')\n")
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
        "next": "PHASE_RUN",
    }

    advance = resolve_completion_advance(tmp_path, raw_spec, "PHASE_CODE", 1)

    assert advance.next_state is None
    assert advance.problem == "PHASE_CODE completion requires current_phase_id"
