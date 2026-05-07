"""Tests for the shared engine/native runner contract."""
from __future__ import annotations

import json
from pathlib import Path

from tiny_lab.evidence import render_evidence_contract
from tiny_lab.runner_contract import (
    CLAUDE_NATIVE_HOOK_MATCHER,
    CODEX_NATIVE_HOOK_MATCHER,
    NATIVE_ENGINE_SELECTION_PLACEHOLDER,
    RUNNER_CONTRACT_END_MARKER,
    RUNNER_CONTRACT_PLACEHOLDER,
    RUNNER_CONTRACT_START_MARKER,
    STATE_ADVANCE_COMMAND,
    claude_hooks_config,
    codex_hooks_config,
    ensure_matcher_tools,
    load_quality_preamble,
    load_runner_state_snapshot,
    render_contract_template,
    render_codex_hooks_json,
    render_native_engine_selection,
    render_runner_contract,
    render_runner_contract_block,
    resolve_runner_state_snapshot,
    resolve_runner_state_contract,
)
from tiny_lab.workflow import _parse_state


def test_contract_renders_quality_and_audit_rules():
    text = render_runner_contract()

    assert "Shared Runner Contract" in text
    assert "Execution Modes" in text
    assert "ml_researcher_rubric.md" in text
    assert "tiny-lab audit --strict" in text
    assert "tiny-lab doctor" in text
    assert "tiny-lab doctor --probe-backend" in text
    assert "tiny-lab doctor --repair-runner" in text
    assert "Run `tiny-lab doctor` before advancing work" in text
    assert "do not execute `tiny-lab prompt` or `tiny-lab step`" in text
    assert "tiny-lab brief" in text
    assert "tiny-lab prompt" in text
    assert "tiny-lab step" in text
    assert "Do not hand-parse `research/.workflow.json`" in text
    assert "debug-only raw state file; do not use instead of brief" in text
    assert "RunnerStateContract.iteration" in text
    assert "RunnerStateContract.current_phase_id" in text
    assert "`current_iteration` from `research/.state.json`" not in text
    assert "`current_phase_id` from `research/.state.json`" not in text
    assert "tiny_lab.hooks.state_policy" in text
    assert "transition application" in text
    assert "Reproducibility seed metadata" in text
    assert "tiny_lab.phase_contract" in text
    assert "tiny_lab.plan" in text
    assert "tiny_lab.quality" in text
    assert "tiny_lab.evidence" in text
    assert "tiny_lab.refs" in text
    assert "tiny_lab.review" in text
    assert "Experimental Plan Quality Contract" in text
    assert "Reference Verification Contract" in text
    assert "Final Paper Contract" in text
    assert "Professor Evaluation Contract" in text
    assert "<current_phase_id>_<current_phase_name_slug>.py" in text


def test_template_placeholder_is_replaced():
    rendered = render_contract_template(
        f"before\n{RUNNER_CONTRACT_PLACEHOLDER}\n{NATIVE_ENGINE_SELECTION_PLACEHOLDER}\nafter",
        native_runner="codex",
    )

    assert RUNNER_CONTRACT_PLACEHOLDER not in rendered
    assert NATIVE_ENGINE_SELECTION_PLACEHOLDER not in rendered
    assert RUNNER_CONTRACT_START_MARKER in rendered
    assert RUNNER_CONTRACT_END_MARKER in rendered
    assert "before" in rendered
    assert "Shared Runner Contract" in rendered
    assert "intended engine was `claude` but native mode is using `codex`" in rendered
    assert "after" in rendered


def test_runner_contract_block_has_markers():
    block = render_runner_contract_block()

    assert block.startswith(RUNNER_CONTRACT_START_MARKER)
    assert block.endswith(RUNNER_CONTRACT_END_MARKER)
    assert render_runner_contract() in block


def test_native_runner_templates_use_contract_placeholders():
    root = Path(__file__).resolve().parents[2]
    templates = [
        root / "src" / "tiny_lab" / "templates" / "CLAUDE.md",
        root / "src" / "tiny_lab" / "templates" / "codex" / "AGENTS.md",
        root / "src" / "tiny_lab" / "templates" / "skill" / "SKILL.md",
    ]
    contract = render_runner_contract()

    for template in templates:
        text = template.read_text()

        assert RUNNER_CONTRACT_PLACEHOLDER in text
        assert "## Shared Runner Contract" not in text
        assert contract in render_contract_template(text)
        assert NATIVE_ENGINE_SELECTION_PLACEHOLDER not in render_contract_template(text)

    assert NATIVE_ENGINE_SELECTION_PLACEHOLDER in templates[1].read_text()
    assert NATIVE_ENGINE_SELECTION_PLACEHOLDER in templates[2].read_text()


