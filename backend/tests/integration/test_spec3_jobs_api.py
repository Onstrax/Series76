"""Spec 3 async jobs API integration + property tests (real PostgreSQL).

Covers ``POST /api/conversation/jobs`` (202 + caps), ``GET /api/jobs/{id}``
(state + shared envelope + headers), and ``POST /api/jobs/{id}/cancel``
(idempotent). Properties 17, 18, 19, 20, 21, 22, 24 run end-to-end against the
live engine through the FastAPI app with the faked agent seam; the worker drain
is invoked in-process to complete a job for the poll-envelope property.

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import uuid

import pytest
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st

from series76_api.application.agent_seam import FakeAgent
from series76_api.application.worker_service import WorkerService
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.settings import Settings

from ._spec3_app import (
    build_settings,
    create_test_engine,
    create_test_session_factory,
    spec3_client,
)
from ._spec3_helpers import register_and_login

pytestmark = pytest.mark.integration


async def _enqueue(client, headers, query, *, session_id=None, crid=None):  # type: ignore[no-untyped-def]
    body = {"query": query}
    if session_id is not None:
        body["session_id"] = session_id
    if crid is not None:
        body["client_request_id"] = crid
    return await client.post("/api/conversation/jobs", json=body, headers=headers)


async def _drain(settings: Settings) -> None:
    """Drain the queue once in-process with the faked agent (zero spend)."""

    factory, engine = create_test_session_factory(settings.database_url)
    try:
        crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
        worker = WorkerService(factory, _Clock(), crypto, FakeAgent(), settings)
        # Drain until empty.
        while await worker.process_one() is not None:
            pass
    finally:
        await engine.dispose()


class _Clock:
    def now(self):  # type: ignore[no-untyped-def]
        from datetime import UTC, datetime

        return datetime.now(UTC)


# Feature: backend-api-auth-jobs-crypto, Property 17: Job acceptance returns 202
# with a QUEUED state; invalid/unauthorized creates nothing.
@given(omit_session=st.booleans())
async def test_property_17_accept_202_queued(
    omit_session: bool, postgres_url: str, migrated_db_module: Config
) -> None:
    """A valid enqueue is 202/QUEUED with job_id+session; invalid creates nothing."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        session_id = None
        if not omit_session:
            created = await client.post(
                "/api/conversation", json={"query": "hi"}, headers=headers
            )
            session_id = created.json()["session_id"]

        resp = await _enqueue(client, headers, "do work", session_id=session_id)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "QUEUED"
        assert uuid.UUID(body["job_id"])
        assert body["session_id"]

        # Invalid query -> 422, nothing enqueued; unauthorized -> 401.
        bad = await _enqueue(client, headers, "   ")
        assert bad.status_code == 422
        unauth = await client.post("/api/conversation/jobs", json={"query": "x"})
        assert unauth.status_code == 401


