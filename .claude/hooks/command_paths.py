"""Shared command/path helpers for tiny-lab hooks."""
from __future__ import annotations

import fnmatch
import re
import shlex
from pathlib import Path


TINY_LAB_ROOTS = ("research/", "shared/")


def tiny_lab_relative_paths(file_paths: list[str] | tuple[str, ...], root: Path | None = None) -> list[str]:
    paths: list[str] = []
    for file_path in file_paths:
        rel = project_relative_path(file_path, root)
        if rel and is_tiny_lab_relative(rel):
            paths.append(rel)
    return paths


def project_relative_path(file_path: str, root: Path | None = None) -> str | None:
    if not file_path:
        return None
    root = (root or Path.cwd()).resolve(strict=False)
    candidate = Path(file_path)
    absolute = candidate if candidate.is_absolute() else root / candidate
    try:
        return absolute.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return None


def is_tiny_lab_relative(path: str) -> bool:
    return any(path == root.rstrip("/") or path.startswith(root) for root in TINY_LAB_ROOTS)


def matches_any(file_path: str, patterns: list[str], iter_str: str) -> bool:
    for pattern in patterns:
        resolved = pattern.replace("{iter}", iter_str)
        if _path_matches(file_path, resolved) or _path_matches(file_path, "*/" + resolved):
            return True
    return False


def _path_matches(file_path: str, pattern: str) -> bool:
    if fnmatch.fnmatch(file_path, pattern):
        return True
    if pattern.endswith("/*"):
        parent = pattern[:-2].rstrip("/")
        return bool(parent) and fnmatch.fnmatch(file_path.rstrip("/"), parent)
    return False


def bash_pattern_matches(command: str, pattern: str, iter_str: str) -> bool:
    resolved = pattern.replace("{iter}", iter_str).strip()
    normalized = " ".join(command.strip().split())
    if not resolved or not normalized:
        return False
    return (
        resolved in normalized
        or fnmatch.fnmatch(normalized, resolved)
        or fnmatch.fnmatch(normalized, f"*{resolved}*")
        or _python_phase_script_execution_matches(normalized, resolved, iter_str)
    )


def bash_write_target_paths(command: str, root: Path | None = None) -> list[str]:
    tokens = _shell_tokens(command)
    paths: list[str] = []
    for index, token in enumerate(tokens):
        if token in {">", ">>", ">|", "2>", "2>>", "&>", "&>>"} and index + 1 < len(tokens):
            _append_tiny_lab_arg_path(paths, tokens[index + 1], root)
            continue
        for prefix in ("&>>", "&>", "2>>", "2>", ">>", ">|", ">"):
            if token.startswith(prefix) and len(token) > len(prefix):
                _append_tiny_lab_arg_path(paths, token[len(prefix):], root)
                break

    for command_tokens in _shell_command_segments(tokens):
        if not command_tokens:
            continue
        name = Path(command_tokens[0]).name
        args = command_tokens[1:]
        if name in {"tee", "touch", "rm", "mv", "mkdir", "rmdir"}:
            for arg in args:
                if not arg.startswith("-"):
                    _append_tiny_lab_arg_path(paths, arg, root)
        elif name == "ln":
            destination = _last_link_destination(args)
            if destination:
                _append_tiny_lab_arg_path(paths, destination, root)
        elif name == "cp":
            for arg in args[-1:]:
                if not arg.startswith("-"):
                    _append_tiny_lab_arg_path(paths, arg, root)
        elif name == "dd":
            for arg in args:
                if arg.startswith("of="):
                    _append_tiny_lab_arg_path(paths, arg.removeprefix("of="), root)
        elif name == "install":
            destination = _last_install_destination(args)
            if destination:
                _append_tiny_lab_arg_path(paths, destination, root)
        elif name == "sed" and any(arg == "-i" or arg.startswith("-i") for arg in args):
            for arg in args:
                if not arg.startswith("-"):
                    _append_tiny_lab_arg_path(paths, arg, root)
    _append_inline_python_write_paths(paths, command, root)
    return list(dict.fromkeys(paths))


def _shell_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _shell_command_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {"&&", "||", "|", ";"}:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _append_tiny_lab_arg_path(paths: list[str], arg: str, root: Path | None) -> None:
    rel = project_relative_path(arg.rstrip(";"), root)
    if rel and is_tiny_lab_relative(rel):
        paths.append(rel)


def _last_install_destination(args: list[str]) -> str | None:
    destinations: list[str] = []
    target_directory: str | None = None
    end_options = False
    options_with_values = {"-g", "-m", "-o", "-S", "-t"}
    long_options_with_values = (
        "--backup",
        "--group",
        "--mode",
        "--owner",
        "--suffix",
        "--target-directory",
    )
    index = 0
    while index < len(args):
        arg = args[index]
        if end_options:
            destinations.append(arg)
            index += 1
            continue
        if arg == "--":
            end_options = True
            index += 1
            continue
        if arg in {"-t", "--target-directory"} and index + 1 < len(args):
            target_directory = args[index + 1]
            index += 2
            continue
        if arg.startswith("--target-directory="):
            target_directory = arg.split("=", 1)[1]
            index += 1
            continue
        if arg in options_with_values or arg in long_options_with_values:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        destinations.append(arg)
        index += 1
    return target_directory or (destinations[-1] if destinations else None)


