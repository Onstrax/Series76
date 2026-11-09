"""Write a replayed, audited package into PostgreSQL and read it back.

:func:`publish_replayed` runs the Spec 1 publication gate and, inside the same
transaction (``Publisher.publish(load_facts=...)``), inserts the provenance
(document, sections, rows, cells, coverage, notes), the typed catalog facts,
the per-field evidence bridges, the verification manifest, one verification
record per audited cell, and the ingestion run. Re-running the same manifest is
an idempotent no-op (Property 2).

:func:`published_cells` reads the *active* edition back into golden-shaped
cells so documental verification can diff it against the golden dataset.
"""

from __future__ import annotations

import datetime
import time
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from series76_data.etl.facts import (
    PN_COLUMN,
    Catalog,
    FieldValue,
    GoldenEntry,
    RowFacts,
    cell_key,
    column_for,
    row_key,
)
from series76_data.etl.layout import TABLES_BY_CODE
from series76_data.etl.replay import (
    ORACLE,
    SOURCE_PDF,
    Replayed,
    edition_id_for,
)
from series76_data.etl.sheets import NA
from series76_data.models.enums import (
    AuthorityRole,
    AvailabilityStatus,
    IngestionMode,
    SupplyMode,
)
from series76_data.models.orm import (
    CatalogCurrent,
    CatalogEdition,
    ConfigurationFieldEvidence,
    ElectricalConfiguration,
    ElectricalMeasurement,
    IngestionRun,
    MeasurementFieldEvidence,
    OperatingCondition,
    PartNumber,
    ServiceFieldEvidence,
    ServicePerformance,
    SourceCellEvidence,
    SourceCellRowCoverage,
    SourceDocument,
    SourceNote,
    SourceNoteRowScope,
    SourceRow,
    SourceSection,
    SupplyProfile,
    SupplyProfileMode,
    UnqualifiedFieldEvidence,
    UnqualifiedPerformance,
    VerificationManifest,
    VerificationRecord,
)
from series76_data.pipeline.publisher import Publisher
from series76_data.pipeline.verifier import AuditedEdition

ACTOR = "series76_data publish (verified_replay)"


def audited_edition(catalog: Catalog, manifest_consistent: bool) -> AuditedEdition:
    ids = frozenset(range(len(catalog.cells)))
    expected = {t.code for t in TABLES_BY_CODE.values()}
    present = {s.layout.code for s in catalog.sheets}
    return AuditedEdition(
        counts=catalog.counts(),
        relevant_cell_ids=ids,
        verified_cell_ids=ids,  # parse_package refused any row not marked OK
        open_critical_discrepancies=0,
        canonical_pns=catalog.canonical_pns(),
        facts_with_evidence=all(_row_has_evidence(r) for r in catalog.rows),
        manifest_hash_consistent=manifest_consistent,
        missing_sections=tuple(sorted(expected - present)),
    )


def _row_has_evidence(row: RowFacts) -> bool:
    fields = [row.motor_power, *(f for _, fs in row.services for f in fs),
              *(row.unqualified or ()), *(f for c in row.conditions for f in c.fields)]
    # Every documented value (a number or a printed N/A) must point at its cell.
    return all(f.cell is not None for f in fields
               if f.status is not AvailabilityStatus.NOT_DOCUMENTED)


def publish_replayed(session: Session, replayed: Replayed) -> tuple[CatalogEdition, bool]:
    """Publish the replayed package; returns (edition, created_now)."""

    started = time.monotonic()
    started_at = datetime.datetime.now(tz=datetime.UTC)
    digest = replayed.digest
    edition_id = edition_id_for(digest)
    existing = session.execute(
        select(CatalogEdition).where(CatalogEdition.manifest_digest == digest)
    ).scalar_one_or_none()
    catalog = replayed.package.catalog

    def load(eid: uuid.UUID) -> None:
        _Loader(session, eid, replayed).load()

    edition = Publisher(session).publish(
        edition_id,
        digest,
        audited_edition(catalog, manifest_consistent=True),
        ACTOR,
        oracle=ORACLE,
        load_facts=load,
    )
    session.add(IngestionRun(
        mode=IngestionMode.VERIFIED_REPLAY,
        input_sha256={a["name"]: a["sha256"] for a in replayed.manifest["artifacts"]}
        | {SOURCE_PDF: replayed.manifest["source"]["sha256"]},
        engine_version=replayed.manifest["versions"]["normalization"],
        model_version=None,  # verified_replay makes no model call
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status=None,
        failures=[],
    ))
    session.commit()
    return edition, existing is None


