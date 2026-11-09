"""The compose provisioning step yields a least-privilege login that can serve."""

from __future__ import annotations

import psycopg
import pytest
from alembic.config import Config

from series76_api.provision import _plain, login_from_url, provision

pytestmark = pytest.mark.integration


def _app_url(admin_url: str, password: str) -> str:
    user, _ = login_from_url(admin_url)
    return admin_url.replace(f"{user}:", "series76_app:", 1).replace(
        admin_url.split(":", 2)[2].split("@", 1)[0], password, 1
    )


def test_provision_creates_least_privilege_login(postgres_url: str, migrated_db: Config) -> None:
    app_url = _app_url(postgres_url, "pw-one-local-only")
    assert provision(postgres_url, app_url) == "series76_app"
    assert provision(postgres_url, _app_url(postgres_url, "pw-two-local-only")) == "series76_app"
    app_url = _app_url(postgres_url, "pw-two-local-only")  # password rotated, still idempotent
    with psycopg.connect(_plain(app_url)) as conn:
        flags = conn.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert flags == (False, False, False)
        conn.execute("SELECT count(*) FROM identity.users").fetchone()  # app_writer
        conn.execute("SET ROLE runtime_reader_role")  # the Spec 2 catalog adapter does this
        conn.execute("SELECT count(*) FROM publication.catalog_current").fetchone()
        conn.execute("RESET ROLE")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE catalog.catalog_edition SET state = state")
    with pytest.raises(ValueError):
        provision(postgres_url, postgres_url)  # never the migration superuser
