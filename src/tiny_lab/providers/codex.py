"""Codex CLI provider."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .base import AIProvider

CODEX_BIN = os.environ.get("CODEX_BIN", "codex")


class CodexProvider(AIProvider):
    """Codex CLI provider.

    Leverages Codex-specific features:
    - --output-schema for enforcing structured JSON output
    - --full-auto for non-interactive sandboxed execution
    - Config profiles (-p) for per-task settings
    """

    @property
    def name(self) -> str:
        return "codex"

    def _check_binary(self) -> None:
        if not shutil.which(CODEX_BIN):
            raise RuntimeError(
                f"codex CLI not found ({CODEX_BIN}). "
                "Install from https://github.com/openai/codex or set agent.provider: claude"
            )

    def run(
        self,
        prompt: str,
        *,
        tools: list[str] | None = None,
        max_turns: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._check_binary()
        # Codex doesn't support tool restrictions or max-turns
        cmd = [CODEX_BIN, "exec", prompt, "--full-auto", "--skip-git-repo-check"]
        return subprocess.run(
            cmd, text=True, capture_output=True,
            cwd=self._effective_cwd(cwd),
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
        """Codex supports --output-schema for enforcing JSON structure."""
        self._check_binary()
        cmd = [CODEX_BIN, "exec", prompt, "--full-auto", "--skip-git-repo-check"]
        if schema_path and schema_path.exists():
            cmd += ["--output-schema", str(schema_path)]
        if output_path:
            # Also instruct in prompt for file writing (schema only shapes final response)
            prompt += f"\n\nIMPORTANT: Write the JSON result to {output_path}"
            cmd[2] = prompt  # Update prompt in command
        return subprocess.run(
            cmd, text=True, capture_output=True,
            cwd=self._effective_cwd(cwd),
        )

    def run_interactive(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._check_binary()
        cmd = [CODEX_BIN, "exec", prompt, "--full-auto", "--skip-git-repo-check"]
        return subprocess.run(
            cmd, cwd=self._effective_cwd(cwd),
        )

    def get_template_files(self) -> list[tuple[str, str]]:
        return [
            # Common files
            ("common/project.yaml", "research/project.yaml"),
            ("common/hypothesis_queue.yaml", "research/hypothesis_queue.yaml"),
            ("common/questions.yaml", "research/questions.yaml"),
            ("common/AGENTS.md", "AGENTS.md"),
            # Codex-specific files
            ("codex/instructions.md", "CODEX.md"),
        ]
