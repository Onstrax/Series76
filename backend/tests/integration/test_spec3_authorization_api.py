"""Spec 3 authorization/ownership guard integration test (real PostgreSQL).

Property 10's HTTP-level indistinguishability needs an owned-resource endpoint;
those arrive in Half B. Here we exercise the guard against the *real* database
with real ``users`` and ``conversations`` rows: ownership is resolved from the
authenticated principal (never the body), a cross-user access — including a
``developer`` reaching another owner's conversation — raises the identical
``NotFound`` as a nonexistent resource, and the owner is admitted.

Named with ``spec3``/``auth`` for selectability.
"""

from __future__ import annotations

import uuid

import pytest
from alembic.config import Config

from series76_api.application.authorization import authorize_ownership, resolve_owner_id
from series76_api.domain.errors import NotFoundError
from series76_api.domain.models import AuthenticatedPrincipal, UserRole
from series76_api.infrastructure.engine import create_app_engine, create_session_factory
from series76_api.infrastructure.orm import ConversationORM, UserORM
from series76_api.infrastructure.security import hash_password

pytestmark = pytest.mark.integration


def _principal(user_id: uuid.UUID, role: UserRole) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=user_id, role=role, auth_session_id=uuid.uuid4())


async def test_spec3_auth_ownership_guard_cross_user_indistinguishable_404(
    migrated_db: Config, postgres_url: str
) -> None:
    """Owner admitted; cross-user and developer-vs-other == nonexistent 404."""

    engine = create_app_engine(postgres_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            owner = UserORM(
                id=uuid.uuid4(),
                email=f"owner-{uuid.uuid4().hex}@example.com",
                password_verifier=hash_password("Str0ng-Passw0rd!"),
                role=UserRole.USER,
                email_verified=False,
            )
            developer = UserORM(
                id=uuid.uuid4(),
                email=f"dev-{uuid.uuid4().hex}@example.com",
                password_verifier=hash_password("Str0ng-Passw0rd!"),
                role=UserRole.DEVELOPER,
                email_verified=True,
            )
            session.add_all([owner, developer])
            await session.flush()

            conversation = ConversationORM(
                session_id=uuid.uuid4(),
                owner_id=owner.id,
                title_ciphertext=None,
            )
            session.add(conversation)
            await session.commit()

            loaded = await session.get(ConversationORM, conversation.session_id)
            assert loaded is not None

            # 1. The owner is admitted; owner id comes from the session principal.
            owner_principal = _principal(owner.id, UserRole.USER)
            assert resolve_owner_id(owner_principal) == owner.id
            assert authorize_ownership(owner_principal, loaded) is loaded

            # 2. A different user is denied with NotFound...
            other_principal = _principal(uuid.uuid4(), UserRole.USER)
            cross_exc = _capture(lambda: authorize_ownership(other_principal, loaded))

            # 3. A developer reaching another owner's conversation: same denial
            #    (developer is NOT a superuser).
            dev_principal = _principal(developer.id, UserRole.DEVELOPER)
            dev_exc = _capture(lambda: authorize_ownership(dev_principal, loaded))

            # 4. A nonexistent resource (None) is denied identically.
            missing_exc = _capture(lambda: authorize_ownership(owner_principal, None))

            for exc in (cross_exc, dev_exc, missing_exc):
                assert exc is not None
            assert cross_exc is not None and dev_exc is not None and missing_exc is not None
            # Indistinguishable: identical code, message, and empty details.
            assert cross_exc.code == dev_exc.code == missing_exc.code
            assert str(cross_exc) == str(dev_exc) == str(missing_exc)
            assert cross_exc.details == dev_exc.details == missing_exc.details == {}
    finally:
        await engine.dispose()


def _capture(fn: object) -> NotFoundError | None:
    try:
        fn()  # type: ignore[operator]
    except NotFoundError as exc:
        return exc
    return None
