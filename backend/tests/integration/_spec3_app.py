"""Helpers to build the Spec 3 FastAPI app against the live container.

Provides an in-process ASGI transport httpx client wired to a freshly migrated
database and a controllable :class:`FixedClock` so auth flows (lockout windows,
token expiry) are deterministic. A valid base64 KEK is generated per test app so
crypto key operations work end-to-end.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from series76_api.app import create_app
from series76_api.infrastructure.clock import FixedClock
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.settings import Settings


def build_settings(database_url: str) -> Settings:
    """Build Settings for the app bound to the container URL (with a real KEK)."""

    kek_b64 = base64.b64encode(os.urandom(32)).decode("ascii")
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
