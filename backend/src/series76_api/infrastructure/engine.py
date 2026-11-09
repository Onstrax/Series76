"""Async SQLAlchemy engine/session provider for the backend (Spec 3).

The application connects as ``app_writer`` over an async psycopg driver
(``postgresql+psycopg://``). This mirrors the Spec 1 engine conventions but is
a distinct async engine with its own session factory controlled by the
Unit_Of_Work in the application layer (repositories never self-commit).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _to_async_url(url: str) -> str:
    """Normalize a URL to the async psycopg driver.

    Accepts a plain ``postgresql://`` or a sync ``postgresql+psycopg://`` URL
    and returns an async ``postgresql+psycopg://`` URL. psycopg 3 uses the same
    driver name for sync and async, selecting async via the async engine.
    """

    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url[len("postgresql+asyncpg://") :]
    return url


def create_app_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the async engine the application uses (connects as app_writer)."""

    return create_async_engine(_to_async_url(url), echo=echo, future=True, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to ``engine``.

    ``expire_on_commit=False`` so DTO assembly after commit does not trigger
    lazy reloads; the Use_Case controls the transaction boundary.
    """

    return async_sessionmaker(bind=engine, expire_on_commit=False)


__all__ = ["create_app_engine", "create_session_factory", "AsyncEngine", "AsyncSession"]
