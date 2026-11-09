"""Spec 3 app smoke + developer-seed integration tests (real PostgreSQL).

* The app factory boots against the migrated container and ``/api/health`` and
  ``/api/ready`` respond; readiness distinguishes database from key material.
* The developer-seed CLI provisions a ``developer`` account (the only path that
  can), and no public endpoint ever yields one.

Named with ``spec3``/``api``/``auth`` for selectability.
"""

from __future__ import annotations

import uuid

import pytest
from alembic.config import Config

from series76_api.domain.models import UserRole
from series76_api.infrastructure.engine import create_app_engine, create_session_factory
from series76_api.infrastructure.orm import UserORM
from series76_api.seed import seed_account

from ._spec3_app import spec3_client

pytestmark = pytest.mark.integration

_STRONG_PASSWORD = "Str0ng-Passw0rd!"


async def test_spec3_api_health_and_ready(migrated_db: Config, postgres_url: str) -> None:
    """Health returns ok; readiness reports database and key-material status."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        health = await client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        ready = await client.get("/api/ready")
        assert ready.status_code == 200
        body = ready.json()
        assert body["dependencies"]["database"] is True
        # The test app is configured with a real KEK.
        assert body["dependencies"]["key_material"] is True
        assert body["ready"] is True


async def test_spec3_auth_developer_seed_cli_only(
    migrated_db: Config, postgres_url: str
) -> None:
    """The seed CLI creates a developer; no public endpoint can (idempotent)."""

    email = f"dev-{uuid.uuid4().hex}@example.com"

    account_id = await seed_account(
        postgres_url, email=email, password=_STRONG_PASSWORD, role=UserRole.DEVELOPER
    )
    # Idempotent: re-seeding the same email returns the same id, no duplicate.
    again = await seed_account(
        postgres_url, email=email, password=_STRONG_PASSWORD, role=UserRole.DEVELOPER
    )
    assert account_id == again

    engine = create_app_engine(postgres_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            user = await session.get(UserORM, account_id)
            assert user is not None
            assert user.role == UserRole.DEVELOPER
    finally:
        await engine.dispose()

    # No public registration path yields a developer, even trying to seed-dup
    # the developer's email through /register (it would be a generic conflict).
    async with spec3_client(postgres_url) as (client, _app, _clock):
        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": _STRONG_PASSWORD, "role": "developer"},
        )
        # Email already exists -> generic conflict; never elevates to developer.
        assert reg.status_code == 409
        # A brand-new public registration is always a user.
        fresh = await client.post(
            "/api/auth/register",
            json={
                "email": f"u-{uuid.uuid4().hex}@example.com",
                "password": _STRONG_PASSWORD,
                "role": "developer",
            },
        )
        assert fresh.status_code == 201
        assert fresh.json()["role"] == "user"
