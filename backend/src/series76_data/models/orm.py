"""SQLAlchemy 2.0 ORM mappings for the Spec 1 catalog/provenance/publication.

These classes mirror the hand-written Alembic migrations. They are the read
surface for the typed repository layer (``series76_data.db.repository``); the
migrations — not this module — remain the schema source of truth.

The PostgreSQL ENUM types created by migration ``0001`` are referenced here with
``create_type=False`` and ``name=...`` so the ORM reuses the DB enum labels that
come straight from :mod:`series76_data.models.enums`. Every metric column pair is
``<stem>_value`` (``Numeric``) + ``<stem>_status`` (``availability_status``),
exactly matching the DB CHECK.

PK types follow ADR 0001: ``BIGINT`` identity surrogates for internal tables and
``UUID`` for ``edition_id``.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Identity,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from series76_data.models.enums import (
    AuthorityRole,
    AvailabilityStatus,
    EditionState,
    FrequencyState,
    IngestionMode,
    RunStatus,
    SupplyMode,
)


class Base(DeclarativeBase):
    """Declarative base for all Spec 1 ORM models."""


# --- reusable enum column types (reference migration-created DB enums) -------


def _availability_enum() -> ENUM:
    return ENUM(
        AvailabilityStatus,
        name="availability_status",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


def _frequency_enum() -> ENUM:
    return ENUM(
        FrequencyState,
        name="frequency_state",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


def _edition_state_enum() -> ENUM:
    return ENUM(
        EditionState,
        name="edition_state",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


def _authority_enum() -> ENUM:
    return ENUM(
        AuthorityRole,
        name="authority_role",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


def _supply_mode_enum() -> ENUM:
    return ENUM(
        SupplyMode,
        name="supply_mode",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


def _ingestion_mode_enum() -> ENUM:
    return ENUM(
        IngestionMode,
        name="ingestion_mode",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


def _run_status_enum() -> ENUM:
    return ENUM(
        RunStatus,
        name="run_status",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


# =============================== catalog ====================================


class CatalogEdition(Base):
    """One immutable published/candidate edition (``catalog.catalog_edition``)."""

    __tablename__ = "catalog_edition"
    __table_args__ = (
        UniqueConstraint("manifest_digest", name="uq_edition_manifest_digest"),
        ForeignKeyConstraint(
            ["prev_edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_edition_prev_edition",
        ),
        {"schema": "catalog"},
    )

    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    manifest_digest: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[EditionState] = mapped_column(_edition_state_enum(), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True))
    prev_edition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class PartNumber(Base):
    """One canonical part number per edition (``catalog.part_number``)."""

    __tablename__ = "part_number"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_part_number_edition",
        ),
        UniqueConstraint(
            "edition_id", "canonical_pn", name="uq_part_number_edition_canonical"
        ),
        UniqueConstraint("edition_id", "part_id", name="uq_part_number_edition_part"),
        {"schema": "catalog"},
    )

    part_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_pn: Mapped[str] = mapped_column(Text, nullable=False)
    printed_pn: Mapped[str] = mapped_column(Text, nullable=False)


class SupplyProfile(Base):
    """Reusable nominal supply profile (``catalog.supply_profile``)."""

    __tablename__ = "supply_profile"
    __table_args__ = (
        UniqueConstraint(
            "voltage_v", "phase_state", "phase_count", name="uq_supply_profile_identity"
        ),
        {"schema": "catalog"},
    )

    profile_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    voltage_v: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    phase_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SupplyProfileMode(Base):
    """Admitted AC/DC mode for a profile (``catalog.supply_profile_mode``)."""

    __tablename__ = "supply_profile_mode"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id"],
            ["catalog.supply_profile.profile_id"],
            name="fk_supply_profile_mode_profile",
            ondelete="CASCADE",
        ),
        {"schema": "catalog"},
    )

    profile_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mode: Mapped[SupplyMode] = mapped_column(_supply_mode_enum(), primary_key=True)


class ElectricalConfiguration(Base):
    """PN × documented configuration (``catalog.electrical_configuration``)."""

    __tablename__ = "electrical_configuration"
    __table_args__ = (
        CheckConstraint(
            "(motor_power_w_status = 'AVAILABLE') = (motor_power_w_value IS NOT NULL)",
            name="ck_motor_power_w_value_status",
        ),
        ForeignKeyConstraint(
            ["edition_id", "part_id"],
            ["catalog.part_number.edition_id", "catalog.part_number.part_id"],
            name="fk_configuration_edition_part",
        ),
        ForeignKeyConstraint(
            ["profile_id"],
            ["catalog.supply_profile.profile_id"],
            name="fk_configuration_profile",
        ),
        UniqueConstraint(
            "edition_id",
            "configuration_id",
            name="uq_configuration_edition_configuration",
        ),
        {"schema": "catalog"},
    )

    configuration_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    part_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    profile_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enclosure: Mapped[str | None] = mapped_column(Text, nullable=True)
    motor_power_w_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    motor_power_w_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    availability: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )


class ServicePerformance(Base):
    """Performance attributed to a service type (``catalog.service_performance``)."""

    __tablename__ = "service_performance"
    __table_args__ = (
        CheckConstraint(
            "(torque_inlbs_status = 'AVAILABLE') = (torque_inlbs_value IS NOT NULL)",
            name="ck_torque_inlbs_value_status",
        ),
        CheckConstraint(
            "(torque_nm_status = 'AVAILABLE') = (torque_nm_value IS NOT NULL)",
            name="ck_torque_nm_value_status",
        ),
        CheckConstraint(
            "(duty_s4_pct_status = 'AVAILABLE') = (duty_s4_pct_value IS NOT NULL)",
            name="ck_duty_s4_pct_value_status",
        ),
        CheckConstraint(
            "(cycles_per_hour_status = 'AVAILABLE') = (cycles_per_hour_value IS NOT NULL)",
            name="ck_cycles_per_hour_value_status",
        ),
        CheckConstraint(
            "(starts_per_hour_status = 'AVAILABLE') = (starts_per_hour_value IS NOT NULL)",
            name="ck_starts_per_hour_value_status",
        ),
        ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                "catalog.electrical_configuration.edition_id",
                "catalog.electrical_configuration.configuration_id",
            ],
            name="fk_service_perf_edition_configuration",
        ),
        UniqueConstraint(
            "edition_id",
            "configuration_id",
            "service_type",
            name="uq_service_perf_config_service_type",
        ),
        UniqueConstraint(
            "edition_id", "service_perf_id", name="uq_service_perf_edition_id"
        ),
        {"schema": "catalog"},
    )

    service_perf_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    configuration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    service_type: Mapped[str] = mapped_column(Text, nullable=False)

    torque_inlbs_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    torque_inlbs_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    torque_nm_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    torque_nm_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    duty_s4_pct_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    duty_s4_pct_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    cycles_per_hour_value: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True
    )
    cycles_per_hour_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    starts_per_hour_value: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True
    )
    starts_per_hour_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )


class UnqualifiedPerformance(Base):
    """T03 performance with NO service attribution (``catalog.unqualified_performance``).

    Deliberately has no ``service_type`` column (design invariant).
    """

    __tablename__ = "unqualified_performance"
    __table_args__ = (
        CheckConstraint(
            "(torque_inlbs_status = 'AVAILABLE') = (torque_inlbs_value IS NOT NULL)",
            name="ck_torque_inlbs_value_status",
        ),
        CheckConstraint(
            "(torque_nm_status = 'AVAILABLE') = (torque_nm_value IS NOT NULL)",
            name="ck_torque_nm_value_status",
        ),
        CheckConstraint(
            "(duty_s4_pct_status = 'AVAILABLE') = (duty_s4_pct_value IS NOT NULL)",
            name="ck_duty_s4_pct_value_status",
        ),
        CheckConstraint(
            "(cycles_per_hour_status = 'AVAILABLE') = (cycles_per_hour_value IS NOT NULL)",
            name="ck_cycles_per_hour_value_status",
        ),
        CheckConstraint(
            "(starts_per_hour_status = 'AVAILABLE') = (starts_per_hour_value IS NOT NULL)",
            name="ck_starts_per_hour_value_status",
        ),
        ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                "catalog.electrical_configuration.edition_id",
                "catalog.electrical_configuration.configuration_id",
            ],
            name="fk_unq_perf_edition_configuration",
        ),
        UniqueConstraint("edition_id", "unq_perf_id", name="uq_unq_perf_edition_id"),
        {"schema": "catalog"},
    )

    unq_perf_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    configuration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    torque_inlbs_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    torque_inlbs_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    torque_nm_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    torque_nm_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    duty_s4_pct_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    duty_s4_pct_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    cycles_per_hour_value: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True
    )
    cycles_per_hour_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    starts_per_hour_value: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True
    )
    starts_per_hour_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )


class OperatingCondition(Base):
    """A frequency context per configuration (``catalog.operating_condition``)."""

    __tablename__ = "operating_condition"
    __table_args__ = (
        CheckConstraint(
            "(frequency_state = 'EXPLICIT') = (frequency_hz IS NOT NULL)",
            name="ck_operating_condition_explicit_hz",
        ),
        CheckConstraint(
            "(frequency_state <> 'EXPLICIT') OR (frequency_hz > 0)",
            name="ck_operating_condition_hz_positive",
        ),
        ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                "catalog.electrical_configuration.edition_id",
                "catalog.electrical_configuration.configuration_id",
            ],
            name="fk_operating_condition_edition_configuration",
        ),
        UniqueConstraint(
            "edition_id", "condition_id", name="uq_operating_condition_edition_id"
        ),
        {"schema": "catalog"},
    )

    condition_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    configuration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frequency_state: Mapped[FrequencyState] = mapped_column(
        _frequency_enum(), nullable=False
    )
    frequency_hz: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class ElectricalMeasurement(Base):
    """One measurement block per operating condition (``catalog.electrical_measurement``)."""

    __tablename__ = "electrical_measurement"
    __table_args__ = (
        CheckConstraint(
            "(operating_speed_sec_status = 'AVAILABLE') = (operating_speed_sec_value IS NOT NULL)",
            name="ck_operating_speed_sec_value_status",
        ),
        CheckConstraint(
            "(fla_a_status = 'AVAILABLE') = (fla_a_value IS NOT NULL)",
            name="ck_fla_a_value_status",
        ),
        CheckConstraint(
            "(lra_a_status = 'AVAILABLE') = (lra_a_value IS NOT NULL)",
            name="ck_lra_a_value_status",
        ),
        ForeignKeyConstraint(
            ["edition_id", "condition_id"],
            [
                "catalog.operating_condition.edition_id",
                "catalog.operating_condition.condition_id",
            ],
            name="fk_measurement_edition_condition",
        ),
        UniqueConstraint(
            "edition_id", "condition_id", name="uq_measurement_edition_condition"
        ),
        UniqueConstraint(
            "edition_id", "measurement_id", name="uq_measurement_edition_id"
        ),
        {"schema": "catalog"},
    )

    measurement_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    condition_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    operating_speed_sec_value: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True
    )
    operating_speed_sec_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    fla_a_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    fla_a_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )
    lra_a_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    lra_a_status: Mapped[AvailabilityStatus] = mapped_column(
        _availability_enum(), nullable=False
    )


# ============================== provenance ==================================


class SourceDocument(Base):
    """A unique source PDF (``provenance.source_document``)."""

    __tablename__ = "source_document"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_source_document_sha256"),
        {"schema": "provenance"},
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    authority_role: Mapped[AuthorityRole] = mapped_column(
        _authority_enum(), nullable=False
    )


class SourceSection(Base):
    """A table within a document/edition (``provenance.source_section``)."""

    __tablename__ = "source_section"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_source_section_edition",
        ),
        ForeignKeyConstraint(
            ["document_id"],
            ["provenance.source_document.document_id"],
            name="fk_source_section_document",
        ),
        UniqueConstraint(
            "edition_id", "table_code", name="uq_source_section_edition_table_code"
        ),
        UniqueConstraint(
            "edition_id", "section_id", name="uq_source_section_edition_id"
        ),
        {"schema": "provenance"},
    )

    section_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_code: Mapped[str] = mapped_column(Text, nullable=False)
    header_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceRow(Base):
    """A visual row (``provenance.source_row``)."""

    __tablename__ = "source_row"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "section_id"],
            [
                "provenance.source_section.edition_id",
                "provenance.source_section.section_id",
            ],
            name="fk_source_row_section",
        ),
        UniqueConstraint("section_id", "ordinal", name="uq_source_row_section_ordinal"),
        UniqueConstraint("edition_id", "row_id", name="uq_source_row_edition_id"),
        {"schema": "provenance"},
    )

    row_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    section_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    documentary_state: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceCellEvidence(Base):
    """An original visual cell (``provenance.source_cell_evidence``)."""

    __tablename__ = "source_cell_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "section_id"],
            [
                "provenance.source_section.edition_id",
                "provenance.source_section.section_id",
            ],
            name="fk_source_cell_section",
        ),
        UniqueConstraint("edition_id", "cell_id", name="uq_source_cell_edition_id"),
        {"schema": "provenance"},
    )

    cell_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    section_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anchor_row: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    header_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    printed_text: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox: Mapped[str | None] = mapped_column(Text, nullable=True)
    span: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceCellRowCoverage(Base):
    """Cell ↔ covered-row link (``provenance.source_cell_row_coverage``)."""

    __tablename__ = "source_cell_row_coverage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cell_id"],
            ["provenance.source_cell_evidence.cell_id"],
            name="fk_cell_row_coverage_cell",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["row_id"],
            ["provenance.source_row.row_id"],
            name="fk_cell_row_coverage_row",
            ondelete="CASCADE",
        ),
        {"schema": "provenance"},
    )

    cell_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    row_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class SourceNote(Base):
    """A literal note / asterisk (``provenance.source_note``)."""

    __tablename__ = "source_note"
    __table_args__ = (
        ForeignKeyConstraint(
            ["section_id"],
            ["provenance.source_section.section_id"],
            name="fk_source_note_section",
        ),
        {"schema": "provenance"},
    )

    note_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    section_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    marker: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    printed_text: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceNoteRowScope(Base):
    """Row affected by a note (``provenance.source_note_row_scope``)."""

    __tablename__ = "source_note_row_scope"
    __table_args__ = (
        ForeignKeyConstraint(
            ["note_id"],
            ["provenance.source_note.note_id"],
            name="fk_note_row_scope_note",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["row_id"],
            ["provenance.source_row.row_id"],
            name="fk_note_row_scope_row",
            ondelete="CASCADE",
        ),
        {"schema": "provenance"},
    )

    note_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    row_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class ServiceFieldEvidence(Base):
    """Typed field ↔ cell bridge for service_performance (real FKs both sides)."""

    __tablename__ = "service_field_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "service_perf_id"],
            [
                "catalog.service_performance.edition_id",
                "catalog.service_performance.service_perf_id",
            ],
            name="fk_service_field_evidence_fact",
        ),
        ForeignKeyConstraint(
            ["edition_id", "cell_id"],
            [
                "provenance.source_cell_evidence.edition_id",
                "provenance.source_cell_evidence.cell_id",
            ],
            name="fk_service_field_evidence_cell",
        ),
        UniqueConstraint(
            "service_perf_id",
            "field_code",
            "cell_id",
            name="uq_service_field_evidence_link",
        ),
        {"schema": "provenance"},
    )

    evidence_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_perf_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    field_code: Mapped[str] = mapped_column(Text, nullable=False)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class UnqualifiedFieldEvidence(Base):
    """Typed field ↔ cell bridge for unqualified_performance (real FKs both sides)."""

    __tablename__ = "unqualified_field_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "unq_perf_id"],
            [
                "catalog.unqualified_performance.edition_id",
                "catalog.unqualified_performance.unq_perf_id",
            ],
            name="fk_unqualified_field_evidence_fact",
        ),
        ForeignKeyConstraint(
            ["edition_id", "cell_id"],
            [
                "provenance.source_cell_evidence.edition_id",
                "provenance.source_cell_evidence.cell_id",
            ],
            name="fk_unqualified_field_evidence_cell",
        ),
        UniqueConstraint(
            "unq_perf_id",
            "field_code",
            "cell_id",
            name="uq_unqualified_field_evidence_link",
        ),
        {"schema": "provenance"},
    )

    evidence_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    unq_perf_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    field_code: Mapped[str] = mapped_column(Text, nullable=False)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class MeasurementFieldEvidence(Base):
    """Typed field ↔ cell bridge for electrical_measurement (real FKs both sides)."""

    __tablename__ = "measurement_field_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "measurement_id"],
            [
                "catalog.electrical_measurement.edition_id",
                "catalog.electrical_measurement.measurement_id",
            ],
            name="fk_measurement_field_evidence_fact",
        ),
        ForeignKeyConstraint(
            ["edition_id", "cell_id"],
            [
                "provenance.source_cell_evidence.edition_id",
                "provenance.source_cell_evidence.cell_id",
            ],
            name="fk_measurement_field_evidence_cell",
        ),
        UniqueConstraint(
            "measurement_id",
            "field_code",
            "cell_id",
            name="uq_measurement_field_evidence_link",
        ),
        {"schema": "provenance"},
    )

    evidence_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    measurement_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    field_code: Mapped[str] = mapped_column(Text, nullable=False)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ConfigurationFieldEvidence(Base):
    """Typed field ↔ cell bridge for electrical_configuration (real FKs both sides)."""

    __tablename__ = "configuration_field_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "configuration_id"],
            [
                "catalog.electrical_configuration.edition_id",
                "catalog.electrical_configuration.configuration_id",
            ],
            name="fk_configuration_field_evidence_fact",
        ),
        ForeignKeyConstraint(
            ["edition_id", "cell_id"],
            [
                "provenance.source_cell_evidence.edition_id",
                "provenance.source_cell_evidence.cell_id",
            ],
            name="fk_configuration_field_evidence_cell",
        ),
        UniqueConstraint(
            "configuration_id",
            "field_code",
            "cell_id",
            name="uq_configuration_field_evidence_link",
        ),
        {"schema": "provenance"},
    )

    evidence_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    configuration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    field_code: Mapped[str] = mapped_column(Text, nullable=False)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


# ============================== ingestion ===================================


class IngestionRun(Base):
    """One execution attempt (``ingestion.ingestion_run``)."""

    __tablename__ = "ingestion_run"
    __table_args__ = (
        CheckConstraint(
            "mode <> 'fresh_extraction' "
            "OR status IS NULL "
            "OR status IN ('REJECTED', 'QUARANTINED', 'VERIFIED_READY')",
            name="ck_ingestion_run_fresh_status",
        ),
        {"schema": "ingestion"},
    )

    run_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    mode: Mapped[IngestionMode] = mapped_column(_ingestion_mode_enum(), nullable=False)
    input_sha256: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[RunStatus | None] = mapped_column(_run_status_enum(), nullable=True)
    failures: Mapped[list[object]] = mapped_column(JSONB, nullable=False)


class StagingExtractionCandidate(Base):
    """One extractor hypothesis (``ingestion.staging_extraction_candidate``)."""

    __tablename__ = "staging_extraction_candidate"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id"],
            ["ingestion.ingestion_run.run_id"],
            name="fk_candidate_run",
            ondelete="CASCADE",
        ),
        {"schema": "ingestion"},
    )

    candidate_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extractor: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    bbox: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)


class StagingDiscrepancy(Base):
    """A disagreement or failed rule (``ingestion.staging_discrepancy``)."""

    __tablename__ = "staging_discrepancy"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id"],
            ["ingestion.ingestion_run.run_id"],
            name="fk_discrepancy_run",
            ondelete="CASCADE",
        ),
        {"schema": "ingestion"},
    )

    discrepancy_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)


class VerificationRecord(Base):
    """A human review/correction by evidence (``ingestion.verification_record``)."""

    __tablename__ = "verification_record"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_cell_id"],
            ["provenance.source_cell_evidence.cell_id"],
            name="fk_verification_record_cell",
        ),
        ForeignKeyConstraint(
            ["manifest_id"],
            ["publication.verification_manifest.manifest_id"],
            name="fk_verification_record_manifest",
        ),
        {"schema": "ingestion"},
    )

    record_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    reviewer: Mapped[str] = mapped_column(Text, nullable=False)
    prior_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    source_cell_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_document_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)


# ============================= publication ==================================


class VerificationManifest(Base):
    """Deterministic package of authorized data (``publication.verification_manifest``)."""

    __tablename__ = "verification_manifest"
    __table_args__ = (
        UniqueConstraint("manifest_digest", name="uq_verification_manifest_digest"),
        {"schema": "publication"},
    )

    manifest_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    manifest_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_shas: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    normalization_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_facts: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    corrections: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    verification_report: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )


class CatalogCurrent(Base):
    """Single-row active-edition pointer (``publication.catalog_current``)."""

    __tablename__ = "catalog_current"
    __table_args__ = (
        CheckConstraint("pin IS TRUE", name="ck_catalog_current_single_row"),
        ForeignKeyConstraint(
            ["edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_catalog_current_edition",
        ),
        {"schema": "publication"},
    )

    pin: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    activated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True))


class CatalogPublicationEvent(Base):
    """Publication / retirement event log (``publication.catalog_publication_event``)."""

    __tablename__ = "catalog_publication_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["prev_edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_pub_event_prev_edition",
        ),
        ForeignKeyConstraint(
            ["new_edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_pub_event_new_edition",
        ),
        {"schema": "publication"},
    )

    event_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    prev_edition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    new_edition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
