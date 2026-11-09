"""Spec 3 deletion + debug-trace integration + property tests (real PostgreSQL).

Covers ``DELETE /api/sessions/{id}`` (tombstone + crypto-shred + no
resurrection) and ``GET /api/sessions/{id}/messages/{mid}/trace`` (developer-
owner sanitized, else identical denial). Properties 31, 32, 33, 34, 46 run
end-to-end against the live engine. The faked agent seam means zero provider
spend; traces are seeded directly (the agent writes them in Spec 4).

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st

from series76_api.application.agent_seam import FakeAgent
from series76_api.application.worker_service import WorkerService
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.models import JobState
from series76_api.infrastructure.clock import FixedClock
from series76_api.infrastructure.crypto import CryptoService

from ._spec3_app import (
    build_settings,
    create_test_engine,
    create_test_session_factory,
    spec3_client,
)
from ._spec3_helpers import register_and_login, seed_developer_and_login

pytestmark = pytest.mark.integration


# Feature: backend-api-auth-jobs-crypto, Property 31: Deletion cancels,
# tombstones, purges, and crypto-shreds.
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_31_delete_tombstone_purge_shred(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Delete returns 204, cancels jobs, purges content, and shreds the DEK."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=headers
        )
        session_id = created.json()["session_id"]
        await client.post(
            "/api/conversation/jobs",
            json={"query": "work", "session_id": session_id},
            headers=headers,
        )

        resp = await client.delete(f"/api/sessions/{session_id}", headers=headers)
        assert resp.status_code == 204

    engine = create_test_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            # Messages purged.
            msg_count = (
                await conn.execute(
                    sa.text(
                        "SELECT count(*) FROM conversation.messages WHERE "
                        "session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).scalar_one()
            assert msg_count == 0
            # Jobs cancelled, sensitive input/result nulled.
            jobs = (
                await conn.execute(
                    sa.text(
                        "SELECT job_state, input_ciphertext, result_ciphertext FROM "
                        "execution.turn_jobs WHERE session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).fetchall()
            assert all(j[0] == "CANCELLED" for j in jobs)
            assert all(j[1] is None and j[2] is None for j in jobs)
            # DEK crypto-shredded (wrapped_dek emptied, shredded_at set).
            km = (
                await conn.execute(
                    sa.text(
                        "SELECT wrapped_dek, shredded_at FROM execution.key_metadata "
                        "WHERE session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).one()
            assert bytes(km[0]) == b""
            assert km[1] is not None
            # Tombstone fence recorded.
            conv = (
                await conn.execute(
                    sa.text(
                        "SELECT deleted_at, tombstone_fence FROM "
                        "conversation.conversations WHERE session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).one()
            assert conv[0] is not None
            assert conv[1] is not None and conv[1] >= 1
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 32: No resurrection of a
# deleted conversation (late fenced write blocked).
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_32_no_resurrection(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A worker write whose fence <= the tombstone token is blocked."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=UTC))

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=headers
        )
        session_id = created.json()["session_id"]
        accepted = await client.post(
            "/api/conversation/jobs",
            json={"query": "work", "session_id": session_id},
            headers=headers,
        )
        job_id = accepted.json()["job_id"]
        # Delete the conversation (writes a tombstone fence).
        await client.delete(f"/api/sessions/{session_id}", headers=headers)

    try:
        # A worker that claimed BEFORE the delete would carry a fence <=
        # tombstone. Simulate its late result write directly via the worker's
        # persist phase: it must be blocked (no resurrection).
        from series76_api.application.worker_service import _ClaimedJob

        worker = WorkerService(factory, clock, crypto, FakeAgent(), settings)
        # Read the tombstone fence; use an equal fence (<= tombstone) to attempt
        # a late write.
        async with factory() as s:
            fence = (
                await s.execute(
                    sa.text(
                        "SELECT tombstone_fence FROM conversation.conversations "
                        "WHERE session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).scalar_one()
        claimed = _ClaimedJob(
            job_id=uuid.UUID(job_id),
            session_id=uuid.UUID(session_id),
            owner_id=uuid.uuid4(),
            fencing_token=int(fence),  # <= tombstone -> must be blocked
            query="work",
            existing_result=None,
        )
        won = await worker._persist_phase(
            claimed, result_ct=b"late", state=JobState.COMPLETED
        )
        assert won is False  # blocked, no resurrection

        # The conversation + its messages are not recreated.
        async with factory() as s:
            msgs = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM conversation.messages WHERE "
                        "session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).scalar_one()
        assert msgs == 0
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 33: Non-owner deletion has no
# effect.
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_33_non_owner_delete_no_effect(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A non-owner DELETE returns 404 and does not tombstone/purge anything."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=headers
        )
        session_id = created.json()["session_id"]

        _other, oh = await register_and_login(client)
        denied = await client.delete(f"/api/sessions/{session_id}", headers=oh)
        assert denied.status_code == 404

        # The owner's conversation is untouched (not deleted) and still readable.
        msgs = await client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        assert msgs.status_code == 200
        assert len(msgs.json()) == 2


# Feature: backend-api-auth-jobs-crypto, Property 34: Deleted and not-owned
# references are indistinguishable.
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_34_deleted_vs_not_owned_indistinguishable(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A deleted conversation -> 410; a not-owned/nonexistent -> 404; no body."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=headers
        )
        session_id = created.json()["session_id"]

        first = await client.delete(f"/api/sessions/{session_id}", headers=headers)
        assert first.status_code == 204
        # Re-deleting a previously deleted conversation -> 410.
        again = await client.delete(f"/api/sessions/{session_id}", headers=headers)
        assert again.status_code == 410
        # A nonexistent conversation -> 404 (indistinguishable from not-owned).
        missing = await client.delete(f"/api/sessions/{uuid.uuid4()}", headers=headers)
        assert missing.status_code == 404
        # A not-owned existing conversation -> 404 as well.
        _other, oh = await register_and_login(client)
        other_created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=oh
        )
        other_sid = other_created.json()["session_id"]
        not_owned = await client.delete(f"/api/sessions/{other_sid}", headers=headers)
        assert not_owned.status_code == 404


# Feature: backend-api-auth-jobs-crypto, Property 46: Trace access returns
# sanitized content to the developer-owner or a byte-for-byte identical denial.
@given(secret=st.text(min_size=6, max_size=20))
async def test_property_46_trace_developer_owner_or_identical_denial(
    secret: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """Only a developer-owner gets a sanitized trace; all others get one denial."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)

    async with spec3_client(postgres_url) as (client, _app, _clock):
        # A developer owner creates a conversation with a message + trace.
        dev_email, dev_headers = await seed_developer_and_login(client, postgres_url)
        me = await client.get("/api/auth/me", headers=dev_headers)
        owner_id = uuid.UUID(me.json()["id"])
        created = await client.post(
            "/api/conversation", json={"query": "hi"}, headers=dev_headers
        )
        session_id = uuid.UUID(created.json()["session_id"])
        msgs = await client.get(
            f"/api/sessions/{session_id}/messages", headers=dev_headers
        )
        message_id = uuid.UUID(msgs.json()[0]["message_id"])

        # Seed an encrypted trace carrying a secret-looking field.
        async with factory() as s:
            dek_row = (
                await s.execute(
                    sa.text(
                        "SELECT wrapped_dek FROM execution.key_metadata WHERE "
                        "session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).scalar_one()
            dek = crypto.unwrap_dek(
                bytes(dek_row), owner_id=owner_id, conversation_id=session_id
            )
            trace_id = uuid.uuid4()
            raw = {
                "tool_args": {"part_number": "ABC", "authorization": secret},
                "tool_results": [{"value": "7V", "token": secret}],
                "duration_ms": 42,
            }
            ct = crypto.encrypt(
                dek,
                json.dumps(raw).encode("utf-8"),
                AADContext(
                    purpose=CryptoPurpose.TOOL_TRACE,
                    owner_id=owner_id,
                    conversation_id=session_id,
                    record_id=trace_id,
                ),
            ).blob
            await s.execute(
                sa.text(
                    "INSERT INTO execution.tool_traces (id, message_id, session_id, "
                    "owner_id, trace_ciphertext, duration_ms) VALUES "
                    "(:id, :mid, :sid, :oid, :ct, 42)"
                ),
                {
                    "id": trace_id,
                    "mid": message_id,
                    "sid": session_id,
                    "oid": owner_id,
                    "ct": ct,
                },
            )
            await s.commit()

        trace_url = f"/api/sessions/{session_id}/messages/{message_id}/trace"

        # Developer-owner: sanitized trace, no secret.
        ok = await client.get(trace_url, headers=dev_headers)
        assert ok.status_code == 200
        assert secret not in ok.text
        assert "authorization" not in ok.text
        assert ok.json()["tool_args"]["part_number"] == "ABC"
        assert ok.json()["duration_ms"] == 42

        # Collect denial responses for every unauthorized case; assert identical.
        denials = []
        # (a) a plain user (non-developer).
        _u_email, user_headers = await register_and_login(client)
        denials.append(await client.get(trace_url, headers=user_headers))
        # (b) a different developer (developer A vs developer B).
        _dev2_email, dev2_headers = await seed_developer_and_login(client, postgres_url)
        denials.append(await client.get(trace_url, headers=dev2_headers))
        # (c) unauthenticated.
        denials.append(await client.get(trace_url))
        # (d) nonexistent message for the developer-owner.
        denials.append(
            await client.get(
                f"/api/sessions/{session_id}/messages/{uuid.uuid4()}/trace",
                headers=dev_headers,
            )
        )

    for d in denials:
        assert d.status_code == 404
        assert d.json() == {"error": "not_found"}
    # Byte-for-byte identical across every denied case.
    bodies = {d.content for d in denials}
    assert len(bodies) == 1

    await engine.dispose()
