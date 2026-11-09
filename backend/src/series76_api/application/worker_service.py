"""Worker claim/lease/fencing turn processing (Spec 3, Req 6).

The ``Worker_Process`` drains the durable ``turn_jobs`` queue without ever
holding a SQL transaction across the model call (Property 27). One drained turn
is three phases:

1. **Claim + lease (short txn, NO external call).** Claim a reclaimable job with
   ``SELECT ... FOR UPDATE SKIP LOCKED``; verify no *other* job in that
   conversation holds a live ``RUNNING`` lease (Property 23); set
   ``lease_expires_at`` 30-120s ahead, assign a strictly monotonic
   ``Fencing_Token``, and increment ``attempt_count`` (Property 25). On an
   expired-lease reclaim, if a result already exists the turn is NOT re-sent to
   the model (Property 26). Commit.

2. **Run the agent (OUTSIDE any SQL transaction).** Dispatch the faked agent
   seam — zero provider spend. No SQL session is open here (Property 27).

3. **Persist result (separate short txn).** Persist only if the fence is still
   current, the lease is valid, the owner matches, and the conversation is not
   tombstoned; a stale-fenced write affects zero rows and is rejected (Property
   26, 32). Commit.

A :class:`FixedClock` makes lease-expiry deterministic in tests.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from series76_api.api.envelopes import (
    ResponseEnvelope,
)
from series76_api.application.agent_seam import (
    AgentPort,
    OutcomeKind,
    ProviderUnavailable,
    TurnOutcome,
    TurnRequest,
    build_response_envelope,
)
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.errors import DomainError
from series76_api.domain.models import JobState
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.crypto import Ciphertext, CryptoService
from series76_api.infrastructure.engine import AsyncSession
from series76_api.infrastructure.orm import TurnJobORM
from series76_api.infrastructure.settings import Settings


@dataclass(frozen=True, slots=True)
class _HistoryRecords:
    """Encrypted history rows written with the result (same fenced txn)."""

    user_id: uuid.UUID
    user_ct: bytes
    assistant_id: uuid.UUID
    assistant_ct: bytes
    assistant_blocks_ct: bytes
    trace_id: uuid.UUID | None
    trace_ct: bytes | None


@dataclass(frozen=True, slots=True)
class _ClaimedJob:
    """The data carried out of the claim transaction into the model call."""

    job_id: uuid.UUID
    session_id: uuid.UUID
    owner_id: uuid.UUID
    fencing_token: int
    query: str
    existing_result: bytes | None


class WorkerService:
    """Processes durable turn jobs with claim/lease/fencing (faked agent)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        crypto: CryptoService,
        agent: AgentPort,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._crypto = crypto
        self._agent = agent
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

    async def _unwrap_dek(
        self, uow: UnitOfWork, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> bytes | None:
        handle = await uow.key_metadata.get_for_session(session_id)
        if handle is None:
            return None
        return self._crypto.unwrap_dek(
            handle.wrapped_dek, owner_id=owner_id, conversation_id=session_id
        )

    async def process_one(self) -> uuid.UUID | None:
        """Drain one turn end-to-end, or return ``None`` if the queue is empty.

        Returns the processed ``job_id`` on success. Guarantees that no SQL
        transaction is open across the agent call (Property 27).
        """

        claimed = await self._claim_phase()
        if claimed is None:
            return None

        # --- Phase 2: run the agent OUTSIDE any SQL transaction -----------
        # If a result already exists (expired-lease reclaim) do NOT re-send to
        # the model (Property 26) — just re-persist idempotently.
        if claimed.existing_result is not None:
            await self._persist_phase(claimed, result_ct=claimed.existing_result,
                                      state=JobState.COMPLETED)
            return claimed.job_id

        try:
            outcome = await self._agent.run_turn(
                TurnRequest(
                    owner_id=claimed.owner_id,
                    session_id=claimed.session_id,
                    query=claimed.query,
                    trace_id=str(claimed.job_id),
                )
            )
        except (ProviderUnavailable, DomainError):
            # Provider failure / fail-closed turn: FAILED without a result.
            await self._fail_phase(claimed)
            return claimed.job_id

        state = _JOB_STATE_BY_OUTCOME.get(outcome.outcome_kind, JobState.COMPLETED)
        assistant_id = uuid.uuid4()
        envelope = build_response_envelope(
            claimed.session_id, outcome, turn_id=str(assistant_id), message_id=str(assistant_id)
        )
        result_ct = await self._encrypt_result(claimed, envelope)
        if result_ct is None:
            await self._fail_phase(claimed)
            return claimed.job_id
        records = await self._history_records(claimed, envelope, assistant_id, outcome)

        # --- Phase 3: persist result in a separate short txn --------------
        await self._persist_phase(claimed, result_ct=result_ct, state=state, records=records)
        return claimed.job_id

    async def _history_records(
        self,
        claimed: _ClaimedJob,
        envelope: ResponseEnvelope,
        assistant_id: uuid.UUID,
        outcome: TurnOutcome,
    ) -> _HistoryRecords | None:
        """Encrypt the turn's user + assistant messages (and trace) for history.

        Written in the same fenced transaction as the result, so a stale or
        tombstoned writer persists none of them (no resurrection).
        """

        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            dek = await self._unwrap_dek(uow, claimed.session_id, claimed.owner_id)
            await uow.rollback()
        if dek is None:
            return None
        user_id = uuid.uuid4()

        def enc(purpose: CryptoPurpose, record: uuid.UUID, data: bytes) -> bytes:
            return self._crypto.encrypt(
                dek, data, self._aad(purpose, claimed.owner_id, claimed.session_id, record)
            ).blob

        blocks = json.dumps([b.model_dump(mode="json") for b in envelope.content_blocks])
        trace_id = uuid.uuid4()
        return _HistoryRecords(
            user_id=user_id,
            user_ct=enc(CryptoPurpose.MESSAGE_CONTENT, user_id, claimed.query.encode("utf-8")),
            assistant_id=assistant_id,
            assistant_ct=enc(
                CryptoPurpose.MESSAGE_CONTENT, assistant_id, envelope.answer.encode("utf-8")
            ),
            assistant_blocks_ct=enc(CryptoPurpose.MESSAGE_BLOCKS, assistant_id, blocks.encode()),
            trace_id=trace_id if outcome.trace is not None else None,
            trace_ct=enc(
                CryptoPurpose.TOOL_TRACE,
                trace_id,
                json.dumps(outcome.trace, sort_keys=True, default=str).encode("utf-8"),
            )
            if outcome.trace is not None
            else None,
        )

    async def _claim_phase(self) -> _ClaimedJob | None:
        """Claim + lease a job in a short transaction with no external call."""

        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            now = self._clock.now()
            job: TurnJobORM | None = await uow.turn_jobs.claim_next(now=now)
            if job is None:
                await uow.rollback()
                return None

            # At most one RUNNING per conversation (Property 23): if another job
            # holds a live lease, leave this one QUEUED and skip it this round.
            if await uow.turn_jobs.has_other_running(
                job.session_id, except_job_id=job.job_id, now=now
            ):
                await uow.rollback()
                return None

            fence = await uow.turn_jobs.max_fencing_token(job.session_id) + 1
            lease_until = now + timedelta(
                seconds=self._settings.job_lease_seconds_min
            )
            await uow.turn_jobs.lease(
                job.job_id,
                fencing_token=fence,
                lease_expires_at=lease_until,
                at=now,
            )
            uow.job_attempts.add(
                job_id=job.job_id, owner_id=job.owner_id, fencing_token=fence
            )

            # Decrypt the input query + detect an existing result (reclaim).
            dek = await self._unwrap_dek(uow, job.session_id, job.owner_id)
            query = ""
            if dek is not None and job.input_ciphertext is not None:
                query = self._crypto.decrypt(
                    dek,
                    Ciphertext(job.input_ciphertext),
                    self._aad(
                        CryptoPurpose.JOB_INPUT,
                        job.owner_id,
                        job.session_id,
                        job.job_id,
                    ),
                ).decode("utf-8")
            existing = job.result_ciphertext
            await uow.commit()
            return _ClaimedJob(
                job_id=job.job_id,
                session_id=job.session_id,
                owner_id=job.owner_id,
                fencing_token=fence,
                query=query,
                existing_result=existing,
            )

    async def _encrypt_result(
        self, claimed: _ClaimedJob, envelope: ResponseEnvelope
    ) -> bytes | None:
        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            dek = await self._unwrap_dek(uow, claimed.session_id, claimed.owner_id)
            await uow.rollback()
        if dek is None:
            return None
        return self._crypto.encrypt(
            dek,
            envelope.model_dump_json().encode("utf-8"),
            self._aad(
                CryptoPurpose.JOB_INPUT,
                claimed.owner_id,
                claimed.session_id,
                claimed.job_id,
            ),
        ).blob

    async def _persist_phase(
        self,
        claimed: _ClaimedJob,
        *,
        result_ct: bytes,
        state: JobState,
        records: _HistoryRecords | None = None,
    ) -> bool:
        """Persist the result only if the fence is current + not tombstoned.

        Returns whether the write won. A stale-fenced write (fence superseded
        by a newer claim) affects zero rows and is rejected (Property 26); a
        tombstoned conversation (fence <= tombstone) blocks the write so a
        deleted conversation is never resurrected (Property 32).
        """

        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            now = self._clock.now()
            conv = await uow.conversations.get(claimed.session_id)
            # No-resurrection guard: a tombstoned conversation whose recorded
            # fence is >= this writer's fence blocks the write (Property 32).
            if conv is None or conv.deleted_at is not None:
                await uow.rollback()
                return False
            if (
                conv.tombstone_fence is not None
                and claimed.fencing_token <= conv.tombstone_fence
            ):
                await uow.rollback()
                return False
            won = await uow.turn_jobs.persist_result(
                claimed.job_id,
                fencing_token=claimed.fencing_token,
                result_ciphertext=result_ct,
                job_state=state,
                at=now,
            )
            if won and records is not None:
                self._stage_history(uow, claimed, records)
                await uow.flush()
                if records.trace_id is not None and records.trace_ct is not None:
                    row = uow.tool_traces.add(
                        message_id=records.assistant_id,
                        session_id=claimed.session_id,
                        owner_id=claimed.owner_id,
                        trace_ciphertext=records.trace_ct,
                        duration_ms=None,
                    )
                    row.id = records.trace_id
            if won:
                await uow.commit()
            else:
                await uow.rollback()
            return won

    def _stage_history(
        self, uow: UnitOfWork, claimed: _ClaimedJob, records: _HistoryRecords
    ) -> None:
        uow.messages.add(
            message_id=records.user_id,
            session_id=claimed.session_id,
            owner_id=claimed.owner_id,
            role="user",
            content_ciphertext=records.user_ct,
            blocks_ciphertext=None,
        )
        uow.messages.add(
            message_id=records.assistant_id,
            session_id=claimed.session_id,
            owner_id=claimed.owner_id,
            role="assistant",
            content_ciphertext=records.assistant_ct,
            blocks_ciphertext=records.assistant_blocks_ct,
        )

    async def _fail_phase(self, claimed: _ClaimedJob) -> None:
        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            now = self._clock.now()
            job = await uow.turn_jobs.get(claimed.job_id)
            if job is not None and job.fencing_token == claimed.fencing_token:
                await uow.turn_jobs.set_state(
                    claimed.job_id, job_state=JobState.FAILED, at=now
                )
                await uow.commit()
            else:
                await uow.rollback()

    def _build_envelope(
        self, session_id: uuid.UUID, outcome: object
    ) -> ResponseEnvelope:
        assert isinstance(outcome, TurnOutcome)
        return build_response_envelope(session_id, outcome)


#: Turn outcome -> durable Job_State (Spec 4 Turn_State mapped at this boundary).
_JOB_STATE_BY_OUTCOME: dict[OutcomeKind, JobState] = {
    OutcomeKind.CLARIFICATION: JobState.NEEDS_CLARIFICATION,
    OutcomeKind.CONFIRMATION: JobState.AWAITING_CONFIRMATION,
    OutcomeKind.STALE_PLAN: JobState.STALE_PLAN,
    OutcomeKind.CATALOG_WITHDRAWN: JobState.CATALOG_WITHDRAWN,
}


__all__ = ["WorkerService"]
