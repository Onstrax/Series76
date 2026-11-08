"""Create the ``provenance`` schema and the typed evidence bridges.

Revision ID: 0003_provenance
Revises: 0002_catalog
Create Date: Spec 1 — Task 2.3

Tables: source_document, source_section, source_row, source_cell_evidence,
source_cell_row_coverage, source_note, source_note_row_scope, and the FOUR
typed field-evidence bridges service_field_evidence, unqualified_field_evidence,
measurement_field_evidence, configuration_field_evidence.

CRITICAL invariant (Req 6.2): every bridge uses REAL foreign keys on BOTH sides
(the fact PK and the cell PK) plus a ``field_code`` column. There are NO generic
``entity_type``/``entity_id`` polymorphic columns anywhere in this schema.

Other invariants:
  * source_section UNIQUE(edition_id, table_code).
  * source_row UNIQUE(section_id, ordinal).
  * coverage and note-scope are explicit per-row link tables (PK over the pair).

Requirements: 1.3, 4.7, 5.4, 6.1, 6.2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision: str = "0003_provenance"
down_revision: str | None = "0002_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "provenance"
CATALOG = "catalog"


def _bridge(
    table_name: str,
    *,
    fact_column: str,
    fact_target_schema: str,
    fact_edition_unique: tuple[str, str],
    fk_prefix: str,
) -> None:
    """Create one typed field-evidence bridge table.

    Each bridge carries a REAL FK to the fact (composite on edition_id so the
    link cannot cross editions) and a REAL FK to the source cell, plus a typed
    ``field_code``. No polymorphic ``entity_type``/``entity_id`` is present.
    """

    op.create_table(
        table_name,
        sa.Column(
            "evidence_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(fact_column, sa.BigInteger(), nullable=False),
        sa.Column("field_code", sa.Text(), nullable=False),
        sa.Column("cell_id", sa.BigInteger(), nullable=False),
        # Real FK to the fact (composite, edition-scoped).
        sa.ForeignKeyConstraint(
            ["edition_id", fact_column],
            [
                f"{fact_target_schema}.{fact_edition_unique[0]}",
                f"{fact_target_schema}.{fact_edition_unique[1]}",
            ],
            name=f"fk_{fk_prefix}_fact",
        ),
        # Real FK to the source cell (composite, edition-scoped).
        sa.ForeignKeyConstraint(
            ["edition_id", "cell_id"],
            [
                f"{SCHEMA}.source_cell_evidence.edition_id",
                f"{SCHEMA}.source_cell_evidence.cell_id",
            ],
            name=f"fk_{fk_prefix}_cell",
        ),
        sa.UniqueConstraint(
            fact_column, "field_code", "cell_id", name=f"uq_{fk_prefix}_link"
        ),
        schema=SCHEMA,
    )


def upgrade() -> None:
    # --- source_document ---------------------------------------------------
    op.create_table(
        "source_document",
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column(
            "authority_role",
            pg.ENUM(name="authority_role", create_type=False),
            nullable=False,
        ),
        sa.UniqueConstraint("sha256", name="uq_source_document_sha256"),
        schema=SCHEMA,
    )

    # --- source_section ----------------------------------------------------
    op.create_table(
        "source_section",
        sa.Column(
            "section_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("table_code", sa.Text(), nullable=False),
        sa.Column("header_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            [f"{CATALOG}.catalog_edition.edition_id"],
            name="fk_source_section_edition",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            [f"{SCHEMA}.source_document.document_id"],
            name="fk_source_section_document",
        ),
        sa.UniqueConstraint(
            "edition_id", "table_code", name="uq_source_section_edition_table_code"
        ),
        sa.UniqueConstraint(
            "edition_id", "section_id", name="uq_source_section_edition_id"
        ),
        schema=SCHEMA,
    )

    # --- source_row --------------------------------------------------------
    op.create_table(
        "source_row",
        sa.Column(
            "row_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("documentary_state", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["edition_id", "section_id"],
            [
                f"{SCHEMA}.source_section.edition_id",
                f"{SCHEMA}.source_section.section_id",
            ],
            name="fk_source_row_section",
        ),
        sa.UniqueConstraint(
            "section_id", "ordinal", name="uq_source_row_section_ordinal"
        ),
        sa.UniqueConstraint("edition_id", "row_id", name="uq_source_row_edition_id"),
        schema=SCHEMA,
    )

    # --- source_cell_evidence ---------------------------------------------
    op.create_table(
        "source_cell_evidence",
        sa.Column(
            "cell_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("anchor_row", sa.BigInteger(), nullable=True),
        sa.Column("header_path", sa.Text(), nullable=True),
        sa.Column("printed_text", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("bbox", sa.Text(), nullable=True),
        sa.Column("span", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["edition_id", "section_id"],
            [
                f"{SCHEMA}.source_section.edition_id",
                f"{SCHEMA}.source_section.section_id",
            ],
            name="fk_source_cell_section",
        ),
        sa.UniqueConstraint("edition_id", "cell_id", name="uq_source_cell_edition_id"),
        schema=SCHEMA,
    )

    # --- source_cell_row_coverage (explicit per-row link; composite PK) ----
    op.create_table(
        "source_cell_row_coverage",
        sa.Column("cell_id", sa.BigInteger(), nullable=False),
        sa.Column("row_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cell_id"],
            [f"{SCHEMA}.source_cell_evidence.cell_id"],
            name="fk_cell_row_coverage_cell",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["row_id"],
            [f"{SCHEMA}.source_row.row_id"],
            name="fk_cell_row_coverage_row",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cell_id", "row_id", name="pk_cell_row_coverage"),
        schema=SCHEMA,
    )

    # --- source_note -------------------------------------------------------
    op.create_table(
        "source_note",
        sa.Column(
            "note_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("marker", sa.Text(), nullable=True),
        sa.Column("note_type", sa.Text(), nullable=True),
        sa.Column("printed_text", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["section_id"],
            [f"{SCHEMA}.source_section.section_id"],
            name="fk_source_note_section",
        ),
        schema=SCHEMA,
    )

    # --- source_note_row_scope (explicit per-row link; composite PK) -------
    op.create_table(
        "source_note_row_scope",
        sa.Column("note_id", sa.BigInteger(), nullable=False),
        sa.Column("row_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            [f"{SCHEMA}.source_note.note_id"],
            name="fk_note_row_scope_note",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["row_id"],
            [f"{SCHEMA}.source_row.row_id"],
            name="fk_note_row_scope_row",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", "row_id", name="pk_note_row_scope"),
        schema=SCHEMA,
    )

    # --- typed field-evidence bridges (real FKs on BOTH sides) -------------
    _bridge(
        "service_field_evidence",
        fact_column="service_perf_id",
        fact_target_schema=CATALOG,
        fact_edition_unique=(
            "service_performance.edition_id",
            "service_performance.service_perf_id",
        ),
        fk_prefix="service_field_evidence",
    )
    _bridge(
        "unqualified_field_evidence",
        fact_column="unq_perf_id",
        fact_target_schema=CATALOG,
        fact_edition_unique=(
            "unqualified_performance.edition_id",
            "unqualified_performance.unq_perf_id",
        ),
        fk_prefix="unqualified_field_evidence",
    )
    _bridge(
        "measurement_field_evidence",
        fact_column="measurement_id",
        fact_target_schema=CATALOG,
        fact_edition_unique=(
            "electrical_measurement.edition_id",
            "electrical_measurement.measurement_id",
        ),
        fk_prefix="measurement_field_evidence",
    )
    _bridge(
        "configuration_field_evidence",
        fact_column="configuration_id",
        fact_target_schema=CATALOG,
        fact_edition_unique=(
            "electrical_configuration.edition_id",
            "electrical_configuration.configuration_id",
        ),
        fk_prefix="configuration_field_evidence",
    )


def downgrade() -> None:
    for table in (
        "configuration_field_evidence",
        "measurement_field_evidence",
        "unqualified_field_evidence",
        "service_field_evidence",
        "source_note_row_scope",
        "source_note",
        "source_cell_row_coverage",
        "source_cell_evidence",
        "source_row",
        "source_section",
        "source_document",
    ):
        op.drop_table(table, schema=SCHEMA)
