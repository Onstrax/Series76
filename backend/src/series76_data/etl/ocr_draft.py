"""Deterministic OCR *draft* of the audit sheets (no language model).

``series_76_electric_data.pdf`` is rasterized: every table is an embedded image,
so there is no text layer to read. This module runs a **local** OCR engine
(RapidOCR, ONNX models, CPU) over the embedded images and lays the recognized
tokens out into one audit sheet per table. The draft is only a *candidate*: it
is never published. Every cell must be confirmed or corrected by the human
auditor against the PDF (Spec 1 Req 3), and any cell the engine was unsure of
is written with a ``?`` prefix that the loader refuses until resolved.

Dependencies (optional extra ``etl-draft``): ``rapidocr-onnxruntime`` (which
brings ``opencv`` and ``numpy``) and poppler's ``pdfimages`` binary. Nothing
here is imported by the runtime API, the worker, or the verified_replay path.

Layout recovery is geometric and deterministic:

* rows are anchored on part-number tokens (``76…/A``);
* a token is *row-aligned* when its vertical centre is within 40% of the row
  pitch of a part-number row, otherwise it is a *merged* cell; a merged cell
  covers the rows of its band between two printed horizontal rules;
* columns are recovered by splitting the sorted x-centres of the row-aligned
  tokens at their largest gaps (the column count comes from the layout); a
  column that is only ever printed as a merged cell (e.g. Motor Power) is the
  right-most column.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from series76_data.etl.layout import TABLES, TableLayout
from series76_data.etl.sheets import (
    MERGED_ABOVE,
    MERGED_LEFT,
    PN_RE,
    UNSURE,
    DraftCell,
    NoteDraft,
    SheetDraft,
)

ENGINE_ID = "rapidocr-onnxruntime"
CONFIDENCE_FLOOR = 0.90


_PN_PREFIX = re.compile(r"^76[1-7]")
_NUMBER_RE = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")

# Which embedded image (pdfimages order) holds which tables, top to bottom.
# Structure only: images 0, 2 are the page headings; 1, 3, 4, 5 are the tables.
IMAGE_TABLES: dict[int, tuple[str, ...]] = {
    1: ("T01", "T02"),
    3: ("T03",),
    4: ("T04", "T05"),
    5: ("T06", "T07"),
}
@dataclass(frozen=True, slots=True)
class Token:
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def extract_images(pdf: Path, out_dir: Path) -> list[Path]:
    """Extract the embedded images losslessly with poppler's ``pdfimages``."""

    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["pdfimages", "-png", str(pdf), str(out_dir / "img")],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob("img-*.png"))


# Two independent reads per image (native and 2x bicubic upscale). A cell is
# drafted as-is only when both reads agree; otherwise it is written "?a|b".
OCR_SCALES = (1, 2)


def ocr_tokens(image: Path, scale: int) -> list[Token]:  # pragma: no cover - OCR extra
    """OCR one image upscaled ``scale``x; boxes are returned in original pixels."""

    import cv2  # type: ignore[import-not-found,unused-ignore]
    from rapidocr_onnxruntime import (  # type: ignore[import-untyped,import-not-found,unused-ignore]
        RapidOCR,
    )

    engine = RapidOCR()
    img = cv2.imread(str(image))
    if img is None:
        raise ValueError(f"unreadable image: {image}")
    if scale != 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    result, _ = engine(img)
    tokens: list[Token] = []
    for box, text, conf in result or []:
        xs = [p[0] / scale for p in box]
        ys = [p[1] / scale for p in box]
        tokens.extend(_split_token(Token(str(text).strip(), float(conf),
                                         min(xs), min(ys), max(xs), max(ys))))
    return tokens


_GLUED_DECIMALS = re.compile(r"^(\d+\.\d)(\d+\.\d)$")


