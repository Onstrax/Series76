"""Spec 6 Properties 19-23, 27, 28: adversarial security on real PostgreSQL.

Runs the Spec 3 API in-process (faked agent seam, zero spend) against a
Testcontainers PostgreSQL. Each property drives the HTTP surface as an attacker
would and inspects the database directly where the property is about storage.
"""

from __future__ import annotations

import statistics
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from series76_api.application.agent_seam import FakeAgent
from series76_api.application.worker_service import WorkerService, _ClaimedJob
from series76_api.domain.models import JobState
from series76_api.infrastructure.clock import FixedClock
from series76_api.infrastructure.crypto import CryptoService

from ._spec3_app import build_settings, create_test_session_factory, spec3_client
from ._spec3_helpers import (
    STRONG_PASSWORD,
    auth_header,
    register_and_login,
    seed_developer_and_login,
    unique_email,
)
from .test_spec3_jobs_api import _drain, _enqueue

pytestmark = pytest.mark.integration

_SLOW = settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
_VOLATILE = {"request_id", "correlation_id", "trace_id", "timestamp"}


def _stable(body: Any) -> Any:
    """Drop per-request identifiers so two denials can be compared byte-for-byte."""

    if isinstance(body, dict):
        return {k: _stable(v) for k, v in body.items() if k not in _VOLATILE}
    if isinstance(body, list):
        return [_stable(v) for v in body]
    return body


async def _timed(client, method: str, url: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    resp = await client.request(method, url, headers=headers)
    return resp, (time.perf_counter() - start) * 1000


# Feature: evaluation-and-reproducibility, Property 19: Cross-owner and cross-developer access is denied indistinguishably
@_SLOW
@given(kind=st.sampled_from(["messages", "job", "trace", "delete"]))
async def test_property_19_cross_owner_denied_indistinguishably(
    kind: str, postgres_url: str, migrated_db_module: Config
) -> None:
    async with spec3_client(postgres_url) as (client, _app, _clock):
        if kind == "trace":  # developer vs developer
            _e, owner = await seed_developer_and_login(client, postgres_url)
            _e, other = await seed_developer_and_login(client, postgres_url)
        else:
            _e, owner = await register_and_login(client)
            _e, other = await register_and_login(client)
        created = await client.post(
            "/api/conversation", json={"query": "secret-title-q"}, headers=owner
        )
        sid = created.json()["session_id"]
        mid = (await client.get(f"/api/sessions/{sid}/messages", headers=owner)).json()[-1][
            "message_id"
        ]
        job_id = (await _enqueue(client, owner, "queued work", session_id=sid)).json()["job_id"]
        ghost = str(uuid.uuid4())
        urls = {
            "messages": ("GET", f"/api/sessions/{sid}/messages", f"/api/sessions/{ghost}/messages"),
            "job": ("GET", f"/api/jobs/{job_id}", f"/api/jobs/{ghost}"),
            "trace": (
                "GET",
                f"/api/sessions/{sid}/messages/{mid}/trace",
                f"/api/sessions/{ghost}/messages/{ghost}/trace",
            ),
            "delete": ("DELETE", f"/api/sessions/{sid}", f"/api/sessions/{ghost}"),
        }
        method, real, missing = urls[kind]
        real_ms, missing_ms = [], []
        for _ in range(5):
            r_real, t_real = await _timed(client, method, real, other)
            r_missing, t_missing = await _timed(client, method, missing, other)
            real_ms.append(t_real)
            missing_ms.append(t_missing)
            assert r_real.status_code in (403, 404) and r_real.status_code == r_missing.status_code
            assert _stable(r_real.json()) == _stable(r_missing.json())
            assert (
                abs(len(r_real.content) - len(r_missing.content)) <= 64
            )  # only volatile ids differ
            for leak in (sid, job_id, mid, "secret-title-q"):
                assert leak not in r_real.text
            assert t_real < 2000
        assert abs(statistics.median(real_ms) - statistics.median(missing_ms)) <= 50
        # The owner's resource is untouched by the denied attempts.
        assert (await client.get(f"/api/sessions/{sid}/messages", headers=owner)).status_code == 200


privilege = st.sampled_from(
    [
        {"role": "developer"},
        {"role": "DEVELOPER"},
        {"is_admin": True},
        {"roles": ["developer"]},
        {"role": "developer", "permissions": ["debug"]},
        {"scope": "developer"},
    ]
)


# Feature: evaluation-and-reproducibility, Property 20: Client-forced privilege never yields a developer account
@_SLOW
@given(extra=privilege)
async def test_property_20_forced_privilege_never_developer(
    extra: dict[str, Any], postgres_url: str, migrated_db_module: Config
) -> None:
    async with spec3_client(postgres_url) as (client, _app, _clock):
        email = unique_email("priv")
        reg = await client.post(
            "/api/auth/register", json={"email": email, "password": STRONG_PASSWORD, **extra}
        )
        assert reg.status_code in (201, 400, 422)
        if reg.status_code == 201:
            login = await client.post(
                "/api/auth/login", json={"email": email, "password": STRONG_PASSWORD}
            )
            me = await client.get("/api/auth/me", headers=auth_header(login.json()["access_token"]))
            assert me.json()["role"] == "user"
    factory, engine = create_test_session_factory(postgres_url)
    try:
        async with factory() as s:
            dev = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM identity.users WHERE email = :e AND role = 'developer'"
                    ),
                    {"e": email},
                )
            ).scalar_one()
        assert dev == 0  # never persisted as developer
    finally:
        await engine.dispose()


