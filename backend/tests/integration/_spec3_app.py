"""Helpers to build the Spec 3 FastAPI app against the live container.

Provides an in-process ASGI transport httpx client wired to a freshly migrated
database and a controllable :class:`FixedClock` so auth flows (lockout windows,
token expiry) are deterministic. A valid base64 KEK is generated per test app so
crypto key operations work end-to-end.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from series76_api.app import create_app
from series76_api.infrastructure.clock import FixedClock
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.engine import _to_async_url
from series76_api.infrastructure.settings import Settings


def create_test_engine(database_url: str) -> AsyncEngine:
    """Create a NullPool async engine for tests (no pooled connections).

    NullPool closes each connection on return so a 100-example Hypothesis suite
    that opens short-lived engines does not exhaust the test database's
    ``max_connections`` limit.
    """

    return create_async_engine(_to_async_url(database_url), poolclass=NullPool)


def create_test_session_factory(
    database_url: str,
) -> tuple[async_sessionmaker, AsyncEngine]:  # type: ignore[type-arg]
    """Create a NullPool-backed session factory + its engine for tests.

    Returns ``(factory, engine)`` so the caller can dispose the engine.
    """

    engine = create_test_engine(database_url)
    return (
        async_sessionmaker(bind=engine, expire_on_commit=False),
        engine,
    )


def build_settings(database_url: str) -> Settings:
    """Build Settings for the app bound to the container URL (with a real KEK).

    The KEK is a FIXED 32-byte test key (not random per call) so a ciphertext
    written by one app instance can be decrypted by another — modeling the
    external KEK that stays stable across API/worker restarts. A random-per-call
    KEK would (correctly) fail closed across instances, which is a test-harness
    artifact, not the behavior under test.
    """

    kek_b64 = base64.b64encode(b"series76-test-kek-32-bytes!!_ok_").decode("ascii")
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        DATABASE_URL=database_url,
        ENCRYPTION_KEK=kek_b64,
    )


@asynccontextmanager
async def spec3_client(
    database_url: str, *, clock: FixedClock | None = None
) -> AsyncIterator[tuple[AsyncClient, FastAPI, FixedClock]]:
    """Yield an (async client, app, clock) triple for the migrated database."""

    fixed_clock = clock or FixedClock(datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC))
    settings = build_settings(database_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    app = create_app(settings, clock=fixed_clock, crypto=crypto)
    transport = ASGITransport(app=app)
    # Drive the lifespan so engine setup/teardown runs, alongside the client.
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client, app, fixed_clock