def _split_token(tok: Token) -> list[Token]:
    """Split a token the engine merged across columns proportionally.

    Handles space-separated numbers ("26 32") and two one-decimal values glued
    together ("17.017.0"); the halves are flagged by the auditor like any cell.
    """

    glued = _GLUED_DECIMALS.match(tok.text.replace(" ", ""))
    parts = list(glued.groups()) if glued else tok.text.split()
    if len(parts) <= 1 or not all(_NUMBER_RE.match(p) or p.upper() == "N/A" for p in parts):
        return [tok]
    total = sum(len(p) for p in parts) + len(parts) - 1
    width = tok.x1 - tok.x0
    out, offset = [], 0
    for p in parts:
        x0 = tok.x0 + width * offset / total
        x1 = tok.x0 + width * (offset + len(p)) / total
        out.append(Token(p, tok.conf, x0, tok.y0, x1, tok.y1))
        offset += len(p) + 1
    return out


@dataclass(frozen=True, slots=True)
class Rule:
    """A printed horizontal rule and the x-spans it actually crosses."""

    y: float
    spans: tuple[tuple[int, int], ...]

    def crosses(self, x: float) -> bool:
        return any(a - 3 <= x <= b + 3 for a, b in self.spans)


def horizontal_rules(image: Path) -> list[Rule]:  # pragma: no cover - needs the OCR extra
    """Printed horizontal rules: pixel rows that are mostly light-grey-or-darker.

    The rules are thin light-grey lines (alternate-row shading is lighter), so
    a pixel row counts when more than half of it is darker than 210. Each rule
    keeps its dark x-spans, because some rules stop short of a merged column.
    """

    import cv2  # type: ignore[import-not-found,unused-ignore]

    gray = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"unreadable image: {image}")
    dark: list[list[bool]] = (gray < 210).tolist()
    rules: list[Rule] = []
    for y, row in enumerate(dark):
        if sum(row) <= len(row) / 2:
            continue
        if rules and y - rules[-1].y <= 2:
            continue
        spans: list[tuple[int, int]] = []
        start = None
        for x, on in enumerate(row):
            if on and start is None:
                start = x
            elif not on and start is not None:
                if x - start >= 20:
                    spans.append((start, x - 1))
                start = None
        if start is not None and len(row) - start >= 20:
            spans.append((start, len(row) - 1))
        rules.append(Rule(float(y), tuple(spans)))
    return rules


def split_columns(xs: Sequence[float], k: int) -> list[float]:
    """Cluster sorted x-centres into ``k`` columns by cutting the largest gaps."""

    pts = sorted(xs)
    if k <= 1 or len(pts) < k:
        return [sum(pts) / len(pts)] if pts else []
    gaps = sorted(range(1, len(pts)), key=lambda i: pts[i] - pts[i - 1], reverse=True)[: k - 1]
    cuts = sorted(gaps)
    groups, start = [], 0
    for c in [*cuts, len(pts)]:
        groups.append(pts[start:c])
        start = c
    return [sum(g) / len(g) for g in groups]


