"""Integration tests for the Alembic migrations (Task 2.5).

Run against a real ``postgres:15-alpine`` container. They assert that the four
logical schemas, the ENUM types (with exact labels), the value+status CHECKs,
and the ``UNIQUE(edition_id, canonical_pn)`` constraint behave as designed, that
no provenance bridge exposes a polymorphic ``entity_type``/``entity_id`` column,
and that ``downgrade base`` reverts the schema cleanly.

Requirements: 5.1, 5.2, 6.2, 7.1, 11.4, 11.5
"""

from __future__ import annotations

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


EXPECTED_SCHEMAS = {"catalog", "provenance", "ingestion", "publication"}

EXPECTED_ENUMS = {
    "availability_status": {
        "AVAILABLE",
        "NOT_APPLICABLE",
        "NOT_DOCUMENTED",
        "NOT_VERIFIED",
    },
    "frequency_state": {"EXPLICIT", "NOT_SPECIFIED", "NOT_APPLICABLE"},
    "edition_state": {"candidate", "published", "retired"},
    "authority_role": {"authorized-technical-source", "context-only"},
    "supply_mode": {"AC", "DC"},
    "ingestion_mode": {"verified_replay", "fresh_extraction"},
    "run_status": {"REJECTED", "QUARANTINED", "VERIFIED_READY"},
}

PROVENANCE_BRIDGES = (
    "service_field_evidence",
    "unqualified_field_evidence",
    "measurement_field_evidence",
    "configuration_field_evidence",
)


def _engine(url: str):
    return create_engine(url, future=True)


def test_four_schemas_exist(migrated_db: Config, postgres_url: str) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = ANY(:names)"
                    ),
                    {"names": list(EXPECTED_SCHEMAS)},
                )
                .scalars()
                .all()
            )
        assert set(rows) == EXPECTED_SCHEMAS
    finally:
        eng.dispose()


def test_enums_exist_with_exact_labels(migrated_db: Config, postgres_url: str) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            for enum_name, labels in EXPECTED_ENUMS.items():
                got = (
                    conn.execute(
                        text(
                            "SELECT e.enumlabel FROM pg_type t "
                            "JOIN pg_enum e ON e.enumtypid = t.oid "
                            "WHERE t.typname = :name"
                        ),
                        {"name": enum_name},
                    )
                    .scalars()
                    .all()
                )
                assert set(got) == labels, f"{enum_name} labels mismatch: {got}"
    finally:
        eng.dispose()


def test_error_taxonomy_lookup_has_thirteen_codes(
    migrated_db: Config, postgres_url: str
) -> None:
    from series76_data.errors.taxonomy import IngestionErrorCode

    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            codes = (
                conn.execute(text("SELECT code FROM ingestion.ingestion_error_code"))
                .scalars()
                .all()
            )
        assert set(codes) == {c.value for c in IngestionErrorCode}
        assert len(codes) == 13
    finally:
        eng.dispose()


def _insert_edition(conn, edition_id: uuid.UUID) -> None:
    conn.execute(
        text(
            "INSERT INTO catalog.catalog_edition (edition_id, manifest_digest, state) "
            "VALUES (:eid, :digest, 'candidate')"
        ),
        {"eid": str(edition_id), "digest": f"digest-{edition_id}"},
    )


def _insert_part(conn, edition_id: uuid.UUID, canonical_pn: str) -> None:
    conn.execute(
        text(
            "INSERT INTO catalog.part_number (edition_id, canonical_pn, printed_pn) "
            "VALUES (:eid, :pn, :pn)"
        ),
        {"eid": str(edition_id), "pn": canonical_pn},
    )


def _insert_configuration(conn, edition_id: uuid.UUID) -> int:
    _insert_part(conn, edition_id, "PN-CFG")
    part_id = conn.execute(
        text("SELECT part_id FROM catalog.part_number WHERE edition_id = :eid"),
        {"eid": str(edition_id)},
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO catalog.electrical_configuration "
            "(edition_id, part_id, motor_power_w_status, availability) "
            "VALUES (:eid, :pid, 'NOT_DOCUMENTED', 'AVAILABLE') "
            "RETURNING configuration_id"
        ),
        {"eid": str(edition_id), "pid": part_id},
    ).scalar_one()


def test_value_status_check_rejects_available_with_null(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.begin() as conn:
            edition_id = uuid.uuid4()
            _insert_edition(conn, edition_id)
            config_id = _insert_configuration(conn, edition_id)
        # AVAILABLE status but NULL value must be rejected by the CHECK.
        with pytest.raises(IntegrityError), eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO catalog.service_performance "
                    "(edition_id, configuration_id, service_type, "
                    " torque_inlbs_value, torque_inlbs_status, "
                    " torque_nm_status, duty_s4_pct_status, "
                    " cycles_per_hour_status, starts_per_hour_status) "
                    "VALUES (:eid, :cid, 'On/Off', NULL, 'AVAILABLE', "
                    " 'NOT_DOCUMENTED', 'NOT_DOCUMENTED', "
                    " 'NOT_DOCUMENTED', 'NOT_DOCUMENTED')"
                ),
                {"eid": str(edition_id), "cid": config_id},
            )
    finally:
        eng.dispose()