def test_codex_native_template_resumes_via_brief_not_raw_state_file():
    root = Path(__file__).resolve().parents[2]
    text = (root / "src" / "tiny_lab" / "templates" / "codex" / "AGENTS.md").read_text()

    assert "run `tiny-lab brief` and follow its current-state contract" in text
    assert "resume from `research/.state.json`" not in text


def test_native_engine_selection_is_rendered_from_runner_profile():
    claude_text = render_native_engine_selection("claude")
    codex_text = render_native_engine_selection("codex")

    assert "`tiny-lab run --engine codex`" in claude_text
    assert "intended engine was `codex` but native mode is using `claude`" in claude_text
    assert "`tiny-lab run --engine claude`" in codex_text
    assert "intended engine was `claude` but native mode is using `codex`" in codex_text


def test_runner_state_contract_matches_for_engine_and_native_specs():
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "prompt": "prompts/phase_code.md",
        "engine": "codex",
        "allowed_tools": ["Read", "Write", "Edit", "Bash"],
        "allowed_write_globs": [
            "research/{iter}/phases/*.py",
            "research/{iter}/results/*.json",
        ],
        "blocked_write_globs": ["research/{iter}/research_plan.json"],
        "blocked_bash_patterns": ["rm -rf research/{iter}"],
        "completion": {
            "artifact": "research/{iter}/phases/phase_*.py",
            "required_fields": [],
        },
        "condition": {"check": "has_pending_phases"},
        "next": {"true": "PHASE_RUN", "false": "PAPER_DRAFT"},
    }

    engine_contract = resolve_runner_state_contract(
        state_id="PHASE_CODE",
        iteration=3,
        current_phase_id="phase_1",
        spec=_parse_state(raw_spec),
        default_engine="claude",
    )
    native_contract = resolve_runner_state_contract(
        state_id="PHASE_CODE",
        iteration=3,
        current_phase_id="phase_1",
        spec=raw_spec,
        default_engine="claude",
    )

    assert engine_contract.to_dict() == native_contract.to_dict()
    assert engine_contract.intended_engine == "codex"
    assert engine_contract.runner_command == "tiny-lab prompt"
    assert engine_contract.allowed_write_globs == (
        "research/iter_3/phases/*.py",
        "research/iter_3/results/*.json",
    )
    assert engine_contract.completion_artifact == "research/iter_3/phases/phase_*.py"
    assert engine_contract.condition == {"check": "has_pending_phases"}


def test_engine_briefing_matches_native_snapshot_for_all_preset_states(tmp_path: Path):
    from tiny_lab.engine import Engine
    from tiny_lab.handlers.defaults import base_registry
    from tiny_lab.state import LoopState, save_state

    root = Path(__file__).resolve().parents[2]
    preset_dir = root / "src" / "tiny_lab" / "presets"
    for preset_path in sorted(preset_dir.glob("*.json")):
        workflow_data = json.loads(preset_path.read_text())
        states = workflow_data.get("states", [])
        if not isinstance(states, list) or not states:
            continue

        project_dir = tmp_path / preset_path.stem
        research_dir = project_dir / "research"
        research_dir.mkdir(parents=True)
        (project_dir / "shared").mkdir()
        (research_dir / ".workflow.json").write_text(preset_path.read_text())

        for raw_spec in states:
            state_id = raw_spec["id"]
            save_state(
                project_dir,
                LoopState(state=state_id, current_iteration=3, current_phase_id="phase_1"),
            )

            engine_contract = Engine(project_dir, base_registry()).current_state_briefing()
            snapshot = load_runner_state_snapshot(project_dir)

            assert snapshot is not None
            assert engine_contract.to_dict() == snapshot.contract.to_dict(), (
                f"{preset_path.name}:{state_id}"
            )


def test_runner_state_contract_resolves_runtime_path_placeholders():
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "allowed_write_globs": [
            "research/{iter}/results/{current_phase_id}.json",
            "research/iteration_{iteration}.txt",
        ],
        "blocked_write_globs": ["research/{iter}/phases/{current_phase_id}.py"],
        "blocked_bash_patterns": ["python research/{iter}/phases/{current_phase_id}.py"],
        "completion": {
            "artifact": "research/{iter}/results/{current_phase_id}.json",
        },
        "next": "PHASE_RUN",
    }

    contract = resolve_runner_state_contract(
        state_id="PHASE_CODE",
        iteration=3,
        current_phase_id="phase_1",
        spec=raw_spec,
        default_engine="claude",
    )

    assert contract.allowed_write_globs == (
        "research/iter_3/results/phase_1.json",
        "research/iteration_3.txt",
    )
    assert contract.blocked_write_globs == ("research/iter_3/phases/phase_1.py",)
    assert contract.blocked_bash_patterns == ("python research/iter_3/phases/phase_1.py",)
    assert contract.completion_artifact == "research/iter_3/results/phase_1.json"


