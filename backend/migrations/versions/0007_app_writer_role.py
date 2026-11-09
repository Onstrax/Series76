"""Create the ``app_writer`` least-privilege role for the application data path.

Revision ID: 0007_app_writer
Revises: 0006_api_schemas
Create Date: Spec 3 — Task 2.2

``app_writer`` reads/writes the ``identity``, ``conversation``, and
``execution`` schemas (the application's own data) and may read the published
catalog surface to resolve editions, but holds **no** privilege on the Spec 1
``ingestion`` staging schema (least privilege, Req 1.5). The catalog read path
keeps using Spec 1's ``runtime_reader_role``; the application connects as
``app_writer`` for app data.

The role is created ``NOLOGIN`` (a group role) idempotently via a ``DO`` block,
mirroring the Spec 1 role migration; a deployment grants it to a concrete login
user. ``ALTER DEFAULT PRIVILEGES`` is set so future tables in the three app
schemas are writable without re-granting.

Requirements: 1.5, 12.2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_app_writer"
down_revision: str | None = "0006_api_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_WRITER = "app_writer"
APP_SCHEMAS = ("identity", "conversation", "execution")


def _create_role_idempotent(role: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
            END
            $$;
            """
        )
    )


def upgrade() -> None:
    _create_role_idempotent(APP_WRITER)

    for schema in APP_SCHEMAS:
        op.execute(sa.text(f"GRANT USAGE ON SCHEMA {schema} TO {APP_WRITER}"))
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                f"IN SCHEMA {schema} TO {APP_WRITER}"
            )
        )
        op.execute(
            sa.text(
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {APP_WRITER}"
            )
        )
        # Future tables/sequences in these schemas default-grant to app_writer.
        op.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_WRITER}"
            )
        )
        op.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_WRITER}"
            )
        )

    # app_writer may read the published catalog surface (edition resolution)
    # but gets NO privilege on the ingestion staging schema (defense in depth).
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA catalog, publication TO {APP_WRITER}"))
    op.execute(
        sa.text(f"GRANT SELECT ON ALL TABLES IN SCHEMA catalog, publication TO {APP_WRITER}")
    )
    op.execute(sa.text(f"REVOKE ALL ON SCHEMA ingestion FROM {APP_WRITER}"))
    op.execute(
        sa.text(f"REVOKE ALL ON ALL TABLES IN SCHEMA ingestion FROM {APP_WRITER}")
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_WRITER}') THEN
                    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA '
                        || 'identity, conversation, execution '
                        || 'REVOKE ALL ON TABLES FROM {APP_WRITER}';
                    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA '
                        || 'identity, conversation, execution '
                        || 'REVOKE ALL ON SEQUENCES FROM {APP_WRITER}';
                    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA '
                        || 'identity, conversation, execution, catalog, publication '
                        || 'FROM {APP_WRITER}';
                    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA '
                        || 'identity, conversation, execution '
                        || 'FROM {APP_WRITER}';
                    EXECUTE 'REVOKE ALL ON SCHEMA '
                        || 'identity, conversation, execution, catalog, publication '
                        || 'FROM {APP_WRITER}';
                    DROP ROLE {APP_WRITER};
                END IF;
            END
            $$;
            """
        )
    )
