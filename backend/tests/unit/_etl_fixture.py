"""A SYNTHETIC, fully audited Spec 1 package for the ETL tests.

Every value below is an arbitrary fixture value generated from the row/column
index — none is a figure from ``series_76_electric_data.pdf``. Part numbers use
the ``SYN`` marker so they can never be mistaken for catalog part numbers. The
package has the same SHAPE as the real audit (7 tables, 11/16/11/5/5/10/10 rows,
a 4-row N/A block in T03, Motor Power merged in bands of two rows, notes) so the
7/68/4 oracle and every code path are exercised.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from series76_data.etl.layout import TABLES
from series76_data.etl.replay import DRAFT_FILE, NOTES_FILE
from series76_data.etl.sheets import NOTES_HEADERS, headers_for

ROWS = {"T01": 11, "T02": 16, "T03": 11, "T04": 5, "T05": 5, "T06": 10, "T07": 10}
REVIEWER = "Synthetic Reviewer"


def pn(table_index: int, row: int) -> str:
    return f"76{1 + row % 7}Q{table_index:02d}-SYN{table_index % 10}{row:04d}/A"


def value(table_index: int, row: int, col: int) -> str:
    n = (table_index * 97 + row * 31 + col * 17) % 900 + 10
    if col % 5 == 0:
        return f"{n // 10}.{n % 10}"  # one decimal, like the printed currents
    if col % 4 == 0:
        return f"{n + 1000:,}"  # thousands separator, like the printed torques
    return str(n)


def sheet_rows(table_index: int, code: str) -> list[dict[str, str]]:
    layout = TABLES[table_index - 1]
    keys = layout.column_keys
    rows: list[dict[str, str]] = []
    for r in range(1, ROWS[code] + 1):
        cells: dict[str, str] = {"pn": pn(table_index, r)}
        for c, key in enumerate(keys):
            if key == "config.motor_power_w":
                if code == "T03" and r <= 4:
                    cells[key] = ""  # not printed for the N/A rows
                else:
                    first = r % 2 == 1
                    cells[key] = str(10 + table_index * 5 + r) if first else "^"
                continue
            if code == "T03" and r <= 4:
                cells[key] = ("N/A" if c == 0 else "<") if r == 1 else "^"
                continue
            cells[key] = value(table_index, r, c)
        rows.append(cells)
    if code == "T03":  # the first row after the N/A block starts a new merged band
        rows[4]["config.motor_power_w"] = "77"
    return rows


def render(code: str, rows: list[dict[str, str]], audit: str = "OK") -> str:
    layout = next(t for t in TABLES if t.code == code)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers_for(layout))
    for i, row in enumerate(rows, start=1):
        w.writerow([i, row["pn"], *(row[k] for k in layout.column_keys), audit, ""])
    return buf.getvalue()


NOTES = [
    ["T01,T02", "*", "Synthetic asterisk note", None, "OK", ""],
    ["T01,T02", "1", "Synthetic note one", "all", "OK", ""],
    ["T04,T05", "", "Synthetic certification\nline two", "all", "OK", ""],
]


def write_package(audit_dir: Path, pdf: Path) -> dict[str, list[dict[str, str]]]:
    """Write the audited sheets, notes and an OCR draft equal to them."""

    audit_dir.mkdir(parents=True, exist_ok=True)
    sheets: dict[str, list[dict[str, str]]] = {}
    for i, t in enumerate(TABLES, start=1):
        rows = sheet_rows(i, t.code)
        sheets[t.code] = rows
        (audit_dir / f"{t.code}.csv").write_text(render(t.code, rows), encoding="utf-8")
    star_rows = ";".join(pn(2, r) for r in (12, 13))
    notes = [[*n[:3], star_rows if n[3] is None else n[3], *n[4:]] for n in NOTES]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(NOTES_HEADERS)
    w.writerows(notes)
    (audit_dir / NOTES_FILE).write_text(buf.getvalue(), encoding="utf-8")
    draft = {"engine": {"engine": "synthetic"}, "sheets": sheets, "notes": [n[2] for n in notes]}
    (audit_dir / DRAFT_FILE).write_text(json.dumps(draft), encoding="utf-8")
    pdf.write_bytes(b"%PDF-1.7 synthetic fixture, not the real catalog\n")
    return sheets
