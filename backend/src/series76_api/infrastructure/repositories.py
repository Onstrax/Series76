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


# ============================================================================
# Half B: conversation / jobs / plans / crypto-key / trace repositories.
# ============================================================================

from sqlalchemy import and_, delete  # noqa: E402

from series76_api.domain.models import JobState  # noqa: E402
from series76_api.infrastructure.orm import (  # noqa: E402
    ConversationORM,
    DomainStateORM,
    EncryptedCheckpointORM,
    JobAttemptORM,
    KeyMetadataORM,
    MessageORM,
    PlanORM,
    ToolTraceORM,
    TurnJobORM,
)

# Terminal job states (no further processing / not cancelable).
_TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
)
# Cancelable job states (Property 19).
CANCELABLE_JOB_STATES: frozenset[JobState] = frozenset(
    {
        JobState.QUEUED,
        JobState.RUNNING,
        JobState.NEEDS_CLARIFICATION,
        JobState.AWAITING_CONFIRMATION,
    }
)
# Non-terminal states that require a Retry-After header when polled (Property 20).
NON_TERMINAL_JOB_STATES: frozenset[JobState] = CANCELABLE_JOB_STATES


class ConversationRepository:
    """Persistence for ``conversation.conversations`` (owner-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        title_ciphertext: bytes | None = None,
        catalog_edition_id: uuid.UUID | None = None,
    ) -> ConversationORM:
        """Stage a new conversation for insertion (caller-owned)."""

        conv = ConversationORM(
            session_id=session_id,
            owner_id=owner_id,
            title_ciphertext=title_ciphertext,
            catalog_edition_id=catalog_edition_id,
        )
        self._session.add(conv)
        return conv

    async def get(self, session_id: uuid.UUID) -> ConversationORM | None:
        """Return a conversation by id, or ``None`` (no owner filter here).

        Ownership is enforced by the authorization guard against the returned
        ``owner_id`` so a not-owned conversation is an indistinguishable 404.
        """

        return await self._session.get(ConversationORM, session_id)

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int = 1000
    ) -> list[ConversationORM]:
        """Return the owner's non-deleted conversations, newest first.

        Only the caller's own rows are ever fetched (owner-scoped WHERE), so
        decryption of titles happens only after authorization (Property 35).
        """

        stmt = (
            select(ConversationORM)
            .where(
                ConversationORM.owner_id == owner_id,
                ConversationORM.deleted_at.is_(None),
            )
            .order_by(ConversationORM.created_at.desc(), ConversationORM.session_id)
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def set_title(
        self, session_id: uuid.UUID, *, title_ciphertext: bytes, at: datetime
    ) -> None:
        """Persist a new encrypted title and bump ``updated_at`` (staged)."""

        stmt = (
            update(ConversationORM)
            .where(ConversationORM.session_id == session_id)
            .values(title_ciphertext=title_ciphertext, updated_at=at)
        )
        await self._session.execute(stmt)

    async def touch(self, session_id: uuid.UUID, *, at: datetime) -> None:
        """Bump ``updated_at`` for ordering (staged)."""

        stmt = (
            update(ConversationORM)
            .where(ConversationORM.session_id == session_id)
            .values(updated_at=at)
        )
        await self._session.execute(stmt)

    async def tombstone(
        self, session_id: uuid.UUID, *, fence: int, at: datetime
    ) -> None:
        """Mark a conversation deleted and record the tombstone fence (staged)."""

        stmt = (
            update(ConversationORM)
            .where(ConversationORM.session_id == session_id)
            .values(deleted_at=at, tombstone_fence=fence, title_ciphertext=None)
        )
        await self._session.execute(stmt)


class MessageRepository:
    """Persistence for ``conversation.messages`` (encrypted content/blocks)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        message_id: uuid.UUID,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        content_ciphertext: bytes,
        blocks_ciphertext: bytes | None = None,
    ) -> MessageORM:
        """Stage a new message for insertion."""

        msg = MessageORM(
            message_id=message_id,
            session_id=session_id,
            owner_id=owner_id,
            role=role,
            content_ciphertext=content_ciphertext,
            blocks_ciphertext=blocks_ciphertext,
        )
        self._session.add(msg)
        return msg

    async def list_for_session(self, session_id: uuid.UUID) -> list[MessageORM]:
        """Return a conversation's messages in deterministic total order.

        Ordered by ``(created_at asc, message_id asc)`` so ties are broken
        deterministically (Property 36). Debug traces live in a separate table
        and are never included here.
        """

        stmt = (
            select(MessageORM)
            .where(MessageORM.session_id == session_id)
            .order_by(MessageORM.created_at.asc(), MessageORM.message_id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get(self, message_id: uuid.UUID) -> MessageORM | None:
        """Return a message by id, or ``None``."""

        return await self._session.get(MessageORM, message_id)

    async def delete(self, message_id: uuid.UUID) -> None:
        """Delete one message (staged) — used to undo a failed turn's input."""

        await self._session.execute(
            delete(MessageORM).where(MessageORM.message_id == message_id)
        )

    async def delete_for_session(self, session_id: uuid.UUID) -> None:
        """Purge all messages for a conversation (staged)."""

        await self._session.execute(
            delete(MessageORM).where(MessageORM.session_id == session_id)
        )


class DomainStateRepository:
    """Persistence for ``conversation.domain_states`` (encrypted state)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        state_ciphertext: bytes,
        revision: int,
    ) -> DomainStateORM:
        """Stage a new domain-state revision for insertion."""

        row = DomainStateORM(
            id=uuid.uuid4(),
            session_id=session_id,
            owner_id=owner_id,
            state_ciphertext=state_ciphertext,
            revision=revision,
        )
        self._session.add(row)
        return row

    async def delete_for_session(self, session_id: uuid.UUID) -> None:
        """Purge all domain state for a conversation (staged)."""

        await self._session.execute(
            delete(DomainStateORM).where(DomainStateORM.session_id == session_id)
        )


class PlanRepository:
    """Persistence for ``conversation.plans`` (revisioned, encrypted)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def max_revision(self, session_id: uuid.UUID) -> int:
        """Return the highest plan revision for a conversation (0 if none)."""

        stmt = select(func.max(PlanORM.plan_revision)).where(
            PlanORM.session_id == session_id
        )
        value = (await self._session.execute(stmt)).scalar_one_or_none()
        return int(value) if value is not None else 0

    async def add_revision(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        plan_ciphertext: bytes,
    ) -> PlanORM:
        """Create a strictly-greater revision, marking prior ones not-current.

        Clears ``is_current`` on all existing revisions first (so the partial
        unique index ``uq_plans_one_current`` is never violated), then inserts
        the new current revision at ``max_revision + 1`` (Property 28).
        """

        await self._session.execute(
            update(PlanORM)
            .where(PlanORM.session_id == session_id, PlanORM.is_current.is_(True))
            .values(is_current=False)
        )
        next_rev = await self.max_revision(session_id) + 1
        plan = PlanORM(
            plan_id=uuid.uuid4(),
            session_id=session_id,
            owner_id=owner_id,
            plan_revision=next_rev,
            is_current=True,
            plan_ciphertext=plan_ciphertext,
        )
        self._session.add(plan)
        await self._session.flush()
        return plan

    async def get_revision(
        self, session_id: uuid.UUID, revision: int
    ) -> PlanORM | None:
        """Return a specific plan revision for a conversation, or ``None``."""

        stmt = select(PlanORM).where(
            PlanORM.session_id == session_id, PlanORM.plan_revision == revision
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_confirmed_executed(
        self, plan_id: uuid.UUID, *, at: datetime
    ) -> None:
        """Record confirmation + execution timestamps once (staged, idempotent).

        Only sets the timestamps when they are still NULL so a repeated confirm
        records at most one confirmation and triggers at most one execution
        (Property 29).
        """

        stmt = (
            update(PlanORM)
            .where(PlanORM.plan_id == plan_id, PlanORM.confirmed_at.is_(None))
            .values(confirmed_at=at, executed_at=at)
        )
        await self._session.execute(stmt)


class TurnJobRepository:
    """Persistence for ``execution.turn_jobs`` (the durable turn queue)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_accepted_seq(self, session_id: uuid.UUID) -> int:
        """Return the next strictly-increasing ``accepted_seq`` for a session.

        Computed within the acceptance transaction as ``max + 1`` so two
        accepted turns in a conversation always get strictly increasing values;
        the ``UNIQUE(session_id, accepted_seq)`` constraint rejects any
        duplicate under a race, forcing a retry (Property 24).
        """

        stmt = select(func.max(TurnJobORM.accepted_seq)).where(
            TurnJobORM.session_id == session_id
        )
        value = (await self._session.execute(stmt)).scalar_one_or_none()
        return (int(value) if value is not None else 0) + 1

    async def pending_counts(self, owner_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Outstanding (QUEUED / RUNNING) job count per conversation of an owner."""

        stmt = (
            select(TurnJobORM.session_id, func.count())
            .where(
                TurnJobORM.owner_id == owner_id,
                TurnJobORM.job_state.in_([JobState.QUEUED, JobState.RUNNING]),
            )
            .group_by(TurnJobORM.session_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return {sid: int(n) for sid, n in rows}

    async def get_by_client_request_id(
        self, owner_id: uuid.UUID, client_request_id: str
    ) -> TurnJobORM | None:
        """Return an existing job for this (owner, client_request_id), or None.

        The basis for idempotency (Property 15): a repeated client request id
        resolves to the already-accepted job instead of creating a second.
        """

        stmt = select(TurnJobORM).where(
            TurnJobORM.owner_id == owner_id,
            TurnJobORM.client_request_id == client_request_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def add(
        self,
        *,
        job_id: uuid.UUID,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        accepted_seq: int,
        client_request_id: str,
        input_ciphertext: bytes | None = None,
        job_state: JobState = JobState.QUEUED,
    ) -> TurnJobORM:
        """Stage a new durable turn job for insertion (initial ``QUEUED``)."""

        job = TurnJobORM(
            job_id=job_id,
            session_id=session_id,
            owner_id=owner_id,
            job_state=job_state,
            accepted_seq=accepted_seq,
            client_request_id=client_request_id,
            input_ciphertext=input_ciphertext,
        )
        self._session.add(job)
        return job

    async def get(self, job_id: uuid.UUID) -> TurnJobORM | None:
        """Return a job by id, or ``None``."""

        return await self._session.get(TurnJobORM, job_id)

    async def pending_count_for_owner(self, owner_id: uuid.UUID) -> int:
        """Count non-terminal jobs for an owner (the per-user pending cap)."""

        return await self._pending_count(TurnJobORM.owner_id == owner_id)

    async def pending_count_for_session(self, session_id: uuid.UUID) -> int:
        """Count non-terminal jobs for a conversation (per-session cap)."""

        return await self._pending_count(TurnJobORM.session_id == session_id)

    async def _pending_count(self, predicate: object) -> int:
        stmt = (
            select(func.count())
            .select_from(TurnJobORM)
            .where(
                and_(
                    predicate,  # type: ignore[arg-type]
                    TurnJobORM.job_state.notin_(
                        [s.value for s in _TERMINAL_JOB_STATES]
                    ),
                )
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def claim_next(self, *, now: datetime) -> TurnJobORM | None:
        """Claim one reclaimable job with ``FOR UPDATE SKIP LOCKED``.

        A job is reclaimable when it is ``QUEUED`` or its lease has expired
        while ``RUNNING``. ``SKIP LOCKED`` lets distinct workers claim distinct
        rows concurrently; claim order is NOT assumed to be FIFO (design/
        Property 24). The row is locked for the caller's transaction so the
        lease/fence update is single-winner.
        """

        reclaimable = (
            select(TurnJobORM)
            .where(
                TurnJobORM.job_state.in_(
                    [JobState.QUEUED.value, JobState.RUNNING.value]
                ),
                (
                    (TurnJobORM.job_state == JobState.QUEUED.value)
                    | (
                        (TurnJobORM.job_state == JobState.RUNNING.value)
                        & (TurnJobORM.lease_expires_at.isnot(None))
                        & (TurnJobORM.lease_expires_at <= now)
                    )
                ),
            )
            .order_by(TurnJobORM.accepted_seq.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return (await self._session.execute(reclaimable)).scalar_one_or_none()

    async def has_other_running(
        self, session_id: uuid.UUID, *, except_job_id: uuid.UUID, now: datetime
    ) -> bool:
        """Whether another job in the conversation holds a live RUNNING lease.

        Used to enforce at-most-one RUNNING per conversation (Property 23): a
        RUNNING job whose lease has expired no longer counts as live.
        """

        stmt = (
            select(func.count())
            .select_from(TurnJobORM)
            .where(
                TurnJobORM.session_id == session_id,
                TurnJobORM.job_id != except_job_id,
                TurnJobORM.job_state == JobState.RUNNING.value,
                TurnJobORM.lease_expires_at.isnot(None),
                TurnJobORM.lease_expires_at > now,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one()) > 0

    async def max_fencing_token(self, session_id: uuid.UUID) -> int:
        """Return the highest fencing token issued in a conversation (0 if none).

        Fencing tokens are strictly monotonic per conversation so a stale
        holder's token is always strictly less than the current one (Property
        25/26).
        """

        stmt = select(func.max(TurnJobORM.fencing_token)).where(
            TurnJobORM.session_id == session_id
        )
        value = (await self._session.execute(stmt)).scalar_one_or_none()
        return int(value) if value is not None else 0

    async def lease(
        self,
        job_id: uuid.UUID,
        *,
        fencing_token: int,
        lease_expires_at: datetime,
        at: datetime,
    ) -> None:
        """Set the lease, assign the fence, and increment attempt_count (staged).

        Transitions the job to ``RUNNING`` within the short claim transaction
        (no external call). ``attempt_count`` increments by one (Property 25).
        """

        stmt = (
            update(TurnJobORM)
            .where(TurnJobORM.job_id == job_id)
            .values(
                job_state=JobState.RUNNING,
                fencing_token=fencing_token,
                lease_expires_at=lease_expires_at,
                attempt_count=TurnJobORM.attempt_count + 1,
                updated_at=at,
            )
        )
        await self._session.execute(stmt)

    async def persist_result(
        self,
        job_id: uuid.UUID,
        *,
        fencing_token: int,
        result_ciphertext: bytes,
        job_state: JobState,
        at: datetime,
    ) -> bool:
        """Persist a result only if the presented fence is still current.

        Guards with ``WHERE fencing_token = :fence`` so a stale holder whose
        fence has been superseded affects zero rows and is rejected (Property
        26). Returns whether the write won.
        """

        stmt = (
            update(TurnJobORM)
            .where(
                TurnJobORM.job_id == job_id,
                TurnJobORM.fencing_token == fencing_token,
            )
            .values(
                job_state=job_state,
                result_ciphertext=result_ciphertext,
                lease_expires_at=None,
                updated_at=at,
            )
            .returning(TurnJobORM.job_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def set_state(
        self, job_id: uuid.UUID, *, job_state: JobState, at: datetime
    ) -> None:
        """Set a job's state unconditionally (staged); used by cancel."""

        stmt = (
            update(TurnJobORM)
            .where(TurnJobORM.job_id == job_id)
            .values(job_state=job_state, updated_at=at)
        )
        await self._session.execute(stmt)

    async def cancel_active_for_session(
        self, session_id: uuid.UUID, *, at: datetime
    ) -> None:
        """Cancel every non-terminal job for a conversation (staged)."""

        stmt = (
            update(TurnJobORM)
            .where(
                TurnJobORM.session_id == session_id,
                TurnJobORM.job_state.notin_([s.value for s in _TERMINAL_JOB_STATES]),
            )
            .values(job_state=JobState.CANCELLED, lease_expires_at=None, updated_at=at)
        )
        await self._session.execute(stmt)

    async def list_ids_for_session(self, session_id: uuid.UUID) -> list[uuid.UUID]:
        """Return all job ids for a conversation (for attempt-detail purge)."""

        stmt = select(TurnJobORM.job_id).where(TurnJobORM.session_id == session_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def clear_sensitive_for_session(self, session_id: uuid.UUID) -> None:
        """Null out job input/result ciphertext for a deleted conversation.

        Retains no deleted sensitive content in the queue table (Property 31)
        while keeping the terminal rows for audit of cancellation.
        """

        await self._session.execute(
            update(TurnJobORM)
            .where(TurnJobORM.session_id == session_id)
            .values(input_ciphertext=None, result_ciphertext=None)
        )


class JobAttemptRepository:
    """Persistence for ``execution.job_attempts`` (per-attempt audit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        job_id: uuid.UUID,
        owner_id: uuid.UUID,
        fencing_token: int,
    ) -> JobAttemptORM:
        """Stage a new job attempt row."""

        row = JobAttemptORM(
            id=uuid.uuid4(),
            job_id=job_id,
            owner_id=owner_id,
            fencing_token=fencing_token,
        )
        self._session.add(row)
        return row

    async def clear_detail_for_session_jobs(self, job_ids: list[uuid.UUID]) -> None:
        """Null out attempt detail ciphertext for a deleted conversation."""

        if not job_ids:
            return
        await self._session.execute(
            update(JobAttemptORM)
            .where(JobAttemptORM.job_id.in_(job_ids))
            .values(detail_ciphertext=None)
        )


class ToolTraceRepository:
    """Persistence for ``execution.tool_traces`` (encrypted sanitized traces)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        message_id: uuid.UUID,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        trace_ciphertext: bytes,
        duration_ms: int | None,
    ) -> ToolTraceORM:
        """Stage a new tool-trace row."""

        row = ToolTraceORM(
            id=uuid.uuid4(),
            message_id=message_id,
            session_id=session_id,
            owner_id=owner_id,
            trace_ciphertext=trace_ciphertext,
            duration_ms=duration_ms,
        )
        self._session.add(row)
        return row

    async def get_for_message(self, message_id: uuid.UUID) -> ToolTraceORM | None:
        """Return the trace for a message, or ``None``."""

        stmt = select(ToolTraceORM).where(ToolTraceORM.message_id == message_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def delete_for_session(self, session_id: uuid.UUID) -> None:
        """Purge all traces for a conversation (staged)."""

        await self._session.execute(
            delete(ToolTraceORM).where(ToolTraceORM.session_id == session_id)
        )


class CheckpointRepository:
    """Persistence for ``execution.encrypted_checkpoints`` (GCM blobs)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        record_id: uuid.UUID,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        thread_id: str,
        checkpoint_ciphertext: bytes,
        pending_writes_ciphertext: bytes | None,
        cipher_version: int,
    ) -> EncryptedCheckpointORM:
        """Stage a new encrypted checkpoint row.

        ``record_id`` is the row PK AND the crypto AAD ``record_id`` so the
        stored ciphertext decrypts under the same five-field context on read.
        """

        row = EncryptedCheckpointORM(
            id=record_id,
            session_id=session_id,
            owner_id=owner_id,
            thread_id=thread_id,
            checkpoint_ciphertext=checkpoint_ciphertext,
            pending_writes_ciphertext=pending_writes_ciphertext,
            cipher_version=cipher_version,
        )
        self._session.add(row)
        return row

    async def latest_for_thread(
        self, session_id: uuid.UUID, thread_id: str
    ) -> EncryptedCheckpointORM | None:
        """Return the most recent checkpoint for a (session, thread)."""

        stmt = (
            select(EncryptedCheckpointORM)
            .where(
                EncryptedCheckpointORM.session_id == session_id,
                EncryptedCheckpointORM.thread_id == thread_id,
            )
            .order_by(EncryptedCheckpointORM.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def delete_for_session(self, session_id: uuid.UUID) -> None:
        """Purge all checkpoints for a conversation (staged)."""

        await self._session.execute(
            delete(EncryptedCheckpointORM).where(
                EncryptedCheckpointORM.session_id == session_id
            )
        )


class KeyMetadataRepository:
    """Persistence for ``execution.key_metadata`` (wrapped DEK handle)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        wrapped_dek: bytes,
        cipher_version: int,
    ) -> KeyMetadataORM:
        """Stage a new wrapped-DEK key handle row."""

        row = KeyMetadataORM(
            key_id=uuid.uuid4(),
            session_id=session_id,
            owner_id=owner_id,
            wrapped_dek=wrapped_dek,
            cipher_version=cipher_version,
        )
        self._session.add(row)
        return row

    async def get_for_session(self, session_id: uuid.UUID) -> KeyMetadataORM | None:
        """Return the (non-shredded) key handle for a conversation, or ``None``."""

        stmt = select(KeyMetadataORM).where(
            KeyMetadataORM.session_id == session_id,
            KeyMetadataORM.shredded_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def shred(self, session_id: uuid.UUID, *, at: datetime) -> None:
        """Crypto-shred: delete the wrapped DEK so ciphertext is unrecoverable.

        Zeroes the stored wrapped DEK and records ``shredded_at``; the DEK can
        no longer be unwrapped, rendering all the conversation's ciphertext
        permanently undecryptable from active storage (Property 31).
        """

        stmt = (
            update(KeyMetadataORM)
            .where(KeyMetadataORM.session_id == session_id)
            .values(wrapped_dek=b"", shredded_at=at)
        )
        await self._session.execute(stmt)


__all__ += [
    "CANCELABLE_JOB_STATES",
    "NON_TERMINAL_JOB_STATES",
    "ConversationRepository",
    "MessageRepository",
    "DomainStateRepository",
    "PlanRepository",
    "TurnJobRepository",
    "JobAttemptRepository",
    "ToolTraceRepository",
    "CheckpointRepository",
    "KeyMetadataRepository",
]
