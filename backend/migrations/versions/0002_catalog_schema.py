"""Create the ``catalog`` schema tables with every design invariant.

Revision ID: 0002_catalog
Revises: 0001_schemas_enums
Create Date: Spec 1 — Task 2.2

Tables: catalog_edition, part_number, supply_profile, supply_profile_mode,
electrical_configuration, service_performance, unqualified_performance,
operating_condition, electrical_measurement.

Invariants enforced here (design § catalog schema):
  * catalog_edition.manifest_digest UNIQUE; state enum; prev_edition self-FK.
  * part_number UNIQUE(edition_id, canonical_pn) + aux UNIQUE(edition_id, part_id).
  * Every technical metric is a (value, status) pair with a CHECK:
        (status = 'AVAILABLE') = (value IS NOT NULL).
  * torque_inlbs and torque_nm are two INDEPENDENT column pairs.
  * operating_condition: (frequency_state='EXPLICIT') = (frequency_hz IS NOT NULL)
    AND (frequency_state <> 'EXPLICIT' OR frequency_hz > 0).
  * Composite FKs (edition_id, part_id)/(edition_id, configuration_id)/
    (edition_id, condition_id) prevent cross-edition references.
  * service_performance has service_type NOT NULL; unqualified_performance has none.

Requirements: 4.1, 4.4, 4.5, 5.1, 5.2, 5.3, 7.1, 8.1, 11.1, 11.4, 11.5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision: str = "0002_catalog"
down_revision: str | None = "0001_schemas_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "catalog"

# Metric families -> their physical column stems. Each stem gets
# ``<stem>_value NUMERIC`` + ``<stem>_status availability_status`` and a CHECK.
_SERVICE_METRICS = (
    "torque_inlbs",
    "torque_nm",
    "duty_s4_pct",
    "cycles_per_hour",
    "starts_per_hour",
)
_MEASUREMENT_METRICS = ("operating_speed_sec", "fla_a", "lra_a")


def _availability() -> pg.ENUM:
    """Reference the already-created availability_status enum (no re-create)."""

    return pg.ENUM(name="availability_status", create_type=False)


def _metric_columns(stems: tuple[str, ...]) -> list[sa.Column]:
    """Build (value NUMERIC, status availability_status) column pairs."""

    cols: list[sa.Column] = []
    for stem in stems:
        cols.append(sa.Column(f"{stem}_value", sa.Numeric(), nullable=True))
        cols.append(sa.Column(f"{stem}_status", _availability(), nullable=False))
    return cols


def _metric_checks(stems: tuple[str, ...]) -> list[sa.CheckConstraint]:
    """CHECK: (status = 'AVAILABLE') = (value IS NOT NULL) per metric pair."""

    checks: list[sa.CheckConstraint] = []
    for stem in stems:
        checks.append(
            sa.CheckConstraint(
                f"({stem}_status = 'AVAILABLE') = ({stem}_value IS NOT NULL)",
                name=f"ck_{stem}_value_status",
            )
        )
    return checks


def upgrade() -> None:
    # --- catalog_edition ---------------------------------------------------
    op.create_table(
        "catalog_edition",
        sa.Column("edition_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("manifest_digest", sa.Text(), nullable=False),
        sa.Column(
            "state",
            pg.ENUM(name="edition_state", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("prev_edition_id", pg.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("manifest_digest", name="uq_edition_manifest_digest"),
        sa.ForeignKeyConstraint(
            ["prev_edition_id"],
            [f"{SCHEMA}.catalog_edition.edition_id"],
            name="fk_edition_prev_edition",
        ),
        schema=SCHEMA,
    )

    # --- part_number -------------------------------------------------------
    op.create_table(
        "part_number",
        sa.Column(
            "part_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_pn", sa.Text(), nullable=False),
        sa.Column("printed_pn", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            [f"{SCHEMA}.catalog_edition.edition_id"],
            name="fk_part_number_edition",
        ),
        sa.UniqueConstraint(
            "edition_id", "canonical_pn", name="uq_part_number_edition_canonical"
        ),
        # Aux unique target for composite (edition_id, part_id) child FKs.
        sa.UniqueConstraint("edition_id", "part_id", name="uq_part_number_edition_part"),
        schema=SCHEMA,
    )

    # --- supply_profile ----------------------------------------------------
    op.create_table(
        "supply_profile",
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("voltage_v", sa.Numeric(), nullable=True),
        sa.Column("phase_state", sa.Text(), nullable=True),
        sa.Column("phase_count", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "voltage_v", "phase_state", "phase_count", name="uq_supply_profile_identity"
        ),
        schema=SCHEMA,
    )

    # --- supply_profile_mode (link table; composite natural PK) ------------
    op.create_table(
        "supply_profile_mode",
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("mode", pg.ENUM(name="supply_mode", create_type=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            [f"{SCHEMA}.supply_profile.profile_id"],
            name="fk_supply_profile_mode_profile",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("profile_id", "mode", name="pk_supply_profile_mode"),
        schema=SCHEMA,
    )

    # --- electrical_configuration -----------------------------------------
    op.create_table(
        "electrical_configuration",
        sa.Column(
            "configuration_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("part_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=True),
        sa.Column("enclosure", sa.Text(), nullable=True),
        sa.Column("motor_power_w_value", sa.Numeric(), nullable=True),
        sa.Column("motor_power_w_status", _availability(), nullable=False),
        sa.Column("availability", _availability(), nullable=False),
        sa.CheckConstraint(
            "(motor_power_w_status = 'AVAILABLE') = (motor_power_w_value IS NOT NULL)",
            name="ck_motor_power_w_value_status",
        ),
        sa.ForeignKeyConstraint(
            ["edition_id", "part_id"],
            [f"{SCHEMA}.part_number.edition_id", f"{SCHEMA}.part_number.part_id"],
            name="fk_configuration_edition_part",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            [f"{SCHEMA}.supply_profile.profile_id"],
            name="fk_configuration_profile",
        ),
        # Aux unique target for composite (edition_id, configuration_id) child FKs.
        sa.UniqueConstraint(
            "edition_id", "configuration_id", name="uq_configuration_edition_configuration"
        ),
        schema=SCHEMA,
    )

    # --- service_performance (has service_type) ----------------------------
    op.create_table(
        "service_performance",
        sa.Column(
            "service_perf_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("configuration_id", sa.BigInteger(), nullable=False),
        sa.Column("service_type", sa.Text(), nullable=False),
        *_metric_columns(_SERVICE_METRICS),
        *_metric_checks(_SERVICE_METRICS),
        sa.ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                f"{SCHEMA}.electrical_configuration.edition_id",
                f"{SCHEMA}.electrical_configuration.configuration_id",
            ],
            name="fk_service_perf_edition_configuration",
        ),
        sa.UniqueConstraint(
            "edition_id",
            "configuration_id",
            "service_type",
            name="uq_service_perf_config_service_type",
        ),
        sa.UniqueConstraint(
            "edition_id", "service_perf_id", name="uq_service_perf_edition_id"
        ),
        schema=SCHEMA,
    )

    # --- unqualified_performance (NO service_type column) ------------------
    op.create_table(
        "unqualified_performance",
        sa.Column(
            "unq_perf_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("configuration_id", sa.BigInteger(), nullable=False),
        *_metric_columns(_SERVICE_METRICS),
        *_metric_checks(_SERVICE_METRICS),
        sa.ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                f"{SCHEMA}.electrical_configuration.edition_id",
                f"{SCHEMA}.electrical_configuration.configuration_id",
            ],
            name="fk_unq_perf_edition_configuration",
        ),
        sa.UniqueConstraint("edition_id", "unq_perf_id", name="uq_unq_perf_edition_id"),
        schema=SCHEMA,
    )

    # --- operating_condition ----------------------------------------------
    op.create_table(
        "operating_condition",
        sa.Column(
            "condition_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("configuration_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "frequency_state",
            pg.ENUM(name="frequency_state", create_type=False),
            nullable=False,
        ),
        sa.Column("frequency_hz", sa.Numeric(), nullable=True),
        sa.CheckConstraint(
            "(frequency_state = 'EXPLICIT') = (frequency_hz IS NOT NULL)",
            name="ck_operating_condition_explicit_hz",
        ),
        sa.CheckConstraint(
            "(frequency_state <> 'EXPLICIT') OR (frequency_hz > 0)",
            name="ck_operating_condition_hz_positive",
        ),
        sa.ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                f"{SCHEMA}.electrical_configuration.edition_id",
                f"{SCHEMA}.electrical_configuration.configuration_id",
            ],
            name="fk_operating_condition_edition_configuration",
        ),
        sa.UniqueConstraint(
            "edition_id", "condition_id", name="uq_operating_condition_edition_id"
        ),
        schema=SCHEMA,
    )

    # --- electrical_measurement (one row per operating_condition) ----------
    op.create_table(
        "electrical_measurement",
        sa.Column(
            "measurement_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("edition_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", sa.BigInteger(), nullable=False),
        *_metric_columns(_MEASUREMENT_METRICS),
        *_metric_checks(_MEASUREMENT_METRICS),
        sa.ForeignKeyConstraint(
            ["edition_id", "condition_id"],
            [
                f"{SCHEMA}.operating_condition.edition_id",
                f"{SCHEMA}.operating_condition.condition_id",
            ],
            name="fk_measurement_edition_condition",
        ),
        # Exactly one measurement block per operating condition.
        sa.UniqueConstraint(
            "edition_id", "condition_id", name="uq_measurement_edition_condition"
        ),
        sa.UniqueConstraint(
            "edition_id", "measurement_id", name="uq_measurement_edition_id"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "electrical_measurement",
        "operating_condition",
        "unqualified_performance",
        "service_performance",
        "electrical_configuration",
        "supply_profile_mode",
        "supply_profile",
        "part_number",
        "catalog_edition",
    ):
        op.drop_table(table, schema=SCHEMA)
