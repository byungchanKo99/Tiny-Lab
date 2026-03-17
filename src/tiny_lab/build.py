"""BUILD plugins — construct experiment commands from hypotheses."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import BuildError
from .logging import log
from .project import baseline_command, build_config, build_type, immutable_files, levers, project_name, project_description
from .providers.base import AIProvider


def build_command_flag(project: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    """Replace a lever's CLI flag in the baseline command. Deterministic, no LLM."""
    cmd = baseline_command(project)
    lever_name = hypothesis["lever"]
    value = hypothesis["value"]
    lever = levers(project)[lever_name]
    flag = lever["flag"]
    baseline_value = lever["baseline"]

    pattern = re.compile(re.escape(flag) + r"\s+" + re.escape(str(baseline_value)))
    replacement = f"{flag} {value}"

    if pattern.search(cmd):
        return pattern.sub(replacement, cmd)
    return f"{cmd} {flag} {value}"


def build_command_multi_flag(project: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    """Replace multiple levers' CLI flags in the baseline command. Deterministic, no LLM."""
    cmd = baseline_command(project)
    values = hypothesis["value"]  # dict: {"lr": "0.05", "batch_size": "32"}
    project_levers = levers(project)
    for lever_name, value in values.items():
        lever = project_levers[lever_name]
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
        scripts = build_config(project).get("scripts", {})
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
    cfg = build_config(project)
    target_files = cfg.get("target_files", [])

    target_desc = "\n".join(f"- {f}" for f in target_files) if target_files else "- (determine from project context)"

    immutable = immutable_files(project)
    immutable_warning = ""
    if immutable:
        immutable_warning = "\n\nDO NOT MODIFY these files under any circumstances:\n" + "\n".join(f"- {f}" for f in immutable)
        overlap = set(target_files) & set(immutable)
        if overlap:
            log(f"BUILD[code]: WARNING — target_files overlap with immutable_files: {overlap}")

    prompt = f"""You are the code modifier for the research loop.

PROJECT: {project_name(project)}
DESCRIPTION: {project_description(project)}

HYPOTHESIS: {hypothesis['description']}
LEVER: {hypothesis['lever']} = {hypothesis['value']}

TARGET FILES:
{target_desc}{immutable_warning}

TASK:
Modify the target files to implement this hypothesis.
Make the MINIMUM changes needed. Do not refactor or clean up unrelated code.

After modifying, confirm the change is complete by printing:
CODE_MODIFIED: {hypothesis['id']}"""

    log(f"BUILD[code]: calling {provider.name} subagent for {hypothesis['id']}")
    result = provider.run(prompt, tools=["Read", "Write", "Edit", "Bash"], cwd=str(project_dir))
    if result.returncode != 0:
        log(f"BUILD[code]: {provider.name} subagent failed (exit={result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-10:]:
                log(f"BUILD[code]: stderr: {line}")
        raise BuildError(f"Code modifier failed for {hypothesis['id']}")

    return baseline_command(project)


def dispatch_build(
    project: dict[str, Any],
    hypothesis: dict[str, Any],
    project_dir: Path,
    provider: AIProvider | None = None,
) -> str:
    """Route to the correct BUILD plugin based on project.yaml build.type."""
    btype = build_type(project)
    project_levers = levers(project)

    if btype == "flag":
        # v2 hypothesis with approach: return baseline command as-is
        # (parameters will be injected by the optimizer)
        if "approach" in hypothesis and "lever" not in hypothesis:
            return baseline_command(project)

        # Validate required fields with helpful error messages
        if "lever" not in hypothesis:
            hint = ""
            if "changed_variable" in hypothesis:
                hint = " (did you mean 'lever' instead of 'changed_variable'?)"
            raise BuildError(
                f"Hypothesis {hypothesis.get('id', '?')} missing 'lever' field{hint}. "
                f"Use 'approach' for strategy-based hypotheses, or 'lever' + 'value' for flag-based."
            )
        if "value" not in hypothesis:
            raise BuildError(
                f"Hypothesis {hypothesis.get('id', '?')} missing 'value' field. "
                f"Flag-based hypotheses require 'lever' + 'value'."
            )

        value = hypothesis["value"]
        if isinstance(value, dict):
            for lever_name, lever_value in value.items():
                if lever_name not in project_levers:
                    raise BuildError(f"Unknown lever '{lever_name}'")
                lever = project_levers[lever_name]
                if "flag" in lever and lever_value not in lever["space"]:
                    raise BuildError(f"Value {lever_value} not in space for '{lever_name}'")
            return build_command_multi_flag(project, hypothesis)
        else:
            lever_name = hypothesis["lever"]
            if lever_name not in project_levers:
                raise BuildError(f"Unknown lever '{lever_name}'")
            lever = project_levers[lever_name]
            if "flag" in lever and value not in lever["space"]:
                raise BuildError(f"Value {value} not in space for '{lever_name}'")
            return build_command_flag(project, hypothesis)

    elif btype == "script":
        return build_command_script(project, hypothesis)

    elif btype == "code":
        if provider is None:
            raise BuildError("build.type=code requires an AI provider")
        return build_command_code(project, hypothesis, project_dir, provider)

    else:
        raise BuildError(f"Unknown build type: {btype}")
