"""Tests for the metadata-driven pipeline engine."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from tiny_lab.pipeline import run_pipeline, StepResult, PipelineResult


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    research = tmp_path / "research"
    research.mkdir()
    return tmp_path


@pytest.fixture()
def mock_provider():
    provider = MagicMock()
    provider.name = "mock"
    return provider


def _write_pipeline(tmp_path: Path, steps: list[dict]) -> Path:
    """Write a pipeline YAML and associated prompt/schema files."""
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir(exist_ok=True)
    prompts_dir = pipeline_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    schemas_dir = pipeline_dir / "schemas"
    schemas_dir.mkdir(exist_ok=True)

    for step in steps:
        # Create prompt template
        prompt_path = pipeline_dir / step["prompt_template"]
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(step.pop("_prompt_content", "Do something for {project_name}"))

        # Create schema
        schema_path = pipeline_dir / step["output_schema"]
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(step.pop("_schema_content", {"type": "object"})))

    pipeline_path = pipeline_dir / "pipeline.yaml"
    pipeline_path.write_text(yaml.dump({"name": "test", "steps": steps}))
    return pipeline_path


class TestRunPipeline:
    def test_single_step_success(self, project_dir, mock_provider):
        """Single step pipeline runs successfully."""
        output_data = {"result": "ok"}

        def mock_run_structured(prompt, *, output_path=None, schema_path=None, tools=None, cwd=None):
            if output_path:
                Path(output_path).write_text(json.dumps(output_data))
            return subprocess.CompletedProcess(args="", returncode=0, stdout="done", stderr="")

        mock_provider.run_structured = mock_run_structured

        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step1", "prompt_template": "prompts/s1.md", "output_schema": "schemas/s1.json",
             "_prompt_content": "Hello {project_name}"},
        ])

        result = run_pipeline(pipeline_path, {"project_name": "test"}, mock_provider, project_dir)

        assert result.success
        assert "step1" in result.steps
        assert result.steps["step1"].output == output_data

    def test_multi_step_with_requires(self, project_dir, mock_provider):
        """Steps receive output from required previous steps."""
        captured_prompts = []

        def mock_run_structured(prompt, *, output_path=None, schema_path=None, tools=None, cwd=None):
            captured_prompts.append(prompt)
            step_id = Path(output_path).stem.replace(".step_", "")
            if "step1" in str(output_path):
                data = {"value": 42}
            else:
                data = {"combined": True}
            Path(output_path).write_text(json.dumps(data))
            return subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")

        mock_provider.run_structured = mock_run_structured

        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step1", "prompt_template": "prompts/s1.md", "output_schema": "schemas/s1.json",
             "_prompt_content": "First step"},
            {"id": "step2", "prompt_template": "prompts/s2.md", "output_schema": "schemas/s2.json",
             "requires": ["step1"],
             "_prompt_content": "Second step got value={step1_value}"},
        ])

        result = run_pipeline(pipeline_path, {}, mock_provider, project_dir)

        assert result.success
        assert len(result.steps) == 2
        # Second prompt should have received step1's output via flattened context
        assert "value=42" in captured_prompts[1]

    def test_fail_fast_on_error(self, project_dir, mock_provider):
        """Pipeline stops on first step failure."""
        call_count = 0

        def mock_run_structured(prompt, *, output_path=None, schema_path=None, tools=None, cwd=None):
            nonlocal call_count
            call_count += 1
            return subprocess.CompletedProcess(args="", returncode=1, stdout="", stderr="error")

        mock_provider.run_structured = mock_run_structured

        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step1", "prompt_template": "prompts/s1.md", "output_schema": "schemas/s1.json"},
            {"id": "step2", "prompt_template": "prompts/s2.md", "output_schema": "schemas/s2.json",
             "requires": ["step1"]},
        ])

        result = run_pipeline(pipeline_path, {}, mock_provider, project_dir)

        assert not result.success
        assert call_count == 1  # step2 was never called
        assert "step1" in result.steps
        assert "step2" not in result.steps

    def test_missing_require_fails(self, project_dir, mock_provider):
        """Step with unmet requires fails immediately."""
        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step2", "prompt_template": "prompts/s2.md", "output_schema": "schemas/s2.json",
             "requires": ["step1"]},  # step1 doesn't exist
        ])

        result = run_pipeline(pipeline_path, {}, mock_provider, project_dir)
        assert not result.success

    def test_context_passthrough(self, project_dir, mock_provider):
        """Initial context is available in prompt templates."""
        captured_prompt = []

        def mock_run_structured(prompt, *, output_path=None, schema_path=None, tools=None, cwd=None):
            captured_prompt.append(prompt)
            Path(output_path).write_text("{}")
            return subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        mock_provider.run_structured = mock_run_structured

        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step1", "prompt_template": "prompts/s1.md", "output_schema": "schemas/s1.json",
             "_prompt_content": "Project: {my_var}"},
        ])

        run_pipeline(pipeline_path, {"my_var": "hello"}, mock_provider, project_dir)
        assert "hello" in captured_prompt[0]

    def test_tools_passed_to_provider(self, project_dir, mock_provider):
        """Step tools are passed to provider.run_structured."""
        captured_tools = []

        def mock_run_structured(prompt, *, output_path=None, schema_path=None, tools=None, cwd=None):
            captured_tools.append(tools)
            Path(output_path).write_text("{}")
            return subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        mock_provider.run_structured = mock_run_structured

        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step1", "prompt_template": "prompts/s1.md", "output_schema": "schemas/s1.json",
             "tools": ["WebSearch", "Read"]},
        ])

        run_pipeline(pipeline_path, {}, mock_provider, project_dir)
        assert captured_tools[0] == ["WebSearch", "Read"]

    def test_invalid_json_output_continues(self, project_dir, mock_provider):
        """Step with invalid JSON output gets empty dict, doesn't crash."""
        def mock_run_structured(prompt, *, output_path=None, schema_path=None, tools=None, cwd=None):
            Path(output_path).write_text("not valid json")
            return subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        mock_provider.run_structured = mock_run_structured

        pipeline_path = _write_pipeline(project_dir, [
            {"id": "step1", "prompt_template": "prompts/s1.md", "output_schema": "schemas/s1.json"},
        ])

        result = run_pipeline(pipeline_path, {}, mock_provider, project_dir)
        assert result.success
        assert result.steps["step1"].output == {}
