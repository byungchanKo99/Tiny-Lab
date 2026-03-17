"""Tests for queue loading with corrupt YAML recovery."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tiny_lab.queue import load_queue, save_queue


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    research = tmp_path / "research"
    research.mkdir()
    return tmp_path


class TestLoadQueueCorruptYAML:
    def test_corrupt_yaml_recovers_from_backup(self, project_dir: Path):
        """If YAML is corrupt, load_queue restores from .bak backup."""
        queue_path = project_dir / "research" / "hypothesis_queue.yaml"

        # Save a valid queue (creates .bak)
        save_queue(project_dir, [{"id": "H-1", "status": "pending", "lever": "lr", "value": "0.1", "description": "t"}])
        # Save again so .bak has the H-1 entry
        save_queue(project_dir, [{"id": "H-1", "status": "done", "lever": "lr", "value": "0.1", "description": "t"}])

        # Corrupt the file
        queue_path.write_text("hypotheses:\n  - reasoning: bad yaml: colon: breaks\n    - invalid")

        result = load_queue(project_dir)
        # Should recover from backup (which has H-1 as pending)
        assert len(result) == 1
        assert result[0]["id"] == "H-1"

    def test_corrupt_yaml_no_backup_returns_empty(self, project_dir: Path):
        """If YAML is corrupt and no backup, returns empty list."""
        queue_path = project_dir / "research" / "hypothesis_queue.yaml"
        queue_path.write_text("hypotheses:\n  - reasoning: bad: yaml\n    - invalid")

        result = load_queue(project_dir)
        assert result == []

    def test_normal_load_still_works(self, project_dir: Path):
        """Normal YAML loads correctly."""
        save_queue(project_dir, [
            {"id": "H-1", "status": "pending", "lever": "lr", "value": "0.1", "description": "test"},
        ])
        result = load_queue(project_dir)
        assert len(result) == 1
        assert result[0]["id"] == "H-1"

    def test_save_creates_backup(self, project_dir: Path):
        """save_queue creates .bak before overwriting."""
        queue_path = project_dir / "research" / "hypothesis_queue.yaml"
        backup_path = queue_path.with_suffix(".yaml.bak")

        save_queue(project_dir, [{"id": "H-1", "status": "pending", "lever": "lr", "value": "0.1", "description": "t"}])
        assert not backup_path.exists()  # first save, no backup

        save_queue(project_dir, [{"id": "H-2", "status": "pending", "lever": "lr", "value": "0.2", "description": "t"}])
        assert backup_path.exists()  # second save creates backup of first

        backup_data = yaml.safe_load(backup_path.read_text())
        assert backup_data["hypotheses"][0]["id"] == "H-1"  # backup has first version
