"""Durable turn-job acceptance, polling, and cancellation (Spec 3, Req 5, 6).

The async path shares the **same** durable ``turn_jobs`` row and the **same**
``Response_Envelope`` as the sync path. This service:

* accepts a job transactionally — assigns a strictly increasing per-conversation
  ``accepted_seq`` and enforces ``UNIQUE(owner_id, client_request_id)``
  idempotency, with initial state ``QUEUED`` (Properties 17, 22, 24, 15);
* enforces configurable per-user and per-session pending-job caps, rejecting
  over-cap acceptance as ``RATE_LIMITED`` with no side effects (Property 21);
* polls a job owner-scoped, returning exactly one ``Job_State`` and, on
  ``COMPLETED``, the shared ``Response_Envelope`` (Property 18);
* cancels idempotently for cancelable states (Property 19).

The ``202`` acceptance is never substituted for the mandatory sync final
response (Property 11) — that contract lives in the conversation service.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from series76_api.api.envelopes import ResponseEnvelope
from series76_api.application.authorization import authorize_ownership
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.errors import RateLimitedError, ValidationError
from series76_api.domain.models import AuthenticatedPrincipal, JobState
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.crypto import Ciphertext, CryptoService
from series76_api.infrastructure.orm import ConversationORM, TurnJobORM
from series76_api.infrastructure.repositories import CANCELABLE_JOB_STATES
from series76_api.infrastructure.settings import Settings

# Retry-After bounds for non-terminal poll responses (Property 20).
RETRY_AFTER_MIN = 1
RETRY_AFTER_MAX = 60
_DEFAULT_RETRY_AFTER = 2


@dataclass(frozen=True, slots=True)
class JobAccepted:
    """The outcome of accepting an async job (202)."""

    job_id: uuid.UUID
    session_id: uuid.UUID
    status: JobState


@dataclass(frozen=True, slots=True)
class JobPoll:
    """The outcome of polling a job: its state and (on COMPLETED) the envelope."""

    job_id: uuid.UUID
    state: JobState
    envelope: ResponseEnvelope | None
    retry_after: int | None


class JobsService:
    """Application service for durable turn jobs."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        crypto: CryptoService,
        settings: Settings,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._crypto = crypto
        self._settings = settings

    def _aad(
        self,
        purpose: CryptoPurpose,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> AADContext:
        return AADContext(
            purpose=purpose,
            owner_id=owner_id,
            conversation_id=session_id,
            record_id=record_id,
        )

    async def _ensure_dek(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bytes:
        handle = await self._uow.key_metadata.get_for_session(session_id)
        if handle is not None:
            return self._crypto.unwrap_dek(
                handle.wrapped_dek, owner_id=owner_id, conversation_id=session_id
            )
        dek = self._crypto.generate_dek()
        wrapped = self._crypto.wrap_dek(
            dek, owner_id=owner_id, conversation_id=session_id
        )
        self._uow.key_metadata.add(
            session_id=session_id,
            owner_id=owner_id,
            wrapped_dek=wrapped,
            cipher_version=Ciphertext(wrapped).cipher_version,
        )
        return dek

    # --- acceptance -------------------------------------------------------

    async def accept(
        self,
        principal: AuthenticatedPrincipal,
        *,
        session_id: uuid.UUID | None,
        query: str,
        client_request_id: str | None,
    ) -> JobAccepted:
        """Accept an async turn job, returning ``202``-worthy acceptance data.

        Validates + resolves/creates the conversation, enforces pending caps,
        assigns ``accepted_seq`` transactionally, and inserts a ``QUEUED`` job.
        A repeated ``client_request_id`` returns the already-accepted job with
        no second effect (Property 15). Over-cap acceptance raises
        :class:`RateLimitedError` with nothing created (Property 21).
        """

        from series76_api.application.conversation_service import validate_query

        clean_query = validate_query(query)

        # Idempotency first: a retried client_request_id returns the existing
        # job and never creates a second (Property 15).
        if client_request_id:
            existing = await self._uow.turn_jobs.get_by_client_request_id(
                principal.user_id, client_request_id
            )
            if existing is not None:
                await self._uow.commit()
                return JobAccepted(
                    job_id=existing.job_id,
                    session_id=existing.session_id,
                    status=existing.job_state,
                )

        conv = await self._resolve_conversation(principal, session_id)

        # Pending-job caps (per user AND per session). Over cap -> RATE_LIMITED
        # with NO side effects: we roll back any conversation just created.
        cap = self._settings.pending_job_cap
        user_pending = await self._uow.turn_jobs.pending_count_for_owner(
            principal.user_id
        )
        session_pending = await self._uow.turn_jobs.pending_count_for_session(
            conv_session_id := conv.session_id
        )
        if user_pending >= cap or session_pending >= cap:
            await self._uow.rollback()
            raise RateLimitedError(
                "Too many pending jobs. Please wait for them to complete.",
                retry_after_seconds=RETRY_AFTER_MAX,
            )

        dek = await self._ensure_dek(
            session_id=conv_session_id, owner_id=principal.user_id
        )
        seq = await self._uow.turn_jobs.next_accepted_seq(conv_session_id)
        job_id = uuid.uuid4()
        input_ct = self._crypto.encrypt(
            dek,
            clean_query.encode("utf-8"),
            self._aad(
                CryptoPurpose.JOB_INPUT, principal.user_id, conv_session_id, job_id
            ),
        ).blob
        self._uow.turn_jobs.add(
            job_id=job_id,
            session_id=conv_session_id,
            owner_id=principal.user_id,
            accepted_seq=seq,
            client_request_id=client_request_id or job_id.hex,
            input_ciphertext=input_ct,
            job_state=JobState.QUEUED,
        )
        await self._uow.commit()
        return JobAccepted(
            job_id=job_id, session_id=conv_session_id, status=JobState.QUEUED
        )

    async def _resolve_conversation(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID | None,
    ) -> ConversationORM:
        if session_id is None:
            new_id = uuid.uuid4()
            conv = self._uow.conversations.add(
                session_id=new_id, owner_id=principal.user_id
            )
            await self._uow.flush()
            return conv
        existing: ConversationORM | None = await self._uow.conversations.get(session_id)
        if existing is not None and existing.deleted_at is not None:
            existing = None
        authorize_ownership(principal, existing)
        assert existing is not None
        return existing

    # (resolved conversation type imported below at module import time)

    # --- polling ----------------------------------------------------------

    async def poll(
        self, principal: AuthenticatedPrincipal, job_id: uuid.UUID
    ) -> JobPoll:
        """Poll a job owner-scoped, returning its state (+ envelope if done).

        A nonexistent or not-owned job is an indistinguishable 404 (Property
        10). On ``COMPLETED`` the shared ``Response_Envelope`` is decrypted and
        returned (Property 18). Non-terminal states carry a ``Retry-After`` in
        ``[1, 60]`` (Property 20).
        """

        job: TurnJobORM | None = await self._uow.turn_jobs.get(job_id)
        authorize_ownership(principal, job)
        assert job is not None  # authorize_ownership raised otherwise

        envelope: ResponseEnvelope | None = None
        retry_after: int | None = None
        if job.job_state == JobState.COMPLETED and job.result_ciphertext is not None:
            envelope = await self._decrypt_envelope(principal, job)
        if job.job_state in CANCELABLE_JOB_STATES:
            retry_after = _DEFAULT_RETRY_AFTER
        await self._uow.commit()
        return JobPoll(
            job_id=job_id,
            state=job.job_state,
            envelope=envelope,
            retry_after=retry_after,
        )

    async def _decrypt_envelope(
        self, principal: AuthenticatedPrincipal, job: TurnJobORM
    ) -> ResponseEnvelope | None:
        if job.result_ciphertext is None:
            return None
        handle = await self._uow.key_metadata.get_for_session(job.session_id)
        if handle is None:
            return None
        dek = self._crypto.unwrap_dek(
            handle.wrapped_dek,
            owner_id=principal.user_id,
            conversation_id=job.session_id,
        )
        raw = self._crypto.decrypt(
            dek,
            Ciphertext(job.result_ciphertext),
            self._aad(
                CryptoPurpose.JOB_INPUT, principal.user_id, job.session_id, job.job_id
            ),
        )
        return ResponseEnvelope.model_validate_json(raw.decode("utf-8"))

    # --- cancellation -----------------------------------------------------

    async def cancel(
        self, principal: AuthenticatedPrincipal, job_id: uuid.UUID
    ) -> JobState:
        """Cancel a job idempotently for cancelable states (Property 19).

        A nonexistent or not-owned job is an indistinguishable 404. Cancelling a
        cancelable job transitions it to ``CANCELLED``; repeating the cancel on
        an already-cancelled job returns ``CANCELLED`` with no extra effect. A
        job in another terminal state (``COMPLETED``/``FAILED``) is left
        unchanged and its state returned.
        """

        job: TurnJobORM | None = await self._uow.turn_jobs.get(job_id)
        authorize_ownership(principal, job)
        assert job is not None
        if job.job_state in CANCELABLE_JOB_STATES:
            await self._uow.turn_jobs.set_state(
                job_id, job_state=JobState.CANCELLED, at=self._clock.now()
            )
            await self._uow.commit()
            return JobState.CANCELLED
        # Terminal (incl. already CANCELLED): idempotent no-op.
        await self._uow.commit()
        return job.job_state


__all__ = [
    "RETRY_AFTER_MIN",
    "RETRY_AFTER_MAX",
    "JobAccepted",
    "JobPoll",
    "JobsService",
]


_ = ValidationError  # referenced indirectly via validate_query