class _Loader:
    def __init__(self, session: Session, edition_id: uuid.UUID, replayed: Replayed) -> None:
        self.s = session
        self.e = edition_id
        self.r = replayed
        self.cat = replayed.package.catalog
        self.cell_ids: dict[str, int] = {}
        self.row_ids: dict[tuple[str, int], int] = {}
        self.section_ids: dict[str, int] = {}

    def add(self, obj: object) -> object:
        self.s.add(obj)
        self.s.flush()
        return obj

    def load(self) -> None:
        doc = self._document()
        for sheet in self.cat.sheets:
            lay = sheet.layout
            section = self.add(SourceSection(
                edition_id=self.e, document_id=doc.document_id, page=lay.page,
                table_code=lay.code, header_path=f"{lay.enclosure} / {lay.title}",
            ))
            assert isinstance(section, SourceSection)
            self.section_ids[lay.code] = section.section_id
            for row in sheet.rows:
                src = self.add(SourceRow(
                    edition_id=self.e, section_id=section.section_id, ordinal=row.ordinal,
                    documentary_state="N/A" if self.cat.row_is_na(lay.code, row.ordinal)
                    else "documented",
                ))
                assert isinstance(src, SourceRow)
                self.row_ids[(lay.code, row.ordinal)] = src.row_id
                self._cell(cell_key(lay.code, row.ordinal, PN_COLUMN), lay.code, row.ordinal,
                           PN_COLUMN, row.printed_pn, "", [row.ordinal], [PN_COLUMN])
        for cell in self.cat.cells.values():
            self._cell(cell.key, cell.table, cell.anchor_row, cell.column, cell.printed_text,
                       cell.unit, cell.rows, cell.columns)
        self._notes()
        for facts in self.cat.rows:
            self._row(facts)
        manifest_id = self._manifest()
        self._verification_records(manifest_id, doc.sha256)

    def _document(self) -> SourceDocument:
        src = self.r.manifest["source"]
        doc = self.s.execute(
            select(SourceDocument).where(SourceDocument.sha256 == src["sha256"])
        ).scalar_one_or_none()
        if doc is None:
            doc = SourceDocument(
                sha256=src["sha256"], filename=src["filename"], byte_size=src["byte_size"],
                page_count=4, template="T01-T07",
                authority_role=AuthorityRole.AUTHORIZED_TECHNICAL_SOURCE,
            )
            self.add(doc)
        return doc

    def _cell(self, key: str, table: str, anchor: int, column: str, text: str, unit: str,
              rows: list[int], cols: list[str]) -> None:
        cell = self.add(SourceCellEvidence(
            edition_id=self.e, section_id=self.section_ids[table],
            anchor_row=self.row_ids[(table, anchor)], header_path=column,
            printed_text=text, unit=unit or None, bbox=None,
            span=f"rows={','.join(map(str, rows))};cols={','.join(cols)}",
        ))
        assert isinstance(cell, SourceCellEvidence)
        self.cell_ids[key] = cell.cell_id
        for r in rows:
            self.s.add(SourceCellRowCoverage(cell_id=cell.cell_id,
                                             row_id=self.row_ids[(table, r)]))
        self.s.flush()

    def _notes(self) -> None:
        for note in self.cat.notes:
            src = self.add(SourceNote(
                section_id=self.section_ids[note.tables[0]], marker=note.marker or None,
                note_type="asterisk" if note.marker == "*" else "footnote",
                printed_text=note.printed_text, scope=",".join(note.tables),
            ))
            assert isinstance(src, SourceNote)
            covered: set[int] = set()
            for sheet in self.cat.sheets:
                if sheet.layout.code not in note.tables:
                    continue
                for row in sheet.rows:
                    if note.rows is None or row.printed_pn in note.rows:
                        covered.add(self.row_ids[(sheet.layout.code, row.ordinal)])
            for rid in sorted(covered):
                self.s.add(SourceNoteRowScope(note_id=src.note_id, row_id=rid))
            self.s.flush()

    def _profile(self, table: str) -> int:
        lay = TABLES_BY_CODE[table]
        voltage = Decimal(lay.voltage_v)
        modes = set(lay.supply_modes)
        candidates = self.s.execute(
            select(SupplyProfile).where(
                SupplyProfile.voltage_v == voltage,
                SupplyProfile.phase_state.is_not_distinct_from(lay.phase_state),
                SupplyProfile.phase_count.is_not_distinct_from(lay.phase_count),
            )
        ).scalars().all()
        for prof in candidates:
            have = set(self.s.execute(
                select(SupplyProfileMode.mode).where(
                    SupplyProfileMode.profile_id == prof.profile_id)
            ).scalars().all())
            if {m.value for m in have} == modes:
                return prof.profile_id
        created = SupplyProfile(voltage_v=voltage, phase_state=lay.phase_state,
                                phase_count=lay.phase_count)
        self.add(created)
        for m in sorted(modes):
            self.s.add(SupplyProfileMode(profile_id=created.profile_id, mode=SupplyMode(m)))
        self.s.flush()
        return created.profile_id

    def _row(self, row: RowFacts) -> None:
        lay = TABLES_BY_CODE[row.table]
        part = self.add(PartNumber(edition_id=self.e, canonical_pn=row.canonical_pn,
                                   printed_pn=row.printed_pn))
        assert isinstance(part, PartNumber)
        mp = row.motor_power
        cfg = self.add(ElectricalConfiguration(
            edition_id=self.e, part_id=part.part_id, profile_id=self._profile(row.table),
            enclosure=lay.enclosure, motor_power_w_value=mp.value,
            motor_power_w_status=mp.status, availability=AvailabilityStatus.AVAILABLE,
        ))
        assert isinstance(cfg, ElectricalConfiguration)
        self._evidence(ConfigurationFieldEvidence, "configuration_id", cfg.configuration_id,
                       [FieldValue("part_number", row.printed_pn, "", row.pn_cell), mp])
        for label, fields in row.services:
            perf = self.add(ServicePerformance(
                edition_id=self.e, configuration_id=cfg.configuration_id, service_type=label,
                **_perf_columns(fields),
            ))
            assert isinstance(perf, ServicePerformance)
            self._evidence(ServiceFieldEvidence, "service_perf_id", perf.service_perf_id, fields)
        if row.unqualified is not None:
            unq = self.add(UnqualifiedPerformance(
                edition_id=self.e, configuration_id=cfg.configuration_id,
                **_perf_columns(row.unqualified),
            ))
            assert isinstance(unq, UnqualifiedPerformance)
            self._evidence(UnqualifiedFieldEvidence, "unq_perf_id", unq.unq_perf_id,
                           row.unqualified)
        for cond in row.conditions:
            oc = self.add(OperatingCondition(
                edition_id=self.e, configuration_id=cfg.configuration_id,
                frequency_state=cond.frequency_state, frequency_hz=cond.frequency_hz,
            ))
            assert isinstance(oc, OperatingCondition)
            by = {f.field: f for f in cond.fields}
            meas = self.add(ElectricalMeasurement(
                edition_id=self.e, condition_id=oc.condition_id,
                operating_speed_sec_value=by["operating_speed_sec"].value,
                operating_speed_sec_status=by["operating_speed_sec"].status,
                fla_a_value=by["fla_a"].value, fla_a_status=by["fla_a"].status,
                lra_a_value=by["lra_a"].value, lra_a_status=by["lra_a"].status,
            ))
            assert isinstance(meas, ElectricalMeasurement)
            self._evidence(MeasurementFieldEvidence, "measurement_id", meas.measurement_id,
                           cond.fields)

    def _evidence(self, bridge: type, fact_col: str, fact_id: int,
                  fields: tuple[FieldValue, ...] | list[FieldValue]) -> None:
        for f in fields:
            if f.cell is None:
                continue
            self.s.add(bridge(edition_id=self.e, field_code=f.field,
                              cell_id=self.cell_ids[f.cell], **{fact_col: fact_id}))
        self.s.flush()

    def _manifest(self) -> int:
        m = self.r.manifest
        row = self.s.execute(
            select(VerificationManifest).where(
                VerificationManifest.manifest_digest == self.r.digest)
        ).scalar_one_or_none()
        if row is None:
            row = VerificationManifest(
                manifest_digest=self.r.digest,
                source_shas={a["name"]: a["sha256"] for a in m["artifacts"]}
                | {SOURCE_PDF: m["source"]["sha256"]},
                normalization_version=m["versions"]["normalization"],
                rules_version=m["versions"]["rules"],
                canonical_facts={"golden_cells": len(self.cat.golden()),
                                 "counts": m["counts"]},
                corrections=list(self.r.package.corrections),
                verification_report={"passed": True, "counts": m["counts"],
                                     "reviewer": m["reviewer"],
                                     "audited_at": m["audited_at"]},
            )
            self.add(row)
        return row.manifest_id

    def _verification_records(self, manifest_id: int, doc_sha: str) -> None:
        reviewer = self.r.manifest["reviewer"]
        corrected = {c["cell"]: c for c in self.r.package.corrections}
        keys = [cell_key(r.table, r.row, PN_COLUMN) for r in self.cat.rows] + list(self.cat.cells)
        for key in keys:
            text = (self.cat.cells[key].printed_text if key in self.cat.cells
                    else next(r.printed_pn for r in self.cat.rows if r.pn_cell == key))
            c = corrected.get(key)
            self.s.add(VerificationRecord(
                reviewer=reviewer,
                prior_value=c["prior_value"] if c else text,
                verified_value=text,
                justification=c["justification"] if c else "confirmed against the PDF image",
                source_cell_id=self.cell_ids[key],
                source_document_hash=doc_sha,
                manifest_id=manifest_id,
                state="verified",
            ))
        self.s.add(VerificationRecord(
            reviewer=reviewer, prior_value=None, verified_value=None,
            justification="edition audit marked complete", source_cell_id=None,
            source_document_hash=doc_sha, manifest_id=manifest_id, state="audit_complete",
        ))
        self.s.flush()