def test_runner_state_contract_handles_done_without_workflow_spec():
    contract = resolve_runner_state_contract(
        state_id="DONE",
        iteration=2,
        current_phase_id=None,
        spec=None,
        default_engine="claude",
    )

    assert contract.state == "DONE"
    assert contract.state_type == "terminal"
    assert contract.runner_command is None
    assert contract.allowed_tools == ()
    assert contract.next is None


def test_runner_state_contract_preserves_unknown_state_without_workflow_spec():
    contract = resolve_runner_state_contract(
        state_id="MISSING_STATE",
        iteration=2,
        current_phase_id="phase_1",
        spec=None,
        default_engine="claude",
    )

    assert contract.state == "MISSING_STATE"
    assert contract.state_type == "unknown"
    assert contract.runner_command is None
    assert "missing from research/.workflow.json" in contract.action
    assert contract.current_phase_id == "phase_1"


def test_runner_state_snapshot_resolves_raw_state_and_workflow_once():
    raw_spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "prompt": "prompts/phase_code.md",
        "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
        "next": "PHASE_RUN",
    }

    snapshot = resolve_runner_state_snapshot(
        state_data={"state": "PHASE_CODE", "current_iteration": "3", "current_phase_id": 7},
        workflow_data={"engine": "codex", "states": [raw_spec]},
    )

    assert snapshot.state_spec == raw_spec
    assert snapshot.contract.state == "PHASE_CODE"
    assert snapshot.contract.iteration == 3
    assert snapshot.contract.current_phase_id == "7"
    assert snapshot.contract.completion_artifact == "research/iter_3/phases/phase_*.py"
    assert snapshot.contract.intended_engine == "codex"


def test_runner_state_snapshot_reports_unknown_state_contract():
    snapshot = resolve_runner_state_snapshot(
        state_data={"state": "MISSING_STATE", "current_iteration": 3},
        workflow_data={"engine": "codex", "states": []},
    )

    assert snapshot.state_spec is None
    assert snapshot.contract.state == "MISSING_STATE"
    assert snapshot.contract.state_type == "unknown"
    assert snapshot.contract.intended_engine == "codex"


def test_runner_state_snapshot_loader_is_project_file_ssot(tmp_path: Path):
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    (research_dir / ".state.json").write_text(
        '{"state":"REFLECT","current_iteration":2,"current_phase_id":"phase_1"}\n'
    )
    (research_dir / ".workflow.json").write_text(
        '{"engine":"codex","states":[{"id":"REFLECT","type":"ai_session",'
        '"completion":{"artifact":"research/{iter}/reflect.json","required_fields":["decision"]},'
        '"next":"PAPER_DRAFT"}]}\n'
    )

    snapshot = load_runner_state_snapshot(tmp_path)

    assert snapshot is not None
    assert snapshot.contract.state == "REFLECT"
    assert snapshot.contract.iteration == 2
    assert snapshot.contract.current_phase_id == "phase_1"
    assert snapshot.contract.completion_artifact == "research/iter_2/reflect.json"
    assert snapshot.contract.completion_required_fields == ("decision",)
    assert snapshot.contract.intended_engine == "codex"


def test_runner_state_snapshot_loader_fails_open_for_missing_or_invalid_files(tmp_path: Path):
    assert load_runner_state_snapshot(tmp_path) is None

    research_dir = tmp_path / "research"
    research_dir.mkdir()
    (research_dir / ".state.json").write_text("{")
    (research_dir / ".workflow.json").write_text('{"states":[]}')

    assert load_runner_state_snapshot(tmp_path) is None

    (research_dir / ".state.json").write_text('{"state":"REFLECT","current_iteration":2}\n')
    (research_dir / ".workflow.json").write_text('{"states":{"id":"REFLECT"}}\n')

    assert load_runner_state_snapshot(tmp_path) is None


def test_engine_briefing_uses_shared_runner_state_contract():
    root = Path(__file__).resolve().parents[2]
    engine = root / "src" / "tiny_lab" / "engine.py"

    assert "resolve_runner_state_contract" in engine.read_text()


def test_ai_session_handler_consumes_runner_contract_for_runtime_decisions():
    root = Path(__file__).resolve().parents[2]
    handler = root / "src" / "tiny_lab" / "handlers" / "ai_session.py"
    text = handler.read_text()

    assert "_current_runner_contract" in text
    assert "backend_name = contract.intended_engine" in text
    assert "allowed_tools=list(contract.allowed_tools) or None" in text
    assert "resolve_runner_completion_advance(ctx.project_dir, contract)" in text
    assert "spec.completion.artifact.replace" not in text
    assert "allowed_tools=spec.allowed_tools" not in text


