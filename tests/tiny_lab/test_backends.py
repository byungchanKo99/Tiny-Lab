"""Tests for v7.7 AI backend abstraction."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tiny_lab.backends import get_backend
from tiny_lab.backends.base import BackendResult


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


class TestCodexBackendCommandShape:
    def test_default_base_cmd(self, monkeypatch):
        monkeypatch.delenv("TINYLAB_CODEX_CMD", raising=False)
        from tiny_lab.backends.codex import _base_cmd

        assert _base_cmd() == ["codex", "exec", "--json"]

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("TINYLAB_CODEX_CMD", "codex exec --json --skip-git-repo-check")
        from tiny_lab.backends.codex import _base_cmd

        assert _base_cmd() == ["codex", "exec", "--json", "--skip-git-repo-check"]


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
        # Hard rules section present
        assert "Hard rules" in content or "hard rules" in content.lower()

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
