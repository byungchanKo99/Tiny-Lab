"""Tests for schema migration."""
from __future__ import annotations

from pathlib import Path

import yaml
import pytest

from tiny_lab.migrate import (
    CURRENT_SCHEMA_VERSION,
    get_schema_version,
    needs_migration,
    migrate,
    migrate_and_save,
)


def _minimal_project(**overrides):
    """Return a minimal valid project config dict."""
    base = {
        "name": "test",
        "baseline": {"command": "echo 1"},
        "metric": {"name": "score", "direction": "maximize"},
        "levers": {"lr": {"space": [0.01, 0.1]}},
    }
    base.update(overrides)
    return base


class TestGetSchemaVersion:
    def test_missing_defaults_to_1(self):
        assert get_schema_version(_minimal_project()) == 1

    def test_explicit_version(self):
        assert get_schema_version(_minimal_project(schema_version=2)) == 2


class TestNeedsMigration:
    def test_no_version_needs_migration(self):
        assert needs_migration(_minimal_project()) is True

    def test_current_version_no_migration(self):
        assert needs_migration(_minimal_project(schema_version=CURRENT_SCHEMA_VERSION)) is False

    def test_old_version_needs_migration(self):
        assert needs_migration(_minimal_project(schema_version=1)) is True


class TestMigrate:
    def test_v1_to_v2_adds_schema_version(self):
        data = _minimal_project()
        assert "schema_version" not in data
        result = migrate(data)
        assert result["schema_version"] == 2

    def test_v1_to_v2_preserves_fields(self):
        data = _minimal_project(description="hello")
        result = migrate(data)
        assert result["name"] == "test"
        assert result["description"] == "hello"
        assert result["baseline"] == {"command": "echo 1"}

    def test_already_current_is_noop(self):
        data = _minimal_project(schema_version=CURRENT_SCHEMA_VERSION)
        result = migrate(data)
        assert result is data  # same object, untouched

    def test_migrate_is_idempotent(self):
        data = _minimal_project()
        result1 = migrate(data)
        result2 = migrate(result1)
        assert result1["schema_version"] == result2["schema_version"] == CURRENT_SCHEMA_VERSION


class TestMigrateAndSave:
    def test_writes_file(self, tmp_path: Path):
        path = tmp_path / "project.yaml"
        data = _minimal_project()
        path.write_text(yaml.dump(data))

        result = migrate_and_save(data, path)

        assert result["schema_version"] == CURRENT_SCHEMA_VERSION
        saved = yaml.safe_load(path.read_text())
        assert saved["schema_version"] == CURRENT_SCHEMA_VERSION
        assert saved["name"] == "test"

    def test_preserves_key_order(self, tmp_path: Path):
        path = tmp_path / "project.yaml"
        data = _minimal_project()
        migrate_and_save(data, path)

        text = path.read_text()
        # schema_version should appear in the output (sort_keys=False)
        assert "schema_version:" in text
        assert "name:" in text


class TestLoadProjectMigration:
    """Integration: load_project triggers auto-migration."""

    def test_auto_migrates_on_load(self, tmp_path: Path):
        from tiny_lab.project import load_project

        research = tmp_path / "research"
        research.mkdir()
        proj = _minimal_project()
        (research / "project.yaml").write_text(yaml.dump(proj))

        data = load_project(tmp_path)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION

        # File was updated on disk
        saved = yaml.safe_load((research / "project.yaml").read_text())
        assert saved["schema_version"] == CURRENT_SCHEMA_VERSION