def layout_table(
    layout: TableLayout,
    tokens: Sequence[Token],
    rules: Sequence[Rule],
) -> SheetDraft:
    """Place one table's tokens into a draft sheet (pure, unit-testable)."""

    pn_tokens = sorted((t for t in tokens if _PN_PREFIX.match(t.text)), key=lambda t: t.cy)
    if not pn_tokens:
        raise ValueError(f"{layout.code}: no part-number tokens recognized")
    row_ys = [t.cy for t in pn_tokens]
    pitch = _median([b - a for a, b in zip(row_ys, row_ys[1:], strict=False)]) or 20.0
    pn_right = max(t.x1 for t in pn_tokens)
    top, bottom = row_ys[0] - pitch * 0.6, row_ys[-1] + pitch * 0.6
    data = [t for t in tokens
            if t not in pn_tokens and t.x0 > pn_right - 2 and top <= t.cy <= bottom]

    def nearest_row(tok: Token) -> int | None:
        i = min(range(len(row_ys)), key=lambda r: abs(row_ys[r] - tok.cy))
        return i if abs(row_ys[i] - tok.cy) <= pitch * 0.4 else None

    k = len(layout.columns)
    # Only Motor Power is printed as a vertically merged cell in these tables;
    # any other column never inherits a value from the row above (a missing
    # token there stays an unresolved '?' for the auditor, never a silent copy).
    mergeable = {i for i, c in enumerate(layout.columns) if c.key == "config.motor_power_w"}
    centres = split_columns([t.cx for t in data if t.text.upper() != "N/A"], k)
    while len(centres) < k:
        centres.append(centres[-1] + pitch * 2 if centres else 0.0)

    def col_of(tok: Token) -> int:
        return min(range(k), key=lambda c: abs(centres[c] - tok.cx))

    grid: list[list[DraftCell | None]] = [[None] * k for _ in row_ys]
    merged: list[Token] = []
    for tok in data:
        c = col_of(tok)
        r = nearest_row(tok)
        if c in mergeable or (r is None and tok.text.upper() == "N/A"):
            merged.append(tok)
            continue
        if r is None:  # off-row token in a non-merged column: keep it, flagged
            r = min(range(len(row_ys)), key=lambda i: abs(row_ys[i] - tok.cy))
            tok = Token(tok.text, 0.0, tok.x0, tok.y0, tok.x1, tok.y1)
        prev = grid[r][c]
        if prev is not None:  # two tokens in one cell: keep both, flag for audit
            grid[r][c] = DraftCell(f"{prev.text} {tok.text}", 0.0)
        else:
            grid[r][c] = DraftCell(tok.text, tok.conf)

    for tok in sorted(merged, key=lambda t: t.text.upper() == "N/A"):
        band = _band_rows(tok.cy, tok.cx, row_ys, rules)
        if not band:
            continue
        if tok.text.upper() == "N/A":
            # The N/A block spans the data columns; whether it also covers the
            # (merged) Motor Power column is left to the auditor ('?').
            cols = [c for c in range(k)
                    if c not in mergeable and all(grid[r][c] is None for r in band)]
            if not cols:
                continue
            first = cols[0]
            grid[band[0]][first] = DraftCell(tok.text, tok.conf)
            for c in cols[1:]:
                grid[band[0]][c] = DraftCell(MERGED_LEFT, 1.0)
            for r in band[1:]:
                for c in cols:
                    grid[r][c] = DraftCell(MERGED_ABOVE, 1.0)
            continue
        c = col_of(tok)
        free = [r for r in band if grid[r][c] is None]
        if not free:
            continue
        grid[free[0]][c] = DraftCell(tok.text, tok.conf)
        for r in free[1:]:
            grid[r][c] = DraftCell(MERGED_ABOVE, 1.0)

    rows: list[tuple[DraftCell, list[DraftCell]]] = []
    for i, pn in enumerate(pn_tokens):
        pn_cell = DraftCell(pn.text, pn.conf if PN_RE.match(pn.text) else 0.0)
        cells = [cell if cell is not None else DraftCell("", 0.0) for cell in grid[i]]
        rows.append((pn_cell, cells))
    return SheetDraft(layout.code, rows)


def _band_rows(
    y: float, x: float, row_ys: Sequence[float], rules: Sequence[Rule]
) -> list[int]:
    """Rows between the nearest rules above and below ``y`` that cross ``x``."""

    crossing = [r.y for r in rules if r.crosses(x)]
    above = max((r for r in crossing if r < y), default=float("-inf"))
    below = min((r for r in crossing if r > y), default=float("inf"))
    return [i for i, ry in enumerate(row_ys) if above < ry < below]


