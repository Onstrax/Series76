"""Create the four logical schemas, shared ENUM types, and the error taxonomy.

Revision ID: 0001_schemas_enums
Revises:
Create Date: Spec 1 — Task 2.1

Creates logical schemas ``catalog``, ``provenance``, ``ingestion``,
``publication`` and the PostgreSQL ENUM types whose labels match the string
values in ``series76_data.models.enums`` *exactly*. The 13-code ingestion error
taxonomy (``series76_data.errors.taxonomy``) is materialised as a lookup table
in ``ingestion`` whose codes match :class:`IngestionErrorCode` exactly.

Requirements: 7.1, 9.1
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_schemas_enums"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS: tuple[str, ...] = ("catalog", "provenance", "ingestion", "publication")

# ENUM name -> ordered labels. These MUST mirror series76_data.models.enums.
ENUMS: dict[str, tuple[str, ...]] = {
    "availability_status": ("AVAILABLE", "NOT_APPLICABLE", "NOT_DOCUMENTED", "NOT_VERIFIED"),
    "frequency_state": ("EXPLICIT", "NOT_SPECIFIED", "NOT_APPLICABLE"),
    "edition_state": ("candidate", "published", "retired"),
    "authority_role": ("authorized-technical-source", "context-only"),
    "supply_mode": ("AC", "DC"),
    "ingestion_mode": ("verified_replay", "fresh_extraction"),
    "run_status": ("REJECTED", "QUARANTINED", "VERIFIED_READY"),
}

# The 13-code ingestion error taxonomy (series76_data.errors.taxonomy).
# (code, disposition) — disposition mirrors Disposition on each code.
ERROR_TAXONOMY: tuple[tuple[str, str], ...] = (
    ("INPUT_UNREADABLE", "halt"),
    ("HASH_MISMATCH", "halt"),
    ("TEMPLATE_UNKNOWN", "halt"),
    ("SECTION_MISSING", "reject"),
    ("ROW_COUNT_MISMATCH", "reject"),
    ("CELL_COORDINATE_AMBIGUOUS", "quarantine"),
    ("EXTRACTOR_DISAGREEMENT", "quarantine"),
    ("UNSUPPORTED_UNIT", "quarantine"),
    ("DUPLICATE_IDENTITY", "reject"),
    ("SOURCE_CONFLICT", "quarantine"),
    ("EVIDENCE_MISSING", "reject"),
    ("CORRECTION_STALE", "halt"),
    ("PUBLICATION_FAILED", "halt"),
)


def _quote_labels(labels: tuple[str, ...]) -> str:
    return ", ".join("'" + label.replace("'", "''") + "'" for label in labels)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Logical schemas.
    for schema in SCHEMAS:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # 2. Shared ENUM types (in the public schema so every logical schema can use
    #    them without duplication).
    for name, labels in ENUMS.items():
        op.execute(sa.text(f"CREATE TYPE {name} AS ENUM ({_quote_labels(labels)})"))

    # 3. Error-taxonomy lookup table (closed set; one row per code).
    op.create_table(
        "ingestion_error_code",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('halt', 'quarantine', 'reject')",
            name="ck_error_code_disposition",
        ),
        schema="ingestion",
    )
    taxonomy_table = sa.table(
        "ingestion_error_code",
        sa.column("code", sa.Text()),
        sa.column("disposition", sa.Text()),
        schema="ingestion",
    )
    op.bulk_insert(
        taxonomy_table,
        [{"code": code, "disposition": disp} for code, disp in ERROR_TAXONOMY],
    )
    _ = bind  # bind kept for symmetry/debugging; execution goes through op


def downgrade() -> None:
    op.drop_table("ingestion_error_code", schema="ingestion")
    for name in ENUMS:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {name}"))
    # Drop schemas last; CASCADE clears any dependent objects created later and
    # not yet dropped by their own downgrades (defensive for a full teardown).
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
