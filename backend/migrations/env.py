"""Alembic migration environment for the Series 76 data slice (Spec 1).

The database URL is resolved at runtime from the environment:

1. ``SERIES76_MIGRATE_URL`` (preferred; integration tests set this to the
   ephemeral PostgreSQL container URL),
2. ``DATABASE_URL`` (fallback for ordinary deployments).

Migrations use SQLAlchemy 2.0 style (``Connection.execute`` via the Alembic
operation context). All objects are created inside the four logical schemas
(``catalog``, ``provenance``, ``ingestion``, ``publication``); the first
migration creates those schemas before any table references them.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This spec hand-writes every migration, so there is no autogenerate target
# metadata. The ORM in ``series76_data.models.orm`` mirrors the same tables for
# the repository layer but is deliberately not the migration source of truth.
target_metadata = None


def _resolve_url() -> str:
    """Resolve the DB URL from the environment (Alembic never hard-codes it)."""

    url = os.environ.get("SERIES76_MIGRATE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No database URL configured. Set SERIES76_MIGRATE_URL or DATABASE_URL "
            "before running Alembic migrations."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""

    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
