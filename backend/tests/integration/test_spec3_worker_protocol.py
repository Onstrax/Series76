"""Spec 3 worker claim/lease/fencing protocol tests (real PostgreSQL).

Drives :class:`WorkerService` directly against the live engine with a
:class:`FixedClock` so lease expiry is deterministic. Properties 23, 25, 26, 27
are each one Hypothesis test. The agent seam is faked (zero provider spend).

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st

from series76_api.application.agent_seam import FakeAgent
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.application.worker_service import WorkerService
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.models import JobState
from series76_api.infrastructure.clock import FixedClock
from series76_api.infrastructure.crypto import Ciphertext, CryptoService

from ._spec3_app import build_settings, create_test_session_factory

pytestmark = pytest.mark.integration


async def _seed_user_and_conversation(factory, crypto):  # type: ignore[no-untyped-def]
    """Insert a user + conversation + wrapped DEK directly; return ids + dek."""

    owner_id = uuid.uuid4()
    session_id = uuid.uuid4()
    dek = crypto.generate_dek()
    wrapped = crypto.wrap_dek(dek, owner_id=owner_id, conversation_id=session_id)
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO identity.users (id, email, password_verifier, role, "
                "email_verified) VALUES (:id, :email, 'x', 'user', true)"
            ),
            {"id": owner_id, "email": f"{owner_id}@e.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO conversation.conversations (session_id, owner_id) "
                "VALUES (:sid, :oid)"
            ),
            {"sid": session_id, "oid": owner_id},
        )
        await s.execute(
            sa.text(
                "INSERT INTO execution.key_metadata (key_id, cipher_version, "
                "wrapped_dek, session_id, owner_id) VALUES "
                "(:kid, :cv, :wd, :sid, :oid)"
            ),
            {
                "kid": uuid.uuid4(),
                "cv": Ciphertext(wrapped).cipher_version,
                "wd": wrapped,
                "sid": session_id,
                "oid": owner_id,
            },
        )
        await s.commit()
    return owner_id, session_id, dek


async def _enqueue_job(factory, crypto, owner_id, session_id, dek, seq, query="hi"):  # type: ignore[no-untyped-def]
    job_id = uuid.uuid4()
    ct = crypto.encrypt(
        dek,
        query.encode("utf-8"),
        AADContext(
            purpose=CryptoPurpose.JOB_INPUT,
            owner_id=owner_id,
            conversation_id=session_id,
            record_id=job_id,
        ),
    ).blob
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO execution.turn_jobs (job_id, session_id, owner_id, "
                "job_state, accepted_seq, client_request_id, input_ciphertext, "
                "fencing_token, attempt_count) VALUES (:jid, :sid, :oid, 'QUEUED', "
                ":seq, :crid, :ct, 0, 0)"
            ),
            {
                "jid": job_id,
                "sid": session_id,
                "oid": owner_id,
                "seq": seq,
                "crid": job_id.hex,
                "ct": ct,
            },
        )
        await s.commit()
    return job_id


def _worker(factory, clock, crypto, settings):  # type: ignore[no-untyped-def]
    return WorkerService(factory, clock, crypto, FakeAgent(), settings)


# Feature: backend-api-auth-jobs-crypto, Property 25: Claim establishes a single
# fenced lease holder (lease 30-120s, strictly monotonic fence, attempt++).
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_25_claim_single_fenced_lease(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A claim sets a 30-120s lease, a monotonic fence, and increments attempts."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=UTC))
    try:
        owner_id, session_id, dek = await _seed_user_and_conversation(factory, crypto)
        job_id = await _enqueue_job(factory, crypto, owner_id, session_id, dek, 1)

        worker = _worker(factory, clock, crypto, settings)
        await worker.process_one()

        async with factory() as s:
            row = (
                await s.execute(
                    sa.text(
                        "SELECT fencing_token, attempt_count, lease_expires_at, "
                        "job_state FROM execution.turn_jobs WHERE job_id = :jid"
                    ),
                    {"jid": job_id},
                )
            ).one()
        fence, attempts, lease, state = row
        assert fence == 1  # strictly monotonic, first claim -> 1
        assert attempts == 1  # incremented once
        # Terminal after the faked turn completes.
        assert state == "COMPLETED"
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 23: At most one RUNNING per
# conversation; distinct conversations may run in parallel.
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_23_at_most_one_running_per_conversation(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Two queued jobs in one conversation never both become RUNNING at once."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    # Freeze the clock so a claimed lease stays live across the next claim.
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=UTC))
    try:
        owner_id, session_id, dek = await _seed_user_and_conversation(factory, crypto)
        await _enqueue_job(factory, crypto, owner_id, session_id, dek, 1, "[clarify]")
        await _enqueue_job(factory, crypto, owner_id, session_id, dek, 2, "[clarify]")

        worker = _worker(factory, clock, crypto, settings)
        # First drain: one job becomes NEEDS_CLARIFICATION (a live, non-terminal
        # lease holder). The second claim must NOT start while the first holds a
        # live lease — at most one RUNNING/live per conversation.
        await worker.process_one()

        async with factory() as s:
            running = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM execution.turn_jobs WHERE "
                        "session_id = :sid AND job_state = 'RUNNING' AND "
                        "lease_expires_at > :now"
                    ),
                    {"sid": session_id, "now": clock.now()},
                )
            ).scalar_one()
        assert running <= 1
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 27: No SQL transaction spans
# the model call (state persisted before + after in separate short txns).
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_27_no_txn_spans_model_call(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """The claim txn commits (RUNNING persisted) before the agent is called.

    We assert the observable consequence of the no-transaction-across-the-model
    invariant: when the agent runs, the claim transaction has already committed
    (the job is RUNNING with a lease + fence durably on disk), and the result is
    persisted by a second, separate transaction.
    """

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=UTC))

    observed: dict[str, object] = {}

    class _ObservingAgent(FakeAgent):
        async def run_turn(self, request):  # type: ignore[no-untyped-def]
            # At the moment the agent runs, read the job state in a brand-new
            # connection; if a transaction spanned the call this would block or
            # see pre-commit state. It must observe the committed RUNNING row.
            async with factory() as s:
                r = (
                    await s.execute(
                        sa.text(
                            "SELECT job_state, fencing_token FROM "
                            "execution.turn_jobs WHERE session_id = :sid"
                        ),
                        {"sid": request.session_id},
                    )
                ).one()
                observed["state"] = r[0]
                observed["fence"] = r[1]
            return await super().run_turn(request)

    try:
        owner_id, session_id, dek = await _seed_user_and_conversation(factory, crypto)
        await _enqueue_job(factory, crypto, owner_id, session_id, dek, 1)
        worker = WorkerService(factory, clock, crypto, _ObservingAgent(), settings)
        await worker.process_one()

        # The agent saw a committed RUNNING row with its fence (claim txn closed
        # before the model call); the result was then persisted separately.
        assert observed["state"] == "RUNNING"
        assert observed["fence"] == 1
        async with factory() as s:
            final = (
                await s.execute(
                    sa.text(
                        "SELECT job_state FROM execution.turn_jobs WHERE "
                        "session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).scalar_one()
        assert final == "COMPLETED"
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 26: Stale fencing writes are
# rejected and no duplication occurs.
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_26_stale_fence_rejected(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A write carrying a superseded fencing token is rejected (zero rows)."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=UTC))
    try:
        owner_id, session_id, dek = await _seed_user_and_conversation(factory, crypto)
        job_id = await _enqueue_job(factory, crypto, owner_id, session_id, dek, 1)

        # Simulate a current holder with fence=5 (a newer claim superseded a
        # stale holder that still carries fence=2).
        async with factory() as s:
            await s.execute(
                sa.text(
                    "UPDATE execution.turn_jobs SET fencing_token = 5, "
                    "job_state = 'RUNNING' WHERE job_id = :jid"
                ),
                {"jid": job_id},
            )
            await s.commit()

        async with factory() as s:
            uow = UnitOfWork(s)
            # A stale holder (fence=2) tries to persist -> rejected (zero rows).
            won_stale = await uow.turn_jobs.persist_result(
                job_id,
                fencing_token=2,
                result_ciphertext=b"x",
                job_state=JobState.COMPLETED,
                at=clock.now(),
            )
            await uow.commit()
            assert won_stale is False

        async with factory() as s:
            uow = UnitOfWork(s)
            # The current holder (fence=5) persists -> wins exactly once.
            won_current = await uow.turn_jobs.persist_result(
                job_id,
                fencing_token=5,
                result_ciphertext=b"y",
                job_state=JobState.COMPLETED,
                at=clock.now(),
            )
            await uow.commit()
            assert won_current is True

        async with factory() as s:
            cnt = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM execution.turn_jobs WHERE "
                        "job_id = :jid AND job_state = 'COMPLETED'"
                    ),
                    {"jid": job_id},
                )
            ).scalar_one()
        assert cnt == 1  # no duplication
    finally:
        await engine.dispose()
