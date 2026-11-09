"""Audited sheets -> source cells -> typed facts and golden values (pure).

Everything here is a deterministic function of the audited sheets: the same
sheets always yield the same cells, facts, golden values and counts, which is
what lets ``verified_replay`` rebuild an identical edition without the PDF and
without any model call. No value is computed, converted or inferred: numbers
are parsed from the printed text exactly (``Decimal``), N/A stays N/A, an empty
printed cell stays absent, and merged cells only cover what the auditor marked
with ``^`` / ``<``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from series76_data.etl.layout import SERVICE_LABELS, TableKind, TableLayout
from series76_data.etl.sheets import (
    MERGED_ABOVE,
    MERGED_LEFT,
    NA,
    AuditedNote,
    AuditedSheet,
)
from series76_data.models.enums import AvailabilityStatus, FrequencyState
from series76_data.models.value_status import Measured
from series76_data.pipeline.normalizer import PrintedCell, normalize_metric
from series76_data.pipeline.verifier import AuditedCounts

PN_COLUMN = "pn"


def cell_key(table: str, row: int, column: str) -> str:
    return f"{table}#{row}:{column}"


def row_key(table: str, row: int) -> str:
    return f"{table}#{row}"


@dataclass(slots=True)
class SourceCell:
    """One printed cell of the PDF (merged cells are one cell covering many)."""

    key: str
    table: str
    anchor_row: int
    column: str
    printed_text: str
    unit: str
    rows: list[int] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)

    @property
    def span(self) -> str:
        return f"rows={','.join(map(str, self.rows))};cols={','.join(self.columns)}"


@dataclass(frozen=True, slots=True)
class FieldValue:
    """A typed field of a fact with its exact printed text and source cell."""

    field: str
    printed: str
    unit: str
    cell: str | None  # origin cell key; None when the layout has no such column

    def measured(self) -> Measured:
        text = self.printed if self.cell is not None else ""
        unit = self.unit or None
        return normalize_metric(self.field, PrintedCell(text, unit))

    @property
    def status(self) -> AvailabilityStatus:
        return self.measured().metric.status

    @property
    def value(self) -> Decimal | None:
        return self.measured().metric.value


@dataclass(frozen=True, slots=True)
class ConditionFacts:
    frequency_state: FrequencyState
    frequency_hz: Decimal | None
    fields: tuple[FieldValue, ...]


@dataclass(frozen=True, slots=True)
class RowFacts:
    """Every typed fact of one printed row (one part number, one configuration)."""

    table: str
    row: int
    printed_pn: str
    canonical_pn: str
    pn_cell: str
    motor_power: FieldValue
    services: tuple[tuple[str, tuple[FieldValue, ...]], ...]
    unqualified: tuple[FieldValue, ...] | None
    conditions: tuple[ConditionFacts, ...]


@dataclass(frozen=True, slots=True)
class GoldenEntry:
    """One golden value: a (table, row, column) of the PDF with its exact text."""

    table: str
    row: int
    column: str
    printed_value: str
    unit: str
    not_applicable: bool
    note: str
    row_ref: str
    cell_ref: str

    def as_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "row": self.row,
            "column": self.column,
            "printed_value": self.printed_value,
            "unit": self.unit,
            "not_applicable": self.not_applicable,
            "note": self.note,
            "row_ref": self.row_ref,
            "cell_ref": self.cell_ref,
        }


@dataclass(slots=True)
class Catalog:
    sheets: tuple[AuditedSheet, ...]
    notes: tuple[AuditedNote, ...]
    cells: dict[str, SourceCell]
    origin: dict[tuple[str, int, str], str]  # (table, row, column) -> cell key
    rows: list[RowFacts]

    # --- counts for the publication gate --------------------------------
    def counts(self) -> AuditedCounts:
        na_rows = {
            (c.table, r) for c in self.cells.values() if c.printed_text == NA for r in c.rows
        }
        return AuditedCounts(
            tables=len(self.sheets),
            rows=sum(len(s.rows) for s in self.sheets),
            na_values=len(na_rows),
        )

    def canonical_pns(self) -> tuple[str, ...]:
        return tuple(r.canonical_pn for r in self.rows)

    def row_is_na(self, table: str, row: int) -> bool:
        return any(
            self.cells[k].printed_text == NA
            for (t, r, _c), k in self.origin.items()
            if t == table and r == row
        )

    # --- golden ---------------------------------------------------------
    def golden(self) -> list[GoldenEntry]:
        out: list[GoldenEntry] = []
        for sheet in self.sheets:
            t = sheet.layout.code
            for row in sheet.rows:
                out.append(GoldenEntry(t, row.ordinal, PN_COLUMN, row.printed_pn, "", False, "",
                                       row_key(t, row.ordinal), cell_key(t, row.ordinal,
                                                                         PN_COLUMN)))
                for col in sheet.layout.columns:
                    origin = self.cells[self.origin[(t, row.ordinal, col.key)]]
                    out.append(GoldenEntry(
                        t, row.ordinal, col.key, origin.printed_text, col.unit,
                        origin.printed_text == NA, "", row_key(t, row.ordinal), origin.key,
                    ))
        for note in self.notes:
            scope = "all"
            if note.rows is not None:  # in printed row order, independent of typing order
                scope = ";".join(
                    r.printed_pn for s in self.sheets if s.layout.code in note.tables
                    for r in s.rows if r.printed_pn in note.rows
                )
            out.append(GoldenEntry(
                note.tables[0], 0, f"note{note.index}", note.printed_text, "", False,
                f"{','.join(note.tables)}|{note.marker}|{scope}",
                f"{note.tables[0]}#notes", f"{note.tables[0]}#note{note.index}",
            ))
        return out


def build_catalog(sheets: tuple[AuditedSheet, ...], notes: tuple[AuditedNote, ...]) -> Catalog:
    cells: dict[str, SourceCell] = {}
    origin: dict[tuple[str, int, str], str] = {}
    for sheet in sheets:
        t = sheet.layout.code
        keys = sheet.layout.column_keys
        units = {c.key: c.unit for c in sheet.layout.columns}
        for row in sheet.rows:
            for i, col in enumerate(keys):
                value = row.cells[col]
                if value == MERGED_ABOVE:
                    key = origin[(t, row.ordinal - 1, col)]
                elif value == MERGED_LEFT:
                    key = origin[(t, row.ordinal, keys[i - 1])]
                else:
                    key = cell_key(t, row.ordinal, col)
                    cells[key] = SourceCell(key, t, row.ordinal, col, value, units[col])
                origin[(t, row.ordinal, col)] = key
                c = cells[key]
                if row.ordinal not in c.rows:
                    c.rows.append(row.ordinal)
                if col not in c.columns:
                    c.columns.append(col)
    catalog = Catalog(sheets, notes, cells, origin, [])
    catalog.rows = [_row_facts(catalog, s.layout, r.ordinal, r.printed_pn)
                    for s in sheets for r in s.rows]
    return catalog


def _field(catalog: Catalog, layout: TableLayout, row: int, column: str, name: str,
           unit: str) -> FieldValue:
    if column not in layout.column_keys:
        return FieldValue(name, "", unit, None)
    key = catalog.origin[(layout.code, row, column)]
    return FieldValue(name, catalog.cells[key].printed_text, unit, key)


_PERF_FIELDS = (
    ("torque_inlbs", "in-lbs"),
    ("torque_nm", "Nm"),
    ("duty_s4_pct", "%"),
    ("cycles_per_hour", ""),
    ("starts_per_hour", ""),
)
_MEAS_FIELDS = (("operating_speed_sec", "sec"), ("fla_a", "A"), ("lra_a", "A"))


def _row_facts(catalog: Catalog, layout: TableLayout, row: int, printed_pn: str) -> RowFacts:
    t = layout.code

    def perf(group: str) -> tuple[FieldValue, ...]:
        return tuple(_field(catalog, layout, row, f"{group}.{f}", f, u) for f, u in _PERF_FIELDS)

    services: list[tuple[str, tuple[FieldValue, ...]]] = []
    unqualified: tuple[FieldValue, ...] | None = None
    if layout.kind is TableKind.DUAL_SERVICE:
        services = [(SERVICE_LABELS["onoff"], perf("onoff")), (SERVICE_LABELS["mod"], perf("mod"))]
    elif layout.kind is TableKind.ONOFF_24:
        services = [(SERVICE_LABELS["onoff"], perf("onoff"))]
    elif layout.kind is TableKind.MODULATING_24:
        services = [(SERVICE_LABELS["mod"], perf("mod"))]
    else:
        unqualified = perf("unq")

    conditions: list[ConditionFacts] = []
    if layout.kind in (TableKind.DUAL_SERVICE, TableKind.UNQUALIFIED):
        for hz in ("60", "50"):
            conditions.append(ConditionFacts(
                FrequencyState.EXPLICIT, Decimal(hz),
                tuple(_field(catalog, layout, row, f"meas.{f}@{hz}", f, u)
                      for f, u in _MEAS_FIELDS),
            ))
    else:
        conditions.append(ConditionFacts(
            FrequencyState.NOT_SPECIFIED, None,
            tuple(_field(catalog, layout, row, f"meas.{f}", f, u) for f, u in _MEAS_FIELDS),
        ))

    return RowFacts(
        table=t,
        row=row,
        printed_pn=printed_pn,
        canonical_pn=printed_pn.rstrip("*").strip(),
        pn_cell=cell_key(t, row, PN_COLUMN),
        motor_power=_field(catalog, layout, row, "config.motor_power_w", "motor_power_w", "W"),
        services=tuple(services),
        unqualified=unqualified,
        conditions=tuple(conditions),
    )


def column_for(kind: TableKind, group: str, field_name: str, hz: Decimal | None) -> str:
    """The sheet column a typed field was read from (inverse of ``_row_facts``)."""

    if group == "config":
        return "config.motor_power_w"
    if group == "meas":
        if kind in (TableKind.DUAL_SERVICE, TableKind.UNQUALIFIED) and hz is not None:
            return f"meas.{field_name}@{int(hz)}"
        return f"meas.{field_name}"
    return f"{group}.{field_name}"