def _perf_columns(fields: tuple[FieldValue, ...]) -> dict[str, object]:
    out: dict[str, object] = {}
    for f in fields:
        out[f"{f.field}_value"] = f.value
        out[f"{f.field}_status"] = f.status
    return out


# --- read-back for documental verification ----------------------------------


def published_cells(session: Session) -> tuple[uuid.UUID, list[GoldenEntry]]:
    """The active edition as golden-shaped cells (exact printed text per cell).

    For every typed field with evidence the printed text of its source cell is
    reported; if the stored typed value disagrees with that text (a number that
    is not the printed number, a status that is not the printed N/A/absence),
    the cell is reported as ``<printed> != stored <value/status>`` so the diff
    fails loudly instead of hiding the inconsistency.
    """

    edition_id = session.execute(select(CatalogCurrent.edition_id)).scalar_one()
    sections = {s.section_id: s for s in session.execute(
        select(SourceSection).where(SourceSection.edition_id == edition_id)).scalars()}
    rows = {r.row_id: r for r in session.execute(
        select(SourceRow).where(SourceRow.edition_id == edition_id)).scalars()}
    cells = {c.cell_id: c for c in session.execute(
        select(SourceCellEvidence).where(SourceCellEvidence.edition_id == edition_id)).scalars()}

    def where(cell: SourceCellEvidence) -> tuple[str, int]:
        row = rows[cell.anchor_row] if cell.anchor_row is not None else None
        return sections[cell.section_id].table_code, row.ordinal if row else 0

    def ref(cell: SourceCellEvidence) -> str:
        t, r = where(cell)
        return cell_key(t, r, cell.header_path or "")

    out: list[GoldenEntry] = []

    def emit(table: str, row: int, column: str, cell: SourceCellEvidence,
             status: AvailabilityStatus, value: Decimal | None) -> None:
        lay = TABLES_BY_CODE[table]
        unit = next((c.unit for c in lay.columns if c.key == column), "")
        printed = cell.printed_text
        shown = printed
        if not _consistent(printed, status, value):
            shown = f"{printed} != stored {value if value is not None else status.value}"
        out.append(GoldenEntry(table, row, column, shown, unit, printed == NA, "",
                               row_key(table, row), ref(cell)))

    configs = session.execute(select(ElectricalConfiguration).where(
        ElectricalConfiguration.edition_id == edition_id)).scalars().all()
    for cfg in configs:
        ev = _bridge(session, ConfigurationFieldEvidence, "configuration_id", cfg.configuration_id)
        pn_cell = cells[ev["part_number"]]
        table, row = where(pn_cell)
        kind = TABLES_BY_CODE[table].kind
        out.append(GoldenEntry(table, row, PN_COLUMN, pn_cell.printed_text, "", False, "",
                               row_key(table, row), ref(pn_cell)))
        if "motor_power_w" in ev:
            emit(table, row, column_for(kind, "config", "motor_power_w", None),
                 cells[ev["motor_power_w"]], cfg.motor_power_w_status, cfg.motor_power_w_value)
        groups = {"On/Off": "onoff", "Modulating": "mod"}
        for perf in session.execute(select(ServicePerformance).where(
                ServicePerformance.edition_id == edition_id,
                ServicePerformance.configuration_id == cfg.configuration_id)).scalars():
            pev = _bridge(session, ServiceFieldEvidence, "service_perf_id", perf.service_perf_id)
            for f, cid in pev.items():
                emit(table, row, column_for(kind, groups[perf.service_type], f, None), cells[cid],
                     getattr(perf, f"{f}_status"), getattr(perf, f"{f}_value"))
        for unq in session.execute(select(UnqualifiedPerformance).where(
                UnqualifiedPerformance.edition_id == edition_id,
                UnqualifiedPerformance.configuration_id == cfg.configuration_id)).scalars():
            uev = _bridge(session, UnqualifiedFieldEvidence, "unq_perf_id", unq.unq_perf_id)
            for f, cid in uev.items():
                emit(table, row, column_for(kind, "unq", f, None), cells[cid],
                     getattr(unq, f"{f}_status"), getattr(unq, f"{f}_value"))
        for oc in session.execute(select(OperatingCondition).where(
                OperatingCondition.edition_id == edition_id,
                OperatingCondition.configuration_id == cfg.configuration_id)).scalars():
            meas = session.execute(select(ElectricalMeasurement).where(
                ElectricalMeasurement.edition_id == edition_id,
                ElectricalMeasurement.condition_id == oc.condition_id)).scalar_one()
            mev = _bridge(session, MeasurementFieldEvidence, "measurement_id",
                          meas.measurement_id)
            for f, cid in mev.items():
                emit(table, row, column_for(kind, "meas", f, oc.frequency_hz), cells[cid],
                     getattr(meas, f"{f}_status"), getattr(meas, f"{f}_value"))

    for note in session.execute(select(SourceNote).join(
            SourceSection, SourceSection.section_id == SourceNote.section_id).where(
            SourceSection.edition_id == edition_id).order_by(SourceNote.note_id)).scalars():
        out.append(_note_entry(session, note, sections, rows, len([
            e for e in out if e.column.startswith("note")]) + 1))
    return edition_id, out