# Feature: backend-api-auth-jobs-crypto, Property 18: Polling returns a valid
# state and the shared envelope on completion.
@given(marker=st.sampled_from(["", "[noresults]"]))
async def test_property_18_poll_state_and_envelope(
    marker: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """A completed job poll returns the shared envelope (session_id + answer)."""

    settings = build_settings(postgres_url)
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        accepted = await _enqueue(client, headers, f"work {marker}")
        job_id = accepted.json()["job_id"]
        session_id = accepted.json()["session_id"]

        # Before the worker runs: exactly one non-terminal state is returned.
        pending = await client.get(f"/api/jobs/{job_id}", headers=headers)
        assert pending.status_code == 200
        assert pending.json()["status"] == "QUEUED"

    await _drain(settings)

    async with spec3_client(postgres_url) as (client, _app, _clock):
        login = await client.post(
            "/api/auth/login", json={"email": _email, "password": "Str0ng-Passw0rd!"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        done = await client.get(f"/api/jobs/{job_id}", headers=headers)
        assert done.status_code == 200
        body = done.json()
        assert body["status"] == "COMPLETED"
        env = body["response"]
        assert env["session_id"] == session_id
        assert env["answer"]


# Feature: backend-api-auth-jobs-crypto, Property 19: Cancellation is idempotent.
@given(reps=st.integers(min_value=2, max_value=4))
async def test_property_19_cancel_idempotent(
    reps: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Cancelling a cancelable job is accepted and idempotent on repeat."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        accepted = await _enqueue(client, headers, "work")
        job_id = accepted.json()["job_id"]

        statuses = []
        for _ in range(reps):
            c = await client.post(f"/api/jobs/{job_id}/cancel", headers=headers)
            assert c.status_code == 200
            statuses.append(c.json()["status"])
        # Every cancel returns CANCELLED; no extra effect.
        assert all(s == "CANCELLED" for s in statuses)

        # Non-owner cancel is an indistinguishable 404.
        _other, oh = await register_and_login(client)
        denied = await client.post(f"/api/jobs/{job_id}/cancel", headers=oh)
        assert denied.status_code == 404


# Feature: backend-api-auth-jobs-crypto, Property 20: Polling headers are correct
# per state (Cache-Control always; Retry-After 1-60 non-terminal).
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_20_poll_headers(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """no-store is always set; a non-terminal state carries Retry-After 1-60."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        accepted = await _enqueue(client, headers, "work")
        job_id = accepted.json()["job_id"]

        resp = await client.get(f"/api/jobs/{job_id}", headers=headers)
        assert resp.headers.get("cache-control") == "no-store"
        # QUEUED is non-terminal -> Retry-After present, integer in [1, 60].
        ra = resp.headers.get("retry-after")
        assert ra is not None
        assert 1 <= int(ra) <= 60


# Feature: backend-api-auth-jobs-crypto, Property 21: Exceeding the pending-job
# cap rejects without side effects.
@given(_seed=st.integers(min_value=0, max_value=3))
async def test_property_21_pending_cap_rejects(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """The (cap+1)th pending job is RATE_LIMITED with no new job created."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        cap = 5  # default pending_job_cap
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=headers
        )
        session_id = created.json()["session_id"]
        for _ in range(cap):
            ok = await _enqueue(client, headers, "work", session_id=session_id)
            assert ok.status_code == 202

        over = await _enqueue(client, headers, "work", session_id=session_id)
        assert over.status_code == 429
        assert over.json()["error"]["code"] == "RATE_LIMITED"


# Feature: backend-api-auth-jobs-crypto, Property 24: Accepted_seq is
# transactional, strictly increasing, and not claim-order.
@given(n=st.integers(min_value=2, max_value=5))
async def test_property_24_accepted_seq_strictly_increasing(
    n: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Accepted turns in a conversation get strictly increasing accepted_seq."""

    import sqlalchemy as sa

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=headers
        )
        session_id = created.json()["session_id"]
        for _ in range(n):
            r = await _enqueue(client, headers, "work", session_id=session_id)
            assert r.status_code == 202

    engine = create_test_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT accepted_seq FROM execution.turn_jobs "
                        "WHERE session_id = :sid ORDER BY accepted_seq"
                    ),
                    {"sid": session_id},
                )
            ).fetchall()
        seqs = [r[0] for r in rows]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # strictly increasing (unique)
        assert all(b - a == 1 for a, b in zip(seqs, seqs[1:], strict=False))
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 22: Accepted jobs are durable
# across restart.
@given(marker=st.sampled_from(["", "[clarify]"]))
async def test_property_22_accepted_jobs_durable_across_restart(
    marker: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """An accepted job survives an app restart with its Job_State unchanged."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        accepted = await _enqueue(client, headers, f"work {marker}")
        job_id = accepted.json()["job_id"]
        assert accepted.json()["status"] == "QUEUED"

    # "Restart": a fresh app instance still resolves the durable job as QUEUED.
    async with spec3_client(postgres_url) as (client, _app, _clock):
        login = await client.post(
            "/api/auth/login", json={"email": _email, "password": "Str0ng-Passw0rd!"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = await client.get(f"/api/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "QUEUED"


@pytest.mark.parametrize(("marker", "state"), [("[clarify]", "NEEDS_CLARIFICATION"),
                                               ("[confirm]", "AWAITING_CONFIRMATION")])
async def test_poll_returns_the_clarification_or_plan_the_user_must_answer(
    marker: str, state: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """The question (or plan) is the turn's answer: polling must deliver it."""

    settings = build_settings(postgres_url)
    async with spec3_client(postgres_url) as (client, _app, _clock):
        email, headers = await register_and_login(client)
        accepted = await _enqueue(client, headers, f"work {marker}")
        job_id = accepted.json()["job_id"]
    await _drain(settings)
    async with spec3_client(postgres_url) as (client, _app, _clock):
        login = await client.post(
            "/api/auth/login", json={"email": email, "password": "Str0ng-Passw0rd!"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        polled = await client.get(f"/api/jobs/{job_id}", headers=headers)
    body = polled.json()
    assert body["status"] == state
    assert body["response"]["answer"]
    assert 1 <= int(polled.headers["Retry-After"]) <= 60  # still a pending state
