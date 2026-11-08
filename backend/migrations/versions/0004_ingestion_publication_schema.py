"""Create the ``ingestion`` (staging) and ``publication`` schema tables.

Revision ID: 0004_ingestion_pub
Revises: 0003_provenance
Create Date: Spec 1 — Task 2.4

ingestion: ingestion_run (mode, input SHA-256 set as jsonb, status with a CHECK
that a completed fresh run status is in {REJECTED, QUARANTINED, VERIFIED_READY}),
staging_extraction_candidate, staging_discrepancy, verification_record.

publication: verification_manifest (manifest_digest + versions + canonical facts
jsonb), catalog_current (single-row active pointer enforced via a constant PK
column + CHECK), catalog_publication_event (append-only log).

Requirements: 1.5, 2.6, 3.4, 8.2, 8.4, 10.4
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision: str = "0004_ingestion_pub"
down_revision: str | None = "0003_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INGESTION = "ingestion"
PUBLICATION = "publication"
CATALOG = "catalog"
PROVENANCE = "provenance"


def upgrade() -> None:
    # ======================= ingestion schema ============================

    # --- ingestion_run -----------------------------------------------------
    op.create_table(
        "ingestion_run",
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column(
            "mode",
            pg.ENUM(name="ingestion_mode", create_type=False),
            nullable=False,
        ),
        # Input SHA-256 set (document -> digest) kept verbatim as JSONB.
        sa.Column(
            "input_sha256",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        # ``status`` is a run_status for terminal fresh runs; NULL while in-flight
        # or for replay runs that do not take a fresh-run terminal status.
        sa.Column(
            "status", pg.ENUM(name="run_status", create_type=False), nullable=True
        ),
        sa.Column(
            "failures",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # A completed fresh_extraction run must take one of the three terminal
        # statuses; other modes/in-flight runs may leave status NULL.
        sa.CheckConstraint(
            "mode <> 'fresh_extraction' "
            "OR status IS NULL "
            "OR status IN ('REJECTED', 'QUARANTINED', 'VERIFIED_READY')",
            name="ck_ingestion_run_fresh_status",
        ),
        schema=INGESTION,
    )

    # --- staging_extraction_candidate -------------------------------------
    op.create_table(
        "staging_extraction_candidate",
        sa.Column(
            "candidate_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("extractor", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("structure", pg.JSONB(), nullable=True),
        sa.Column("bbox", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{INGESTION}.ingestion_run.run_id"],
            name="fk_candidate_run",
            ondelete="CASCADE",
        ),
        schema=INGESTION,
    )

    # --- staging_discrepancy ----------------------------------------------
    op.create_table(
        "staging_discrepancy",
        sa.Column(
            "discrepancy_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("ocr_value", sa.Text(), nullable=True),
        sa.Column("gemini_value", sa.Text(), nullable=True),
        sa.Column("failed_rule", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{INGESTION}.ingestion_run.run_id"],
            name="fk_discrepancy_run",
            ondelete="CASCADE",
        ),
        schema=INGESTION,
    )

    # --- verification_record ----------------------------------------------
    op.create_table(
        "verification_record",
        sa.Column(
            "record_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("prior_value", sa.Text(), nullable=True),
        sa.Column("verified_value", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("source_cell_id", sa.BigInteger(), nullable=True),
        sa.Column("source_document_hash", sa.Text(), nullable=False),
        sa.Column("manifest_id", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_cell_id"],
            [f"{PROVENANCE}.source_cell_evidence.cell_id"],
            name="fk_verification_record_cell",
        ),
        schema=INGESTION,
    )

    # ======================= publication schema ==========================

    # --- verification_manifest --------------------------------------------
    op.create_table(
        "verification_manifest",
        sa.Column(
            "manifest_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("manifest_digest", sa.Text(), nullable=False),
        sa.Column(
            "source_shas",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("normalization_version", sa.Text(), nullable=True),
        sa.Column("rules_version", sa.Text(), nullable=True),
        sa.Column(
            "canonical_facts",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "corrections",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "verification_report",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint("manifest_digest", name="uq_verification_manifest_digest"),
        schema=PUBLICATION,
    )

    # Backfill the verification_record.manifest_id FK now that the manifest
    # table exists (declared here to avoid a forward reference above).
    op.create_foreign_key(
        "fk_verification_record_manifest",
        "verification_record",
        "verification_manifest",
        ["manifest_id"],
        ["manifest_id"],
        source_schema=INGESTION,
        referent_schema=PUBLICATION,
    )

    # --- catalog_current (single-row active pointer) ----------------------
    op.create_table(
        "catalog_current",
        # Constant single-value PK guarantees at most one active pointer row.
        sa.Column(
            "pin", sa.Boolean(), primary_key=True, server_default=sa.text("TRUE")
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "activated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("pin IS TRUE", name="ck_catalog_current_single_row"),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            [f"{CATALOG}.catalog_edition.edition_id"],
            name="fk_catalog_current_edition",
        ),
        schema=PUBLICATION,
    )

    # --- catalog_publication_event (append-only log) ----------------------
    op.create_table(
        "catalog_publication_event",
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("prev_edition_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("new_edition_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("manifest_digest", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["prev_edition_id"],
            [f"{CATALOG}.catalog_edition.edition_id"],
            name="fk_pub_event_prev_edition",
        ),
        sa.ForeignKeyConstraint(
            ["new_edition_id"],
            [f"{CATALOG}.catalog_edition.edition_id"],
            name="fk_pub_event_new_edition",
        ),
        schema=PUBLICATION,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_verification_record_manifest",
        "verification_record",
        schema=INGESTION,
        type_="foreignkey",
    )
    op.drop_table("catalog_publication_event", schema=PUBLICATION)
    op.drop_table("catalog_current", schema=PUBLICATION)
    op.drop_table("verification_manifest", schema=PUBLICATION)
    op.drop_table("verification_record", schema=INGESTION)
    op.drop_table("staging_discrepancy", schema=INGESTION)
    op.drop_table("staging_extraction_candidate", schema=INGESTION)
    op.drop_table("ingestion_run", schema=INGESTION)
