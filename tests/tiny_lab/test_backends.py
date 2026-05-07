"""Tests for v7.7 AI backend abstraction."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tiny_lab.backends import get_backend
from tiny_lab.backends.base import BackendResult
from tiny_lab.review import REQUIRED_SCORE_KEYS, RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA

PNG_SIGNATURE = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakePopen:
    def __init__(self, cmd, *, returncode=0, stdout="", stderr="", on_communicate=None, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._on_communicate = on_communicate
        self.pid = 12345
        self.killed = False

    def communicate(self, input=None, timeout=None):
        if self._on_communicate:
            return self._on_communicate(self, input, timeout)
        self.input = input
        self.timeout = timeout
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


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


class TestBackendRegistry:
    def test_claude_loads(self):
        backend = get_backend("claude")
        assert backend.name == "claude"

    def test_codex_loads(self):
        backend = get_backend("codex")
        assert backend.name == "codex"

    def test_unknown_raises(self):
        from tiny_lab.errors import TinyLabError

        with pytest.raises(TinyLabError, match="Unknown backend"):
            get_backend("definitely-not-a-real-backend")

    def test_registry_caches(self):
        a = get_backend("claude")
        b = get_backend("claude")
        assert a is b


class TestClaudeBackendCommandShape:
    def test_error_envelope_does_not_return_session_id(self, monkeypatch, tmp_path):
        from tiny_lab.backends.claude import ClaudeBackend

        def fake_popen(*args, **kwargs):
            return _FakePopen(
                args[0],
                returncode=1,
                stdout=json.dumps({
                    "is_error": True,
                    "result": "Not logged in · Please run /login",
                    "session_id": "error-session",
                }),
                stderr="",
            )

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        result = ClaudeBackend().invoke("prompt", tmp_path)

        assert result.exit_code == 1
        assert result.session_id is None

    def test_success_envelope_returns_session_id(self, monkeypatch, tmp_path):
        from tiny_lab.backends.claude import ClaudeBackend

        def fake_popen(*args, **kwargs):
            return _FakePopen(
                args[0],
                returncode=0,
                stdout=json.dumps({
                    "is_error": False,
                    "result": "ok",
                    "session_id": "created-session",
                }),
                stderr="",
            )

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        result = ClaudeBackend().invoke("prompt", tmp_path)

        assert result.exit_code == 0
        assert result.session_id == "created-session"

    def test_prompt_is_sent_on_stdin_not_argv(self, monkeypatch, tmp_path):
        from tiny_lab.backends.claude import ClaudeBackend

        seen = {}

        def fake_popen(*args, **kwargs):
            seen["cmd"] = args[0]
            proc = _FakePopen(
                args[0],
                returncode=0,
                stdout=json.dumps({"is_error": False, "result": "ok", "session_id": "sid"}),
                stderr="",
            )
            original = proc.communicate

            def communicate(input=None, timeout=None):
                seen["input"] = input
                return original(input=input, timeout=timeout)

            proc.communicate = communicate
            return proc

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        ClaudeBackend().invoke("secret prompt", tmp_path)

        assert "secret prompt" not in seen["cmd"]
        assert seen["input"] == "secret prompt"

    def test_missing_claude_command_reports_unavailable(self, monkeypatch, tmp_path):
        from tiny_lab.backends.claude import ClaudeBackend

        def fake_popen(*args, **kwargs):
            raise FileNotFoundError

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        result = ClaudeBackend().invoke("prompt", tmp_path)

        assert result.exit_code == 127
        assert result.session_id is None
        assert result.stderr == "Backend command not found: claude"

    def test_claude_timeout_reports_backend_result(self, monkeypatch, tmp_path):
        from tiny_lab.backends.claude import ClaudeBackend

        def on_communicate(proc, input, timeout):
            raise subprocess.TimeoutExpired(cmd="claude", timeout=3)

        def fake_popen(*args, **kwargs):
            return _FakePopen(args[0], on_communicate=on_communicate)

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        result = ClaudeBackend().invoke("prompt", tmp_path, timeout=3)

        assert result.exit_code == 124
        assert result.session_id is None
        assert result.stderr == "Backend command timed out after 3s: claude"


def test_missing_codex_command_reports_unavailable(monkeypatch, tmp_path):
    from tiny_lab.backends.codex import CodexBackend

    def fake_popen(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    result = CodexBackend().invoke("prompt", tmp_path)

    assert result.exit_code == 127
    assert result.session_id is None
    assert result.stderr == "Backend command not found: codex"


def test_codex_timeout_reports_backend_result(monkeypatch, tmp_path):
    from tiny_lab.backends.codex import CodexBackend

    def on_communicate(proc, input, timeout):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=2)

    def fake_popen(*args, **kwargs):
        return _FakePopen(args[0], on_communicate=on_communicate)

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    result = CodexBackend().invoke("prompt", tmp_path, timeout=2)

    assert result.exit_code == 124
    assert result.session_id is None
    assert result.stderr == "Backend command timed out after 2s: codex"


def test_codex_timeout_signals_process_group(monkeypatch, tmp_path):
    from tiny_lab.backends.codex import CodexBackend

    signals = []

    def fake_killpg(pid, sig):
        signals.append((pid, sig))

    def on_communicate(proc, input, timeout):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=2)

    def fake_popen(*args, **kwargs):
        return _FakePopen(args[0], on_communicate=on_communicate)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("tiny_lab.backends.codex.os.killpg", fake_killpg)

    result = CodexBackend().invoke("prompt", tmp_path, timeout=2)

    assert result.exit_code == 124
    assert signals == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]


class TestCodexBackendCommandShape:
    def test_default_base_cmd(self, monkeypatch):
        monkeypatch.delenv("TINYLAB_CODEX_CMD", raising=False)
        from tiny_lab.backends.codex import _base_cmd

        assert _base_cmd() == ["codex", "exec", "--json", "--skip-git-repo-check"]

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("TINYLAB_CODEX_CMD", "codex exec --json --skip-git-repo-check")
        from tiny_lab.backends.codex import _base_cmd

        assert _base_cmd() == ["codex", "exec", "--json", "--skip-git-repo-check"]

    def test_prompt_is_sent_on_stdin_not_argv(self, monkeypatch, tmp_path):
        from tiny_lab.backends.codex import CodexBackend

        seen = {}

        def fake_popen(*args, **kwargs):
            seen["cmd"] = args[0]
            seen["kwargs"] = kwargs
            proc = _FakePopen(args[0], returncode=0, stdout='{"session_id":"sid"}\n', stderr="")
            original = proc.communicate

            def communicate(input=None, timeout=None):
                seen["input"] = input
                return original(input=input, timeout=timeout)

            proc.communicate = communicate
            return proc

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        CodexBackend().invoke("secret prompt", tmp_path)

        assert "secret prompt" not in seen["cmd"]
        assert seen["input"] == "secret prompt"
        assert seen["kwargs"]["start_new_session"] == (os.name != "nt")


class TestStateSpecEngineField:
    def test_engine_field_parses(self):
        from tiny_lab.workflow import _parse_state

        spec = _parse_state({"id": "X", "type": "ai_session", "engine": "codex"})
        assert spec.engine == "codex"

    def test_engine_field_optional(self):
        from tiny_lab.workflow import _parse_state

        spec = _parse_state({"id": "X", "type": "ai_session"})
        assert spec.engine is None


class TestStateGateNativeMode:
    """Hook should pass through unrelated writes when in skill mode."""

    def _run_hook(self, env: dict, cwd: Path) -> int:
        """Invoke the hook script in a subprocess. Returns exit code."""
        import subprocess

        hook = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        result = subprocess.run(
            [sys.executable, str(hook)],
            env={**os.environ, **env},
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        return result.returncode

    def _setup(self, tmp_path: Path, state: str, allowed_globs: list[str]) -> None:
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / ".state.json").write_text(
            f'{{"state":"{state}","current_iteration":1}}\n'
        )
        (rd / ".workflow.json").write_text(
            '{"states":[{"id":"' + state + '","type":"ai_session",'
            '"allowed_write_globs":' + repr(allowed_globs).replace("'", '"') + "}]}\n"
        )

    def _setup_raw(self, tmp_path: Path, state: str, spec_fields: dict) -> None:
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / ".state.json").write_text(
            f'{{"state":"{state}","current_iteration":1}}\n'
        )
        spec = {"id": state, "type": "ai_session", **spec_fields}
        (rd / ".workflow.json").write_text(json.dumps({"states": [spec]}))

    def test_active_state_ignores_malformed_workflow_entries(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / ".state.json").write_text('{"state":"DOMAIN_RESEARCH","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [
                "not an object",
                {"type": "ai_session"},
                {
                    "id": "DOMAIN_RESEARCH",
                    "type": "ai_session",
                    "allowed_write_globs": ["research/{iter}/.domain_research.json"],
                },
            ]
        }))

        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / ".forbidden.json"),
            },
            tmp_path,
        )

        assert code == 1

    def test_active_state_allows_when_workflow_states_is_malformed(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / ".state.json").write_text('{"state":"DOMAIN_RESEARCH","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({"states": {"id": "DOMAIN_RESEARCH"}}))

        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / ".forbidden.json"),
            },
            tmp_path,
        )

        assert code == 0

    def test_done_state_allows_anything(self, tmp_path):
        self._setup(tmp_path, "DONE", ["research/{iter}/.foo.json"])
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "src" / "anything.py"),
            },
            tmp_path,
        )
        assert code == 0

    def test_active_state_allows_non_tinylab_path(self, tmp_path):
        self._setup(tmp_path, "DOMAIN_RESEARCH", ["research/iter_1/.domain_research.json"])
        # Writing to src/ should not be blocked even though the state has
        # narrow allowed_write_globs — src/ is not tiny-lab's territory.
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "src" / "app.py"),
            },
            tmp_path,
        )
        assert code == 0

    def test_active_state_blocks_disallowed_research_path(self, tmp_path):
        self._setup(tmp_path, "DOMAIN_RESEARCH", ["research/iter_1/.domain_research.json"])
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / ".forbidden.json"),
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_disallowed_research_path_from_multiedit(self, tmp_path):
        self._setup(tmp_path, "DOMAIN_RESEARCH", ["research/iter_1/.domain_research.json"])
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "MultiEdit",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / ".forbidden.json"),
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_explicit_blocked_write_glob(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_RUN", {
            "blocked_write_globs": ["research/{iter}/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / "phases" / "phase_0.py"),
            },
            tmp_path,
        )
        assert code == 1

    def test_bash_redirection_respects_blocked_write_glob(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_RUN", {
            "allowed_tools": ["Bash"],
            "blocked_write_globs": ["research/{iter}/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "cat > research/iter_1/phases/phase_0.py",
            },
            tmp_path,
        )
        assert code == 1

    def test_bash_tee_respects_blocked_write_glob(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_RUN", {
            "allowed_tools": ["Bash"],
            "blocked_write_globs": ["research/{iter}/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "printf data | tee research/iter_1/phases/phase_0.py",
            },
            tmp_path,
        )
        assert code == 1

    def test_bash_read_of_blocked_write_path_is_allowed(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_RUN", {
            "allowed_tools": ["Bash"],
            "blocked_write_globs": ["research/{iter}/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "cat research/iter_1/phases/phase_0.py",
            },
            tmp_path,
        )
        assert code == 0

    def test_active_state_blocks_tinylab_write_when_tool_not_allowed(self, tmp_path):
        self._setup_raw(tmp_path, "DOMAIN_RESEARCH", {
            "allowed_tools": ["Read"],
            "allowed_write_globs": ["research/{iter}/.domain_research.json"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / ".domain_research.json"),
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_allows_external_write_even_when_write_not_allowed(self, tmp_path):
        self._setup_raw(tmp_path, "DOMAIN_RESEARCH", {
            "allowed_tools": ["Read"],
            "allowed_write_globs": ["research/{iter}/.domain_research.json"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "src" / "scratch.py"),
            },
            tmp_path,
        )
        assert code == 0

    def test_active_state_allows_external_path_with_research_segment(self, tmp_path):
        self._setup(tmp_path, "DOMAIN_RESEARCH", ["research/iter_1/.domain_research.json"])
        external_dir = tmp_path.parent / f"{tmp_path.name}_outside" / "research" / "iter_1"
        external_dir.mkdir(parents=True)
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(external_dir / ".forbidden.json"),
            },
            tmp_path,
        )
        assert code == 0

    def test_active_state_allows_multiedit_when_edit_allowed(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Edit"],
            "allowed_write_globs": ["research/{iter}/phases/*"],
        })
        (tmp_path / "research" / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_0"}\n'
        )
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "MultiEdit",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / "phases" / "phase_0.py"),
            },
            tmp_path,
        )
        assert code == 0

    def test_phase_code_blocks_other_phase_script_write(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write"],
            "allowed_write_globs": ["research/{iter}/phases/*"],
        })
        (tmp_path / "research" / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_1"}\n'
        )
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / "phases" / "phase_0.py"),
            },
            tmp_path,
        )
        assert code == 1

    def test_phase_code_allows_current_phase_script_write(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write"],
            "allowed_write_globs": ["research/{iter}/phases/*"],
        })
        (tmp_path / "research" / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_1"}\n'
        )
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / "phases" / "phase_1_model.py"),
            },
            tmp_path,
        )
        assert code == 0

    def test_phase_code_blocks_second_matching_current_phase_script(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write"],
            "allowed_write_globs": ["research/{iter}/phases/*"],
        })
        pdir = tmp_path / "research" / "iter_1" / "phases"
        pdir.mkdir(parents=True)
        (pdir / "phase_1_model.py").write_text("print('existing')\n")
        (tmp_path / "research" / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_1"}\n'
        )
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(pdir / "phase_1_eval.py"),
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_bash_when_tool_not_allowed(self, tmp_path):
        self._setup_raw(tmp_path, "PLAN", {
            "allowed_tools": ["Read", "Write"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "python -m pytest",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_allows_bash_when_tool_allowed(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "python -m pytest",
            },
            tmp_path,
        )
        assert code == 0

    def test_active_state_blocks_bash_glob_pattern(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
            "blocked_bash_patterns": ["python research/*/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "python research/iter_1/phases/phase_0.py",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_python3_phase_script_execution(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
            "blocked_bash_patterns": ["python research/*/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "python3 -u research/iter_1/phases/phase_0.py --seed 7",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_uv_run_python_phase_script_execution(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
            "blocked_bash_patterns": ["python research/*/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "uv run python research/iter_1/phases/phase_0.py",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_python_module_phase_script_execution(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
            "blocked_bash_patterns": ["python research/*/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "python -m research.iter_1.phases.phase_0",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_bash_glob_pattern_inside_longer_command(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
            "blocked_bash_patterns": ["python research/*/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "cd . && python research/iter_1/phases/phase_0.py --seed 7",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_blocks_bash_pattern_with_iter_placeholder(self, tmp_path):
        self._setup_raw(tmp_path, "PHASE_CODE", {
            "allowed_tools": ["Read", "Write", "Bash"],
            "blocked_bash_patterns": ["python research/{iter}/phases/*"],
        })
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "python research/iter_1/phases/phase_0.py",
            },
            tmp_path,
        )
        assert code == 1

    def test_active_state_allows_matching_research_path(self, tmp_path):
        self._setup(tmp_path, "DOMAIN_RESEARCH", ["research/iter_1/.domain_research.json"])
        code = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(tmp_path / "research" / "iter_1" / ".domain_research.json"),
            },
            tmp_path,
        )
        assert code == 0


class TestStateAdvanceQualityGates:
    """PostToolUse state advance must not bypass engine quality gates."""

    def _run_hook(self, env: dict, cwd: Path):
        import subprocess

        hook = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        return subprocess.run(
            [sys.executable, str(hook)],
            env={**os.environ, **env},
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )

    def test_native_hook_does_not_advance_invalid_constraints(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"SHAPE_FULL","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [
                {
                    "id": "SHAPE_FULL",
                    "type": "ai_session",
                    "completion": {"artifact": "research/constraints.json"},
                    "next": "DOMAIN_RESEARCH",
                },
                {
                    "id": "DOMAIN_RESEARCH",
                    "type": "ai_session",
                },
            ],
        }))
        constraints_path = rd / "constraints.json"
        constraints_path.write_text(json.dumps({
            "objective": " ",
            "goal": "reduce error somehow",
            "invariants": [],
        }))

        result = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(constraints_path),
            },
            tmp_path,
        )

        assert result.returncode == 0
        assert "Invalid constraints" in result.stdout
        state = json.loads((rd / ".state.json").read_text())
        assert state["state"] == "SHAPE_FULL"

    def _setup_review(self, tmp_path: Path) -> Path:
        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / ".state.json").write_text('{"state":"REVIEW","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "REVIEW",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/evaluation.json",
                    "required_fields": ["verdict", "scores"],
                },
                "next": "REVIEW_DONE",
            }]
        }))
        return rd / "evaluation.json"

    def _write_complete_final_paper(self, tmp_path: Path, sentence: str = "") -> None:
        default_result = tmp_path / "research" / "iter_1" / "results" / "phase_0.json"
        default_uncertainty_sentence = ""
        if not sentence and default_result.exists():
            try:
                result_data = json.loads(default_result.read_text())
            except (OSError, json.JSONDecodeError):
                result_data = {}
            if isinstance(result_data, dict) and "mae_std" in result_data:
                default_uncertainty_sentence = (
                    "The statistical uncertainty is reported in research/iter_1/results/phase_0.json. "
                )
        text = (
            "# Final Paper\n\n"
            "## Abstract\n"
            "This paper summarizes a rigorous automated ML study with traceable artifacts, "
            "controlled comparisons, and explicit limitations. "
            f"{sentence}\n\n"
            "## Related Work\n"
            "Prior work establishes the baseline context for this study.\n\n"
            "## Method\n"
            "The method section describes split protocol, baselines, reproducibility metadata, "
            "leakage audit, feature importance, target achievement, and evaluation procedure "
            "in enough detail for rerunning the study.\n\n"
            "## Results\n"
            f"{default_uncertainty_sentence}"
            "The results section reports artifact-backed findings and discusses repeated splits, "
            "feature importance, target achievement, leakage audit, and "
            "failure cases without unsupported metric claims.\n\n"
            "## Limitations\n"
            "The limitations section documents data quality, evaluation constraints, possible "
            "distribution shift, and implementation assumptions. "
            "Additional text pads the fixture so it resembles a complete paper rather than a stub. "
            * 3
        )
        (tmp_path / "research" / "final_paper.md").write_text(text)

    def _write_complete_plan_and_result(self, tmp_path: Path, iteration: int = 1) -> None:
        idir = tmp_path / "research" / f"iter_{iteration}"
        pdir = idir / "phases"
        rdir = idir / "results"
        pdir.mkdir(parents=True, exist_ok=True)
        rdir.mkdir(exist_ok=True)
        script = pdir / "phase_0.py"
        script.write_text("print('phase complete')\n")
        script_sha = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "complete rigorous fixture",
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
                "why": "Compare baselines under leakage-safe splits.",
                "type": "script",
                "depends_on": [],
                "methodology": (
                    "Run held-out split, seasonal naive, linear regression, ablation, "
                    "cross-validation fold residual error analysis, and leakage audit."
                ),
                "expected_outputs": {
                    "report": {
                        "path": f"research/iter_{iteration}/results/phase_0.json",
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
        }))
        (rdir / "phase_0.json").write_text(json.dumps({
            "mae_mean": 0.42,
            "mae_std": 0.03,
            "baseline_results": [
                {"name": "seasonal naive", "mae_mean": 0.58},
                {"name": "linear regression", "mae_mean": 0.49},
            ],
            "improvement_over_baseline": 0.07,
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
            "script_path": f"research/iter_{iteration}/phases/phase_0.py",
            "script_sha256": script_sha,
        }))
        (rdir / "phase_0_error.png").write_bytes(PNG_SIGNATURE)

    def _complete_result_citation(self, iteration: int = 1) -> str:
        return (
            f"The primary result artifact research/iter_{iteration}/results/phase_0.json documents "
            "the baseline comparison, statistical uncertainty, feature importance, cross-validation fold evaluation protocol, "
            "error analysis, leakage audit, target achievement, and reproducibility metadata, "
            f"and the primary error figure is research/iter_{iteration}/results/phase_0_error.png."
        )

    def test_native_hook_applies_traceable_final_paper_fallback_for_claim_failures(self, tmp_path):
        from tiny_lab.claims import verify_paper_numeric_claims
        from tiny_lab.quality import audit_final_paper

        rd = tmp_path / "research"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / ".state.json").write_text('{"state":"STORY_TELL","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [
                {
                    "id": "STORY_TELL",
                    "type": "ai_session",
                    "completion": {"artifact": "research/final_paper.md"},
                    "next": "REVIEW",
                },
                {"id": "REVIEW", "type": "ai_session"},
            ]
        }))
        self._write_complete_plan_and_result(tmp_path)
        self._write_complete_final_paper(
            tmp_path,
            self._complete_result_citation() + " The model reached MAE 0.99.",
        )
        final_paper = rd / "final_paper.md"

        result = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Write",
                "CLAUDE_TOOL_INPUT_FILE_PATH": str(final_paper),
            },
            tmp_path,
        )

        assert result.returncode == 0
        assert "Traceable final paper fallback applied" in result.stdout
        assert "State: STORY_TELL" in result.stdout
        state = json.loads((rd / ".state.json").read_text())
        assert state["state"] == "REVIEW"
        assert "Audited ML Research Artifact Summary" in final_paper.read_text()
        assert audit_final_paper(tmp_path, iteration=1) == []
        assert verify_paper_numeric_claims(tmp_path) == []

    def test_review_inconsistent_verdict_does_not_advance(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        eval_path.write_text(json.dumps({
            "verdict": "ACCEPT",
            "scores": {
                "academic_rigor": 7,
                "experimental_sufficiency": 7,
                "novelty": 7,
                "narrative_coherence": 7,
                "goal_achievement": 7,
            },
            "total": 35,
            "feedback": _complete_review_feedback(7),
        }))

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "Evaluation consistency issues" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "REVIEW"

    def test_review_consistent_verdict_advances(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        self._write_complete_plan_and_result(tmp_path)
        self._write_complete_final_paper(
            tmp_path,
            f"{self._complete_result_citation()} research/iter_1/.domain_research.json",
        )
        eval_path.write_text(json.dumps({
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

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "State: REVIEW" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "REVIEW_DONE"

    def test_review_reference_issues_do_not_advance(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        self._write_complete_plan_and_result(tmp_path)
        self._write_complete_final_paper(
            tmp_path,
            f"{self._complete_result_citation()} research/iter_1/.domain_research.json",
        )
        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True, exist_ok=True)
        (idir / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Imaginary Paper", "doi": "10.9999/missing"}]
        }))
        (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": "research/iter_1/.domain_research.json",
            "summary": {"total": 1, "verified": 0, "unverified": 0, "not_found": 1, "error": 0},
            "refs": [],
        }))
        eval_path.write_text(json.dumps({
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

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "reference verification issues" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "REVIEW"

    def test_review_out_of_scope_previous_iteration_results_do_not_advance(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        self._write_complete_plan_and_result(tmp_path, iteration=1)
        self._write_complete_plan_and_result(tmp_path, iteration=2)
        self._write_complete_final_paper(
            tmp_path,
            f"{self._complete_result_citation(iteration=1)} {self._complete_result_citation(iteration=2)} "
            "research/iter_1/.domain_research.json",
        )
        state_path = tmp_path / "research" / ".state.json"
        state_path.write_text('{"state":"REVIEW","current_iteration":2}\n')
        idir = tmp_path / "research" / "iter_1"
        idir.mkdir(parents=True, exist_ok=True)
        (idir / ".domain_research.json").write_text(json.dumps({
            "references": [{"title": "Old Imaginary Paper", "doi": "10.9999/old-missing"}]
        }))
        (idir / ".domain_research.ref_verification.json").write_text(json.dumps({
            "source_file": "research/iter_1/.domain_research.json",
            "summary": {"total": 1, "verified": 0, "unverified": 0, "not_found": 1, "error": 0},
            "refs": [],
        }))
        eval_path.write_text(json.dumps({
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

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "out-of-scope research result artifacts" in result.stdout
        assert "iter_1" in result.stdout
        state = json.loads(state_path.read_text())
        assert state["state"] == "REVIEW"

    def test_review_incomplete_phase_outputs_do_not_advance(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        idir = tmp_path / "research" / "iter_1"
        rdir = idir / "results"
        idir.mkdir(parents=True, exist_ok=True)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        self._write_complete_final_paper(
            tmp_path,
            "The incomplete phase result is cited in research/iter_1/results/phase_0.json.",
        )
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "rigorous",
            "metric": {"name": "mae", "direction": "minimize"},
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
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                        },
                    }
                },
                "visualization": ["phase_0_error.png"],
                "status": "done",
            }],
        }))
        eval_path.write_text(json.dumps({
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

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "incomplete research artifacts" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "REVIEW"

    def test_review_incomplete_phase_outputs_from_previous_iterations_do_not_advance(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        state_path = tmp_path / "research" / ".state.json"
        state_path.write_text('{"state":"REVIEW","current_iteration":2}\n')
        idir = tmp_path / "research" / "iter_1"
        rdir = idir / "results"
        idir.mkdir(parents=True, exist_ok=True)
        rdir.mkdir(exist_ok=True)
        (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        self._write_complete_final_paper(
            tmp_path,
            "The incomplete prior result is cited in research/iter_1/results/phase_0.json.",
        )
        (idir / "research_plan.json").write_text(json.dumps({
            "name": "old rigorous",
            "metric": {"name": "mae", "direction": "minimize"},
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
                "name": "Old model comparison",
                "why": "Compare baseline under CV folds",
                "type": "script",
                "depends_on": [],
                "methodology": "Run held-out split, seasonal naive, linear regression, ablation, CV fold residual error analysis.",
                "expected_outputs": {
                    "report": {
                        "path": "research/iter_1/results/phase_0.json",
                        "schema": {
                            "mae_mean": {"type": "number"},
                            "mae_std": {"type": "number"},
                            "random_seed": {"type": "integer"},
                            "dataset_fingerprint": {"type": "string"},
                            "split_id": {"type": "string"},
                            "python_version": {"type": "string"},
                        },
                    }
                },
                "visualization": ["phase_0_error.png"],
                "status": "pending",
            }],
        }))
        eval_path.write_text(json.dumps({
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

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "incomplete research artifacts" in result.stdout
        assert "iter_1" in result.stdout
        state = json.loads(state_path.read_text())
        assert state["state"] == "REVIEW"

    def test_review_missing_final_paper_does_not_advance(self, tmp_path):
        eval_path = self._setup_review(tmp_path)
        rdir = tmp_path / "research" / "iter_1" / "results"
        rdir.mkdir(parents=True)
        (rdir / "phase_0.json").write_text(json.dumps({"mae_mean": 0.42}))
        eval_path.write_text(json.dumps({
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

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(eval_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "final paper issues" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "REVIEW"

    def test_native_hook_resolves_builtin_condition_like_engine(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"REFLECT","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "REFLECT",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/reflect.json",
                    "required_fields": ["decision", "reason"],
                },
                "condition": {"check": "has_pending_phases"},
                "next": {"true": "PHASE_CODE", "false": "PAPER_DRAFT"},
            }]
        }))
        reflect_path = idir / "reflect.json"
        reflect_path.write_text(json.dumps({"decision": "done", "reason": "target met"}))

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT_FILE_PATH": str(reflect_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "State: REFLECT" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PAPER_DRAFT"

    def test_native_hook_advances_after_multiedit_completion_write(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"REFLECT","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "REFLECT",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/reflect.json",
                    "required_fields": ["decision", "reason"],
                },
                "next": "PAPER_DRAFT",
            }]
        }))
        reflect_path = idir / "reflect.json"
        reflect_path.write_text(json.dumps({"decision": "done", "reason": "target met"}))

        result = self._run_hook(
            {"CLAUDE_TOOL_NAME": "MultiEdit", "CLAUDE_TOOL_INPUT_FILE_PATH": str(reflect_path)},
            tmp_path,
        )

        assert result.returncode == 0
        assert "State: REFLECT" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PAPER_DRAFT"

    def test_native_hook_advances_after_bash_completion_write(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"REFLECT","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "REFLECT",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/reflect.json",
                    "required_fields": ["decision", "reason"],
                },
                "next": "PAPER_DRAFT",
            }]
        }))
        reflect_path = idir / "reflect.json"
        reflect_path.write_text(json.dumps({"decision": "done", "reason": "target met"}))

        result = self._run_hook(
            {
                "CLAUDE_TOOL_NAME": "Bash",
                "CLAUDE_TOOL_INPUT_COMMAND": "cat > research/iter_1/reflect.json",
            },
            tmp_path,
        )

        assert result.returncode == 0
        assert "State: REFLECT" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PAPER_DRAFT"


class TestSkillInstallation:
    def test_init_installs_skill(self, tmp_path):
        from tiny_lab.cli import _cmd_init

        _cmd_init(tmp_path, "ml-experiment")
        skill_path = tmp_path / ".claude" / "skills" / "tiny-lab" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text()
        # YAML frontmatter present
        assert content.startswith("---")
        assert "name: tiny-lab" in content
        # Shared runner contract rendered from the SSOT
        assert "Shared Runner Contract" in content
        assert "tiny_lab.runner_contract" in content
        assert "{{TINY_LAB_RUNNER_CONTRACT}}" not in content
        assert "ml_researcher_rubric.md" in content
        assert "tiny-lab audit --strict" in content

    def test_init_installs_codex_artifacts(self, tmp_path):
        """v7.8 codex parity: AGENTS.md and .codex/hooks.json should be installed."""
        from tiny_lab.cli import _cmd_init

        _cmd_init(tmp_path, "ml-experiment")
        agents = tmp_path / "AGENTS.md"
        codex_hooks = tmp_path / ".codex" / "hooks.json"
        assert agents.exists(), "AGENTS.md should be installed for Codex CLI"
        assert codex_hooks.exists(), ".codex/hooks.json should be installed"
        # AGENTS.md content sanity
        content = agents.read_text()
        assert "tiny-lab native runner" in content.lower()
        assert "Shared Runner Contract" in content
        assert "tiny_lab.runner_contract" in content
        assert "{{TINY_LAB_RUNNER_CONTRACT}}" not in content
        assert "ml_researcher_rubric.md" in content
        assert "tiny-lab audit --strict" in content
        # Hooks JSON sanity — must register state_gate + state_advance + ref_verify
        import json as _json
        hooks = _json.loads(codex_hooks.read_text())
        all_cmds = []
        for evt in hooks.get("hooks", {}).values():
            for matcher_block in evt:
                for h in matcher_block.get("hooks", []):
                    all_cmds.append(h.get("command", ""))
        assert any("state_gate" in c for c in all_cmds)
        assert any("state_advance" in c for c in all_cmds)
        assert any("ref_verify" in c for c in all_cmds)
        advance_matchers = [
            block.get("matcher", "")
            for block in hooks.get("hooks", {}).get("PostToolUse", [])
            for h in block.get("hooks", [])
            if "state_advance" in h.get("command", "")
        ]
        assert any("Bash" in matcher for matcher in advance_matchers)


class TestCodexHookFormat:
    """The hook io adapter must produce Codex-style JSON when invoked from
    a Codex-flavored stdin payload, and Claude-style exit codes when
    invoked under Claude env vars."""

    def _run_hook_codex(self, hook_path, env: dict, cwd, stdin_json: str):
        import subprocess

        return subprocess.run(
            [sys.executable, hook_path],
            env={
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                **env,  # tests pass any extra (must NOT include CLAUDE_TOOL_*)
            },
            cwd=str(cwd),
            input=stdin_json,
            capture_output=True,
            text=True,
        )

    def test_codex_apply_patch_disallowed_returns_deny_json(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"DOMAIN_RESEARCH","current_iteration":1}\n'
        )
        (rd / ".workflow.json").write_text(
            '{"states":[{"id":"DOMAIN_RESEARCH","type":"ai_session",'
            '"allowed_write_globs":["research/iter_1/.domain_research.json"]}]}\n'
        )
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        # Realistic Codex payload — apply_patch with a write to a forbidden file
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Add File: '
            'research/iter_1/.WRONG.json\\n+content\\n*** End Patch"}}'
        )
        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)
        assert result.returncode == 0, "Codex deny is exit 0 + JSON, not exit 1"
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "WRONG" in deny.get("permissionDecisionReason", "")

    def test_codex_apply_patch_checks_all_touched_files(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"DOMAIN_RESEARCH","current_iteration":1}\n'
        )
        (rd / ".workflow.json").write_text(
            '{"states":[{"id":"DOMAIN_RESEARCH","type":"ai_session",'
            '"allowed_write_globs":["research/iter_1/.domain_research.json"]}]}\n'
        )
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Update File: '
            'research/iter_1/.domain_research.json\\n line\\n*** Add File: '
            'research/iter_1/.WRONG.json\\n+content\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "WRONG" in deny.get("permissionDecisionReason", "")

    def test_codex_apply_patch_completion_can_be_second_file(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"REFLECT","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "REFLECT",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/reflect.json",
                    "required_fields": ["decision", "reason"],
                },
                "next": "PAPER_DRAFT",
            }]
        }))
        reflect_path = idir / "reflect.json"
        reflect_path.write_text(json.dumps({"decision": "done", "reason": "target met"}))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        )
        payload = (
            '{"hook_event_name":"PostToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Update File: '
            'research/iter_1/notes.md\\n line\\n*** Update File: '
            'research/iter_1/reflect.json\\n line\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert "State: REFLECT" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PAPER_DRAFT"

    def test_codex_bash_completion_advances_state(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"REFLECT","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "REFLECT",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/reflect.json",
                    "required_fields": ["decision", "reason"],
                },
                "next": "PAPER_DRAFT",
            }]
        }))
        (idir / "reflect.json").write_text(json.dumps({"decision": "done", "reason": "target met"}))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        )
        payload = (
            '{"hook_event_name":"PostToolUse","tool_name":"Bash",'
            '"tool_input":{"command":"cat > research/iter_1/reflect.json"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert "State: REFLECT" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PAPER_DRAFT"

    def test_codex_completion_transition_resets_session_for_phase_loop(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text(json.dumps({
            "state": "VALIDATE_PLAN",
            "current_iteration": 1,
            "session_id": "planning-session",
        }) + "\n")
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "VALIDATE_PLAN",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/.plan_validation.json",
                    "required_fields": ["verdict", "checks"],
                },
                "condition": {
                    "source": "{iter}/.plan_validation.json",
                    "field": "verdict",
                },
                "next": {
                    "APPROVE": "PHASE_SELECT",
                    "REJECT": "PLAN",
                },
            }]
        }))
        (idir / ".plan_validation.json").write_text(json.dumps({
            "verdict": "APPROVE",
            "checks": [],
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        )
        payload = (
            '{"hook_event_name":"PostToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Update File: '
            'research/iter_1/.plan_validation.json\\n line\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert "State: VALIDATE_PLAN" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PHASE_SELECT"
        assert state.get("session_id") is None

    def test_codex_explore_completion_starts_new_iteration_with_seed(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text(json.dumps({
            "state": "EXPLORE",
            "current_iteration": 1,
            "session_id": "explore-session",
        }) + "\n")
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "EXPLORE",
                "type": "ai_session",
                "completion": {
                    "artifact": "research/{iter}/.explore_seed.json",
                    "required_fields": ["new_seed", "rationale"],
                },
                "next": "DOMAIN_RESEARCH",
            }]
        }))
        (idir / ".explore_seed.json").write_text(json.dumps({
            "new_seed": "Try a causal representation learning direction.",
            "rationale": "The current supervised baseline has plateaued.",
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        )
        payload = (
            '{"hook_event_name":"PostToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Update File: '
            'research/iter_1/.explore_seed.json\\n line\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert "State: EXPLORE" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "DOMAIN_RESEARCH"
        assert state["current_iteration"] == 2
        assert state.get("session_id") is None
        assert (tmp_path / "research" / "iter_2" / ".explore_seed.json").exists()
        seed = json.loads((tmp_path / "research" / "iter_2" / ".iteration_seed.json").read_text())
        assert seed["source_artifact"] == "research/iter_1/.explore_seed.json"
        assert seed["new_idea"] == "Try a causal representation learning direction."

    def test_codex_phase_code_completion_requires_current_phase_script(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        pdir = idir / "phases"
        pdir.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_1"}\n'
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_CODE",
                "type": "ai_session",
                "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
                "next": "PHASE_RUN",
            }]
        }))
        old_script = pdir / "phase_0_baseline.py"
        old_script.write_text("print('old phase')\n")
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        )
        payload = (
            '{"hook_event_name":"PostToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Update File: '
            'research/iter_1/phases/phase_0_baseline.py\\n line\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert "does not match current_phase_id phase_1" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PHASE_CODE"

    def test_codex_phase_code_completion_advances_for_current_phase_script(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        pdir = idir / "phases"
        pdir.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_1"}\n'
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_CODE",
                "type": "ai_session",
                "completion": {"artifact": "research/{iter}/phases/phase_*.py"},
                "next": "PHASE_RUN",
            }]
        }))
        current_script = pdir / "phase_1_model.py"
        current_script.write_text("print('current phase')\n")
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_advance.py"
        )
        payload = (
            '{"hook_event_name":"PostToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Add File: '
            'research/iter_1/phases/phase_1_model.py\\n+content\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert "State: PHASE_CODE" in result.stdout
        state = json.loads((tmp_path / "research" / ".state.json").read_text())
        assert state["state"] == "PHASE_RUN"

    def test_codex_apply_patch_update_respects_edit_allowed_tool(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_0"}\n'
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_CODE",
                "type": "ai_session",
                "allowed_tools": ["Read", "Edit"],
                "allowed_write_globs": ["research/{iter}/phases/*"],
            }]
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Update File: '
            'research/iter_1/phases/phase_0.py\\n line\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        assert result.stdout == ""

    def test_codex_apply_patch_add_file_requires_write_allowed_tool(self, tmp_path):
        rd = tmp_path / "research"
        idir = rd / "iter_1"
        idir.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1}\n'
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_CODE",
                "type": "ai_session",
                "allowed_tools": ["Read", "Edit"],
                "allowed_write_globs": ["research/{iter}/phases/*"],
            }]
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"apply_patch",'
            '"tool_input":{"input":"*** Begin Patch\\n*** Add File: '
            'research/iter_1/phases/phase_0.py\\n+content\\n*** End Patch"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "Write" in deny.get("permissionDecisionReason", "")

    def test_codex_bash_blocks_glob_pattern(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_0"}\n'
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_CODE",
                "type": "ai_session",
                "allowed_tools": ["Read", "Write", "Bash"],
                "blocked_bash_patterns": ["python research/*/phases/*"],
            }]
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"Bash",'
            '"tool_input":{"command":"python research/iter_1/phases/phase_0.py"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "python research/*/phases/*" in deny.get("permissionDecisionReason", "")

    def test_codex_bash_blocks_python3_phase_script_execution(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text(
            '{"state":"PHASE_CODE","current_iteration":1,"current_phase_id":"phase_0"}\n'
        )
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_CODE",
                "type": "ai_session",
                "allowed_tools": ["Read", "Write", "Bash"],
                "blocked_bash_patterns": ["python research/*/phases/*"],
            }]
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"Bash",'
            '"tool_input":{"command":"python3 research/iter_1/phases/phase_0.py"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "python research/*/phases/*" in deny.get("permissionDecisionReason", "")

    def test_codex_bash_redirection_respects_blocked_write_glob(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"PHASE_RUN","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "PHASE_RUN",
                "type": "process",
                "allowed_tools": ["Bash"],
                "blocked_write_globs": ["research/{iter}/phases/*"],
            }]
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"Bash",'
            '"tool_input":{"command":"cat > research/iter_1/phases/phase_0.py"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "research/iter_1/phases/phase_0.py" in deny.get("permissionDecisionReason", "")

    def test_codex_bash_mkdir_respects_allowed_write_glob(self, tmp_path):
        rd = tmp_path / "research"
        rd.mkdir(parents=True)
        (rd / ".state.json").write_text('{"state":"DOMAIN_RESEARCH","current_iteration":1}\n')
        (rd / ".workflow.json").write_text(json.dumps({
            "states": [{
                "id": "DOMAIN_RESEARCH",
                "type": "ai_session",
                "allowed_tools": ["Bash"],
                "allowed_write_globs": ["research/{iter}/.domain_research.json"],
            }]
        }))
        hook = (
            Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "state_gate.py"
        )
        payload = (
            '{"hook_event_name":"PreToolUse","tool_name":"Bash",'
            '"tool_input":{"command":"mkdir -p research/iter_1/.forbidden"}}'
        )

        result = self._run_hook_codex(str(hook), {}, tmp_path, payload)

        assert result.returncode == 0
        import json as _json
        out = _json.loads(result.stdout)
        deny = out.get("hookSpecificOutput", {})
        assert deny.get("permissionDecision") == "deny"
        assert "research/iter_1/.forbidden" in deny.get("permissionDecisionReason", "")


class TestRefVerifyHook:
    def _load_hook(self):
        import importlib.util

        hook = Path(__file__).parent.parent.parent / "src" / "tiny_lab" / "hooks" / "ref_verify.py"
        spec = importlib.util.spec_from_file_location("ref_verify_hook_test", hook)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _install_fake_refs(self, monkeypatch):
        import types

        fake = types.ModuleType("tiny_lab.refs")
        seen: list[Path] = []

        def verify_file(path: Path):
            try:
                data = json.loads(path.read_text())
            except Exception:
                data = {}
            if not any(key in data for key in ("references", "papers", "bibliography", "sources")):
                return SimpleNamespace(total=0, verified=0, not_found=0, unverified=0, error=0)
            seen.append(path)
            return SimpleNamespace(total=1, verified=1, not_found=0, unverified=0, error=0)

        def write_verification(path: Path, result):
            out = path.parent / (path.stem + ".ref_verification.json")
            out.write_text(json.dumps({"source_file": str(path), "summary": {"total": result.total}}))
            return out

        fake.verify_file = verify_file
        fake.write_verification = write_verification
        monkeypatch.setitem(sys.modules, "tiny_lab.refs", fake)
        return seen

    def test_ref_verify_handles_write_hook_input(self, tmp_path, monkeypatch):
        module = self._load_hook()
        seen = self._install_fake_refs(monkeypatch)
        artifact = tmp_path / "research" / "iter_1" / ".domain_research.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({"references": [{"title": "Known Paper"}]}))
        monkeypatch.setattr(
            module,
            "read_hook_input",
            lambda event_name=None: SimpleNamespace(
                tool_name="Write",
                file_paths=(str(artifact),),
                command="",
            ),
        )

        assert module.main() == 0

        assert seen == [artifact]
        assert (artifact.parent / ".domain_research.ref_verification.json").exists()

    def test_ref_verify_handles_literature_scan_artifact(self, tmp_path, monkeypatch):
        module = self._load_hook()
        seen = self._install_fake_refs(monkeypatch)
        artifact = tmp_path / "research" / "iter_1" / ".lit_scan.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({"papers": [{"title": "Known Paper"}]}))
        monkeypatch.setattr(
            module,
            "read_hook_input",
            lambda event_name=None: SimpleNamespace(
                tool_name="Write",
                file_paths=(str(artifact),),
                command="",
            ),
        )

        assert module.main() == 0

        assert seen == [artifact]
        assert (artifact.parent / ".lit_scan.ref_verification.json").exists()

    def test_ref_verify_handles_bash_written_artifact(self, tmp_path, monkeypatch):
        module = self._load_hook()
        seen = self._install_fake_refs(monkeypatch)
        artifact = tmp_path / "research" / "iter_1" / ".domain_research.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({"references": [{"title": "Known Paper"}]}))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            module,
            "read_hook_input",
            lambda event_name=None: SimpleNamespace(
                tool_name="Bash",
                file_paths=(),
                command="cat > research/iter_1/.domain_research.json",
            ),
        )

        assert module.main() == 0

        assert seen == [Path("research/iter_1/.domain_research.json")]
        assert (artifact.parent / ".domain_research.ref_verification.json").exists()

    def test_ref_verify_ignores_non_reference_artifact(self, tmp_path, monkeypatch):
        module = self._load_hook()
        seen = self._install_fake_refs(monkeypatch)
        artifact = tmp_path / "research" / "iter_1" / "notes.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}")
        monkeypatch.setattr(
            module,
            "read_hook_input",
            lambda event_name=None: SimpleNamespace(
                tool_name="Write",
                file_paths=(str(artifact),),
                command="",
            ),
        )

        assert module.main() == 0

        assert seen == []

    def test_ref_verify_fallback_rejects_unsafe_and_non_reference_paths(self):
        module = self._load_hook()

        assert module._fallback_reference_artifact_candidate_path("research/iter_1/.lit_scan.json") is True
        assert module._fallback_reference_artifact_candidate_path("research/iter_1/.lit_scan.ref_verification.json") is False
        assert module._fallback_reference_artifact_candidate_path("../research/iter_1/.lit_scan.json") is False
        assert module._fallback_reference_artifact_candidate_path("research/iter_x/.lit_scan.json") is False
        assert module._fallback_reference_artifact_candidate_path("research/iter_1/results/phase_0.json") is False
