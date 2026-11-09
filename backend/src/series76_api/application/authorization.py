"""Authorization / ownership guard (Spec 3, Req 3).

Resolves the authoritative ``Owner_User_Id`` from the validated session token
only — never from a body/query/header. Cross-user access returns an
indistinguishable ``404`` leaking no field/metadata/count (Property 10). The
ownership check completes *before* any decryption (Property 42) and *before*
any model or tool dispatch (Property 43); the ``developer`` role is a Debug
capability over its OWN resources only, denied with the same ``404`` for other
owners.
"""

from __future__ import annotations

import uuid
from typing import Protocol, TypeVar

from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.auth import parse_bearer_token
from series76_api.domain.errors import AuthRequiredError, NotFoundError
from series76_api.domain.models import AuthenticatedPrincipal, TokenType, UserRole
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.security import verify_token_secret


class OwnedResource(Protocol):
    """Anything with an authoritative ``owner_id`` (conversation, job, plan...).

    Declared as a plain attribute (not a ``property``) so SQLAlchemy ORM models,
    whose ``owner_id`` is a ``Mapped[UUID]`` descriptor, satisfy this Protocol
    structurally.
    """

    owner_id: uuid.UUID


# A resource the guard authorizes. Bound to ``object`` (not ``OwnedResource``)
# because SQLAlchemy ORM instances expose ``owner_id`` as a ``Mapped[UUID]``
# descriptor that the stock mypy config does not narrow to ``uuid.UUID``; the
# guard reads the attribute defensively. The concrete type is preserved so
# callers get back the exact ORM model they passed in.
ResourceT = TypeVar("ResourceT")


async def authenticate(
    uow: UnitOfWork, clock: Clock, authorization_header: str | None
) -> AuthenticatedPrincipal:
    """Resolve the authenticated principal from a Bearer access token.

    Parses ``<public_id>.<secret>``, looks up the verifier by public id,
    constant-time compares the SHA-256 verifier, and checks the token is an
    access token, not revoked, not expired, and its session not revoked.
    Raises :class:`AuthRequiredError` on any failure (no distinction between
    causes). The resolved ``user_id`` is the sole source of ``Owner_User_Id``.
    """

    if not authorization_header:
        raise AuthRequiredError("Authentication is required.")

    presented = parse_bearer_token(authorization_header)
    token = await uow.tokens.get_by_public_id(presented.public_id)
    if token is None or token.token_type != TokenType.ACCESS:
        raise AuthRequiredError("Authentication is required.")
    if not verify_token_secret(token.verifier, presented.secret):
        raise AuthRequiredError("Authentication is required.")

    now = clock.now()
    if token.revoked_at is not None or token.expires_at <= now:
        raise AuthRequiredError("Authentication is required.")

    auth_session = await uow.auth_sessions.get(token.auth_session_id)
    if auth_session is None or auth_session.revoked_at is not None:
        raise AuthRequiredError("Authentication is required.")

    user = await uow.users.get_by_id(token.owner_id)
    if user is None:
        raise AuthRequiredError("Authentication is required.")

    return AuthenticatedPrincipal(
        user_id=user.id,
        role=user.role,
        auth_session_id=token.auth_session_id,
    )


def resolve_owner_id(principal: AuthenticatedPrincipal) -> uuid.UUID:
    """Return the authoritative owner id — always from the session principal.

    This is the *only* sanctioned source of ``Owner_User_Id``; any owner id in
    a request body/query/header is ignored by construction (it is never read).
    """

    return principal.user_id


def authorize_ownership(
    principal: AuthenticatedPrincipal,
    resource: ResourceT | None,
) -> ResourceT:
    """Authorize that ``resource`` is owned by the session principal.

    Returns the resource when the stored owner equals the session owner.
    Raises an indistinguishable :class:`NotFoundError` when the resource does
    not exist OR is owned by another user — including a ``developer`` accessing
    another owner's resource (``developer`` is not a superuser). The two cases
    (nonexistent vs not-owned) raise the identical error with no attributes, so
    existence is never confirmed (Property 10).

    This comparison completes before any decryption (Property 42) and before
    any model/tool dispatch (Property 43): callers must invoke this guard and
    let it raise before touching ciphertext or dispatching work.
    """

    owner = getattr(resource, "owner_id", None) if resource is not None else None
    if resource is None or owner != resolve_owner_id(principal):
        raise NotFoundError("Resource not found.")
    return resource


def is_developer(principal: AuthenticatedPrincipal) -> bool:
    """Return whether the principal holds the ``developer`` role.

    A ``developer`` gains Debug capability over its OWN resources only; it is
    never a superuser, so ownership is still enforced by
    :func:`authorize_ownership`.
    """

    return principal.role == UserRole.DEVELOPER


__all__ = [
    "OwnedResource",
    "authenticate",
    "resolve_owner_id",
    "authorize_ownership",
    "is_developer",
]
