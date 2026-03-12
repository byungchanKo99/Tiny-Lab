"""Tests for BUILD plugins."""
from __future__ import annotations

import pytest

from tiny_lab.build import build_command_flag, build_command_script, dispatch_build
from tiny_lab.errors import BuildError


def _project(build_type: str = "flag") -> dict:
    return {
        "name": "test",
        "baseline": {"command": "python train.py --lr 0.01 --epochs 10"},
        "metric": {"name": "loss"},
        "levers": {
            "lr": {"flag": "--lr", "baseline": "0.01", "space": ["0.01", "0.05", "0.1"]},
            "epochs": {"flag": "--epochs", "baseline": "10", "space": ["10", "20", "50"]},
        },
        "build": {"type": build_type},
    }


class TestBuildCommandFlag:
    def test_replaces_existing_flag(self):
        project = _project()
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
        result = build_command_flag(project, hyp)
        assert "--lr 0.05" in result
        assert "--lr 0.01" not in result

    def test_appends_when_flag_not_in_baseline(self):
        project = _project()
        project["baseline"]["command"] = "python train.py"
        project["levers"]["lr"]["baseline"] = "missing"
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
        result = build_command_flag(project, hyp)
        assert result.endswith("--lr 0.05")

    def test_preserves_other_flags(self):
        project = _project()
        hyp = {"id": "H-1", "lever": "lr", "value": "0.1", "description": "test"}
        result = build_command_flag(project, hyp)
        assert "--epochs 10" in result
        assert "--lr 0.1" in result


class TestBuildCommandScript:
    def test_uses_hypothesis_script(self):
        project = _project("script")
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test", "script": "run.sh --fast"}
        assert build_command_script(project, hyp) == "run.sh --fast"

    def test_uses_project_scripts_mapping(self):
        project = _project("script")
        project["build"]["scripts"] = {"lr:0.05": "run_lr05.sh"}
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
        assert build_command_script(project, hyp) == "run_lr05.sh"

    def test_raises_when_no_script(self):
        project = _project("script")
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
        with pytest.raises(BuildError):
            build_command_script(project, hyp)


class TestDispatchBuild:
    def test_flag_routing(self):
        project = _project("flag")
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
        result = dispatch_build(project, hyp, None)
        assert "--lr 0.05" in result

    def test_unknown_lever_raises_build_error(self):
        project = _project("flag")
        hyp = {"id": "H-1", "lever": "nonexistent", "value": "x", "description": "test"}
        with pytest.raises(BuildError, match="Unknown lever"):
            dispatch_build(project, hyp, None)

    def test_value_not_in_space_raises_build_error(self):
        project = _project("flag")
        hyp = {"id": "H-1", "lever": "lr", "value": "999", "description": "test"}
        with pytest.raises(BuildError, match="not in space"):
            dispatch_build(project, hyp, None)

    def test_unknown_build_type_raises(self):
        project = _project("unknown")
        hyp = {"id": "H-1", "lever": "lr", "value": "0.01", "description": "test"}
        with pytest.raises(BuildError, match="Unknown build type"):
            dispatch_build(project, hyp, None)

    def test_code_without_provider_raises(self):
        project = _project("code")
        hyp = {"id": "H-1", "lever": "lr", "value": "0.01", "description": "test"}
        with pytest.raises(BuildError, match="requires an AI provider"):
            dispatch_build(project, hyp, None, provider=None)

    def test_script_routing(self):
        project = _project("script")
        project["build"]["scripts"] = {"lr:0.05": "special.sh"}
        hyp = {"id": "H-1", "lever": "lr", "value": "0.05", "description": "test"}
        assert dispatch_build(project, hyp, None) == "special.sh"
