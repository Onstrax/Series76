"""Authentication router: register, login, refresh, logout, me (Spec 3, Req 2).

Maps the HTTP contracts onto the :class:`AuthService` and the authorization
guard. Register returns ``201``; login/refresh return a token pair; logout
revokes the current session; ``/me`` returns identity+role with no secret
material. Domain errors raised by the service are turned into the stable
``Error_Envelope`` by the installed exception handler.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from series76_api.api.dependencies import ClockDep, SessionDep, SettingsDep
from series76_api.api.dtos import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from series76_api.application.auth_service import AuthService
from series76_api.application.authorization import authenticate
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.auth import parse_bearer_token
from series76_api.domain.errors import AuthRequiredError
from series76_api.domain.models import TokenType
from series76_api.infrastructure.security import verify_token_secret

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> UserResponse:
    """Register a new account (role ``user``, assigned server-side)."""

    async with UnitOfWork(session) as uow:
        service = AuthService(uow, clock, settings)
        user = await service.register(body.email, body.password)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        email_verified=user.email_verified,
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> TokenPairResponse:
    """Authenticate and issue an access+refresh pair (generic failures)."""

    async with UnitOfWork(session) as uow:
        service = AuthService(uow, clock, settings)
        pair = await service.login(body.email, body.password)
    return TokenPairResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


async def _resolve_refresh_token_id(uow: UnitOfWork, presented_raw: str) -> uuid.UUID:
    """Resolve + verify a presented refresh token, returning its primary key.

    Verification mirrors access-token verification: parse, look up by public
    id, constant-time compare the SHA-256 verifier, and require a refresh type.
    A malformed/unknown/mismatched token raises a generic
    :class:`AuthRequiredError` so the two failure modes are indistinguishable.
    """

    presented = parse_bearer_token(presented_raw)
    token = await uow.tokens.get_by_public_id(presented.public_id)
    if token is None or token.token_type != TokenType.REFRESH:
        raise AuthRequiredError("Invalid token.")
    if not verify_token_secret(token.verifier, presented.secret):
        raise AuthRequiredError("Invalid token.")
    return token.id


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> TokenPairResponse:
    """Rotate a refresh token atomically (single-winner; reuse revokes family)."""

    async with UnitOfWork(session) as uow:
        token_id = await _resolve_refresh_token_id(uow, body.refresh_token)
        service = AuthService(uow, clock, settings)
        pair = await service.refresh(token_id)
    return TokenPairResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Revoke the current session's tokens (other sessions keep working)."""

    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = AuthService(uow, clock, settings)
        await service.logout(principal.auth_session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def me(
    session: SessionDep,
    clock: ClockDep,
    authorization: Annotated[str | None, Header()] = None,
) -> MeResponse:
    """Return the caller's identity and role — never any secret material."""

    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        user = await uow.users.get_by_id(principal.user_id)
        if user is None:
            raise AuthRequiredError("Authentication is required.")
        return MeResponse(id=str(user.id), email=user.email, role=user.role)


__all__ = ["router"]
