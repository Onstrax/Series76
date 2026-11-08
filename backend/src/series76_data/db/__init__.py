"""Database access layer for Spec 1.

Exposes the SQLAlchemy engine/session factory and the typed, parameterized
repository surface. No code path here executes free-form, model-generated SQL
(Req 7.4).
"""

from series76_data.db.engine import (
    create_db_engine,
    create_session_factory,
    resolve_database_url,
)
from series76_data.db.repository import CatalogRepository

__all__ = [
    "create_db_engine",
    "create_session_factory",
    "resolve_database_url",
    "CatalogRepository",
]