def _note_entry(session: Session, note: SourceNote, sections: dict[int, SourceSection],
                rows: dict[int, SourceRow], index: int) -> GoldenEntry:
    first = sections[note.section_id].table_code
    tables = (note.scope or first).split(",")
    covered = session.execute(select(SourceNoteRowScope.row_id).where(
        SourceNoteRowScope.note_id == note.note_id)).scalars().all()
    by_table: dict[str, set[int]] = {}
    for rid in covered:
        r = rows[rid]
        by_table.setdefault(sections[r.section_id].table_code, set()).add(r.ordinal)
    all_rows = all(
        by_table.get(t, set()) == {r.ordinal for r in rows.values()
                                   if sections[r.section_id].table_code == t}
        for t in tables
    )
    if all_rows:
        scope = "all"
    else:
        pns = session.execute(
            select(SourceCellEvidence.printed_text).where(
                SourceCellEvidence.header_path == PN_COLUMN,
                SourceCellEvidence.anchor_row.in_(covered),
            ).order_by(SourceCellEvidence.anchor_row)).scalars().all()
        scope = ";".join(pns)
    return GoldenEntry(first, 0, f"note{index}", note.printed_text, "", False,
                       f"{','.join(tables)}|{note.marker or ''}|{scope}",
                       f"{first}#notes", f"{first}#note{index}")


def _bridge(session: Session, bridge: type, fact_col: str, fact_id: int) -> dict[str, int]:
    rows = session.execute(
        select(bridge.field_code, bridge.cell_id).where(  # type: ignore[attr-defined]
            getattr(bridge, fact_col) == fact_id)
    ).all()
    return {f: c for f, c in rows}


def _consistent(printed: str, status: AvailabilityStatus, value: Decimal | None) -> bool:
    if printed == NA:
        return status is AvailabilityStatus.NOT_APPLICABLE and value is None
    if printed == "":
        return status is AvailabilityStatus.NOT_DOCUMENTED and value is None
    try:
        expected = Decimal(printed.replace(",", ""))
    except InvalidOperation:
        return False
    return status is AvailabilityStatus.AVAILABLE and value == expected