def _last_link_destination(args: list[str]) -> str | None:
    destinations: list[str] = []
    target_directory: str | None = None
    end_options = False
    index = 0
    while index < len(args):
        arg = args[index]
        if end_options:
            destinations.append(arg)
            index += 1
            continue
        if arg == "--":
            end_options = True
            index += 1
            continue
        if arg in {"-t", "--target-directory"} and index + 1 < len(args):
            target_directory = args[index + 1]
            index += 2
            continue
        if arg.startswith("--target-directory="):
            target_directory = arg.split("=", 1)[1]
            index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        destinations.append(arg)
        index += 1
    if target_directory:
        return target_directory
    return destinations[-1] if len(destinations) >= 2 else None


def _append_inline_python_write_paths(paths: list[str], command: str, root: Path | None) -> None:
    for match in _PYTHON_OPEN_WRITE_RE.finditer(command):
        if _mode_can_write(match.group("mode")):
            _append_tiny_lab_arg_path(paths, match.group("path"), root)
    for pattern in (_PYTHON_PATH_WRITE_RE, _PYTHON_PATH_OPEN_WRITE_RE):
        for match in pattern.finditer(command):
            if "mode" not in match.groupdict() or _mode_can_write(match.group("mode")):
                _append_tiny_lab_arg_path(paths, match.group("path"), root)
    for match in _PYTHON_OS_PATH_MUTATION_RE.finditer(command):
        _append_tiny_lab_arg_path(paths, match.group("path"), root)


_QUOTED_PATH = r"(?P<quote>['\"])(?P<path>[^'\"]*(?:research|shared)/[^'\"]+)(?P=quote)"
_QUOTED_MODE = r"(?P<mode_quote>['\"])(?P<mode>[^'\"]*)(?P=mode_quote)"
_PYTHON_OPEN_WRITE_RE = re.compile(
    rf"\bopen\s*\(\s*{_QUOTED_PATH}\s*,\s*{_QUOTED_MODE}",
)
_PYTHON_PATH_WRITE_RE = re.compile(
    rf"\b(?:Path|pathlib\.Path)\s*\(\s*{_QUOTED_PATH}\s*\)\s*\.\s*"
    r"(?:write_text|write_bytes|touch|mkdir|rmdir|unlink)\s*\(",
)
_PYTHON_PATH_OPEN_WRITE_RE = re.compile(
    rf"\b(?:Path|pathlib\.Path)\s*\(\s*{_QUOTED_PATH}\s*\)\s*\.\s*open\s*\(\s*{_QUOTED_MODE}",
)
_PYTHON_OS_PATH_MUTATION_RE = re.compile(
    rf"\b(?:os\.)?(?:makedirs|mkdir|rmdir|remove|unlink)\s*\(\s*{_QUOTED_PATH}",
)


def _mode_can_write(mode: str) -> bool:
    return any(token in mode for token in ("w", "a", "x", "+"))


def _python_phase_script_execution_matches(command: str, pattern: str, iter_str: str) -> bool:
    if "python" not in pattern or "research/" not in pattern or "/phases/" not in pattern:
        return False
    tokens = _shell_tokens(command)

    for index, token in enumerate(tokens):
        if not _is_python_executable(token):
            continue
        args = tokens[index + 1:]
        for arg_index, arg in enumerate(args):
            if arg in {"&&", "||", "|", ";"}:
                break
            if arg == "-m" and arg_index + 1 < len(args):
                if _is_phase_module_arg(args[arg_index + 1], iter_str):
                    return True
            if _is_phase_script_path_arg(arg, iter_str):
                return True
    return False


def _is_python_executable(token: str) -> bool:
    name = Path(token).name
    return name == "python" or name.startswith("python3") or name.startswith("python2")


def _is_phase_script_path_arg(arg: str, iter_str: str) -> bool:
    cleaned = arg.rstrip(";")
    return (
        fnmatch.fnmatch(cleaned, f"research/{iter_str}/phases/*.py")
        or fnmatch.fnmatch(cleaned, "research/iter_*/phases/*.py")
        or fnmatch.fnmatch(cleaned, f"*/research/{iter_str}/phases/*.py")
        or fnmatch.fnmatch(cleaned, "*/research/iter_*/phases/*.py")
    )


def _is_phase_module_arg(arg: str, iter_str: str) -> bool:
    cleaned = arg.rstrip(";")
    return (
        cleaned.startswith(f"research.{iter_str}.phases.")
        or fnmatch.fnmatch(cleaned, "research.iter_*.phases.*")
    )
