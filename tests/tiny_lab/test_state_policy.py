"""Tests for shared native state gate policy."""
from __future__ import annotations

from tiny_lab.hooks.state_policy import evaluate_runner_state_gate, evaluate_state_gate
from tiny_lab.hooks.tool_names import WRITE_TOOL_NAMES


def test_write_tool_names_are_shared_for_hook_policy():
    assert WRITE_TOOL_NAMES == ("Write", "Edit", "MultiEdit")


def test_state_policy_blocks_disallowed_tinylab_write(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Write",
        file_paths=("research/iter_1/.forbidden.json",),
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "허용되지 않음" in (decision.reason or "")


def test_runner_state_contract_policy_blocks_disallowed_resolved_write(tmp_path):
    contract = {
        "state": "DOMAIN_RESEARCH",
        "iteration": 2,
        "current_phase_id": None,
        "state_type": "ai_session",
        "allowed_tools": ("Write",),
        "allowed_write_globs": ("research/iter_2/.domain_research.json",),
        "blocked_write_globs": (),
        "blocked_bash_patterns": (),
    }

    decision = evaluate_runner_state_gate(
        contract,
        {"state": "DOMAIN_RESEARCH", "current_iteration": 2},
        tool_name="Write",
        file_paths=("research/iter_2/.forbidden.json",),
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "research/iter_2/.domain_research.json" in (decision.reason or "")


def test_state_policy_blocks_tinylab_write_when_state_is_unknown(tmp_path):
    contract = {
        "state": "MISSING_STATE",
        "iteration": 2,
        "current_phase_id": None,
        "state_type": "unknown",
        "allowed_tools": (),
        "allowed_write_globs": (),
        "blocked_write_globs": (),
        "blocked_bash_patterns": (),
    }

    decision = evaluate_runner_state_gate(
        contract,
        {"state": "MISSING_STATE", "current_iteration": 2},
        tool_name="Write",
        file_paths=("research/iter_2/results/phase_0.json",),
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "workflow" in (decision.reason or "")


def test_state_policy_allows_external_write_when_state_is_unknown(tmp_path):
    contract = {
        "state": "MISSING_STATE",
        "iteration": 2,
        "current_phase_id": None,
        "state_type": "unknown",
        "allowed_tools": (),
        "allowed_write_globs": (),
        "blocked_write_globs": (),
        "blocked_bash_patterns": (),
    }

    decision = evaluate_runner_state_gate(
        contract,
        {"state": "MISSING_STATE", "current_iteration": 2},
        tool_name="Write",
        file_paths=(str(tmp_path / "notes.txt"),),
        root=tmp_path,
    )

    assert decision.allowed is True


def test_state_policy_allows_external_write(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Read"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Write",
        file_paths=(str(tmp_path / "src" / "scratch.py"),),
        root=tmp_path,
    )

    assert decision.allowed is True


def test_state_policy_resolves_runtime_placeholders_from_contract(tmp_path):
    spec = {
        "id": "PHASE_RECORD",
        "type": "ai_session",
        "allowed_tools": ["Write"],
        "allowed_write_globs": ["research/{iter}/results/{current_phase_id}.json"],
    }
    state = {"state": "PHASE_RECORD", "current_iteration": 3, "current_phase_id": "phase_2"}

    allowed = evaluate_state_gate(
        spec,
        state,
        tool_name="Write",
        file_paths=("research/iter_3/results/phase_2.json",),
        root=tmp_path,
    )
    denied = evaluate_state_gate(
        spec,
        state,
        tool_name="Write",
        file_paths=("research/iter_3/results/phase_3.json",),
        root=tmp_path,
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "research/iter_3/results/phase_2.json" in (denied.reason or "")


def test_state_policy_blocks_wrong_phase_script(tmp_path):
    spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "allowed_tools": ["Read", "Write"],
        "allowed_write_globs": ["research/{iter}/phases/*"],
    }
    state = {"state": "PHASE_CODE", "current_iteration": 1, "current_phase_id": "phase_1"}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Write",
        file_paths=("research/iter_1/phases/phase_0.py",),
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "현재 phase `phase_1`" in (decision.reason or "")


def test_state_policy_blocks_bash_write_to_blocked_path(tmp_path):
    spec = {
        "id": "PHASE_RUN",
        "type": "process",
        "allowed_tools": ["Bash"],
        "blocked_write_globs": ["research/{iter}/phases/*"],
    }
    state = {"state": "PHASE_RUN", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="cat > research/iter_1/phases/phase_0.py",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "Bash command writes blocked path" in (decision.reason or "")


def test_state_policy_blocks_bash_write_outside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="cat > research/iter_1/.forbidden.json",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "outside allowed paths" in (decision.reason or "")


def test_state_policy_blocks_mkdir_outside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="mkdir -p research/iter_1/.forbidden",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "outside allowed paths" in (decision.reason or "")


def test_state_policy_allows_mkdir_for_allowed_glob_parent(tmp_path):
    spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/phases/*", "shared/lib/*"],
    }
    state = {"state": "PHASE_CODE", "current_iteration": 1, "current_phase_id": "phase_0"}

    phase_dir = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="mkdir -p research/iter_1/phases",
        root=tmp_path,
    )
    shared_lib = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="mkdir -p shared/lib",
        root=tmp_path,
    )

    assert phase_dir.allowed is True
    assert shared_lib.allowed is True


def test_state_policy_blocks_rmdir_of_blocked_glob_parent(tmp_path):
    spec = {
        "id": "PHASE_RUN",
        "type": "process",
        "allowed_tools": ["Bash"],
        "blocked_write_globs": ["research/{iter}/phases/*"],
    }
    state = {"state": "PHASE_RUN", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="rmdir research/iter_1/phases",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "blocked path" in (decision.reason or "")


def test_state_policy_blocks_dd_output_outside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="dd if=/dev/null of=research/iter_1/.forbidden.json bs=1 count=0",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "outside allowed paths" in (decision.reason or "")


def test_state_policy_blocks_install_destination_outside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="install -m 644 /tmp/result.json research/iter_1/.forbidden.json",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "outside allowed paths" in (decision.reason or "")


def test_state_policy_allows_bash_write_inside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="cat > research/iter_1/.domain_research.json",
        root=tmp_path,
    )

    assert decision.allowed is True


def test_state_policy_blocks_checkpoint_bash_write_to_tinylab_path(tmp_path):
    spec = {
        "id": "CHECKPOINT",
        "type": "checkpoint",
    }
    state = {"state": "CHECKPOINT", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="cat > research/.intervention.json",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "checkpoint" in (decision.reason or "")


def test_state_policy_blocks_bash_write_to_wrong_phase_script(tmp_path):
    spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/phases/*"],
    }
    state = {"state": "PHASE_CODE", "current_iteration": 1, "current_phase_id": "phase_1"}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command="cat > research/iter_1/phases/phase_0.py",
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "현재 phase `phase_1`" in (decision.reason or "")


def test_state_policy_blocks_inline_python_open_write_outside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command='python -c "open(\'research/iter_1/.forbidden.json\', \'w\').write(\'{}\')"',
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "outside allowed paths" in (decision.reason or "")


def test_state_policy_blocks_inline_python_path_write_to_wrong_phase_script(tmp_path):
    spec = {
        "id": "PHASE_CODE",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/phases/*"],
    }
    state = {"state": "PHASE_CODE", "current_iteration": 1, "current_phase_id": "phase_1"}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command='python -c "from pathlib import Path; Path(\'research/iter_1/phases/phase_0.py\').write_text(\'x\')"',
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "현재 phase `phase_1`" in (decision.reason or "")


def test_state_policy_blocks_inline_python_path_mkdir_outside_allowed_globs(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command='python -c "from pathlib import Path; Path(\'research/iter_1/.forbidden\').mkdir()"',
        root=tmp_path,
    )

    assert decision.allowed is False
    assert "outside allowed paths" in (decision.reason or "")


def test_state_policy_allows_inline_python_read_of_research_path(tmp_path):
    spec = {
        "id": "DOMAIN_RESEARCH",
        "type": "ai_session",
        "allowed_tools": ["Bash"],
        "allowed_write_globs": ["research/{iter}/.domain_research.json"],
    }
    state = {"state": "DOMAIN_RESEARCH", "current_iteration": 1}

    decision = evaluate_state_gate(
        spec,
        state,
        tool_name="Bash",
        command='python -c "open(\'research/iter_1/.forbidden.json\', \'r\').read()"',
        root=tmp_path,
    )

    assert decision.allowed is True
