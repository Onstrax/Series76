"""Engine and session factory for the Spec 1 data layer.

The database URL is read from the ``DATABASE_URL`` environment variable (the
runtime surface), kept out of source. A caller may also pass an explicit URL
(used by tests pointing at the ephemeral PostgreSQL container).
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def resolve_database_url(url: str | None = None) -> str:
    """Return the DB URL: explicit argument, else ``DATABASE_URL``."""

    resolved = url or os.environ.get("DATABASE_URL")
    if not resolved:
        raise RuntimeError(
            "No database URL configured. Pass url=... or set DATABASE_URL."
        )
    return resolved


def create_db_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy 2.0 engine for the resolved URL."""

    return create_engine(resolve_database_url(url), echo=echo, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to ``engine`` (2.0 style, no autoflush surprises)."""

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)
