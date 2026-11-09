"""Authentication use cases: register, login, refresh, logout, me (Spec 3, Req 2).

Orchestrates the identity invariants: Argon2id password hashing, opaque tokens
with SHA-256 verifiers, server-side ``user`` role assignment, generic/
indistinguishable login failures with 5/15min lockout, atomic single-winner
refresh rotation with family-wide reuse detection, session-scoped logout, and a
secret-free ``/me``. The Use_Case owns the transaction boundary via the
Unit_Of_Work; repositories never self-commit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.auth import (
    LOGIN_FAILURE_WINDOW_SECONDS,
    LOGIN_MAX_FAILURES,
    canonicalize_email,
    is_locked_out,
    validate_email,
    validate_password,
)
from series76_api.domain.errors import (
    AuthRequiredError,
    ConflictError,
    RateLimitedError,
)
from series76_api.domain.models import TokenType, User, UserRole
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.orm import UserORM
from series76_api.infrastructure.security import (
    IssuedToken,
    generate_token,
    hash_password,
    verify_password,
)
from series76_api.infrastructure.settings import Settings

# A single generic login-failure message (never distinguishes the two cases).
_GENERIC_LOGIN_FAILURE = "Invalid email or password."
# A single generic registration-failure message (no account enumeration).
_GENERIC_REGISTER_CONFLICT = "Registration could not be completed."


@dataclass(frozen=True, slots=True)
class TokenPair:
    """A freshly issued access+refresh pair, presented to the client once."""

    access_token: str
    refresh_token: str
    auth_session_id: uuid.UUID


class AuthService:
    """Application service for the authentication endpoints."""

    def __init__(self, uow: UnitOfWork, clock: Clock, settings: Settings) -> None:
        self._uow = uow
        self._clock = clock
        self._settings = settings

    # --- registration -----------------------------------------------------

    async def register(self, email: str, password: str) -> User:
        """Register a new account with role ``user`` assigned server-side.

        Validates email/password; any client-supplied role is ignored (not even
        accepted as a parameter here — the api DTO drops it). A duplicate email
        raises a generic :class:`ConflictError` that does not reveal which
        account exists (Property 4). The created account is never a developer
        (Property 3).
        """

        canonical = validate_email(email)
        validate_password(password)

        existing = await self._uow.users.get_by_email(canonical)
        if existing is not None:
            # Surface generically; do not confirm the email is registered.
            raise ConflictError(_GENERIC_REGISTER_CONFLICT)

        verifier = hash_password(password)
        # Role is HARD-CODED to user server-side (never from input).
        orm = self._uow.users.add(
            email=canonical, password_verifier=verifier, role=UserRole.USER
        )
        await self._uow.commit()
        return _to_user(orm)

    # --- login ------------------------------------------------------------

    async def login(self, email: str, password: str) -> TokenPair:
        """Authenticate and issue a token pair, or fail generically.

        Unknown-email and wrong-password both raise the same generic
        :class:`AuthRequiredError` (Property 5). After
        :data:`LOGIN_MAX_FAILURES` failures within the window the attempt is
        rate-limited regardless of correctness.
        """

        canonical = canonicalize_email(email)
        now = self._clock.now()

        failures = await self._uow.login_attempts.recent_failure_count(
            canonical, now=now, window_seconds=LOGIN_FAILURE_WINDOW_SECONDS
        )
        if is_locked_out(failures):
            # Do not even check the password; lockout is independent of it.
            await self._uow.commit()
            raise RateLimitedError(
                "Too many attempts. Try again later.",
                retry_after_seconds=LOGIN_FAILURE_WINDOW_SECONDS,
            )

        user = await self._uow.users.get_by_email(canonical)
        # Always run a verify to keep timing closer between the two failure
        # modes; verify against the stored hash if present, else a decoy.
        ok = False
        if user is not None:
            ok = verify_password(user.password_verifier, password)

        if not ok or user is None:
            self._uow.login_attempts.record(email=canonical, succeeded=False)
            await self._uow.commit()
            raise AuthRequiredError(_GENERIC_LOGIN_FAILURE)

        self._uow.login_attempts.record(email=canonical, succeeded=True)
        pair = await self._issue_session_tokens(user.id)
        await self._uow.commit()
        return pair

    # --- refresh ----------------------------------------------------------

    async def refresh(self, presented_token_id: uuid.UUID) -> TokenPair:
        """Rotate a refresh token atomically; detect reuse and revoke family.

        ``presented_token_id`` is the resolved id of a verified refresh token
        (the api layer verifies the secret first). Rotation claims the row with
        a single-winner ``UPDATE`` (Property 6); presenting a token already
        rotated or revoked is reuse and revokes the whole family (Property 7).
        """

        token = await self._uow.tokens.get_by_id(presented_token_id)
        if token is None or token.token_type != TokenType.REFRESH:
            await self._uow.commit()
            raise AuthRequiredError("Invalid token.")

        now = self._clock.now()

        # Reuse detection: a previously rotated or revoked token is an attack
        # signal -> revoke the entire family and reject.
        if token.rotated_at is not None or token.revoked_at is not None:
            if token.refresh_family_id is not None:
                await self._uow.tokens.revoke_family(token.refresh_family_id, at=now)
            await self._uow.commit()
            raise AuthRequiredError("Invalid token.")

        if token.expires_at <= now:
            await self._uow.commit()
            raise AuthRequiredError("Invalid token.")

        # Single-winner claim.
        won = await self._uow.tokens.claim_rotation(token.id, at=now)
        if not won:
            await self._uow.commit()
            raise AuthRequiredError("Invalid token.")

        family_id = token.refresh_family_id or uuid.uuid4()
        pair = await self._issue_session_tokens(
            token.owner_id,
            auth_session_id=token.auth_session_id,
            refresh_family_id=family_id,
            prev_token_id=token.id,
        )
        await self._uow.commit()
        return pair

    # --- logout -----------------------------------------------------------

    async def logout(self, auth_session_id: uuid.UUID) -> None:
        """Revoke the current session's tokens, leaving other sessions intact.

        Revokes every not-yet-revoked token bound to ``auth_session_id`` and
        marks the auth session revoked (Property 8). Other sessions' tokens are
        untouched.
        """

        now = self._clock.now()
        await self._uow.tokens.revoke_session_tokens(auth_session_id, at=now)
        await self._uow.auth_sessions.revoke(auth_session_id, at=now)
        await self._uow.commit()

    # --- helpers ----------------------------------------------------------

    async def _issue_session_tokens(
        self,
        owner_id: uuid.UUID,
        *,
        auth_session_id: uuid.UUID | None = None,
        refresh_family_id: uuid.UUID | None = None,
        prev_token_id: uuid.UUID | None = None,
    ) -> TokenPair:
        now = self._clock.now()
        if auth_session_id is None:
            auth_session = self._uow.auth_sessions.add(owner_id=owner_id)
            await self._uow.flush()
            auth_session_id = auth_session.auth_session_id

        access: IssuedToken = generate_token()
        refresh: IssuedToken = generate_token()
        family = refresh_family_id or uuid.uuid4()

        self._uow.tokens.add(
            public_id=access.public_id,
            token_type=TokenType.ACCESS,
            verifier=access.verifier,
            owner_id=owner_id,
            auth_session_id=auth_session_id,
            expires_at=now + timedelta(seconds=self._settings.access_token_ttl_seconds),
        )
        self._uow.tokens.add(
            public_id=refresh.public_id,
            token_type=TokenType.REFRESH,
            verifier=refresh.verifier,
            owner_id=owner_id,
            auth_session_id=auth_session_id,
            expires_at=now
            + timedelta(seconds=self._settings.refresh_token_ttl_seconds),
            refresh_family_id=family,
            prev_token_id=prev_token_id,
        )
        return TokenPair(
            access_token=access.presented,
            refresh_token=refresh.presented,
            auth_session_id=auth_session_id,
        )


def _to_user(orm: UserORM) -> User:
    return User(
        id=orm.id,
        email=orm.email,
        password_verifier=orm.password_verifier,
        role=orm.role,
        email_verified=orm.email_verified,
        created_at=orm.created_at,
    )


__all__ = ["AuthService", "TokenPair", "LOGIN_MAX_FAILURES"]
