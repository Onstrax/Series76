"""Spec 3 seed CLI + cold-start reproducibility integration tests.

Verifies the seed CLI provisions BOTH demo accounts (a ``user`` and a
``developer``) from caller-supplied credentials, and that the app boots and
serves against a freshly migrated database with a degraded-but-non-fatal
provider dependency surfaced by ``/ready`` (Req 12.4, 12.5, 12.6).

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from series76_api.app import create_app
from series76_api.domain.models import UserRole
from series76_api.infrastructure.engine import create_app_engine, create_session_factory
from series76_api.infrastructure.orm import UserORM
from series76_api.infrastructure.settings import Settings
from series76_api.seed import seed_demo_accounts

from ._spec3_helpers import STRONG_PASSWORD

pytestmark = pytest.mark.integration


async def test_spec3_seed_demo_provisions_user_and_developer(
    migrated_db: Config, postgres_url: str
) -> None:
    """The seed CLI provisions a demo user and developer (idempotent)."""

    user_email = f"demo-user-{uuid.uuid4().hex}@example.com"
    dev_email = f"demo-dev-{uuid.uuid4().hex}@example.com"

    ids = await seed_demo_accounts(
        postgres_url,
        user_email=user_email,
        developer_email=dev_email,
        user_password=STRONG_PASSWORD,
        developer_password=STRONG_PASSWORD,
    )
    # Idempotent: re-running returns the same ids, no duplicates.
    again = await seed_demo_accounts(
        postgres_url,
        user_email=user_email,
        developer_email=dev_email,
        user_password=STRONG_PASSWORD,
        developer_password=STRONG_PASSWORD,
    )
    assert ids == again

    engine = create_app_engine(postgres_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as s:
            user = await s.get(UserORM, ids["user"])
            dev = await s.get(UserORM, ids["developer"])
            assert user is not None and user.role == UserRole.USER
            assert dev is not None and dev.role == UserRole.DEVELOPER
    finally:
        await engine.dispose()


async def test_spec3_cold_start_serves_with_degraded_provider(
    migrated_db: Config, postgres_url: str
) -> None:
    """The app boots and serves with NO provider configured; /ready is degraded.

    A missing provider key/model is a degraded-but-non-fatal dependency: the
    process starts, ``/health`` is live, and ``/ready`` reports the provider as
    ``False`` while the database + key material are available (Req 12.5).
    """

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        DATABASE_URL=postgres_url,
        ENCRYPTION_KEK=base64.b64encode(os.urandom(32)).decode("ascii"),
        OPENROUTER_API_KEY="",  # provider unreachable / unconfigured
        AGENT_MODEL="",
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        health = await client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        ready = await client.get("/api/ready")
        assert ready.status_code == 200
        deps = ready.json()["dependencies"]
        assert deps["database"] is True
        assert deps["key_material"] is True
        # Provider degraded but the process still serves (did not crash).
        assert deps["provider"] is False


def test_seed_demo_preloads_the_documented_test_users(
    migrated_db: Config, postgres_url: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`seed --demo` (run by the Compose migrate job) pre-loads both test users."""

    import asyncio

    from sqlalchemy import select

    from series76_api.seed import main

    suffix = uuid.uuid4().hex[:8]
    monkeypatch.setenv("DEMO_USER_EMAIL", f"user-{suffix}@example.com")
    monkeypatch.setenv("DEMO_DEVELOPER_EMAIL", f"dev-{suffix}@example.com")
    monkeypatch.setenv("DEMO_USER_PASSWORD", STRONG_PASSWORD)
    monkeypatch.setenv("DEMO_DEVELOPER_PASSWORD", STRONG_PASSWORD)
    assert main(["--demo", "--database-url", postgres_url]) == 0
    assert main(["--demo", "--database-url", postgres_url]) == 0  # idempotent

    async def roles() -> dict[str, UserRole]:
        engine = create_app_engine(postgres_url)
        try:
            async with create_session_factory(engine)() as s:
                rows = (await s.execute(select(UserORM).where(
                    UserORM.email.like(f"%-{suffix}@example.com")))).scalars().all()
                return {u.email: u.role for u in rows}
        finally:
            await engine.dispose()

    assert asyncio.run(roles()) == {f"user-{suffix}@example.com": UserRole.USER,
                                    f"dev-{suffix}@example.com": UserRole.DEVELOPER}
    monkeypatch.setenv("DEMO_USER_PASSWORD", "")
    assert main(["--demo", "--database-url", postgres_url]) == 0
    assert "demo accounts disabled" in capsys.readouterr().out
