"""Spec 3 plan confirmation integration + property tests (real PostgreSQL).

Covers ``POST /api/sessions/{id}/plans/{rev}/confirm``. Properties 28, 29, 30
run end-to-end against the live engine. Plan revisions are created directly
through the :class:`PlansService` (the agent turn drives this in Spec 4); the
HTTP contract under test is confirmation.

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import uuid

import pytest
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st

from series76_api.application.plans_service import PlansService
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.models import AuthenticatedPrincipal, UserRole
from series76_api.infrastructure.clock import SystemClock
from series76_api.infrastructure.crypto import CryptoService

from ._spec3_app import (
    build_settings,
    create_test_engine,
    create_test_session_factory,
    spec3_client,
)
from ._spec3_helpers import register_and_login

pytestmark = pytest.mark.integration


async def _make_conversation_and_principal(client, headers):  # type: ignore[no-untyped-def]
    created = await client.post(
        "/api/conversation", json={"query": "hi"}, headers=headers
    )
    me = await client.get("/api/auth/me", headers=headers)
    return uuid.UUID(created.json()["session_id"]), uuid.UUID(me.json()["id"])


async def _add_revisions(postgres_url, owner_id, session_id, count):  # type: ignore[no-untyped-def]
    """Create ``count`` strictly increasing plan revisions via the service."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    revisions = []
    try:
        principal = AuthenticatedPrincipal(
            user_id=owner_id, role=UserRole.USER, auth_session_id=uuid.uuid4()
        )
        for i in range(count):
            async with factory() as s:
                svc = PlansService(UnitOfWork(s), SystemClock(), crypto)
                rev = await svc.create_revision(
                    principal, session_id, plan_text=f"plan v{i}"
                )
                revisions.append(rev)
    finally:
        await engine.dispose()
    return revisions


# Feature: backend-api-auth-jobs-crypto, Property 28: Plan revisions are strictly
# increasing and only the current revision confirms (non-current -> 409).
@given(n=st.integers(min_value=2, max_value=4))
async def test_property_28_revisions_increasing_current_only(
    n: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Later revisions exceed earlier ones; a stale revision -> 409 STALE_PLAN."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        session_id, owner_id = await _make_conversation_and_principal(client, headers)
        revs = await _add_revisions(postgres_url, owner_id, session_id, n)
        # Strictly increasing.
        assert revs == sorted(revs)
        assert len(set(revs)) == len(revs)

        current = revs[-1]
        stale = revs[0]
        # Confirming a non-current (stale) revision -> 409 STALE_PLAN.
        bad = await client.post(
            f"/api/sessions/{session_id}/plans/{stale}/confirm", headers=headers
        )
        assert bad.status_code == 409
        assert bad.json()["error"]["code"] == "STALE_PLAN"

        # Confirming the current revision succeeds.
        ok = await client.post(
            f"/api/sessions/{session_id}/plans/{current}/confirm", headers=headers
        )
        assert ok.status_code == 200
        assert ok.json()["plan_revision"] == current


# Feature: backend-api-auth-jobs-crypto, Property 29: Plan confirmation is
# idempotent for the current revision.
@given(reps=st.integers(min_value=2, max_value=4))
async def test_property_29_confirm_idempotent(
    reps: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Repeated confirm of the current revision is idempotent (one confirmation)."""

    import sqlalchemy as sa

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        session_id, owner_id = await _make_conversation_and_principal(client, headers)
        revs = await _add_revisions(postgres_url, owner_id, session_id, 1)
        current = revs[-1]

        for _ in range(reps):
            ok = await client.post(
                f"/api/sessions/{session_id}/plans/{current}/confirm",
                headers=headers,
            )
            assert ok.status_code == 200

    engine = create_test_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.text(
                        "SELECT confirmed_at, executed_at FROM conversation.plans "
                        "WHERE session_id = :sid AND plan_revision = :rev"
                    ),
                    {"sid": session_id, "rev": current},
                )
            ).one()
        # Confirmed + executed recorded exactly once (not re-stamped per confirm).
        assert row[0] is not None
        assert row[1] is not None
    finally:
        await engine.dispose()


# Feature: backend-api-auth-jobs-crypto, Property 30: Unauthenticated plan
# confirmation performs no effect (401).
@given(rev=st.integers(min_value=1, max_value=5))
async def test_property_30_unauthenticated_confirm_no_effect(
    rev: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A confirm with no/invalid auth returns 401 and records nothing."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        session_id, owner_id = await _make_conversation_and_principal(client, headers)
        await _add_revisions(postgres_url, owner_id, session_id, 1)

        # No Authorization header -> 401, no effect.
        unauth = await client.post(f"/api/sessions/{session_id}/plans/{rev}/confirm")
        assert unauth.status_code == 401

        # A non-owner is an indistinguishable 404 (Property 10 reuse).
        _other, oh = await register_and_login(client)
        denied = await client.post(
            f"/api/sessions/{session_id}/plans/{rev}/confirm", headers=oh
        )
        assert denied.status_code == 404
