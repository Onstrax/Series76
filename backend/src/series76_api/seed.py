"""Developer-account seed CLI (Spec 3, Req 2.10, 12.4).

Provisions ``developer`` (and optionally ``user``) accounts out-of-band. This
is the ONLY path that can create a ``developer``: no public HTTP endpoint can
create or elevate one (the register use case hard-codes role ``user`` and the
register DTO drops any client-supplied role). Demo credentials come from the
environment, never from committed source.

Run with::

    python -m series76_api.seed --email dev@example.com --role developer
    python -m series76_api.seed --demo   # the documented demo user + developer (DEMO_* env)

If ``--password`` is omitted the value is read from ``SEED_PASSWORD`` in the
environment so credentials are never passed on the command line in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid

from sqlalchemy import select

from series76_api.domain.auth import validate_email, validate_password
from series76_api.domain.models import UserRole
from series76_api.infrastructure.engine import create_app_engine, create_session_factory
from series76_api.infrastructure.orm import UserORM
from series76_api.infrastructure.security import hash_password
from series76_api.infrastructure.settings import get_settings


async def seed_account(
    database_url: str, *, email: str, password: str, role: UserRole
) -> uuid.UUID:
    """Create (or no-op if present) an account with the given role.

    Returns the account id. Idempotent on email: if the canonical email already
    exists, the existing id is returned and no duplicate is created.
    """

    canonical = validate_email(email)
    validate_password(password)

    engine = create_app_engine(database_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            existing = (
                await session.execute(select(UserORM).where(UserORM.email == canonical))
            ).scalar_one_or_none()
            if existing is not None:
                return existing.id
            user = UserORM(
                id=uuid.uuid4(),
                email=canonical,
                password_verifier=hash_password(password),
                role=role,
                email_verified=True,
            )
            session.add(user)
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


async def seed_demo_accounts(
    database_url: str,
    *,
    user_email: str,
    developer_email: str,
    user_password: str,
    developer_password: str,
) -> dict[str, uuid.UUID]:
    """Provision both demo accounts (a ``user`` and a ``developer``).

    Idempotent per email. Credentials come from the caller (env placeholders in
    the CLI), never from committed source or the image (Req 12.4, 12.6).
    Returns a mapping of role name to account id.
    """

    user_id = await seed_account(
        database_url, email=user_email, password=user_password, role=UserRole.USER
    )
    dev_id = await seed_account(
        database_url,
        email=developer_email,
        password=developer_password,
        role=UserRole.DEVELOPER,
    )
    return {"user": user_id, "developer": dev_id}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo accounts (developer/user).")
    parser.add_argument("--email", default=None)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed the documented demo user + developer from DEMO_* env vars "
        "(skipped when their passwords are empty).",
    )
    parser.add_argument(
        "--role",
        choices=[r.value for r in UserRole],
        default=UserRole.DEVELOPER.value,
        help="Account role (default: developer).",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Account password; if omitted, read from the SEED_PASSWORD env var.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override the database URL (default: Settings.database_url).",
    )
    return parser.parse_args(argv)


def _seed_demo(database_url: str) -> int:
    """Pre-load the documented demo accounts (assessment: "pre-loaded test users").

    Credentials come from ``DEMO_USER_EMAIL`` / ``DEMO_USER_PASSWORD`` /
    ``DEMO_DEVELOPER_EMAIL`` / ``DEMO_DEVELOPER_PASSWORD``. Empty passwords
    disable the demo accounts. Idempotent: existing accounts are left as they are.
    """

    env = os.environ
    user_pw = env.get("DEMO_USER_PASSWORD", "")
    dev_pw = env.get("DEMO_DEVELOPER_PASSWORD", "")
    if not user_pw or not dev_pw:
        print("demo accounts disabled (DEMO_USER_PASSWORD / DEMO_DEVELOPER_PASSWORD empty)")
        return 0
    ids = asyncio.run(seed_demo_accounts(
        database_url,
        user_email=env.get("DEMO_USER_EMAIL", "user@example.com"),
        developer_email=env.get("DEMO_DEVELOPER_EMAIL", "dev@example.com"),
        user_password=user_pw,
        developer_password=dev_pw,
    ))
    print(f"demo accounts ready: user id={ids['user']} developer id={ids['developer']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Never prints the password; prints only the account id."""

    args = _parse_args(argv)
    if args.demo:
        return _seed_demo(args.database_url or get_settings().database_url)
    if not args.email:
        raise SystemExit("--email is required (or use --demo).")
    password = args.password or os.environ.get("SEED_PASSWORD")
    if not password:
        raise SystemExit("No password: pass --password or set SEED_PASSWORD.")
    database_url = args.database_url or get_settings().database_url
    role = UserRole(args.role)
    account_id = asyncio.run(
        seed_account(database_url, email=args.email, password=password, role=role)
    )
    print(f"seeded {role.value} account id={account_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