def _median(values: Sequence[float]) -> float:
    vals = sorted(values)
    return vals[len(vals) // 2] if vals else 0.0


def _split_regions(
    codes: tuple[str, ...], tokens: Sequence[Token]
) -> dict[str, tuple[float, float]]:
    """Vertical region of each table inside one image, from its title tokens.

    A title is a "... Power" heading naming a phase or the 24V supply (the
    "Motor Power" column header never does). Titles are taken top to bottom;
    the image must contain exactly one per expected table.
    """

    def is_title(text: str) -> bool:
        t = text.lower().replace(" ", "")
        return "power" in t and ("phase" in t or "24v" in t)

    starts = sorted(t.cy for t in tokens if is_title(t.text))
    if len(starts) != len(codes):
        raise ValueError(f"{'/'.join(codes)}: expected {len(codes)} table titles, "
                         f"recognized {len(starts)}")
    ends = [*starts[1:], float("inf")]
    return {c: (s, e) for c, s, e in zip(codes, starts, ends, strict=True)}


def _notes(tokens: Sequence[Token], after_y: float) -> list[str]:
    """Text lines below the last table of an image (the printed NOTES block)."""

    lines: dict[int, list[Token]] = {}
    for t in tokens:
        if t.cy > after_y:
            lines.setdefault(round(t.cy / 6), []).append(t)
    out: list[str] = []
    for key in sorted(lines):
        line = " ".join(t.text for t in sorted(lines[key], key=lambda t: t.x0)).strip()
        if line:
            out.append(line if min(t.conf for t in lines[key]) >= CONFIDENCE_FLOOR
                       else UNSURE + line)
    return out


def draft_from_pdf(pdf: Path) -> tuple[list[SheetDraft], list[NoteDraft], dict[str, Any]]:
    """Run the OCR draft over the PDF; returns sheets, note drafts, engine info."""

    by_code = {t.code: t for t in TABLES}
    sheets: list[SheetDraft] = []
    notes: list[NoteDraft] = []
    with tempfile.TemporaryDirectory() as tmp:
        images = extract_images(pdf, Path(tmp))
        for index, codes in IMAGE_TABLES.items():
            image = images[index]
            rules = horizontal_rules(image)
            reads: list[dict[str, SheetDraft]] = []
            note_tokens: list[Token] = []
            last_bottom = 0.0
            for scale in OCR_SCALES:
                tokens = ocr_tokens(image, scale)
                regions = _split_regions(codes, tokens)
                read: dict[str, SheetDraft] = {}
                for code in codes:
                    lo, hi = regions[code]
                    region = [t for t in tokens if lo < t.cy < hi]
                    read[code] = layout_table(by_code[code], region, rules)
                    pn_ys = [t.cy for t in region if _PN_PREFIX.match(t.text)]
                    last_bottom = max([last_bottom, *pn_ys])
                reads.append(read)
                if scale == 1:  # the native read keeps note spacing best
                    note_tokens = tokens
            for code in codes:
                sheets.append(reconcile(reads[0][code], reads[1][code]))
            scope = ",".join(codes)
            notes.extend(NoteDraft(scope, line) for line in _notes(note_tokens, last_bottom + 8))
    order = {t.code: i for i, t in enumerate(TABLES)}
    sheets.sort(key=lambda s: order[s.table])
    return sheets, notes, {
        "engine": ENGINE_ID,
        "confidence_floor": CONFIDENCE_FLOOR,
        "scales": list(OCR_SCALES),
    }


def reconcile(a: SheetDraft, b: SheetDraft) -> SheetDraft:
    """Cell-by-cell agreement of two independent reads (never picks a winner).

    Agreeing cells keep the lower confidence; disagreeing cells become a
    zero-confidence "a|b" candidate the auditor must resolve. A row-count
    disagreement keeps read ``a`` with every cell at zero confidence.
    """

    if len(a.rows) != len(b.rows):
        return SheetDraft(a.table, [
            (DraftCell(pn.text, 0.0), [DraftCell(c.text, 0.0) for c in cells])
            for pn, cells in a.rows
        ])

    def merge(x: DraftCell, y: DraftCell) -> DraftCell:
        if x.text == y.text:
            return DraftCell(x.text, min(x.conf, y.conf))
        return DraftCell(f"{x.text}|{y.text}", 0.0)

    rows = [
        (merge(pa, pb), [merge(ca, cb) for ca, cb in zip(cells_a, cells_b, strict=True)])
        for (pa, cells_a), (pb, cells_b) in zip(a.rows, b.rows, strict=True)
    ]
    return SheetDraft(a.table, rows)
