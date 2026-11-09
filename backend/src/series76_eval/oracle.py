"""GoldenOracle: the single numeric oracle and documental verification (Spec 6 Req 2.1-2.3).

Every expected technical value must have Golden_Dataset provenance, bound to
``series_76_electric_data.pdf`` by a SHA-256 manifest. The comparator diffs the
published catalog cell by cell at the exact recorded string (no rounding,
truncation, or normalization); any mismatch fails the run with a per-cell
report and never modifies the golden dataset.

The *real* golden dataset requires a manual audit of the rasterized PDF (Spec 1
``[EXPERIMENT]``); until it exists, documental verification is ``pending``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class Provenance(str, Enum):
    GOLDEN_DATASET = "GOLDEN_DATASET"
    LANGUAGE_MODEL = "LANGUAGE_MODEL"
    PART_NUMBER_SUBSTRING = "PART_NUMBER_SUBSTRING"
    SUMMARY_PDF = "SUMMARY_PDF"
    GENERATED_PROSE = "GENERATED_PROSE"


class ProvenanceError(ValueError):
    """An expected value did not come from the golden dataset."""


@dataclass(frozen=True, slots=True)
class ExpectedValue:
    """An expected value used by a test or scenario."""

    cell_key: str
    value: str
    provenance: Provenance
    manifest_sha256: str

    def __post_init__(self) -> None:
        if self.provenance is not Provenance.GOLDEN_DATASET:
            raise ProvenanceError(
                f"expected value {self.cell_key} has {self.provenance.value} provenance"
            )
        if len(self.manifest_sha256) != 64:
            raise ProvenanceError("expected value is not bound to a SHA-256 manifest")


@dataclass(frozen=True, slots=True)
class GoldenCell:
    """One audited cell: table, row, column, printed value, unit, N/A, note."""

    table: str
    row: int
    column: str
    printed_value: str
    unit: str = ""
    not_applicable: bool = False
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.table}:{self.row}:{self.column}"

    def comparable(self) -> tuple[str, str, bool, str]:
        return (self.printed_value, self.unit, self.not_applicable, self.note)


@dataclass(frozen=True, slots=True)
class CellMismatch:
    cell: str
    expected: str
    observed: str


@dataclass(frozen=True, slots=True)
class OracleReport:
    """Result of documental verification."""

    covered: int
    total: int
    mismatches: tuple[CellMismatch, ...]
    manifest_ok: bool

    @property
    def passed(self) -> bool:
        return self.manifest_ok and not self.mismatches and self.covered == self.total > 0

    @property
    def field_coverage(self) -> str:
        return f"{self.covered}/{self.total}"


def dataset_digest(cells: tuple[GoldenCell, ...]) -> str:
    """Deterministic SHA-256 over the canonical serialization of the golden cells."""

    h = hashlib.sha256()
    for c in sorted(cells, key=lambda x: x.key):
        h.update(
            "\x1f".join([c.key, c.printed_value, c.unit, str(c.not_applicable), c.note]).encode()
        )
        h.update(b"\x1e")
    return h.hexdigest()


class GoldenOracle:
    """Cell-by-cell comparator; never mutates the golden dataset."""

    def verify(
        self,
        published: tuple[GoldenCell, ...],
        golden: tuple[GoldenCell, ...],
        manifest_sha256: str,
    ) -> OracleReport:
        manifest_ok = dataset_digest(golden) == manifest_sha256
        by_key = {c.key: c for c in published}
        mismatches: list[CellMismatch] = []
        covered = 0
        for expected in sorted(golden, key=lambda c: c.key):
            observed = by_key.get(expected.key)
            if observed is None:
                mismatches.append(CellMismatch(expected.key, _fmt(expected), "<missing>"))
                continue
            covered += 1
            if observed.comparable() != expected.comparable():  # exact strings, no normalization
                mismatches.append(CellMismatch(expected.key, _fmt(expected), _fmt(observed)))
        golden_keys = {c.key for c in golden}
        for extra in sorted(k for k in by_key if k not in golden_keys):
            mismatches.append(CellMismatch(extra, "<not in golden dataset>", _fmt(by_key[extra])))
        return OracleReport(
            covered=covered,
            total=len(golden),
            mismatches=tuple(mismatches),
            manifest_ok=manifest_ok,
        )


def _fmt(c: GoldenCell) -> str:
    state = "N/A" if c.not_applicable else c.printed_value
    return f"{state} {c.unit}".strip() + (f" [note: {c.note}]" if c.note else "")
