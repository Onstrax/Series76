"""FastAPI application factory and composition root (Spec 3, Req 1.8).

Builds the app, constructs the singletons (settings, async engine + session
factory connecting as ``app_writer``, the crypto service holding the KEK, and
the clock) on ``app.state``, installs the error handlers, and mounts the
routers. Light DI via FastAPI ``Depends`` only — no extra container.

The LLM provider and the Spec 4 agent runtime are faked (no real calls) and the
conversation/jobs/plans/trace routers are a later task; clean seams are left.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from series76_api.api.errors import install_error_handlers
from series76_api.api.routers import auth as auth_router
from series76_api.api.routers import health as health_router
from series76_api.infrastructure.clock import Clock, SystemClock
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.engine import (
    create_app_engine,
    create_session_factory,
)
from series76_api.infrastructure.settings import Settings, get_settings


def _build_crypto(settings: Settings) -> CryptoService:
    """Construct the crypto service from the configured KEK (never logged).

    Accepts a base64 KEK or, as a convenience for local dev, a raw 32-byte
    value; a missing/invalid KEK yields a service that fails closed on key ops.
    """

    kek_b64 = settings.resolve_kek_base64()
    service = CryptoService.from_base64_kek(kek_b64)
    if service.has_kek or not kek_b64:
        return service
    # The value was present but not valid base64-of-32-bytes; try raw UTF-8/32.
    raw = kek_b64.encode("utf-8")
    if len(raw) == 32:
        return CryptoService.from_base64_kek(base64.b64encode(raw).decode("ascii"))
    return service


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    crypto: CryptoService | None = None,
) -> FastAPI:
    """Create and wire the FastAPI application.

    Parameters are injectable so tests can supply a fake clock or an in-memory
    crypto service. When omitted, production singletons are built from the
    environment-backed :class:`Settings`.
    """

    resolved_settings = settings or get_settings()
    resolved_clock = clock or SystemClock()
    resolved_crypto = crypto or _build_crypto(resolved_settings)

    engine = create_app_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Engine is created eagerly above; dispose it on shutdown.
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="Series 76 Technical Assistant — Backend API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.clock = resolved_clock
    app.state.crypto = resolved_crypto
    app.state.engine = engine
    app.state.session_factory = session_factory

    install_error_handlers(app)
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    return app


__all__ = ["create_app"]
