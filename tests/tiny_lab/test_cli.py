"""Tests for CLI commands."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from tiny_lab.review import REQUIRED_SCORE_KEYS, RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA

PNG_SIGNATURE = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _claude_hook_blocks(settings: dict, event: str, command_fragment: str) -> list[dict]:
    return [
        block for block in settings["hooks"][event]
        if any(
            isinstance(hook, dict) and command_fragment in str(hook.get("command", ""))
            for hook in block.get("hooks", [])
        )
    ]


def _claude_hook_commands(settings: dict, event: str) -> set[str]:
    return {
        str(hook.get("command", ""))
        for block in settings["hooks"][event]
        for hook in block.get("hooks", [])
        if isinstance(hook, dict)
    }


def _complete_review_feedback(score: int = 8) -> list[dict]:
    return [
        {
            "criterion": criterion,
            "score": score,
            "recommendation": (
                f"Maintain artifact-backed evidence for {criterion.replace('_', ' ')} "
                f"using {_feedback_artifact_for(criterion)}."
            ),
        }
        for criterion in REQUIRED_SCORE_KEYS
    ]


def _feedback_artifact_for(criterion: str) -> str:
    if criterion in RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA:
        return "research/iter_1/results/phase_0.json"
    return "research/final_paper.md"


class _FakeReferenceVerificationResult:
    def __init__(
        self,
        *,
        total: int,
        verified: int,
        not_found: int = 0,
        unverified: int = 0,
        error: int = 0,
    ) -> None:
        self.source_file = "research/iter_1/.domain_research.json"
        self.total = total
        self.verified = verified
        self.not_found = not_found
        self.unverified = unverified
        self.error = error


class TestInit:
    def test_init_creates_structure(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "ml-experiment")

        assert (tmp_path / "research" / ".workflow.json").exists()
        assert (tmp_path / ".claude" / "hooks" / "state_gate.py").exists()
        assert (tmp_path / ".claude" / "hooks" / "state_advance.py").exists()
        assert (tmp_path / ".claude" / "hooks" / "state_policy.py").exists()
        assert (tmp_path / ".claude" / "hooks" / "command_paths.py").exists()
        assert (tmp_path / ".claude" / "hooks" / "tool_names.py").exists()
        assert (tmp_path / "prompts" / "domain_research.md").exists()
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".claude" / "skills" / "tiny-lab" / "SKILL.md").exists()
        assert (tmp_path / "shared").exists()
        from tiny_lab.runner_contract import render_runner_contract

        contract = render_runner_contract()
        for runner_doc in (
            tmp_path / "CLAUDE.md",
            tmp_path / "AGENTS.md",
            tmp_path / ".claude" / "skills" / "tiny-lab" / "SKILL.md",
        ):
            text = runner_doc.read_text()
            assert contract in text
            assert "{{TINY_LAB_RUNNER_CONTRACT}}" not in text
            assert "{{TINY_LAB_NATIVE_ENGINE_SELECTION}}" not in text

    def test_init_next_steps_include_readiness_check(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_init

        _cmd_init(tmp_path, "ml-experiment")
        output = capsys.readouterr().out

        assert "Next steps:" in output
        assert "1. Write your idea" in output
        assert "2. Check readiness:  tiny-lab doctor --probe-backend" in output
        assert "3. Start the loop:   tiny-lab run" in output

    def test_init_registers_hooks(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        from tiny_lab.runner_contract import CLAUDE_NATIVE_HOOK_MATCHER
        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        hooks = settings["hooks"]
        assert _claude_hook_blocks(settings, "PreToolUse", "state_gate")
        assert _claude_hook_blocks(settings, "PostToolUse", "state_advance")
        assert all(
            e["matcher"] == CLAUDE_NATIVE_HOOK_MATCHER
            for e in _claude_hook_blocks(settings, "PreToolUse", "state_gate")
        )
        assert all(
            e["matcher"] == CLAUDE_NATIVE_HOOK_MATCHER
            for e in (
                _claude_hook_blocks(settings, "PostToolUse", "state_advance")
                + _claude_hook_blocks(settings, "PostToolUse", "ref_verify")
            )
        )

        from tiny_lab.runner_contract import codex_hooks_config
        assert json.loads((tmp_path / ".codex" / "hooks.json").read_text()) == codex_hooks_config()

    def test_init_normalizes_existing_claude_hook_schema(self, tmp_path):
        from tiny_lab.cli import _cmd_init

        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {
                "Stop": [{
                    "command": "echo Done",
                    "timeout": 5,
                }],
            },
        }))

        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        stop = settings["hooks"]["Stop"][0]
        assert stop["matcher"] == ""
        assert stop["hooks"] == [{
            "type": "command",
            "command": "echo Done",
            "timeout": 5,
        }]

    def test_init_upgrades_post_tool_hooks_to_include_bash(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {
                "PostToolUse": [{
                    "matcher": "Write|Edit|MultiEdit",
                    "command": "python3 .claude/hooks/state_advance.py",
                }, {
                    "matcher": "Write|Edit|MultiEdit",
                    "command": "python3 .claude/hooks/ref_verify.py",
                }]
            }
        }))

        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        advance = _claude_hook_blocks(settings, "PostToolUse", "state_advance")
        ref_verify = _claude_hook_blocks(settings, "PostToolUse", "ref_verify")
        assert len(advance) == 1
        assert len(ref_verify) == 1
        assert "Bash" in advance[0]["matcher"]
        assert "Bash" in ref_verify[0]["matcher"]

    def test_init_preserves_extra_claude_hook_matchers(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Write|NotebookEdit",
                    "command": "python3 .claude/hooks/state_gate.py",
                }]
            }
        }))

        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        gate = _claude_hook_blocks(settings, "PreToolUse", "state_gate")[0]
        assert gate["matcher"] == "Write|NotebookEdit|Edit|MultiEdit|Bash"

    def test_init_idempotent_hooks(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "ml-experiment")
        first = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        _cmd_init(tmp_path, "ml-experiment")  # second init
        second = json.loads((tmp_path / ".claude" / "settings.json").read_text())

        # Hooks count must not grow on re-init
        assert len(second["hooks"]["PreToolUse"]) == len(first["hooks"]["PreToolUse"])
        assert len(second["hooks"]["PostToolUse"]) == len(first["hooks"]["PostToolUse"])
        # And the registered hooks should still include both expected commands
        post_cmds = _claude_hook_commands(second, "PostToolUse")
        assert any("state_advance" in c for c in post_cmds)
        assert any("ref_verify" in c for c in post_cmds)

    def test_init_updates_stale_legacy_runner_doc(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        from tiny_lab.runner_contract import render_runner_contract

        _cmd_init(tmp_path, "ml-experiment")
        (tmp_path / "AGENTS.md").write_text(
            "# tiny-lab native runner\n\n"
            "## Shared Runner Contract (SSOT)\n"
            "stale generated contract\n"
        )

        _cmd_init(tmp_path, "ml-experiment")

        text = (tmp_path / "AGENTS.md").read_text()
        assert render_runner_contract() in text
        assert "stale generated contract" not in text

    def test_init_marks_current_legacy_runner_doc(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        from tiny_lab.runner_contract import (
            RUNNER_CONTRACT_END_MARKER,
            RUNNER_CONTRACT_START_MARKER,
            render_runner_contract,
        )

        _cmd_init(tmp_path, "ml-experiment")
        text = (tmp_path / "AGENTS.md").read_text()
        legacy_text = text.replace(RUNNER_CONTRACT_START_MARKER + "\n", "").replace(
            "\n" + RUNNER_CONTRACT_END_MARKER,
            "",
        )
        (tmp_path / "AGENTS.md").write_text(legacy_text)

        _cmd_init(tmp_path, "ml-experiment")

        updated = (tmp_path / "AGENTS.md").read_text()
        assert RUNNER_CONTRACT_START_MARKER in updated
        assert RUNNER_CONTRACT_END_MARKER in updated
        assert render_runner_contract() in updated

    def test_init_appends_runner_doc_to_existing_custom_doc(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        from tiny_lab.runner_contract import render_runner_contract

        (tmp_path / "AGENTS.md").write_text("# Project instructions\n\nKeep this note.\n")

        _cmd_init(tmp_path, "ml-experiment")

        text = (tmp_path / "AGENTS.md").read_text()
        assert "# Project instructions" in text
        assert "Keep this note." in text
        assert render_runner_contract() in text

    def test_init_upgrades_existing_codex_post_tool_hooks_to_include_bash(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        hooks_path = tmp_path / ".codex" / "hooks.json"
        hooks_path.parent.mkdir(parents=True)
        hooks_path.write_text(json.dumps({
            "hooks": {
                "PostToolUse": [{
                    "matcher": "apply_patch",
                    "hooks": [{
                        "type": "command",
                        "command": "python3 .claude/hooks/state_advance.py",
                    }, {
                        "type": "command",
                        "command": "python3 .claude/hooks/ref_verify.py",
                    }],
                }]
            }
        }))

        _cmd_init(tmp_path, "ml-experiment")

        hooks = json.loads(hooks_path.read_text())
        matchers = [
            block["matcher"]
            for block in hooks["hooks"]["PostToolUse"]
            for hook in block["hooks"]
            if "state_advance" in hook["command"]
        ]
        assert matchers == ["apply_patch|Bash"]

    def test_init_repairs_missing_codex_hook_commands(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        from tiny_lab.runner_contract import STATE_GATE_COMMAND, STATE_ADVANCE_COMMAND

        hooks_path = tmp_path / ".codex" / "hooks.json"
        hooks_path.parent.mkdir(parents=True)
        hooks_path.write_text(json.dumps({"hooks": {}}))

        _cmd_init(tmp_path, "ml-experiment")

        hooks = json.loads(hooks_path.read_text())["hooks"]
        all_commands = [
            hook["command"]
            for blocks in hooks.values()
            for block in blocks
            for hook in block["hooks"]
        ]
        assert STATE_GATE_COMMAND in all_commands
        assert STATE_ADVANCE_COMMAND in all_commands

    def test_init_preserves_existing_settings(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        # Pre-existing settings
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Read"]}, "hooks": {}})
        )
        _cmd_init(tmp_path, "ml-experiment")

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert settings["permissions"]["allow"] == ["Read"]
        assert "PreToolUse" in settings["hooks"]

    def test_init_review_preset(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "review-paper")

        wf = json.loads((tmp_path / "research" / ".workflow.json").read_text())
        state_ids = [s["id"] for s in wf["states"]]
        assert "SCOPE_DEFINITION" in state_ids
        assert "LITERATURE_SEARCH" in state_ids

    def test_init_copies_review_prompts(self, tmp_path):
        from tiny_lab.cli import _cmd_init
        _cmd_init(tmp_path, "review-paper")

        assert (tmp_path / "prompts" / "review" / "scope.md").exists()
        assert (tmp_path / "prompts" / "review" / "literature_search.md").exists()
        assert (tmp_path / "prompts" / "review" / "synthesis.md").exists()


class TestRun:
    def test_run_exits_nonzero_when_engine_reports_failure(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self):
                return False

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None)

        assert exc.value.code == 1

    def test_run_does_not_require_initial_idea_for_non_shape_first_state(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self):
                return True

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        _cmd_run(tmp_path, None)

    def test_run_passes_max_steps_to_engine(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))
        seen: dict[str, int | None] = {}

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self, max_steps=None):
                seen["max_steps"] = max_steps
                return True

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        _cmd_run(tmp_path, None, max_steps=2)

        assert seen["max_steps"] == 2

    def test_run_overrides_max_iterations(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))
        seen: dict[str, int] = {}

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self):
                seen["max_iterations"] = self.workflow.autonomy.max_iterations
                return True

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        _cmd_run(tmp_path, None, max_iter=3)

        assert seen["max_iterations"] == 3

    def test_run_passes_backend_timeout_to_engine(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))
        seen: dict[str, float | None] = {}

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                seen["backend_timeout_seconds"] = kwargs.get("backend_timeout_seconds")
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self):
                return True

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        _cmd_run(tmp_path, None, backend_timeout_seconds=4.5)

        assert seen["backend_timeout_seconds"] == 4.5

    def test_run_rejects_non_positive_max_steps(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))

        def fail_engine(*args, **kwargs):
            raise AssertionError("engine should not start with invalid max_steps")

        monkeypatch.setattr("tiny_lab.engine.Engine", fail_engine)

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None, max_steps=0)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "--max-steps must be a positive integer" in output

    def test_run_rejects_non_positive_max_iterations(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))

        def fail_engine(*args, **kwargs):
            raise AssertionError("engine should not start with invalid max iterations")

        monkeypatch.setattr("tiny_lab.engine.Engine", fail_engine)

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None, max_iter=0)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "--max-iter/--max-iterations must be a positive integer" in output

    def test_run_rejects_non_positive_backend_timeout(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "A", "type": "process"}],
        }))

        def fail_engine(*args, **kwargs):
            raise AssertionError("engine should not start with invalid timeout")

        monkeypatch.setattr("tiny_lab.engine.Engine", fail_engine)

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None, backend_timeout_seconds=0)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "--timeout-seconds must be positive" in output

    def test_run_requires_initial_idea_before_shape(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "SHAPE_FULL", "type": "ai_session"}],
        }))

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "No research idea found" in output

    def test_run_requires_initial_idea_before_ideate_shape(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "SHAPE_LITE", "type": "ai_session"}],
        }))

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "No research idea found" in output

    def test_run_accepts_initial_idea_argument(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "SHAPE_FULL", "type": "ai_session"}],
        }))

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self):
                return True

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        _cmd_run(tmp_path, "predict lab quality from run logs")

        assert (tmp_path / "research" / ".user_idea.txt").read_text() == (
            "predict lab quality from run logs"
        )

    def test_run_allows_shaped_project_without_initial_idea(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "DOMAIN_RESEARCH", "type": "ai_session"}],
        }))
        (tmp_path / "research" / "constraints.json").write_text(json.dumps({
            "objective": "Build a leakage-safe model comparison.",
            "goal": {"success_criteria": "Reduce MAE below the baseline."},
            "invariants": ["No data leakage."],
        }))

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                self.workflow = SimpleNamespace(
                    autonomy=SimpleNamespace(max_iterations=50),
                )

            def run(self):
                return True

        monkeypatch.setattr("tiny_lab.engine.Engine", FakeEngine)

        _cmd_run(tmp_path, None)

    def test_run_rejects_invalid_existing_constraints(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_run

        (tmp_path / "research").mkdir()
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{"id": "DOMAIN_RESEARCH", "type": "ai_session"}],
        }))
        (tmp_path / "research" / "constraints.json").write_text(json.dumps({
            "objective": " ",
            "goal": "reduce error somehow",
            "invariants": [],
        }))

        def fail_engine(*args, **kwargs):
            raise AssertionError("engine should not start with invalid constraints")

        monkeypatch.setattr("tiny_lab.engine.Engine", fail_engine)

        with pytest.raises(SystemExit) as exc:
            _cmd_run(tmp_path, None)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "research/constraints.json is invalid" in output
        assert "'goal' must be an object" in output


class TestShape:
    def _install_shape_workflow(self, tmp_path: Path) -> None:
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [
                {
                    "id": "SHAPE_FULL",
                    "type": "ai_session",
                    "next": "DOMAIN_RESEARCH",
                },
                {
                    "id": "DOMAIN_RESEARCH",
                    "type": "ai_session",
                },
            ],
        }))

    def test_shape_accepts_valid_constraints_and_advances(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_shape
        from tiny_lab.state import load_state

        self._install_shape_workflow(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        constraints = {
            "objective": "Build a leakage-safe model comparison.",
            "goal": {
                "metric": "mae",
                "direction": "minimize",
                "target": 0.5,
                "success_criteria": "Reduce MAE below 0.5.",
            },
            "invariants": ["No data leakage."],
            "exploration_bounds": {
                "allowed": ["linear models"],
                "forbidden": ["test-set tuning"],
            },
        }
        constraints_path.write_text(json.dumps(constraints))

        _cmd_shape(tmp_path, str(constraints_path))
        output = capsys.readouterr().out

        written = json.loads((tmp_path / "research" / "constraints.json").read_text())
        assert written == constraints
        assert load_state(tmp_path).state == "DOMAIN_RESEARCH"
        assert "Constraints written" in output

    def test_shape_rejects_non_object_constraints(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_shape

        self._install_shape_workflow(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        constraints_path.write_text(json.dumps(["not", "an", "object"]))

        with pytest.raises(SystemExit) as exc:
            _cmd_shape(tmp_path, str(constraints_path))
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "Error: invalid constraints" in output
        assert "constraints must be a JSON object" in output
        assert not (tmp_path / "research" / "constraints.json").exists()

    def test_shape_rejects_bad_goal_and_invariants(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_shape

        self._install_shape_workflow(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        constraints_path.write_text(json.dumps({
            "objective": " ",
            "goal": {
                "direction": "lower",
                "target": "soon",
                "success_criteria": "",
            },
            "invariants": [""],
            "exploration_bounds": {
                "allowed": ["linear models"],
                "forbidden": [" "],
            },
        }))

        with pytest.raises(SystemExit) as exc:
            _cmd_shape(tmp_path, str(constraints_path))
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "'objective' must be a non-empty string" in output
        assert "'goal.direction' must be 'minimize', 'maximize', or null" in output
        assert "'goal.target' must be a finite number or null" in output
        assert "'invariants' must be a non-empty list of non-empty strings" in output
        assert "'exploration_bounds.forbidden' must be a list" in output
        assert not (tmp_path / "research" / "constraints.json").exists()

    def test_shape_rejects_invalid_json_without_traceback(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_shape

        self._install_shape_workflow(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        constraints_path.write_text("{not json")

        with pytest.raises(SystemExit) as exc:
            _cmd_shape(tmp_path, str(constraints_path))
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "Error: invalid constraints JSON" in output
        assert "Traceback" not in output

    def test_shape_rejects_bad_workflow_before_overwriting_constraints(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_shape

        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".workflow.json").write_text(json.dumps({"states": {"id": "SHAPE_FULL"}}))
        existing = {
            "objective": "Existing shaped objective.",
            "goal": {"success_criteria": "Keep the current constraints intact."},
            "invariants": ["No data leakage."],
        }
        (rd / "constraints.json").write_text(json.dumps(existing))
        constraints_path = tmp_path / "constraints.json"
        constraints_path.write_text(json.dumps({
            "objective": "New objective.",
            "goal": {"success_criteria": "This should not be written."},
            "invariants": ["Do not overwrite on workflow failure."],
        }))

        with pytest.raises(SystemExit) as exc:
            _cmd_shape(tmp_path, str(constraints_path))
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "Error: cannot read workflow" in output
        assert json.loads((rd / "constraints.json").read_text()) == existing
        assert not (rd / "iter_1").exists()


class TestStatus:
    def test_status_default(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_status
        from tiny_lab.state import save_state, LoopState
        (tmp_path / "research").mkdir()
        save_state(tmp_path, LoopState(state="PLAN", current_iteration=2))

        _cmd_status(tmp_path)
        output = capsys.readouterr().out
        assert "PLAN" in output
        assert "2" in output

    def test_ps_reports_active_backend(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_ps
        from tiny_lab.processes import write_active_backend

        (tmp_path / "research").mkdir()
        write_active_backend(tmp_path, backend="codex", pid=123, command=["codex", "exec", "--json"])
        monkeypatch.setattr("tiny_lab.processes.pid_is_alive", lambda pid: True)

        _cmd_ps(tmp_path)
        output = capsys.readouterr().out

        assert "alive backend=codex pid=123" in output

    def test_stop_signals_active_backend(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_stop
        from tiny_lab.processes import write_active_backend

        (tmp_path / "research").mkdir()
        write_active_backend(tmp_path, backend="claude", pid=456, command=["claude", "-p"])
        seen = {}
        monkeypatch.setattr("tiny_lab.processes.signal_pid", lambda pid: seen.setdefault("pid", pid) or True)

        _cmd_stop(tmp_path)
        output = capsys.readouterr().out

        assert seen["pid"] == 456
        assert "Interrupted active backend pid 456" in output
        assert json.loads((tmp_path / "research" / ".intervention.json").read_text())["action"] == "stop"

    def test_repair_state_records_event(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_repair_state
        from tiny_lab.state import LoopState, save_state, load_state

        (tmp_path / "research").mkdir()
        save_state(tmp_path, LoopState(
            state="DONE",
            current_iteration=1,
            consecutive_failures=3,
            phase_retries=2,
            session_id="abc",
        ))

        _cmd_repair_state(
            tmp_path,
            "PHASE_RUN",
            phase_id="phase_3",
            clear_failures=True,
            clear_session=True,
        )
        output = capsys.readouterr().out
        state = load_state(tmp_path)
        events = (tmp_path / "research" / ".events.jsonl").read_text()

        assert "State repaired: DONE -> PHASE_RUN (phase_3)" in output
        assert state.state == "PHASE_RUN"
        assert state.current_phase_id == "phase_3"
        assert state.consecutive_failures == 0
        assert state.phase_retries == 0
        assert state.session_id is None
        assert "manual_state_repair" in events


class TestDoctor:
    def _install_ready_project(self, tmp_path: Path) -> None:
        import contextlib
        import io

        from tiny_lab.cli import _cmd_init
        from tiny_lab.state import LoopState, save_state

        with contextlib.redirect_stdout(io.StringIO()):
            _cmd_init(tmp_path, "ml-experiment")
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "DOMAIN_RESEARCH",
                "type": "ai_session",
                "prompt": "prompts/domain_research.md",
            }],
        }))
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))

    def test_doctor_reports_ready_project_without_backend_probe(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is True
        assert "PASS workflow" in output
        assert "PASS prompt template sources" in output
        assert "PASS claude hook sources" in output
        assert "PASS claude hook config" in output
        assert "PASS codex hook config" in output
        assert "PASS runner docs" in output
        assert "PASS current state" in output
        assert "PASS backend command" in output
        assert "INFO backend probe: not run" in output

    def test_doctor_fails_stale_claude_hook_source(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        (tmp_path / ".claude" / "hooks" / "state_advance.py").write_text("# stale\n")
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL claude hook sources" in output
        assert "stale .claude/hooks/state_advance.py" in output

    def test_doctor_fails_stale_prompt_template_source(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        (tmp_path / "prompts" / "story_tell.md").write_text("# stale story prompt\n")
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL prompt template sources" in output
        assert "stale prompts/story_tell.md" in output

    def test_doctor_fails_stale_runner_docs(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        (tmp_path / "AGENTS.md").write_text("old native instructions\n")
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL runner docs" in output
        assert "stale AGENTS.md" in output

    def test_doctor_fails_unmanaged_current_runner_docs(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor
        from tiny_lab.runner_contract import (
            RUNNER_CONTRACT_END_MARKER,
            RUNNER_CONTRACT_START_MARKER,
        )

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        text = (tmp_path / "AGENTS.md").read_text()
        (tmp_path / "AGENTS.md").write_text(
            text.replace(RUNNER_CONTRACT_START_MARKER + "\n", "").replace(
                "\n" + RUNNER_CONTRACT_END_MARKER,
                "",
            )
        )
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL runner docs" in output
        assert "unmanaged AGENTS.md" in output

    def test_doctor_fails_missing_codex_hook_command(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        (tmp_path / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {}}))
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL codex hook config" in output
        assert "missing hooks.PreToolUse" in output

    def test_doctor_fails_legacy_claude_hook_command_without_hooks_array(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.write_text(json.dumps({
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Write|Edit|MultiEdit|Bash",
                    "command": "python3 .claude/hooks/state_gate.py",
                }],
                "PostToolUse": [{
                    "matcher": "Write|Edit|MultiEdit|Bash",
                    "command": "python3 .claude/hooks/state_advance.py",
                }, {
                    "matcher": "Write|Edit|MultiEdit|Bash",
                    "command": "python3 .claude/hooks/ref_verify.py",
                }],
            },
        }))
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL claude hook config" in output
        assert "must use hooks array" in output

    def test_doctor_repair_runner_fixes_drift_without_rewriting_workflow_state(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        from tiny_lab.cli import _cmd_doctor
        from tiny_lab.runner_contract import render_runner_contract

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        workflow_path = tmp_path / "research" / ".workflow.json"
        state_path = tmp_path / "research" / ".state.json"
        workflow_before = workflow_path.read_text()
        state_before = state_path.read_text()
        (tmp_path / ".claude" / "hooks" / "state_advance.py").write_text("# stale\n")
        (tmp_path / "prompts" / "story_tell.md").write_text("# stale story prompt\n")
        (tmp_path / "AGENTS.md").write_text("# custom\n")
        (tmp_path / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {}}))
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path, repair_runner=True)
        output = capsys.readouterr().out

        assert ok is True
        assert "INFO repair runner" in output
        assert "PASS prompt template sources" in output
        assert "PASS claude hook sources" in output
        assert "PASS codex hook config" in output
        assert "PASS runner docs" in output
        assert "PostToolUse hook" in (
            tmp_path / ".claude" / "hooks" / "state_advance.py"
        ).read_text()
        assert "{final_paper_evidence_ledger}" in (tmp_path / "prompts" / "story_tell.md").read_text()
        assert render_runner_contract() in (tmp_path / "AGENTS.md").read_text()
        assert workflow_path.read_text() == workflow_before
        assert state_path.read_text() == state_before

    def test_doctor_repair_runner_marks_current_unmanaged_runner_docs(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        from tiny_lab.cli import _cmd_doctor
        from tiny_lab.runner_contract import (
            RUNNER_CONTRACT_END_MARKER,
            RUNNER_CONTRACT_START_MARKER,
            render_runner_contract,
        )

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        text = (tmp_path / "AGENTS.md").read_text()
        (tmp_path / "AGENTS.md").write_text(
            text.replace(RUNNER_CONTRACT_START_MARKER + "\n", "").replace(
                "\n" + RUNNER_CONTRACT_END_MARKER,
                "",
            )
        )
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path, repair_runner=True)
        output = capsys.readouterr().out

        updated = (tmp_path / "AGENTS.md").read_text()
        assert ok is True
        assert "INFO repair runner" in output
        assert "PASS runner docs" in output
        assert RUNNER_CONTRACT_START_MARKER in updated
        assert RUNNER_CONTRACT_END_MARKER in updated
        assert render_runner_contract() in updated

    def test_doctor_fails_missing_initial_idea(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor
        from tiny_lab.state import LoopState, save_state

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "SHAPE_FULL",
                "type": "ai_session",
                "prompt": "prompts/domain_research.md",
            }],
        }))
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL initial idea" in output
        assert "No research idea found" in output

    def test_doctor_fails_invalid_constraints(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        (tmp_path / "research" / "constraints.json").write_text(json.dumps({
            "objective": " ",
            "goal": "reduce error somehow",
            "invariants": [],
        }))
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL constraints" in output
        assert "research/constraints.json is invalid" in output

    def test_doctor_fails_missing_workflow(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_doctor

        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

        ok = _cmd_doctor(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL workflow" in output
        assert "research/.workflow.json not found" in output

    def test_doctor_backend_probe_reports_auth_failure(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.cli import _cmd_doctor

        class UnavailableBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                return BackendResult(
                    exit_code=1,
                    stdout=json.dumps({
                        "is_error": True,
                        "result": "Not logged in · Please run /login",
                    }),
                    stderr="",
                    session_id=None,
                )

        self._install_ready_project(tmp_path)
        (tmp_path / "research" / ".user_idea.txt").write_text("test idea")
        monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")
        monkeypatch.setitem(base._REGISTRY, "claude", UnavailableBackend())

        ok = _cmd_doctor(tmp_path, probe_backend=True)
        output = capsys.readouterr().out

        assert ok is False
        assert "FAIL backend probe" in output
        assert "Not logged in" in output


class TestStep:
    def _install_workflow(self, tmp_path: Path) -> None:
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (tmp_path / "shared").mkdir(exist_ok=True)
        preset = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "ml-experiment.json"
        shutil.copy2(preset, rd / ".workflow.json")

    def test_step_advances_phase_select_with_engine_handler(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step
        from tiny_lab.paths import iter_dir, phases_dir, results_dir
        from tiny_lab.state import LoopState, load_state, save_state

        self._install_workflow(tmp_path)
        idir = iter_dir(tmp_path, 1)
        idir.mkdir(parents=True)
        phases_dir(tmp_path, 1).mkdir(exist_ok=True)
        results_dir(tmp_path, 1).mkdir(exist_ok=True)
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "test",
            "phases": [{
                "id": "phase_0",
                "status": "pending",
                "name": "baseline",
                "depends_on": [],
                "type": "script",
            }],
        }))
        save_state(tmp_path, LoopState(state="PHASE_SELECT", current_iteration=1))

        ok = _cmd_step(tmp_path)
        output = capsys.readouterr().out
        state = load_state(tmp_path)

        assert ok is True
        assert "PHASE_SELECT" in output
        assert state.state == "PHASE_CODE"
        assert state.current_phase_id == "phase_0"

    def test_step_refuses_ai_session_by_default(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, load_state, save_state

        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))

        ok = _cmd_step(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "ai_session" in output
        assert load_state(tmp_path).state == "DOMAIN_RESEARCH"

    def test_step_does_not_block_on_supervised_checkpoint_without_intervention(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, load_state, save_state

        self._install_workflow(tmp_path)
        workflow_path = tmp_path / "research" / ".workflow.json"
        workflow = json.loads(workflow_path.read_text())
        workflow["autonomy"]["mode"] = "supervised"
        workflow_path.write_text(json.dumps(workflow))
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="CHECKPOINT", current_iteration=1))

        ok = _cmd_step(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "waiting for intervention" in output
        assert load_state(tmp_path).state == "CHECKPOINT"

    def test_step_treats_done_as_successful_noop(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        save_state(tmp_path, LoopState(state="DONE", current_iteration=1))

        ok = _cmd_step(tmp_path)
        output = capsys.readouterr().out

        assert ok is True
        assert "already DONE" in output

    def test_step_reports_malformed_workflow_without_traceback(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        (tmp_path / "research" / ".workflow.json").write_text(
            json.dumps({"states": {"id": "PHASE_SELECT", "type": "process"}})
        )
        save_state(tmp_path, LoopState(state="PHASE_SELECT", current_iteration=1))

        ok = _cmd_step(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "Cannot execute step" in output
        assert "states" in output
        assert "Traceback" not in output

    def test_step_run_ai_reports_backend_unavailable_as_failure(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.backends import base
        from tiny_lab.backends.base import BackendResult
        from tiny_lab.cli import _cmd_step
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, load_state, save_state

        class UnavailableBackend:
            name = "claude"

            def invoke(self, *args, **kwargs):
                return BackendResult(
                    exit_code=1,
                    stdout=json.dumps({
                        "is_error": True,
                        "result": "Not logged in · Please run /login",
                    }),
                    stderr="",
                    session_id=None,
                )

        monkeypatch.setitem(base._REGISTRY, "claude", UnavailableBackend())
        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))

        ok = _cmd_step(tmp_path, run_ai=True)
        output = capsys.readouterr().out

        assert ok is False
        assert "backend is unavailable" in output
        assert load_state(tmp_path).state == "DOMAIN_RESEARCH"

    def test_step_rejects_non_positive_backend_timeout(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step

        self._install_workflow(tmp_path)

        ok = _cmd_step(tmp_path, backend_timeout_seconds=0)
        output = capsys.readouterr().out

        assert ok is False
        assert "--timeout-seconds must be positive" in output

    def test_step_run_ai_requires_initial_idea_before_shape(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_step
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, load_state, save_state

        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))

        ok = _cmd_step(tmp_path, run_ai=True)
        output = capsys.readouterr().out

        assert ok is False
        assert "No research idea found" in output
        assert load_state(tmp_path).state == "SHAPE_FULL"


class TestPrompt:
    def _install_workflow(self, tmp_path: Path) -> None:
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (tmp_path / "shared").mkdir(exist_ok=True)
        preset = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "ml-experiment.json"
        shutil.copy2(preset, rd / ".workflow.json")

    def test_prompt_renders_current_ai_session_prompt_from_engine_path(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_prompt
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))

        ok = _cmd_prompt(tmp_path)
        output = capsys.readouterr().out

        assert ok is True
        assert "ENGINE:" not in output
        assert "ML Researcher Quality Standard" in output
        assert "Current iteration: iter_1" in output
        assert str(tmp_path) in output
        assert "{iter}" not in output
        assert "{project_dir}" not in output

    def test_prompt_refuses_non_ai_session_state(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_prompt
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        save_state(tmp_path, LoopState(state="PHASE_SELECT", current_iteration=1))

        ok = _cmd_prompt(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "Cannot render prompt" in output
        assert "tiny-lab step" in output

    def test_prompt_requires_initial_idea_before_shape(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_prompt
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, load_state, save_state

        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="SHAPE_FULL", current_iteration=1))

        ok = _cmd_prompt(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "No research idea found" in output
        assert load_state(tmp_path).state == "SHAPE_FULL"

    def test_prompt_rejects_invalid_constraints(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_prompt
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        (tmp_path / "research" / "constraints.json").write_text(json.dumps({
            "objective": " ",
            "goal": "reduce error somehow",
            "invariants": [],
        }))

        ok = _cmd_prompt(tmp_path)
        output = capsys.readouterr().out

        assert ok is False
        assert "research/constraints.json is invalid" in output


class TestBrief:
    def _install_workflow(self, tmp_path: Path) -> None:
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (tmp_path / "shared").mkdir(exist_ok=True)
        preset = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "presets" / "ml-experiment.json"
        shutil.copy2(preset, rd / ".workflow.json")

    def test_brief_resolves_current_ai_session_contract(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_brief
        from tiny_lab.paths import iter_dir
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        iter_dir(tmp_path, 1).mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))

        ok = _cmd_brief(tmp_path)
        output = capsys.readouterr().out

        assert ok is True
        assert "ENGINE:" not in output
        assert "state: iter_1 DOMAIN_RESEARCH (ai_session)" in output
        assert "action: Run tiny-lab prompt" in output
        assert "command: tiny-lab prompt" in output
        assert "allowed tools: WebSearch, WebFetch, Read, Write" in output
        assert "allowed writes: research/iter_1/.domain_research.json" in output
        assert "completion: research/iter_1/.domain_research.json" in output
        assert "{iter}" not in output

    def test_brief_json_resolves_process_state_contract(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_brief
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        save_state(tmp_path, LoopState(state="PHASE_RUN", current_iteration=3, current_phase_id="phase_2"))

        ok = _cmd_brief(tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)

        assert ok is True
        assert data["state"] == "PHASE_RUN"
        assert data["iteration"] == 3
        assert data["current_phase_id"] == "phase_2"
        assert data["state_type"] == "process"
        assert data["action"].startswith("Run tiny-lab step")
        assert data["runner_command"] == "tiny-lab step"
        assert data["blocked_write_globs"] == ["research/iter_3/phases/*"]
        assert data["next"] == "PHASE_EVALUATE"

    def test_brief_reports_unknown_state_contract(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_brief
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        save_state(tmp_path, LoopState(state="MISSING_STATE", current_iteration=3, current_phase_id="phase_2"))

        ok = _cmd_brief(tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)

        assert ok is True
        assert data["state"] == "MISSING_STATE"
        assert data["state_type"] == "unknown"
        assert data["current_phase_id"] == "phase_2"
        assert data["runner_command"] is None
        assert "missing from research/.workflow.json" in data["action"]

    def test_brief_reports_malformed_workflow_without_traceback(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_brief
        from tiny_lab.state import LoopState, save_state

        self._install_workflow(tmp_path)
        (tmp_path / "research" / ".workflow.json").write_text(
            json.dumps({"states": {"id": "REFLECT", "type": "ai_session"}})
        )
        save_state(tmp_path, LoopState(state="REFLECT", current_iteration=1))

        ok = _cmd_brief(tmp_path, as_json=True)
        output = capsys.readouterr().out

        assert ok is False
        assert "Cannot render briefing" in output
        assert "states" in output
        assert "Traceback" not in output


class TestVerifyRefs:
    def _stub_verify_all(self, monkeypatch, results):
        import tiny_lab.refs as refs

        def fake_summary(items):
            total = sum(r.total for r in items)
            verified = sum(r.verified for r in items)
            not_found = sum(r.not_found for r in items)
            unverified = sum(r.unverified for r in items)
            errors = sum(r.error for r in items)
            return (
                f"References: {verified}/{total} verified "
                f"(not_found={not_found}, unverified={unverified}, error={errors})"
            )

        monkeypatch.setattr(
            refs,
            "verify_all",
            lambda project_dir, iteration=None, write_files=True: results,
        )
        monkeypatch.setattr(refs, "format_summary", fake_summary)

    def test_strict_exits_for_unverified_references(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_verify_refs

        self._stub_verify_all(
            monkeypatch,
            [_FakeReferenceVerificationResult(total=1, verified=0, unverified=1)],
        )

        with pytest.raises(SystemExit) as exc:
            _cmd_verify_refs(tmp_path, None, None, no_write=True, strict=True)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "references not fully verified" in output
        assert "unverified=1" in output

    def test_strict_exits_for_reference_errors(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_verify_refs

        self._stub_verify_all(
            monkeypatch,
            [_FakeReferenceVerificationResult(total=1, verified=0, error=1)],
        )

        with pytest.raises(SystemExit) as exc:
            _cmd_verify_refs(tmp_path, None, None, no_write=True, strict=True)
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "references not fully verified" in output
        assert "error=1" in output

    def test_strict_allows_fully_verified_references(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import _cmd_verify_refs

        self._stub_verify_all(
            monkeypatch,
            [_FakeReferenceVerificationResult(total=1, verified=1)],
        )

        _cmd_verify_refs(tmp_path, None, None, no_write=True, strict=True)
        output = capsys.readouterr().out

        assert "References: 1/1 verified" in output
        assert "strict mode" not in output


class TestAudit:
    def test_audit_passes_clean_artifacts(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        rdir = tmp_path / "research" / "iter_1" / "results"
        rdir.mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DONE", current_iteration=1))

        plan = {
            "name": "rigorous",
            "metric": {"name": "mae", "direction": "minimize", "target": 0.5},
            "formal_notation": {"prediction": "y_hat = f(X)"},
            "baselines": [
                {"name": "seasonal naive", "type": "non-ML"},
                {"name": "linear regression", "type": "simple ML"},
            ],
            "experiment_checklist": {
                "has_non_ml_baseline": "yes",
                "has_simple_ml_baseline": "yes",
                "has_ablation_study": "yes",
                "has_cross_validation": "yes",
                "has_error_analysis": "yes",
            },
            "phases": [{
                "id": "phase_0",
                "name": "Leakage-safe baseline audit",
                "why": "Check split protocol and baseline",
                "type": "script",
                "depends_on": [],
                "methodology": "Run held-out split, seasonal naive, linear regression, ablation, CV fold residual error analysis.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {"type": "number"},
                            "mae_std": {"type": "number"},
                            "baseline_results": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "baseline": {"type": "string"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "improvement_over_baseline": {"type": "number"},
                            "feature_importance": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "feature": {"type": "string"},
                                        "importance_score": {"type": "number"},
                                    },
                                },
                            },
                            "fold_count": {"type": "integer"},
                            "per_fold_metrics": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "fold": {"type": "integer"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "error_analysis": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "slice": {"type": "string"},
                                        "mae_mean": {"type": "number"},
                                    },
                                },
                            },
                            "leakage_found": {"type": "boolean"},
                            "train_test_overlap": {"type": "integer"},
                            "target_achieved": {"type": "boolean"},
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                            "script_path": {"type": "string"},
                            "script_sha256": {"type": "string"},
                        },
                    }
                },
                "visualization": ["phase_0_error.png"],
                "status": "done",
            }],
        }
        (tmp_path / "research" / "iter_1" / "research_plan.json").write_text(json.dumps(plan))
        pdir = tmp_path / "research" / "iter_1" / "phases"
        pdir.mkdir(parents=True)
        script = pdir / "phase_0.py"
        script.write_text("print('phase 0')\n")
        script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
        (rdir / "phase_0.json").write_text(json.dumps({
            "mae_mean": 0.42,
            "mae_std": 0.03,
            "baseline_results": [
                {"name": "seasonal naive", "mae_mean": 0.58},
                {"name": "linear regression", "mae_mean": 0.49},
            ],
            "improvement_over_baseline": 0.1429,
            "feature_importance": [{"feature": "lag_1", "importance": 0.72}],
            "fold_count": 2,
            "per_fold_metrics": [
                {"fold": 0, "mae_mean": 0.43},
                {"fold": 1, "mae_mean": 0.41},
            ],
            "error_analysis": [{"slice": "peak_load", "mae_mean": 0.55}],
            "leakage_found": False,
            "train_test_overlap": 0,
            "target_achieved": True,
            "random_seed": 7,
            "dataset_fingerprint": "sha256:" + "0" * 64,
            "split_id": "fold_0",
            "python_version": "3.11",
            "script_path": "research/iter_1/phases/phase_0.py",
            "script_sha256": script_sha,
        }))
        (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)
        (tmp_path / "research" / "final_paper.md").write_text(
            "# Final Paper\n\n"
            "## Abstract\n"
            "This paper summarizes a rigorous automated ML study with artifact-backed results. "
            "The result artifact research/iter_1/results/phase_0.json documents the baseline "
            "comparison, statistical uncertainty, feature importance, cross-validation fold evaluation "
            "protocol, error analysis, leakage audit, target achievement, reproducibility metadata, "
            "and MAE = 0.42.\n\n"
            "## Related Work\n"
            "Prior work establishes the baseline context for this study "
            "(research/iter_1/.domain_research.json).\n\n"
            "## Method\n"
            "The method section describes split protocol, baselines, reproducibility metadata, "
            "leakage audit, and evaluation procedure in enough detail for rerunning the study.\n\n"
            "## Results\n"
            "The results section reports repeated splits, feature importance, target achievement, "
            "and failure cases without unsupported metric claims. "
            "The primary error figure is research/iter_1/results/phase_0_error.png.\n\n"
            "## Limitations\n"
            "The limitations section documents data quality, evaluation constraints, possible "
            "distribution shift, and implementation assumptions. "
            "Additional text pads the fixture so it resembles a complete paper rather than a stub. "
            * 3
        )
        (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": _complete_review_feedback(8),
        }))
        (tmp_path / "research" / "iter_1" / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Verified Paper", "doi": "10.1234/example"}]
        }))
        (tmp_path / "research" / "iter_1" / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": "research/iter_1/.domain_research.json",
            "summary": {"total": 1, "verified": 1, "unverified": 0, "not_found": 0, "error": 0},
            "refs": [{
                "raw": {"title": "Verified Paper", "doi": "10.1234/example"},
                "title": "Verified Paper",
                "doi": "10.1234/example",
                "status": "verified",
                "method": "crossref",
            }],
        }))

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is True
        assert "Audit: PASS" in output

    def test_audit_fails_weak_plan(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True)
        save_state(tmp_path, LoopState(state="PLAN", current_iteration=1))
        (idir / "research_plan.json").write_text(json.dumps({
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

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "Plan: FAIL" in output
        assert "Audit: FAIL" in output

    def test_audit_fails_missing_plan(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        save_state(tmp_path, LoopState(state="REVIEW", current_iteration=1))

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "Plan: FAIL" in output
        assert "research_plan.json is missing" in output

    def test_audit_all_checks_previous_iterations(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        iter1 = tmp_path / "research" / "iter_1"
        iter2 = tmp_path / "research" / "iter_2"
        iter1.mkdir(parents=True)
        iter2.mkdir(parents=True)
        save_state(tmp_path, LoopState(state="REVIEW", current_iteration=2))
        (iter1 / "research_plan.json").write_text(json.dumps({
            "name": "old weak plan",
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

        ok = _cmd_audit(tmp_path, all_iterations=True)
        output = capsys.readouterr().out

        assert ok is False
        assert "all iterations" in output
        assert "iter_1" in output
        assert "status is 'pending'" in output

    def test_audit_target_iterations_ignores_non_numeric_iteration_dirs(self, tmp_path):
        from tiny_lab.cli import _audit_target_iterations

        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        (tmp_path / "research" / "iter_x").mkdir(parents=True)

        assert _audit_target_iterations(tmp_path, current_iteration=3, iteration=None, all_iterations=True) == [1]

    def test_audit_fails_reference_not_found(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        (idir / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Imaginary Paper", "doi": "10.9999/missing"}]
        }))
        (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": "research/iter_1/.domain_research.json",
            "summary": {"total": 1, "verified": 0, "unverified": 0, "not_found": 1, "error": 0},
            "refs": [],
        }))

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "References: FAIL" in output
        assert "not_found" in output

    def test_audit_fails_reference_unverified(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        (idir / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Unverified Paper", "doi": "10.1234/unverified"}]
        }))
        (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": "research/iter_1/.domain_research.json",
            "summary": {"total": 1, "verified": 0, "unverified": 1, "not_found": 0, "error": 0},
            "refs": [],
        }))

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "References: FAIL" in output
        assert "unverified references" in output

    def test_audit_fails_missing_reference_sidecar(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True)
        save_state(tmp_path, LoopState(state="DOMAIN_RESEARCH", current_iteration=1))
        (idir / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Unchecked Paper", "doi": "10.1234/unchecked"}]
        }))

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "missing ref verification sidecar" in output

    def test_audit_fails_short_final_paper(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        save_state(tmp_path, LoopState(state="REVIEW", current_iteration=1))
        (tmp_path / "research" / "final_paper.md").write_text("## Results\nMAE = 0.42")

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "Final paper: FAIL" in output
        assert "too short" in output

    def test_audit_fails_evaluation_without_final_paper(self, tmp_path, capsys):
        from tiny_lab.cli import _cmd_audit
        from tiny_lab.state import save_state, LoopState

        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        save_state(tmp_path, LoopState(state="REVIEW", current_iteration=1))
        (tmp_path / "research" / "evaluation.json").write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 8,
                "experimental_sufficiency": 8,
                "novelty": 8,
                "narrative_coherence": 8,
                "goal_achievement": 8,
            },
            "total": 40,
            "feedback": _complete_review_feedback(8),
        }))

        ok = _cmd_audit(tmp_path, 1)
        output = capsys.readouterr().out

        assert ok is False
        assert "final_paper.md not found but evaluation.json exists" in output

    def test_audit_strict_main_exits_nonzero_for_issues(self, tmp_path, capsys, monkeypatch):
        from tiny_lab.cli import main
        from tiny_lab.state import save_state, LoopState

        (tmp_path / "research" / "iter_1").mkdir(parents=True)
        save_state(tmp_path, LoopState(state="REVIEW", current_iteration=1))
        (tmp_path / "research" / "final_paper.md").write_text("## Results\nMAE = 0.42")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["tiny-lab", "audit", "--strict"])

        with pytest.raises(SystemExit) as exc:
            main()
        output = capsys.readouterr().out

        assert exc.value.code == 1
        assert "Audit: FAIL" in output


class TestIntervene:
    def test_writes_intervention(self, tmp_path):
        from tiny_lab.cli import _cmd_intervene
        (tmp_path / "research").mkdir()
        _cmd_intervene(tmp_path, "approve", [])

        ipath = tmp_path / "research" / ".intervention.json"
        assert ipath.exists()
        data = json.loads(ipath.read_text())
        assert data["action"] == "approve"

    def test_skip_phase(self, tmp_path):
        from tiny_lab.cli import _cmd_intervene
        (tmp_path / "research").mkdir()
        _cmd_intervene(tmp_path, "skip", ["phase_2"])

        data = json.loads((tmp_path / "research" / ".intervention.json").read_text())
        assert data["action"] == "skip_phase"
        assert data["skip_phase"]["phase_id"] == "phase_2"
