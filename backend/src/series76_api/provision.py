"""Provision the application's login role: ``python -m series76_api.provision``.

The migrations create only ``NOLOGIN`` group roles (``app_writer`` for the
conversation/identity/execution schemas, ``runtime_reader_role`` for the
published catalog). A deployment must grant them to a concrete login user.
This one-shot step, run right after ``alembic upgrade head`` with the
privileged ``SERIES76_MIGRATE_URL``, creates (or updates) the login user named
in ``DATABASE_URL`` and grants it exactly those two roles. It is idempotent and
takes the credentials from the environment only (nothing is hardcoded).
"""

from __future__ import annotations

import os
import sys
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql

GRANTED_ROLES: tuple[str, ...] = ("app_writer", "runtime_reader_role")


def _plain(url: str) -> str:
    scheme, rest = url.split("://", 1)
    return f"{scheme.split('+', 1)[0]}://{rest}"


def login_from_url(url: str) -> tuple[str, str]:
    """(user, password) of a ``postgresql[+driver]://user:password@host/db`` URL."""

    parts = urlsplit(_plain(url))
    if not parts.username or not parts.password:
        raise ValueError("DATABASE_URL must carry the application user and password")
    return unquote(parts.username), unquote(parts.password)


def provision(admin_url: str, app_url: str) -> str:
    """Create/update the login role of ``app_url`` and grant the runtime roles."""

    user, password = login_from_url(app_url)
    admin_user, _ = login_from_url(admin_url)
    if user == admin_user:
        raise ValueError("the application must not connect as the migration superuser")
    with psycopg.connect(_plain(admin_url), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(
            sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(user), sql.Literal(password)
            )
        )
        for role in GRANTED_ROLES:
            conn.execute(
                sql.SQL("GRANT {} TO {}").format(sql.Identifier(role), sql.Identifier(user))
            )
    return user


def main() -> int:
    admin = os.environ.get("SERIES76_MIGRATE_URL", "")
    app = os.environ.get("DATABASE_URL", "")
    if not admin or not app:
        sys.stderr.write("SERIES76_MIGRATE_URL and DATABASE_URL are required\n")
        return 2
    user = provision(admin, app)
    sys.stdout.write(f"provisioned login role {user} with {', '.join(GRANTED_ROLES)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
