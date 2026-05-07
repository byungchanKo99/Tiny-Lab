"""Shared hook tool-name constants.

Hook scripts are copied into project-local `.claude/hooks/`, so this module
must stay importable both as a package module and as a sibling script module.
"""
from __future__ import annotations


WRITE_TOOL_NAMES = ("Write", "Edit", "MultiEdit")
