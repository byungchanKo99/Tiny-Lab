"""BUILD plugins — construct experiment commands from hypotheses."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .logging import log


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


def build_command_script(project: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    """Use a pre-defined script command from the hypothesis. Deterministic, no LLM."""
    script = hypothesis.get("script")
    if not script:
        lever_name = hypothesis["lever"]
        value = hypothesis["value"]
        scripts = project.get("build", {}).get("scripts", {})
        script = scripts.get(f"{lever_name}:{value}")
    if not script:
        raise ValueError(f"No script defined for hypothesis {hypothesis['id']}")
    return script


def build_command_code(
    project: dict[str, Any],
    hypothesis: dict[str, Any],
    project_dir: Path,
    run_claude_fn: Any,
) -> str:
    """LLM subagent modifies code based on the hypothesis. Non-deterministic."""
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

    log(f"BUILD[code]: calling subagent for {hypothesis['id']}")
    result = run_claude_fn(prompt, allowed_tools="Read,Write,Edit,Bash", cwd=str(project_dir))
    if result.returncode != 0:
        log(f"BUILD[code]: subagent failed (exit={result.returncode})")
        raise RuntimeError(f"Code modifier failed for {hypothesis['id']}")

    return project["baseline"]["command"].strip()


def dispatch_build(
    project: dict[str, Any],
    hypothesis: dict[str, Any],
    project_dir: Path,
    run_claude_fn: Any = None,
) -> str:
    """Route to the correct BUILD plugin based on project.yaml build.type."""
    build_type = project.get("build", {}).get("type", "flag")

    if build_type == "flag":
        lever_name = hypothesis["lever"]
        value = hypothesis["value"]
        if lever_name not in project["levers"]:
            raise ValueError(f"Unknown lever '{lever_name}'")
        lever = project["levers"][lever_name]
        if "flag" in lever and value not in lever["space"]:
            raise ValueError(f"Value {value} not in space for '{lever_name}'")
        return build_command_flag(project, hypothesis)

    elif build_type == "script":
        return build_command_script(project, hypothesis)

    elif build_type == "code":
        if run_claude_fn is None:
            raise RuntimeError("build.type=code requires Claude CLI")
        return build_command_code(project, hypothesis, project_dir, run_claude_fn)

    else:
        raise ValueError(f"Unknown build type: {build_type}")
