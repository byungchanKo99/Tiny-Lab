"""AI provider factory."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .base import AIProvider
from .claude import ClaudeProvider
from .codex import CodexProvider


def get_provider(project_dir: Path, provider_name: str | None = None) -> AIProvider:
    """Create the appropriate AI provider.

    Resolution order:
    1. Explicit provider_name argument
    2. project.yaml agent.provider field
    3. TINYLAB_PROVIDER env var
    4. Default: "claude"
    """
    if provider_name is None:
        project_yaml = project_dir / "research" / "project.yaml"
        if project_yaml.exists():
            import yaml
            data = yaml.safe_load(project_yaml.read_text()) or {}
            provider_name = data.get("agent", {}).get("provider")

    if provider_name is None:
        provider_name = os.environ.get("TINYLAB_PROVIDER", "claude")

    providers = {
        "claude": ClaudeProvider,
        "codex": CodexProvider,
    }

    cls = providers.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_name}. Choose from: {list(providers.keys())}")

    return cls(project_dir)


def detect_provider() -> str:
    """Auto-detect AI provider from installed CLIs. If both available, ask user."""
    has_claude = shutil.which("claude") is not None
    has_codex = shutil.which("codex") is not None

    if has_claude and has_codex:
        print("Detected both Claude Code and Codex CLI.")
        while True:
            choice = input("Which provider? [claude/codex] (default: claude): ").strip().lower()
            if choice in ("", "claude"):
                return "claude"
            if choice == "codex":
                return "codex"
            print("  Enter 'claude' or 'codex'.")
    elif has_claude:
        return "claude"
    elif has_codex:
        return "codex"
    else:
        print("Warning: Neither claude nor codex CLI found.")
        print("Install one of:")
        print("  Claude Code: https://claude.ai/claude-code")
        print("  Codex CLI:   https://github.com/openai/codex")
        print("Defaulting to claude. Change in research/project.yaml later.")
        return "claude"
