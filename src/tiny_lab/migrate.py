"""Schema migration for project.yaml files.

Applies versioned migrations so that projects created with older versions
of Tiny-Lab stay compatible after package upgrades.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Individual migrations
# ---------------------------------------------------------------------------

def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """v1 → v2: add schema_version field (infra-only, no data changes)."""
    data["schema_version"] = 2
    return data


_MIGRATIONS: dict[int, Any] = {
    1: _migrate_v1_to_v2,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema_version(data: dict[str, Any]) -> int:
    """Return the schema version of a project config. Defaults to 1 if absent."""
    return data.get("schema_version", 1)


def needs_migration(data: dict[str, Any]) -> bool:
    """Check whether *data* requires migration."""
    return get_schema_version(data) < CURRENT_SCHEMA_VERSION


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Apply all pending migrations in order. Pure function (no I/O)."""
    version = get_schema_version(data)
    while version < CURRENT_SCHEMA_VERSION:
        fn = _MIGRATIONS[version]
        data = fn(data)
        version = get_schema_version(data)
        log.info("Migrated project schema to v%d", version)
    return data


def migrate_and_save(data: dict[str, Any], path: Path) -> dict[str, Any]:
    """Migrate *data* and write the result back to *path*."""
    old_version = get_schema_version(data)
    data = migrate(data)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))
    log.info("Saved migrated project.yaml (v%d → v%d) to %s", old_version, get_schema_version(data), path)
    return data
