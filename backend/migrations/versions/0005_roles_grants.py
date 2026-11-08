"""Create the three least-privilege database roles and their grants.

Revision ID: 0005_roles_grants
Revises: 0004_ingestion_pub
Create Date: Spec 1 — Task 3

Roles (Req 7.2, 7.3, 7.5):
  * ingest_editor_role  — writes ``ingestion.*`` (no edition activation).
  * publisher_role      — the ONLY writer of ``publication.catalog_current``.
  * runtime_reader_role — SELECT only on the published surface of
    ``catalog``/``provenance``; NO UPDATE/DELETE on catalog; NO access to
    ``ingestion``.

Role names are lowercase-safe for PostgreSQL (PostgreSQL folds unquoted
identifiers to lowercase; these are stored lowercase so quoting is never
required). ``CREATE ROLE`` is guarded by a ``DO`` block with an ``IF NOT
EXISTS`` check so re-running the migration is idempotent. Roles are created
``NOLOGIN`` (group roles); a deployment grants them to concrete login users.

Requirements: 7.2, 7.3, 7.5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_roles_grants"
down_revision: str | None = "0004_ingestion_pub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INGEST_EDITOR = "ingest_editor_role"
PUBLISHER = "publisher_role"
RUNTIME_READER = "runtime_reader_role"
ROLES = (INGEST_EDITOR, PUBLISHER, RUNTIME_READER)

# Published-surface tables the runtime reader may SELECT.
_CATALOG_READ_TABLES = (
    "catalog_edition",
    "part_number",
    "supply_profile",
    "supply_profile_mode",
    "electrical_configuration",
    "service_performance",
    "unqualified_performance",
    "operating_condition",
    "electrical_measurement",
)
_PROVENANCE_READ_TABLES = (
    "source_document",
    "source_section",
    "source_row",
    "source_cell_evidence",
    "source_cell_row_coverage",
    "source_note",
    "source_note_row_scope",
    "service_field_evidence",
    "unqualified_field_evidence",
    "measurement_field_evidence",
    "configuration_field_evidence",
)


def _create_role_idempotent(role: str) -> None:
    """Create a NOLOGIN role only if it does not already exist (idempotent)."""

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
    for role in ROLES:
        _create_role_idempotent(role)

    # --- ingest_editor_role: writes ingestion.* ---------------------------
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA ingestion TO {INGEST_EDITOR}"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ingestion "
            f"TO {INGEST_EDITOR}"
        )
    )
    op.execute(
        sa.text(
            "GRANT USAGE ON ALL SEQUENCES IN SCHEMA ingestion "
            f"TO {INGEST_EDITOR}"
        )
    )
    # Ingest editor can read provenance/catalog to attach evidence, but never
    # touches the active pointer.
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA provenance, catalog TO {INGEST_EDITOR}"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA provenance, catalog "
            f"TO {INGEST_EDITOR}"
        )
    )
    op.execute(
        sa.text(
            "GRANT USAGE ON ALL SEQUENCES IN SCHEMA provenance, catalog "
            f"TO {INGEST_EDITOR}"
        )
    )

    # --- publisher_role: the ONLY writer of publication.catalog_current ----
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA publication, catalog TO {PUBLISHER}"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON publication.catalog_current "
            f"TO {PUBLISHER}"
        )
    )
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT ON publication.catalog_publication_event "
            f"TO {PUBLISHER}"
        )
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT ON publication.verification_manifest TO {PUBLISHER}")
    )
    # Publisher flips editions' state during promotion/retirement.
    op.execute(sa.text(f"GRANT SELECT, UPDATE ON catalog.catalog_edition TO {PUBLISHER}"))
    op.execute(
        sa.text("GRANT USAGE ON ALL SEQUENCES IN SCHEMA publication " f"TO {PUBLISHER}")
    )

    # --- runtime_reader_role: SELECT-only on the published surface ---------
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA catalog, provenance TO {RUNTIME_READER}"))
    for table in _CATALOG_READ_TABLES:
        op.execute(sa.text(f"GRANT SELECT ON catalog.{table} TO {RUNTIME_READER}"))
    for table in _PROVENANCE_READ_TABLES:
        op.execute(sa.text(f"GRANT SELECT ON provenance.{table} TO {RUNTIME_READER}"))
    # The runtime reader may read the active pointer to resolve the edition,
    # but must never write it.
    op.execute(sa.text(f"GRANT SELECT ON publication.catalog_current TO {RUNTIME_READER}"))
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA publication TO {RUNTIME_READER}"))
    # Explicitly ensure NO access to the staging schema (defense in depth).
    op.execute(sa.text(f"REVOKE ALL ON SCHEMA ingestion FROM {RUNTIME_READER}"))
    op.execute(
        sa.text(
            "REVOKE ALL ON ALL TABLES IN SCHEMA ingestion "
            f"FROM {RUNTIME_READER}"
        )
    )


def downgrade() -> None:
    # Revoke grants, then drop the roles. Revokes are guarded so a partial
    # upgrade can still be torn down. Roles are owned by no objects (grants
    # only), so DROP ROLE succeeds once grants are revoked.
    for role in ROLES:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA '
                            || 'catalog, provenance, ingestion, publication FROM {role}';
                        EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA '
                            || 'catalog, provenance, ingestion, publication FROM {role}';
                        EXECUTE 'REVOKE ALL ON SCHEMA '
                            || 'catalog, provenance, ingestion, publication FROM {role}';
                        DROP ROLE {role};
                    END IF;
                END
                $$;
                """
            )
        )
