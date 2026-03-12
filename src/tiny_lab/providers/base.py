"""Base AI provider interface."""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class AIProvider(ABC):
    """Abstract base for AI providers (Claude Code, Codex CLI, etc.)."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""

    @abstractmethod
    def run(
        self,
        prompt: str,
        *,
        tools: list[str] | None = None,
        max_turns: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute AI with given prompt. Output captured."""

    @abstractmethod
    def run_structured(
        self,
        prompt: str,
        *,
        output_path: Path | None = None,
        schema_path: Path | None = None,
        tools: list[str] | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute AI expecting structured JSON output.

        For providers that support --output-schema (Codex), the schema is enforced.
        For others (Claude), the prompt is augmented with file-output instructions.
        """

    @abstractmethod
    def run_interactive(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run AI interactively (user sees output directly, not captured)."""

    @abstractmethod
    def get_template_files(self) -> list[tuple[str, str]]:
        """Return (src_template_path, dst_project_path) pairs for init.

        Paths are relative to the templates directory and project root respectively.
        """

    def _effective_cwd(self, cwd: str | None) -> str:
        return cwd or str(self.project_dir)