def test_engine_and_native_hook_use_shared_advancement_logic():
    root = Path(__file__).resolve().parents[2]
    engine = root / "src" / "tiny_lab" / "engine.py"
    conditional_handler = root / "src" / "tiny_lab" / "handlers" / "conditional.py"
    engine_handler = root / "src" / "tiny_lab" / "handlers" / "ai_session.py"
    checkpoint_handler = root / "src" / "tiny_lab" / "handlers" / "checkpoint.py"
    reflect_handler = root / "src" / "tiny_lab" / "handlers" / "reflect.py"
    native_hook = root / "src" / "tiny_lab" / "hooks" / "state_advance.py"

    assert "resolve_next_state" in engine.read_text()
    assert "resolve_next_state" in conditional_handler.read_text()
    assert "resolve_runner_completion_advance" in engine_handler.read_text()
    assert "apply_state_transition" in engine_handler.read_text()
    assert "resolve_next_state_from_value" in checkpoint_handler.read_text()
    assert "resolve_next_state_from_value" in reflect_handler.read_text()
    assert "spec.next.get" not in checkpoint_handler.read_text()
    assert "spec.next.get" not in reflect_handler.read_text()
    hook_text = native_hook.read_text()
    assert "load_runner_state_snapshot" in hook_text
    assert "resolve_runner_completion_advance" in hook_text
    assert "apply_state_transition" in hook_text
    assert "write_traceable_final_paper" in hook_text
    assert "find_state_spec" not in hook_text
    assert "json.loads" not in hook_text
    assert "def _resolve_conditional_next" not in hook_text
    assert "set_state(Path.cwd(), advance.next_state)" not in hook_text


def test_native_state_gate_uses_shared_policy_logic():
    root = Path(__file__).resolve().parents[2]
    native_hook = root / "src" / "tiny_lab" / "hooks" / "state_gate.py"
    policy = root / "src" / "tiny_lab" / "hooks" / "state_policy.py"

    hook_text = native_hook.read_text()
    assert "load_runner_state_snapshot" in hook_text
    assert "find_state_spec" not in hook_text
    assert "evaluate_runner_state_gate" in hook_text
    assert "evaluate_state_gate(" not in hook_text
    assert "wf_data.get(\"states\"" not in hook_text
    assert "json.loads" not in hook_text
    assert "def _write_tool_allowed" not in hook_text
    policy_text = policy.read_text()
    assert "def evaluate_runner_state_gate" in policy_text
    assert "def evaluate_state_gate" in policy_text
    assert "resolve_runner_state_contract" in policy_text
    assert "allowed_write_globs\": _resolved_globs" not in policy_text


def test_native_hook_registration_is_generated_from_shared_contract():
    claude = claude_hooks_config()
    codex = codex_hooks_config()

    assert claude["PreToolUse"][0]["matcher"] == CLAUDE_NATIVE_HOOK_MATCHER
    assert claude["PostToolUse"][0]["hooks"][0]["command"] == STATE_ADVANCE_COMMAND
    assert codex["hooks"]["PostToolUse"][0]["matcher"] == CODEX_NATIVE_HOOK_MATCHER
    assert "state_advance.py" in codex["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert render_codex_hooks_json().endswith("\n")


def test_codex_hooks_template_matches_shared_contract_renderer():
    root = Path(__file__).resolve().parents[2]
    template = root / "src" / "tiny_lab" / "templates" / "codex" / "hooks.json"

    assert template.read_text() == render_codex_hooks_json()


def test_hook_matcher_upgrade_uses_shared_helper():
    assert ensure_matcher_tools("apply_patch", ["Bash"]) == "apply_patch|Bash"
    assert ensure_matcher_tools("apply_patch|Bash", ["Bash"]) == "apply_patch|Bash"


def test_evidence_contract_renders_gate_tokens_for_prompts():
    text = render_evidence_contract()

    assert "Experimental Evidence Contract" in text
    assert "tiny_lab.evidence" in text
    assert "Uncertainty evidence is limited to" in text
    assert "significance evidence is limited to" in text
    assert "do not by themselves establish uncertainty or significance" in text
    for token in (
        "baseline_results",
        "prior_work_results",
        "causal_identification",
        "robustness_checks",
        "external_validation_results",
        "feature_importance",
        "fold_count",
        "error_analysis",
        "leakage_found",
    ):
        assert token in text


def test_quality_preamble_prefers_project_override(tmp_path: Path):
    rubric = tmp_path / "prompts" / "_shared" / "ml_researcher_rubric.md"
    rubric.parent.mkdir(parents=True)
    rubric.write_text("PROJECT RUBRIC")

    assert load_quality_preamble(tmp_path) == "PROJECT RUBRIC"


def test_quality_preamble_falls_back_to_packaged_rubric(tmp_path: Path):
    text = load_quality_preamble(tmp_path)

    assert "ML Researcher Quality Standard" in text
    assert "Traceable claims" in text
