"""Metadata-driven pipeline engine.

Executes a sequence of LLM steps defined in YAML. Each step has a prompt
template, output schema, and dependency on previous steps. The engine
is generic — it doesn't know what the steps do, only how to run them
in order and pass outputs between them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .logging import log
from .providers.base import AIProvider


@dataclass
class StepResult:
    """Result from a single pipeline step."""

    step_id: str
    output: dict[str, Any]
    raw_stdout: str = ""
    returncode: int = 0


@dataclass
class PipelineResult:
    """Result from running a full pipeline."""

    steps: dict[str, StepResult] = field(default_factory=dict)
    success: bool = True


def _resolve_template(base_dir: Path, template_path: str) -> str:
    """Load a prompt template file relative to the pipeline base directory."""
    path = base_dir / template_path
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text()


def _resolve_schema(base_dir: Path, schema_path: str) -> Path:
    """Resolve schema file path relative to the pipeline base directory."""
    path = base_dir / schema_path
    if not path.exists():
        raise FileNotFoundError(f"Output schema not found: {path}")
    return path


def _format_prompt(template: str, context: dict[str, Any]) -> str:
    """Format a prompt template with context, tolerating missing keys."""
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return f"{{{key}}}"

    return template.format_map(SafeDict(context))


def _flatten_context(context: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested context for template formatting.

    Converts {"analyze": {"state": "EXPLORING"}} into
    {"analyze": ..., "analyze.state": "EXPLORING", "analyze_state": "EXPLORING"}
    so templates can use {analyze.state} or {analyze_state}.
    """
    flat: dict[str, Any] = {}
    for key, value in context.items():
        flat[key] = value
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[f"{key}.{sub_key}"] = sub_value
                flat[f"{key}_{sub_key}"] = sub_value
    return flat


def run_pipeline(
    pipeline_path: Path,
    context: dict[str, Any],
    provider: AIProvider,
    project_dir: Path,
) -> PipelineResult:
    """Execute a metadata-driven pipeline.

    Args:
        pipeline_path: Path to the pipeline YAML definition.
        context: Initial context dict (project vars, history, etc.).
        provider: AI provider to execute each step.
        project_dir: Project root directory.

    Returns:
        PipelineResult with step outputs and success status.
    """
    config = yaml.safe_load(pipeline_path.read_text())
    base_dir = pipeline_path.parent
    steps = config.get("steps", [])
    pipeline_name = config.get("name", "unnamed")

    result = PipelineResult()
    step_context = dict(context)

    log(f"PIPELINE[{pipeline_name}]: starting ({len(steps)} steps)")

    for i, step in enumerate(steps):
        step_id = step["id"]
        requires = step.get("requires", [])

        # Validate requires
        for req in requires:
            if req not in result.steps:
                log(f"PIPELINE[{pipeline_name}]: step '{step_id}' requires '{req}' which hasn't run")
                result.success = False
                return result

        # Inject previous step outputs into context
        for req in requires:
            step_context[req] = result.steps[req].output

        # Load and format prompt
        template = _resolve_template(base_dir, step["prompt_template"])
        flat_ctx = _flatten_context(step_context)
        prompt = _format_prompt(template, flat_ctx)

        # Resolve schema and output paths
        output_path = project_dir / "research" / f".step_{step_id}.json"
        schema_path = _resolve_schema(base_dir, step["output_schema"])

        log(f"PIPELINE[{pipeline_name}]: step {i+1}/{len(steps)} '{step_id}'")

        # Execute via provider
        try:
            proc = provider.run_structured(
                prompt,
                output_path=output_path,
                schema_path=schema_path,
                tools=step.get("tools"),
                cwd=str(project_dir),
            )
        except Exception as e:
            log(f"PIPELINE[{pipeline_name}]: step '{step_id}' raised {e}")
            result.steps[step_id] = StepResult(step_id=step_id, output={}, returncode=1)
            result.success = False
            return result

        # Parse output
        output: dict[str, Any] = {}
        if output_path.exists():
            try:
                output = json.loads(output_path.read_text())
            except json.JSONDecodeError:
                log(f"PIPELINE[{pipeline_name}]: step '{step_id}' output is not valid JSON")

        result.steps[step_id] = StepResult(
            step_id=step_id,
            output=output,
            raw_stdout=proc.stdout or "",
            returncode=proc.returncode,
        )

        # Fail-fast on non-zero exit
        if proc.returncode != 0:
            log(f"PIPELINE[{pipeline_name}]: step '{step_id}' failed (exit={proc.returncode})")
            result.success = False
            return result

        log(f"PIPELINE[{pipeline_name}]: step '{step_id}' done")

    log(f"PIPELINE[{pipeline_name}]: completed ({len(result.steps)} steps)")
    return result
