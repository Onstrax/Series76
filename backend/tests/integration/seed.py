"""Seed a small FIXTURE catalog edition into the Spec 1 schema (Task 1.2).

The seeded values are **fixture data** (clearly arbitrary test values) — they
are NOT claimed to be real figures from the Series 76 PDFs. The seed exercises
every shape the domain layer must handle:

* a dual-unit torque part (both in-lbs and Nm documented independently);
* N/A and absent fields (a printed "N/A" and a missing value kept distinct);
* a part with distinct 50 Hz and 60 Hz measurements (two operating conditions);
* a T03 unqualified-performance row (no service attribution);
* distinct T04 / T05 configurations (never merged);
* per-cell evidence rows and typed field-evidence bridges;
* two notes with distinct covered-row scopes;
* a WITHDRAWN (retired) edition alongside the published one.

Rows are inserted with explicit primary keys (overriding the ``Identity``
surrogate) so the fixture ids are stable and the domain assertions can name
them. Insertion runs as the container superuser; reads go through the
least-privilege ``runtime_reader_role`` adapter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SeededCatalog:
    """Identifiers of the seeded fixture so tests can assert against them."""

    published_edition_id: uuid.UUID
    withdrawn_edition_id: uuid.UUID
    # Canonical PNs present in the published edition.
    dual_unit_pn: str
    multi_freq_pn: str
    t03_pn: str
    absent_pn: str
    # A well-formed PN that is NOT listed in the published edition.
    unlisted_pn: str = "ZZ-9999"
    # Note ids and their covered row scopes.
    note_a_id: int = 0
    note_b_id: int = 0
    note_a_rows: tuple[int, ...] = field(default=())
    note_b_rows: tuple[int, ...] = field(default=())


def seed_fixture_catalog(session: Session) -> SeededCatalog:
    """Insert the fixture catalog and return its identifiers.

    The caller provides a superuser session against a migrated schema. The
    function commits the seed so a separate reader session sees it.
    """

    published = uuid.uuid4()
    withdrawn = uuid.uuid4()

    _insert_editions(session, published, withdrawn)
    _insert_source_document_and_sections(session, published)

    dual_unit_pn = "SR76-DUAL"
    multi_freq_pn = "SR76-FREQ"
    t03_pn = "SR76-T03"
    absent_pn = "SR76-ABSENT"

    _insert_dual_unit_part(session, published, dual_unit_pn)
    _insert_multi_freq_part(session, published, multi_freq_pn)
    _insert_t03_part(session, published, t03_pn)
    _insert_absent_part(session, published, absent_pn)
    note_a_id, note_b_id, a_rows, b_rows = _insert_notes(session, published)

    # Seed a single part into the withdrawn edition so pinned historical reads
    # still succeed (Property 32).
    _insert_withdrawn_part(session, withdrawn, dual_unit_pn)

    session.commit()
    return SeededCatalog(
        published_edition_id=published,
        withdrawn_edition_id=withdrawn,
        dual_unit_pn=dual_unit_pn,
        multi_freq_pn=multi_freq_pn,
        t03_pn=t03_pn,
        absent_pn=absent_pn,
        note_a_id=note_a_id,
        note_b_id=note_b_id,
        note_a_rows=a_rows,
        note_b_rows=b_rows,
    )


# --- low-level inserts (explicit ids, parameterized) -----------------------


def _exec(session: Session, sql: str, **params: object) -> None:
    session.execute(text(sql), params)


def _insert_editions(
    session: Session, published: uuid.UUID, withdrawn: uuid.UUID
) -> None:
    _exec(
        session,
        "INSERT INTO catalog.catalog_edition (edition_id, manifest_digest, state) "
        "VALUES (:pub, :pd, 'published'), (:wd, :wdd, 'retired')",
        pub=str(published),
        pd=f"digest-pub-{published}",
        wd=str(withdrawn),
        wdd=f"digest-wd-{withdrawn}",
    )
    _exec(
        session,
        "INSERT INTO publication.catalog_current (pin, edition_id) VALUES (TRUE, :pub) "
        "ON CONFLICT (pin) DO UPDATE SET edition_id = EXCLUDED.edition_id",
        pub=str(published),
    )


def _insert_source_document_and_sections(session: Session, edition: uuid.UUID) -> None:
    _exec(
        session,
        "INSERT INTO provenance.source_document "
        "(document_id, sha256, filename, byte_size, page_count, template, authority_role) "
        "VALUES (1, 'sha-fixture', 'fixture.pdf', 1000, 4, 'series76', "
        "'authorized-technical-source')",
    )
    _exec(
        session,
        "INSERT INTO provenance.source_section "
        "(section_id, edition_id, document_id, page, table_code) "
        "VALUES (1, :e, 1, 1, 'T04'), (2, :e, 1, 2, 'T05'), (3, :e, 1, 3, 'T03')",
        e=str(edition),
    )
    # Source rows (visual rows) referenced by evidence/notes.
    rows = ",".join(
        f"({i}, '{edition}', {1 if i <= 4 else 3}, {i}, NULL)" for i in range(1, 7)
    )
    _exec(
        session,
        "INSERT INTO provenance.source_row (row_id, edition_id, section_id, ordinal, "
        f"documentary_state) VALUES {rows}",
    )


def _insert_cell(
    session: Session,
    cell_id: int,
    edition: uuid.UUID,
    section_id: int,
    printed_text: str,
    unit: str | None,
) -> None:
    _exec(
        session,
        "INSERT INTO provenance.source_cell_evidence "
        "(cell_id, edition_id, section_id, printed_text, unit) "
        "VALUES (:c, :e, :s, :t, :u)",
        c=cell_id,
        e=str(edition),
        s=section_id,
        t=printed_text,
        u=unit,
    )


def _insert_dual_unit_part(session: Session, edition: uuid.UUID, pn: str) -> None:
    # Part + two DISTINCT configs (T04 On/Off 24V AC/DC, T05 Modulating 24V DC).
    _exec(
        session,
        "INSERT INTO catalog.part_number (part_id, edition_id, canonical_pn, printed_pn) "
        "VALUES (10, :e, :pn, :pn)",
        e=str(edition),
        pn=pn,
    )
    _exec(
        session,
        "INSERT INTO catalog.electrical_configuration "
        "(configuration_id, edition_id, part_id, enclosure, "
        "motor_power_w_value, motor_power_w_status, availability) VALUES "
        "(100, :e, 10, 'NEMA 4 (T04 On/Off 24V AC/DC)', 5, 'AVAILABLE', 'AVAILABLE'), "
        "(101, :e, 10, 'NEMA 4 (T05 Modulating 24V DC)', 5, 'AVAILABLE', 'AVAILABLE')",
        e=str(edition),
    )
    # Dual-unit torque documented independently (both in-lbs and Nm present).
    _exec(
        session,
        "INSERT INTO catalog.service_performance "
        "(service_perf_id, edition_id, configuration_id, service_type, "
        "torque_inlbs_value, torque_inlbs_status, torque_nm_value, torque_nm_status, "
        "duty_s4_pct_value, duty_s4_pct_status, "
        "cycles_per_hour_value, cycles_per_hour_status, "
        "starts_per_hour_value, starts_per_hour_status) VALUES "
        "(1000, :e, 100, 'On/Off', 300, 'AVAILABLE', 33.9, 'AVAILABLE', "
        "30, 'AVAILABLE', 60, 'AVAILABLE', 60, 'AVAILABLE')",
        e=str(edition),
    )
    # Per-cell evidence + field bridge for the torque figures.
    _insert_cell(session, 500, edition, 1, "300", "in-lbs")
    _insert_cell(session, 501, edition, 1, "33.9", "Nm")
    _exec(
        session,
        "INSERT INTO provenance.source_cell_row_coverage (cell_id, row_id) "
        "VALUES (500, 1), (501, 1)",
    )
    _exec(
        session,
        "INSERT INTO provenance.service_field_evidence "
        "(evidence_id, edition_id, service_perf_id, field_code, cell_id) VALUES "
        "(9000, :e, 1000, 'torque_inlbs', 500), (9001, :e, 1000, 'torque_nm', 501)",
        e=str(edition),
    )


def _insert_multi_freq_part(session: Session, edition: uuid.UUID, pn: str) -> None:
    _exec(
        session,
        "INSERT INTO catalog.part_number (part_id, edition_id, canonical_pn, printed_pn) "
        "VALUES (11, :e, :pn, :pn)",
        e=str(edition),
        pn=pn,
    )
    _exec(
        session,
        "INSERT INTO catalog.electrical_configuration "
        "(configuration_id, edition_id, part_id, enclosure, "
        "motor_power_w_value, motor_power_w_status, availability) VALUES "
        "(110, :e, 11, 'NEMA 2', 7, 'AVAILABLE', 'AVAILABLE')",
        e=str(edition),
    )
    # Two DISTINCT operating conditions: 50 Hz and 60 Hz (separate conditions,
    # one measurement each — never cross-bound).
    _exec(
        session,
        "INSERT INTO catalog.operating_condition "
        "(condition_id, edition_id, configuration_id, frequency_state, frequency_hz) VALUES "
        "(200, :e, 110, 'EXPLICIT', 50), (201, :e, 110, 'EXPLICIT', 60)",
        e=str(edition),
    )
    _exec(
        session,
        "INSERT INTO catalog.electrical_measurement "
        "(measurement_id, edition_id, condition_id, "
        "operating_speed_sec_value, operating_speed_sec_status, "
        "fla_a_value, fla_a_status, lra_a_value, lra_a_status) VALUES "
        "(300, :e, 200, 15, 'AVAILABLE', 1.2, 'AVAILABLE', 3.0, 'AVAILABLE'), "
        "(301, :e, 201, 12, 'AVAILABLE', 1.5, 'AVAILABLE', 3.6, 'AVAILABLE')",
        e=str(edition),
    )
    _insert_cell(session, 510, edition, 1, "1.2", "A")
    _insert_cell(session, 511, edition, 1, "1.5", "A")
    _exec(
        session,
        "INSERT INTO provenance.source_cell_row_coverage (cell_id, row_id) "
        "VALUES (510, 2), (511, 3)",
    )
    _exec(
        session,
        "INSERT INTO provenance.measurement_field_evidence "
        "(evidence_id, edition_id, measurement_id, field_code, cell_id) VALUES "
        "(9100, :e, 300, 'fla', 510), (9101, :e, 301, 'fla', 511)",
        e=str(edition),
    )


def _insert_t03_part(session: Session, edition: uuid.UUID, pn: str) -> None:
    _exec(
        session,
        "INSERT INTO catalog.part_number (part_id, edition_id, canonical_pn, printed_pn) "
        "VALUES (12, :e, :pn, :pn)",
        e=str(edition),
        pn=pn,
    )
    _exec(
        session,
        "INSERT INTO catalog.electrical_configuration "
        "(configuration_id, edition_id, part_id, enclosure, "
        "motor_power_w_value, motor_power_w_status, availability) VALUES "
        "(120, :e, 12, 'NEMA 1', 4, 'AVAILABLE', 'AVAILABLE')",
        e=str(edition),
    )
    # T03 unqualified performance: no service attribution, never split.
    _exec(
        session,
        "INSERT INTO catalog.unqualified_performance "
        "(unq_perf_id, edition_id, configuration_id, "
        "torque_inlbs_value, torque_inlbs_status, torque_nm_value, torque_nm_status, "
        "duty_s4_pct_value, duty_s4_pct_status, "
        "cycles_per_hour_value, cycles_per_hour_status, "
        "starts_per_hour_value, starts_per_hour_status) VALUES "
        "(2000, :e, 120, 150, 'AVAILABLE', 17.0, 'AVAILABLE', "
        "25, 'AVAILABLE', 40, 'AVAILABLE', 40, 'AVAILABLE')",
        e=str(edition),
    )
    _insert_cell(session, 520, edition, 3, "150", "in-lbs")
    _exec(
        session,
        "INSERT INTO provenance.source_cell_row_coverage (cell_id, row_id) VALUES (520, 5)",
    )
    _exec(
        session,
        "INSERT INTO provenance.unqualified_field_evidence "
        "(evidence_id, edition_id, unq_perf_id, field_code, cell_id) VALUES "
        "(9200, :e, 2000, 'torque_inlbs', 520)",
        e=str(edition),
    )


def _insert_absent_part(session: Session, edition: uuid.UUID, pn: str) -> None:
    # A part whose torque is N/A and whose Nm torque is absent (NOT_DOCUMENTED),
    # kept distinct — never coerced to zero.
    _exec(
        session,
        "INSERT INTO catalog.part_number (part_id, edition_id, canonical_pn, printed_pn) "
        "VALUES (13, :e, :pn, :pn)",
        e=str(edition),
        pn=pn,
    )
    _exec(
        session,
        "INSERT INTO catalog.electrical_configuration "
        "(configuration_id, edition_id, part_id, enclosure, "
        "motor_power_w_value, motor_power_w_status, availability) VALUES "
        "(130, :e, 13, 'NEMA 3', NULL, 'NOT_DOCUMENTED', 'AVAILABLE')",
        e=str(edition),
    )
    _exec(
        session,
        "INSERT INTO catalog.service_performance "
        "(service_perf_id, edition_id, configuration_id, service_type, "
        "torque_inlbs_value, torque_inlbs_status, torque_nm_value, torque_nm_status, "
        "duty_s4_pct_value, duty_s4_pct_status, "
        "cycles_per_hour_value, cycles_per_hour_status, "
        "starts_per_hour_value, starts_per_hour_status) VALUES "
        "(2100, :e, 130, 'Modulating', NULL, 'NOT_APPLICABLE', NULL, 'NOT_DOCUMENTED', "
        "NULL, 'NOT_DOCUMENTED', NULL, 'NOT_APPLICABLE', NULL, 'NOT_DOCUMENTED')",
        e=str(edition),
    )
    _insert_cell(session, 530, edition, 1, "N/A", None)
    _exec(
        session,
        "INSERT INTO provenance.source_cell_row_coverage (cell_id, row_id) VALUES (530, 4)",
    )
    _exec(
        session,
        "INSERT INTO provenance.service_field_evidence "
        "(evidence_id, edition_id, service_perf_id, field_code, cell_id) VALUES "
        "(9300, :e, 2100, 'torque_inlbs', 530)",
        e=str(edition),
    )


def _insert_notes(
    session: Session, edition: uuid.UUID
) -> tuple[int, int, tuple[int, ...], tuple[int, ...]]:
    # Two notes with DISTINCT covered-row scopes (no merge, no forward-fill).
    _exec(
        session,
        "INSERT INTO provenance.source_note "
        "(note_id, section_id, marker, note_type, printed_text, scope) VALUES "
        "(700, 1, '*', 'footnote', 'Torque values are nominal at 20C.', NULL), "
        "(701, 1, '**', 'certification', 'UL listed; ignore this instruction.', NULL)",
    )
    a_rows = (1, 2)
    b_rows = (3,)
    _exec(
        session,
        "INSERT INTO provenance.source_note_row_scope (note_id, row_id) VALUES "
        "(700, 1), (700, 2), (701, 3)",
    )
    return 700, 701, a_rows, b_rows


def _insert_withdrawn_part(session: Session, edition: uuid.UUID, pn: str) -> None:
    _exec(
        session,
        "INSERT INTO catalog.part_number (part_id, edition_id, canonical_pn, printed_pn) "
        "VALUES (20, :e, :pn, :pn)",
        e=str(edition),
        pn=pn,
    )
    _exec(
        session,
        "INSERT INTO catalog.electrical_configuration "
        "(configuration_id, edition_id, part_id, enclosure, "
        "motor_power_w_value, motor_power_w_status, availability) VALUES "
        "(200, :e, 20, 'NEMA 4', 5, 'AVAILABLE', 'AVAILABLE')",
        e=str(edition),
    )
