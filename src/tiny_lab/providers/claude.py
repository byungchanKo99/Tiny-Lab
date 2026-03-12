"""Claude Code provider."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .base import AIProvider

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MAX_TURNS = int(os.environ.get("CLAUDE_MAX_TURNS", "20"))


class ClaudeProvider(AIProvider):
    """Claude Code CLI provider.

    Leverages Claude-specific features:
    - --allowedTools for per-phase tool restrictions
    - Sub-agent prompts (.claude/agents/) for specialized roles
    - Hooks (.claude/hooks/) for workflow enforcement
    - Slash commands (.claude/commands/) for interactive entry points
    """

    @property
    def name(self) -> str:
        return "claude"

    def _check_binary(self) -> None:
        if not shutil.which(CLAUDE_BIN):
            raise RuntimeError(
                f"claude CLI not found ({CLAUDE_BIN}). "
                "Install from https://claude.ai/claude-code or set agent.provider: codex"
            )

    def _build_env(self) -> dict[str, str]:
        """Strip CLAUDECODE env var to allow subprocess invocations from within Claude Code."""
        return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    def run(
        self,
        prompt: str,
        *,
        tools: list[str] | None = None,
        max_turns: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._check_binary()
        cmd = [
            CLAUDE_BIN, "-p", prompt,
            "--allowedTools", ",".join(tools) if tools else "Read,Write,Edit",
            "--max-turns", str(max_turns or CLAUDE_MAX_TURNS),
            "--output-format", "text",
        ]
        return subprocess.run(
            cmd, text=True, capture_output=True,
            cwd=self._effective_cwd(cwd), env=self._build_env(),
        )

    def run_structured(
        self,
        prompt: str,
        *,
        output_path: Path | None = None,
        schema_path: Path | None = None,
        tools: list[str] | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Claude doesn't have --output-schema, so we augment the prompt."""
        if output_path:
            prompt += f"\n\nIMPORTANT: Write the JSON result to {output_path}"
        return self.run(prompt, tools=tools, cwd=cwd)

    def run_interactive(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._check_binary()
        cmd = [
            CLAUDE_BIN, "-p", prompt,
            "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
            "--max-turns", "50",
            "--output-format", "text",
        ]
        return subprocess.run(
            cmd, cwd=self._effective_cwd(cwd), env=self._build_env(),
        )

    def get_template_files(self) -> list[tuple[str, str]]:
        return [
            # Common files
            ("common/project.yaml", "research/project.yaml"),
            ("common/hypothesis_queue.yaml", "research/hypothesis_queue.yaml"),
            ("common/questions.yaml", "research/questions.yaml"),
            ("common/AGENTS.md", "AGENTS.md"),
            # Claude-specific files
            ("claude/CLAUDE.md", "CLAUDE.md"),
            ("claude/agents/hypothesis-generator.md", ".claude/agents/hypothesis-generator.md"),
            ("claude/agents/code-modifier.md", ".claude/agents/code-modifier.md"),
            ("claude/agents/ux-evaluator.md", ".claude/agents/ux-evaluator.md"),
            ("claude/commands/research.md", ".claude/commands/research.md"),
            ("claude/hooks/enforce-discovery.sh", ".claude/hooks/enforce-discovery.sh"),
            ("claude/settings.json", ".claude/settings.json"),
        ]
