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


@pytest.fixture(scope="module")
def migrated_db_module(postgres_url: str) -> Iterator[Config]:
    """Module-scoped migrated schema for Hypothesis property suites.

    Migrating once per module (rather than per example) keeps the >=100-example
    property tests fast; tests isolate themselves with unique users/ids. The
    schema is downgraded to base at module teardown.
    """

    cfg = make_alembic_config(postgres_url)
    command.upgrade(cfg, "head")
    try:
        yield cfg
    finally:
        command.downgrade(cfg, "base")


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


# --- Spec 2: seeded fixture catalog for the domain-and-tools integration tests ---
from collections.abc import Callable  # noqa: E402

from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from .seed import SeededCatalog, seed_fixture_catalog  # noqa: E402


@pytest.fixture
def seeded_catalog(
    migrated_db: Config, postgres_url: str
) -> Iterator[tuple[SeededCatalog, Callable[[], Session], Engine]]:
    """Seed the fixture catalog into a migrated schema and yield read helpers.

    Yields a triple ``(seeded, session_factory, engine)``:

    * ``seeded`` — the :class:`SeededCatalog` identifiers;
    * ``session_factory`` — makes a fresh reader :class:`Session` (the domain
      adapter switches it to ``runtime_reader_role``);
    * ``engine`` — the underlying engine (for role-grant smoke checks).

    The seed is inserted as the container superuser, then committed so reader
    sessions observe it. ``migrated_db`` tears the schema back down to base.
    """

    engine = create_engine(postgres_url, future=True)
    factory = sessionmaker(
        bind=engine, class_=Session, expire_on_commit=False, future=True
    )
    with factory() as seed_session:
        seeded = seed_fixture_catalog(seed_session)
    try:
        yield seeded, factory, engine
    finally:
        engine.dispose()
