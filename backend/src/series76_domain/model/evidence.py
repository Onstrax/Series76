"""``EvidenceReference`` — every returned fact's link to its source (Req 10.2).

An :class:`EvidenceReference` binds a returned technical fact to its source
cell(s) and covered row(s) in the published catalog (Spec 1
``provenance.source_cell_evidence`` / ``source_cell_row_coverage``). It is
**non-empty**: at least one cell or row reference must be present, so no
returned fact can carry an unresolved reference (Property 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class EvidenceError(ValueError):
    """Raised when an :class:`EvidenceReference` would be empty."""


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A non-empty reference resolving a fact to published source cells/rows.

    Args:
        cell_refs: ``source_cell_evidence.cell_id`` values backing the fact.
        row_refs: ``source_row.row_id`` values the fact covers.
        note_refs: optional ``source_note.note_id`` values that annotate it.

    Raises:
        EvidenceError: if both ``cell_refs`` and ``row_refs`` are empty.
    """

    cell_refs: tuple[int, ...] = ()
    row_refs: tuple[int, ...] = ()
    note_refs: tuple[int, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.cell_refs and not self.row_refs:
            raise EvidenceError(
                "EvidenceReference must resolve to at least one source cell or row"
            )

    @property
    def is_resolvable(self) -> bool:
        """True iff the reference resolves to at least one source cell or row."""
        return bool(self.cell_refs) or bool(self.row_refs)

    @classmethod
    def of_cells(cls, *cell_ids: int) -> EvidenceReference:
        """Build a reference from one or more source cell ids."""
        return cls(cell_refs=tuple(cell_ids))

    @classmethod
    def of_rows(cls, *row_ids: int) -> EvidenceReference:
        """Build a reference from one or more source row ids."""
        return cls(row_refs=tuple(row_ids))
