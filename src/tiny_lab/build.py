"""BUILD plugins — construct experiment commands from hypotheses."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import BuildError
from .logging import log
from .providers.base import AIProvider


def build_command_flag(project: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    """Replace a lever's CLI flag in the baseline command. Deterministic, no LLM."""
    baseline_cmd = project["baseline"]["command"].strip()
    lever_name = hypothesis["lever"]
    value = hypothesis["value"]
    lever = project["levers"][lever_name]
    flag = lever["flag"]
    baseline_value = lever["baseline"]

    pattern = re.compile(re.escape(flag) + r"\s+" + re.escape(str(baseline_value)))
    replacement = f"{flag} {value}"

    if pattern.search(baseline_cmd):
        return pattern.sub(replacement, baseline_cmd)
    return f"{baseline_cmd} {flag} {value}"


def build_command_multi_flag(project: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    """Replace multiple levers' CLI flags in the baseline command. Deterministic, no LLM."""
    cmd = project["baseline"]["command"].strip()
    values = hypothesis["value"]  # dict: {"lr": "0.05", "batch_size": "32"}
    for lever_name, value in values.items():
        lever = project["levers"][lever_name]
        flag = lever["flag"]
        baseline_value = lever["baseline"]
        pattern = re.compile(re.escape(flag) + r"\s+" + re.escape(str(baseline_value)))
        replacement = f"{flag} {value}"
        if pattern.search(cmd):
            cmd = pattern.sub(replacement, cmd)
        else:
            cmd = f"{cmd} {flag} {value}"
    return cmd


def build_command_script(project: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    """Use a pre-defined script command from the hypothesis. Deterministic, no LLM."""
    script = hypothesis.get("script")
    if not script:
        lever_name = hypothesis["lever"]
        value = hypothesis["value"]
        scripts = project.get("build", {}).get("scripts", {})
        script = scripts.get(f"{lever_name}:{value}")
    if not script:
        raise BuildError(f"No script defined for hypothesis {hypothesis['id']}")
    return script


def build_command_code(
    project: dict[str, Any],
    hypothesis: dict[str, Any],
    project_dir: Path,
    provider: AIProvider,
) -> str:
    """AI provider modifies code based on the hypothesis. Non-deterministic."""
    build_config = project.get("build", {})
    target_files = build_config.get("target_files", [])

    target_desc = "\n".join(f"- {f}" for f in target_files) if target_files else "- (determine from project context)"

    prompt = f"""You are the code modifier for the research loop.

PROJECT: {project['name']}
DESCRIPTION: {project['description']}

HYPOTHESIS: {hypothesis['description']}
LEVER: {hypothesis['lever']} = {hypothesis['value']}

TARGET FILES:
{target_desc}

TASK:
Modify the target files to implement this hypothesis.
Make the MINIMUM changes needed. Do not refactor or clean up unrelated code.

After modifying, confirm the change is complete by printing:
CODE_MODIFIED: {hypothesis['id']}"""

    log(f"BUILD[code]: calling {provider.name} subagent for {hypothesis['id']}")
    result = provider.run(prompt, tools=["Read", "Write", "Edit", "Bash"], cwd=str(project_dir))
    if result.returncode != 0:
        log(f"BUILD[code]: {provider.name} subagent failed (exit={result.returncode})")
        raise BuildError(f"Code modifier failed for {hypothesis['id']}")

    return project["baseline"]["command"].strip()


def dispatch_build(
    project: dict[str, Any],
    hypothesis: dict[str, Any],
    project_dir: Path,
    provider: AIProvider | None = None,
) -> str:
    """Route to the correct BUILD plugin based on project.yaml build.type."""
    build_type = project.get("build", {}).get("type", "flag")

    if build_type == "flag":
        value = hypothesis["value"]
        if isinstance(value, dict):
            # Multi-lever: validate each lever
            for lever_name, lever_value in value.items():
                if lever_name not in project["levers"]:
                    raise BuildError(f"Unknown lever '{lever_name}'")
                lever = project["levers"][lever_name]
                if "flag" in lever and lever_value not in lever["space"]:
                    raise BuildError(f"Value {lever_value} not in space for '{lever_name}'")
            return build_command_multi_flag(project, hypothesis)
        else:
            lever_name = hypothesis["lever"]
            if lever_name not in project["levers"]:
                raise BuildError(f"Unknown lever '{lever_name}'")
            lever = project["levers"][lever_name]
            if "flag" in lever and value not in lever["space"]:
                raise BuildError(f"Value {value} not in space for '{lever_name}'")
            return build_command_flag(project, hypothesis)

    elif build_type == "script":
        return build_command_script(project, hypothesis)

    elif build_type == "code":
        if provider is None:
            raise BuildError("build.type=code requires an AI provider")
        return build_command_code(project, hypothesis, project_dir, provider)

    else:
        raise BuildError(f"Unknown build type: {build_type}")
