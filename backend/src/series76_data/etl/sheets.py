"""Audit sheets: the human-audited, versioned source of every catalog value.

One CSV per printed table (``T01.csv`` … ``T07.csv``) with the same rows and
columns as the PDF, plus ``notes.csv``. The auditor compares each row against
the PDF image, fixes what differs, and writes ``OK`` in the ``Audit`` column.

Cell syntax (exactly what is printed in that cell of the PDF):

* a number as printed, thousands separators included (``1,330``, ``0.7``);
* ``N/A`` when the PDF prints N/A;
* empty when nothing is printed in that cell;
* ``^`` — this cell is part of the same merged printed cell as the cell above;
* ``<`` — this cell is part of the same merged printed cell as the cell left;
* a leading ``?`` marks an OCR guess the auditor has not resolved yet. The
  loader refuses any sheet that still contains one.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from series76_data.etl.layout import TABLES_BY_CODE, Column, TableLayout

MERGED_ABOVE = "^"
MERGED_LEFT = "<"
UNSURE = "?"
NA = "N/A"
AUDIT_OK = "OK"

ROW_HEADER = "Row"
PN_HEADER = "Base Part Number"
AUDIT_HEADER = "Audit"
JUSTIFICATION_HEADER = "Justification"

NOTES_HEADERS = ("Tables", "Marker", "Printed Text", "Rows", AUDIT_HEADER, JUSTIFICATION_HEADER)
ALL_ROWS = "all"

PN_RE = re.compile(r"^76[1-7][A-Z0-9]{3}-[0-9A-Z]{8}/A\*?$")
NUMBER_RE = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


class SheetError(ValueError):
    """An audit sheet is malformed or not fully audited."""


# --- drafts (written by the OCR step) --------------------------------------


@dataclass(frozen=True, slots=True)
class DraftCell:
    text: str
    conf: float


@dataclass(slots=True)
class SheetDraft:
    table: str
    rows: list[tuple[DraftCell, list[DraftCell]]]


@dataclass(frozen=True, slots=True)
class NoteDraft:
    tables: str
    line: str


def _draft_text(cell: DraftCell, floor: float) -> str:
    text = cell.text.strip()
    if text in (MERGED_ABOVE, MERGED_LEFT):
        return text
    if not text:
        return UNSURE  # the engine read nothing: auditor decides (empty or a value)
    if text.upper() == NA:
        return NA if cell.conf >= floor else UNSURE + text
    plausible = (NUMBER_RE.match(text) or PN_RE.match(text)) and not suspicious(text)
    return text if plausible and cell.conf >= floor else UNSURE + text


_THOUSANDS_AS_DECIMAL = re.compile(r"^\d+\.\d{3,}$")
_LEADING_ZERO = re.compile(r"^0\d")


def suspicious(text: str) -> bool:
    """Classic OCR confusions that would otherwise look like valid values.

    * ``5.300`` — a thousands separator read as a decimal point;
    * ``06`` — an integer with a leading zero (no printed value has one);
    * a part number containing the letters O/I/L (read for the digits 0/1).
    """

    if PN_RE.match(text):
        return any(ch in text.split("-", 1)[1] for ch in "OIL") or "O" in text[:6]
    return bool(_THOUSANDS_AS_DECIMAL.match(text) or _LEADING_ZERO.match(text))


def headers_for(layout: TableLayout) -> list[str]:
    return [ROW_HEADER, PN_HEADER, *(c.header for c in layout.columns),
            AUDIT_HEADER, JUSTIFICATION_HEADER]


def draft_rows(draft: SheetDraft, floor: float) -> list[dict[str, str]]:
    """The drafted text of every cell, keyed by column (``pn`` for the PN)."""

    keys = TABLES_BY_CODE[draft.table].column_keys
    return [
        {"pn": _draft_text(pn, floor), **{k: _draft_text(c, floor) for k, c in zip(keys, cells,
                                                                                    strict=True)}}
        for pn, cells in draft.rows
    ]


def render_sheet(table: str, rows: list[dict[str, str]]) -> str:
    layout = TABLES_BY_CODE[table]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers_for(layout))
    for i, row in enumerate(rows, start=1):
        writer.writerow([i, row["pn"], *(row[k] for k in layout.column_keys), "", ""])
    return buf.getvalue()


_NOTE_START = re.compile(r"^(\d+)\.\s*|^(\*)\s*")


def note_rows_from_lines(
    drafts: list[NoteDraft], star_pns: dict[str, list[str]] | None = None
) -> list[list[str]]:
    """Group OCR'd note lines into notes: a numbered/asterisk line starts a note.

    ``star_pns`` maps a table scope to the drafted part numbers ending with
    ``*``; they pre-fill (unresolved) the rows an asterisk note covers.
    """

    notes: list[list[str]] = []
    for d in drafts:
        line = d.line.strip()
        unsure = line.startswith(UNSURE)
        body = line[1:] if unsure else line
        if body.rstrip(":").strip().upper() == "NOTES":
            continue
        m = _NOTE_START.match(body)
        if m or not notes or notes[-1][0] != d.tables:
            marker = (m.group(1) or m.group(2)) if m else ""
            text = body[m.end():] if m else body
            scope = ALL_ROWS
            if marker == "*":
                pns = (star_pns or {}).get(d.tables, [])
                scope = ";".join(pns) if pns else "rows whose part number ends with *"
            notes.append([d.tables, marker, (UNSURE if unsure else "") + text, scope, "", ""])
        else:
            notes[-1][2] = notes[-1][2] + "\n" + body
            if unsure and not notes[-1][2].startswith(UNSURE):
                notes[-1][2] = UNSURE + notes[-1][2]
    for n in notes:
        # OCR spacing in running text is unreliable ("Fullload"), and a note must
        # be stored verbatim: every note text starts unresolved.
        if not n[2].startswith(UNSURE):
            n[2] = UNSURE + n[2]
        if n[3] != ALL_ROWS:
            n[3] = UNSURE + n[3]  # star scope: auditor lists the exact rows
    return notes


def render_notes(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(NOTES_HEADERS)
    writer.writerows(rows)
    return buf.getvalue()


# --- audited sheets (read by build/replay) ---------------------------------


@dataclass(frozen=True, slots=True)
class AuditedRow:
    ordinal: int
    printed_pn: str
    cells: dict[str, str]
    justification: str


@dataclass(frozen=True, slots=True)
class AuditedSheet:
    layout: TableLayout
    rows: tuple[AuditedRow, ...]


@dataclass(frozen=True, slots=True)
class AuditedNote:
    index: int
    tables: tuple[str, ...]
    marker: str
    printed_text: str
    rows: tuple[str, ...] | None  # None = all rows of the listed tables
    justification: str


@dataclass(slots=True)
class AuditProblems:
    problems: list[str] = field(default_factory=list)

    def add(self, where: str, what: str) -> None:
        self.problems.append(f"{where}: {what}")


def parse_sheet(table: str, text: str, problems: AuditProblems) -> AuditedSheet:
    layout = TABLES_BY_CODE[table]
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows or rows[0] != headers_for(layout):
        raise SheetError(f"{table}.csv: header row does not match the table layout")
    keys = layout.column_keys
    audited: list[AuditedRow] = []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(v.strip() for v in raw):
            continue
        where = f"{table}.csv line {line_no}"
        if len(raw) != len(rows[0]):
            problems.add(where, f"expected {len(rows[0])} columns, found {len(raw)}")
            continue
        ordinal_text, pn, *values = raw
        cells_raw, audit, justification = values[:-2], values[-2].strip(), values[-1].strip()
        try:
            ordinal = int(ordinal_text)
        except ValueError:
            problems.add(where, "Row is not an integer")
            continue
        if ordinal != len(audited) + 1:
            problems.add(where, f"Row must be {len(audited) + 1} (rows are numbered in order)")
        pn = pn.strip()
        if audit.upper() != AUDIT_OK:
            problems.add(where, "row not audited (write OK in the Audit column)")
        if pn.startswith(UNSURE) or not PN_RE.match(pn):
            problems.add(where, f"part number {pn!r} is unresolved or not a Series 76 PN")
        cells: dict[str, str] = {}
        for col_index, (key, value) in enumerate(zip(keys, cells_raw, strict=True)):
            v = value.strip()
            cells[key] = v
            col = layout.columns[col_index].header
            if v.startswith(UNSURE):
                problems.add(where, f"column '{col}' still has an unresolved OCR guess {v!r}")
            elif v == MERGED_ABOVE and not audited:
                problems.add(where, f"column '{col}': '^' on the first row has nothing above")
            elif v == MERGED_LEFT and col_index == 0:
                problems.add(where, f"column '{col}': '<' on the first column has nothing left")
            elif v not in ("", NA, MERGED_ABOVE, MERGED_LEFT) and not NUMBER_RE.match(v):
                problems.add(where, f"column '{col}': {v!r} is not a printed number, N/A, ^, <")
            elif re.match(r"^0\d", v):
                problems.add(where, f"column '{col}': {v!r} has a leading zero (none is printed)")
        audited.append(AuditedRow(ordinal, pn, cells, justification))
    if not audited:
        problems.add(f"{table}.csv", "no rows")
    _check_column_formats(table, layout.columns, audited, problems)
    return AuditedSheet(layout, tuple(audited))


def _check_column_formats(table: str, columns: tuple[Column, ...], rows: list[AuditedRow],
                          problems: AuditProblems) -> None:
    """Flag a column that mixes decimal numbers with whole numbers.

    The catalog prints each column in one style: torques, counts and speeds as
    whole numbers (thousands separated by a comma), currents with one decimal
    after a point. A decimal value among whole numbers (or the reverse) is almost
    always a comma read as a point, so it is reported for the reviewer to check.
    """

    for column in columns:
        decimal: list[int] = []
        whole: list[int] = []
        for row in rows:
            v = row.cells.get(column.key, "")
            if NUMBER_RE.match(v):
                (decimal if "." in v else whole).append(row.ordinal)
        if decimal and whole:
            odd = decimal if len(decimal) <= len(whole) else whole
            problems.add(f"{table}.csv rows {', '.join(map(str, odd))}",
                         f"column '{column.header}' mixes decimal and whole numbers: check the "
                         "point/comma against the PDF")


def parse_notes(text: str, problems: AuditProblems) -> tuple[AuditedNote, ...]:
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows or tuple(rows[0]) != NOTES_HEADERS:
        raise SheetError("notes.csv: header row does not match")
    notes: list[AuditedNote] = []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(v.strip() for v in raw):
            continue
        where = f"notes.csv line {line_no}"
        if len(raw) != len(NOTES_HEADERS):
            problems.add(where, f"expected {len(NOTES_HEADERS)} columns")
            continue
        tables_text, marker, printed, scope, audit, justification = raw
        tables = tuple(t.strip() for t in tables_text.split(",") if t.strip())
        for t in tables:
            if t not in TABLES_BY_CODE:
                problems.add(where, f"unknown table {t!r}")
        if audit.strip().upper() != AUDIT_OK:
            problems.add(where, "note not audited (write OK in the Audit column)")
        if printed.startswith(UNSURE) or scope.startswith(UNSURE):
            problems.add(where, "note text or rows still carry an unresolved '?'")
        if not printed.strip():
            problems.add(where, "empty printed text")
        rows_scope: tuple[str, ...] | None
        if scope.strip().lower() == ALL_ROWS:
            rows_scope = None
        else:
            rows_scope = tuple(p.strip() for p in scope.split(";") if p.strip())
            if not rows_scope:
                problems.add(where, "Rows must be 'all' or part numbers separated by ';'")
        notes.append(AuditedNote(len(notes) + 1, tables, marker.strip(), printed,
                                 rows_scope, justification.strip()))
    return tuple(notes)


def sheet_files(audit_dir: Path) -> dict[str, Path]:
    return {code: audit_dir / f"{code}.csv" for code in TABLES_BY_CODE}
