"""Async SQLAlchemy repositories for the Spec 3 identity path (infrastructure).

Typed repositories over the ORM models, connecting as ``app_writer``. They
never commit on their own — the Use_Case controls the transaction boundary via
the Unit_Of_Work (Req 1.2). Each method issues parameterized, typed SQL only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from series76_api.domain.models import TokenType, UserRole
from series76_api.infrastructure.orm import (
    AuthSessionORM,
    LoginAttemptORM,
    TokenVerifierORM,
    UserORM,
)


class UserRepository:
    """Persistence for ``identity.users``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, canonical_email: str) -> UserORM | None:
        """Return the user with this canonical email, or ``None``."""

        stmt = select(UserORM).where(UserORM.email == canonical_email)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> UserORM | None:
        """Return the user with this id, or ``None``."""

        return await self._session.get(UserORM, user_id)

    def add(
        self,
        *,
        email: str,
        password_verifier: str,
        role: UserRole,
    ) -> UserORM:
        """Stage a new user for insertion (role is assigned by the Use_Case)."""

        user = UserORM(
            id=uuid.uuid4(),
            email=email,
            password_verifier=password_verifier,
            role=role,
            email_verified=False,
        )
        self._session.add(user)
        return user


class AuthSessionRepository:
    """Persistence for ``identity.auth_sessions``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self, *, owner_id: uuid.UUID, device_label: str | None = None
    ) -> AuthSessionORM:
        """Stage a new auth session for insertion."""

        auth_session = AuthSessionORM(
            auth_session_id=uuid.uuid4(),
            owner_id=owner_id,
            device_label=device_label,
        )
        self._session.add(auth_session)
        return auth_session

    async def get(self, auth_session_id: uuid.UUID) -> AuthSessionORM | None:
        """Return the auth session by id, or ``None``."""

        return await self._session.get(AuthSessionORM, auth_session_id)

    async def revoke(self, auth_session_id: uuid.UUID, *, at: datetime) -> None:
        """Mark an auth session revoked (staged, not committed)."""

        stmt = (
            update(AuthSessionORM)
            .where(
                AuthSessionORM.auth_session_id == auth_session_id,
                AuthSessionORM.revoked_at.is_(None),
            )
            .values(revoked_at=at)
        )
        await self._session.execute(stmt)


class TokenVerifierRepository:
    """Persistence for ``identity.token_verifiers`` (only SHA-256 verifiers)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        public_id: str,
        token_type: TokenType,
        verifier: str,
        owner_id: uuid.UUID,
        auth_session_id: uuid.UUID,
        expires_at: datetime,
        refresh_family_id: uuid.UUID | None = None,
        prev_token_id: uuid.UUID | None = None,
    ) -> TokenVerifierORM:
        """Stage a new token verifier row for insertion."""

        row = TokenVerifierORM(
            id=uuid.uuid4(),
            public_id=public_id,
            token_type=token_type,
            verifier=verifier,
            owner_id=owner_id,
            auth_session_id=auth_session_id,
            expires_at=expires_at,
            refresh_family_id=refresh_family_id,
            prev_token_id=prev_token_id,
        )
        self._session.add(row)
        return row

    async def get_by_public_id(self, public_id: str) -> TokenVerifierORM | None:
        """Return the token verifier by its public id, or ``None``."""

        stmt = select(TokenVerifierORM).where(TokenVerifierORM.public_id == public_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, token_id: uuid.UUID) -> TokenVerifierORM | None:
        """Return the token verifier by its primary key, or ``None``."""

        return await self._session.get(TokenVerifierORM, token_id)

    async def claim_rotation(self, token_id: uuid.UUID, *, at: datetime) -> bool:
        """Atomically claim a refresh token for rotation (single-winner).

        Issues ``UPDATE ... WHERE rotated_at IS NULL AND revoked_at IS NULL
        RETURNING`` so that under concurrency exactly one presentation sets
        ``rotated_at`` and wins; every other concurrent presentation of the
        same token affects zero rows and loses (Property 6).
        """

        stmt = (
            update(TokenVerifierORM)
            .where(
                TokenVerifierORM.id == token_id,
                TokenVerifierORM.rotated_at.is_(None),
                TokenVerifierORM.revoked_at.is_(None),
            )
            .values(rotated_at=at)
            .returning(TokenVerifierORM.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def revoke_family(
        self, refresh_family_id: uuid.UUID, *, at: datetime
    ) -> None:
        """Revoke every not-yet-revoked token in a refresh family (Property 7)."""

        stmt = (
            update(TokenVerifierORM)
            .where(
                TokenVerifierORM.refresh_family_id == refresh_family_id,
                TokenVerifierORM.revoked_at.is_(None),
            )
            .values(revoked_at=at)
        )
        await self._session.execute(stmt)

    async def revoke_session_tokens(
        self, auth_session_id: uuid.UUID, *, at: datetime
    ) -> None:
        """Revoke all not-yet-revoked tokens for one auth session (logout)."""

        stmt = (
            update(TokenVerifierORM)
            .where(
                TokenVerifierORM.auth_session_id == auth_session_id,
                TokenVerifierORM.revoked_at.is_(None),
            )
            .values(revoked_at=at)
        )
        await self._session.execute(stmt)


class LoginAttemptRepository:
    """Persistence for ``identity.login_attempts`` (lockout ledger)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def record(self, *, email: str, succeeded: bool) -> None:
        """Stage a login-attempt record for insertion."""

        self._session.add(
            LoginAttemptORM(id=uuid.uuid4(), email=email, succeeded=succeeded)
        )

    async def recent_failure_count(
        self, email: str, *, now: datetime, window_seconds: int
    ) -> int:
        """Count failed attempts for ``email`` within the trailing window.

        Counts failures since the most recent success (consecutive failures)
        bounded by the time window — the basis for the 5/15min lockout.
        """

        since = now - timedelta(seconds=window_seconds)
        last_success_stmt = select(func.max(LoginAttemptORM.at)).where(
            LoginAttemptORM.email == email,
            LoginAttemptORM.succeeded.is_(True),
            LoginAttemptORM.at >= since,
        )
        last_success = (
            await self._session.execute(last_success_stmt)
        ).scalar_one_or_none()
        lower_bound = max(since, last_success) if last_success is not None else since
        count_stmt = (
            select(func.count())
            .select_from(LoginAttemptORM)
            .where(
                LoginAttemptORM.email == email,
                LoginAttemptORM.succeeded.is_(False),
                LoginAttemptORM.at >= lower_bound,
            )
        )
        return int((await self._session.execute(count_stmt)).scalar_one())


__all__ = [
    "UserRepository",
    "AuthSessionRepository",
    "TokenVerifierRepository",
    "LoginAttemptRepository",
]
