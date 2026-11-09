"""Composition root: FastAPI dependency providers (Spec 3, Req 1.8).

Light Dependency Injection via FastAPI ``Depends`` only — no extra DI
container. Singletons (settings, engine, session factory, crypto service,
clock) are created once per application and stored on ``app.state``; per-request
dependencies (the async session / Unit_Of_Work) are yielded here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from series76_api.application.agent_seam import AgentPort
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.settings import Settings


def get_settings_dep(request: Request) -> Settings:
    """Return the application :class:`Settings` from ``app.state``."""

    settings: Settings = request.app.state.settings
    return settings


def get_crypto(request: Request) -> CryptoService:
    """Return the shared :class:`CryptoService` from ``app.state``."""

    crypto: CryptoService = request.app.state.crypto
    return crypto


def get_clock(request: Request) -> Clock:
    """Return the shared :class:`Clock` from ``app.state``."""

    clock: Clock = request.app.state.clock
    return clock


def get_agent(request: Request) -> AgentPort:
    """Return the shared agent seam from ``app.state`` (faked in CI).

    The real Spec 4 agent plugs in here; in this spec and in CI the seam is a
    deterministic, zero-spend :class:`FakeAgent` so no provider is ever called.
    """

    agent: AgentPort = request.app.state.agent
    return agent


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a per-request async session (the Unit_Of_Work substrate).

    The session is opened per request and closed on completion. The Use_Case
    owns commit/rollback; this dependency never commits on its own so a
    repository cannot self-commit (Req 1.2).
    """

    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
CryptoDep = Annotated[CryptoService, Depends(get_crypto)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AgentDep = Annotated[AgentPort, Depends(get_agent)]


__all__ = [
    "get_settings_dep",
    "get_crypto",
    "get_clock",
    "get_agent",
    "get_session",
    "SettingsDep",
    "CryptoDep",
    "ClockDep",
    "SessionDep",
    "AgentDep",
]
