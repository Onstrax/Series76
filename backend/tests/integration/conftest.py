"""Integration-test helpers: run Alembic against the real PostgreSQL container.

The ``postgres_url`` session fixture (from the top-level conftest) provides a
live ``postgres:15-alpine`` Testcontainer URL. Here we add helpers to drive the
Alembic migrations programmatically (via the Alembic API) with
``SERIES76_MIGRATE_URL`` pointed at that URL, plus a module-scoped fixture that
upgrades the schema to ``head`` so schema/constraint assertions run against a
fully migrated database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# backend/ root (two levels up from tests/integration/conftest.py).
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def make_alembic_config(database_url: str) -> Config:
    """Build an Alembic :class:`Config` bound to ``database_url`` via env var."""

    os.environ["SERIES76_MIGRATE_URL"] = database_url
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


@pytest.fixture
def alembic_config(postgres_url: str) -> Config:
    """An Alembic config pointed at the live container (function-scoped)."""

    return make_alembic_config(postgres_url)


@pytest.fixture
def migrated_db(alembic_config: Config) -> Iterator[Config]:
    """Upgrade to head for the test, then downgrade to base to leave a clean DB.

    Function-scoped so each test that uses it gets a freshly migrated schema and
    the teardown verifies that ``downgrade base`` reverts cleanly.
    """

    command.upgrade(alembic_config, "head")
    try:
        yield alembic_config
    finally:
        command.downgrade(alembic_config, "base")