# Feature: evaluation-and-reproducibility, Property 21: Refresh-token reuse revokes the family
@_SLOW
@given(rotations=st.integers(1, 3), reuse_index=st.integers(0, 2))
async def test_property_21_refresh_reuse_revokes_family(
    rotations: int, reuse_index: int, postgres_url: str, migrated_db_module: Config
) -> None:
    async with spec3_client(postgres_url) as (client, _app, _clock):
        email = unique_email("rt")
        await client.post("/api/auth/register", json={"email": email, "password": STRONG_PASSWORD})
        pair = (
            await client.post("/api/auth/login", json={"email": email, "password": STRONG_PASSWORD})
        ).json()
        chain = [pair["refresh_token"]]
        for _ in range(rotations):
            pair = (
                await client.post("/api/auth/refresh", json={"refresh_token": chain[-1]})
            ).json()
            chain.append(pair["refresh_token"])
        reused = chain[min(reuse_index, len(chain) - 2)]  # an already-exchanged token
        again = await client.post("/api/auth/refresh", json={"refresh_token": reused})
        assert again.status_code == 401
        # The whole family is revoked in that same request: the newest token is dead too.
        newest = await client.post("/api/auth/refresh", json={"refresh_token": chain[-1]})
        assert newest.status_code == 401


# Feature: evaluation-and-reproducibility, Property 22: Logged-out tokens perform no authorized action
@_SLOW
@given(action=st.sampled_from(["me", "list", "turn", "job", "refresh"]))
async def test_property_22_logged_out_tokens_powerless(
    action: str, postgres_url: str, migrated_db_module: Config
) -> None:
    async with spec3_client(postgres_url) as (client, _app, _clock):
        email = unique_email("lo")
        await client.post("/api/auth/register", json={"email": email, "password": STRONG_PASSWORD})
        pair = (
            await client.post("/api/auth/login", json={"email": email, "password": STRONG_PASSWORD})
        ).json()
        headers = auth_header(pair["access_token"])
        assert (await client.post("/api/auth/logout", headers=headers)).status_code in (200, 204)
        before = len(
            (
                await client.get("/api/sessions", headers=(await register_and_login(client))[1])
            ).json()
        )
        calls = {
            "me": lambda: client.get("/api/auth/me", headers=headers),
            "list": lambda: client.get("/api/sessions", headers=headers),
            "turn": lambda: client.post("/api/conversation", json={"query": "x"}, headers=headers),
            "job": lambda: _enqueue(client, headers, "x"),
            "refresh": lambda: client.post(
                "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
            ),
        }
        resp = await calls[action]()
        assert resp.status_code == 401
        assert before == 0
    factory, engine = create_test_session_factory(postgres_url)
    try:
        async with factory() as s:
            created = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM conversation.conversations c JOIN identity.users u "
                        "ON u.id = c.owner_id WHERE u.email = :e"
                    ),
                    {"e": email},
                )
            ).scalar_one()
        assert created == 0  # no authorized action took effect
    finally:
        await engine.dispose()


# Feature: evaluation-and-reproducibility, Property 23: Stored sensitive fields reveal no plaintext
@_SLOW
@given(marker=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=12, max_size=20))
async def test_property_23_dump_reveals_no_plaintext(
    marker: str, postgres_url: str, migrated_db_module: Config
) -> None:
    plaintext = f"zq{marker}qz"
    settings_ = build_settings(postgres_url)
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _e, headers = await register_and_login(client)
        created = await client.post("/api/conversation", json={"query": plaintext}, headers=headers)
        sid = created.json()["session_id"]
        await _enqueue(client, headers, f"job {plaintext}", session_id=sid)
    await _drain(settings_)
    factory, engine = create_test_session_factory(postgres_url)
    try:
        async with factory() as s:
            tables = (
                await s.execute(
                    sa.text(
                        "SELECT table_schema, table_name FROM information_schema.tables "
                        "WHERE table_schema IN ('conversation', 'execution', 'identity') "
                        "AND table_type = 'BASE TABLE'"
                    )
                )
            ).all()
            assert tables
            dump = []
            for schema, table in tables:
                rows = (
                    (
                        await s.execute(
                            sa.text(f'SELECT row_to_json(t)::text FROM "{schema}"."{table}" t')
                        )
                    )
                    .scalars()
                    .all()
                )
                dump.extend(rows)
        blob = "\n".join(dump)
        assert plaintext not in blob
        assert plaintext.encode().hex() not in blob  # nor as raw bytea bytes
    finally:
        await engine.dispose()