def test_value_status_check_rejects_not_applicable_with_value(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.begin() as conn:
            edition_id = uuid.uuid4()
            _insert_edition(conn, edition_id)
            config_id = _insert_configuration(conn, edition_id)
        # NOT_APPLICABLE status with a non-null value must be rejected.
        with pytest.raises(IntegrityError), eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO catalog.service_performance "
                    "(edition_id, configuration_id, service_type, "
                    " torque_inlbs_value, torque_inlbs_status, "
                    " torque_nm_status, duty_s4_pct_status, "
                    " cycles_per_hour_status, starts_per_hour_status) "
                    "VALUES (:eid, :cid, 'On/Off', 125, 'NOT_APPLICABLE', "
                    " 'NOT_DOCUMENTED', 'NOT_DOCUMENTED', "
                    " 'NOT_DOCUMENTED', 'NOT_DOCUMENTED')"
                ),
                {"eid": str(edition_id), "cid": config_id},
            )
    finally:
        eng.dispose()


def test_value_status_check_accepts_documented_zero(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.begin() as conn:
            edition_id = uuid.uuid4()
            _insert_edition(conn, edition_id)
            config_id = _insert_configuration(conn, edition_id)
            # A documented numeric zero (AVAILABLE, value 0) must be accepted.
            conn.execute(
                text(
                    "INSERT INTO catalog.service_performance "
                    "(edition_id, configuration_id, service_type, "
                    " torque_inlbs_value, torque_inlbs_status, "
                    " torque_nm_status, duty_s4_pct_status, "
                    " cycles_per_hour_status, starts_per_hour_status) "
                    "VALUES (:eid, :cid, 'On/Off', 0, 'AVAILABLE', "
                    " 'NOT_DOCUMENTED', 'NOT_DOCUMENTED', "
                    " 'NOT_DOCUMENTED', 'NOT_DOCUMENTED')"
                ),
                {"eid": str(edition_id), "cid": config_id},
            )
            stored = conn.execute(
                text(
                    "SELECT torque_inlbs_value FROM catalog.service_performance "
                    "WHERE edition_id = :eid"
                ),
                {"eid": str(edition_id)},
            ).scalar_one()
            assert stored == 0
    finally:
        eng.dispose()


def test_operating_condition_explicit_requires_positive_hz(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.begin() as conn:
            edition_id = uuid.uuid4()
            _insert_edition(conn, edition_id)
            config_id = _insert_configuration(conn, edition_id)
        # EXPLICIT with NULL Hz violates the (state='EXPLICIT') = (hz NOT NULL) CHECK.
        with pytest.raises(IntegrityError), eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO catalog.operating_condition "
                    "(edition_id, configuration_id, frequency_state, frequency_hz) "
                    "VALUES (:eid, :cid, 'EXPLICIT', NULL)"
                ),
                {"eid": str(edition_id), "cid": config_id},
            )
    finally:
        eng.dispose()


def test_unique_edition_canonical_pn_rejects_duplicate(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.begin() as conn:
            edition_id = uuid.uuid4()
            _insert_edition(conn, edition_id)
            _insert_part(conn, edition_id, "76-SAME")
        with pytest.raises(IntegrityError), eng.begin() as conn:
            _insert_part(conn, edition_id, "76-SAME")
    finally:
        eng.dispose()


def test_no_polymorphic_columns_in_provenance(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            offending = conn.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'provenance' "
                    "AND column_name IN ('entity_type', 'entity_id')"
                )
            ).all()
        assert offending == [], f"polymorphic columns found: {offending}"
    finally:
        eng.dispose()


def test_bridges_have_real_fks_both_sides(
    migrated_db: Config, postgres_url: str
) -> None:
    """Each typed bridge must have FKs to both the fact and the source cell."""

    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            for bridge in PROVENANCE_BRIDGES:
                fk_targets = (
                    conn.execute(
                        text(
                            "SELECT ccu.table_name "
                            "FROM information_schema.table_constraints tc "
                            "JOIN information_schema.constraint_column_usage ccu "
                            "  ON tc.constraint_name = ccu.constraint_name "
                            " AND tc.constraint_schema = ccu.constraint_schema "
                            "WHERE tc.constraint_type = 'FOREIGN KEY' "
                            "  AND tc.table_schema = 'provenance' "
                            "  AND tc.table_name = :bridge"
                        ),
                        {"bridge": bridge},
                    )
                    .scalars()
                    .all()
                )
                assert "source_cell_evidence" in fk_targets, bridge
                # At least two distinct FK target tables (fact side + cell side).
                assert len(set(fk_targets)) >= 2, (bridge, fk_targets)
    finally:
        eng.dispose()


def test_downgrade_base_reverts_cleanly(
    alembic_config: Config, postgres_url: str
) -> None:
    """upgrade head then downgrade base must leave none of the four schemas."""

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            remaining = (
                conn.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = ANY(:names)"
                    ),
                    {"names": list(EXPECTED_SCHEMAS)},
                )
                .scalars()
                .all()
            )
        assert remaining == []
    finally:
        eng.dispose()