# Feature: evaluation-and-reproducibility, Property 27: Delete-during-job never resurrects data
@_SLOW
@given(fence_offset=st.integers(-2, 0))
async def test_property_27_delete_during_job_no_resurrection(
    fence_offset: int, postgres_url: str, migrated_db_module: Config
) -> None:
    settings_ = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings_.resolve_kek_base64())
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _e, headers = await register_and_login(client)
        sid = (
            await client.post("/api/conversation", json={"query": "hi"}, headers=headers)
        ).json()["session_id"]
        mid = (await client.get(f"/api/sessions/{sid}/messages", headers=headers)).json()[-1][
            "message_id"
        ]
        job_id = (await _enqueue(client, headers, "work", session_id=sid)).json()["job_id"]
        assert (await client.delete(f"/api/sessions/{sid}", headers=headers)).status_code in (
            200,
            202,
            204,
        )

        factory, engine = create_test_session_factory(postgres_url)
        try:
            async with factory() as s:
                row = (
                    await s.execute(
                        sa.text(
                            "SELECT tombstone_fence, owner_id FROM conversation.conversations WHERE session_id = :sid"
                        ),
                        {"sid": sid},
                    )
                ).one()
            worker = WorkerService(
                factory,
                FixedClock(datetime(2025, 1, 1, tzinfo=UTC)),
                crypto,
                FakeAgent(),
                settings_,
            )
            late = _ClaimedJob(
                uuid.UUID(job_id), uuid.UUID(sid), row[1], int(row[0]) + fence_offset, "work", None
            )
            assert (
                await worker._persist_phase(late, result_ct=b"late", state=JobState.COMPLETED)
                is False
            )
            await _drain(settings_)  # a real worker pass after the delete changes nothing either
            async with factory() as s:
                msgs = (
                    await s.execute(
                        sa.text(
                            "SELECT count(*) FROM conversation.messages WHERE session_id = :sid"
                        ),
                        {"sid": sid},
                    )
                ).scalar_one()
                live = (
                    await s.execute(
                        sa.text(
                            "SELECT deleted_at IS NOT NULL FROM conversation.conversations WHERE session_id = :sid"
                        ),
                        {"sid": sid},
                    )
                ).scalar_one()
            assert msgs == 0 and live is True
        finally:
            await engine.dispose()

        ghost = str(uuid.uuid4())
        pairs = [
            (f"/api/sessions/{sid}/messages", f"/api/sessions/{ghost}/messages"),
            (
                f"/api/sessions/{sid}/messages/{mid}/trace",
                f"/api/sessions/{ghost}/messages/{ghost}/trace",
            ),
        ]
        for real, missing in pairs:
            r_real = await client.get(real, headers=headers)
            r_missing = await client.get(missing, headers=headers)
            assert r_real.status_code == r_missing.status_code and r_real.status_code in (403, 404)
            assert _stable(r_real.json()) == _stable(r_missing.json())
        listing = (await client.get("/api/sessions", headers=headers)).json()
        assert sid not in {s["session_id"] for s in listing}


# Feature: evaluation-and-reproducibility, Property 28: Duplicate or retried turns produce exactly one effect
@_SLOW
@given(duplicates=st.integers(2, 4), drains=st.integers(1, 3))
async def test_property_28_exactly_one_effect(
    duplicates: int, drains: int, postgres_url: str, migrated_db_module: Config
) -> None:
    settings_ = build_settings(postgres_url)
    crid = str(uuid.uuid4())
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _e, headers = await register_and_login(client)
        sid = (
            await client.post("/api/conversation", json={"query": "hi"}, headers=headers)
        ).json()["session_id"]
        ids = set()
        for _ in range(duplicates):
            r = await _enqueue(client, headers, "same turn", session_id=sid, crid=crid)
            assert r.status_code in (200, 202)
            ids.add(r.json()["job_id"])
        assert len(ids) == 1  # one job per idempotency key
        for _ in range(drains):  # retried / repeated worker passes
            await _drain(settings_)
        messages = (await client.get(f"/api/sessions/{sid}/messages", headers=headers)).json()
        effects = [m for m in messages if m["role"] == "user" and m["content"] == "same turn"]
        assert len(effects) == 1
        job = (await client.get(f"/api/jobs/{ids.pop()}", headers=headers)).json()
        assistant = [m["message_id"] for m in messages if m["role"] == "assistant"]
        assert job["response"]["message_id"] in assistant
        assert len(assistant) == 2  # the first sync turn + exactly one async effect
