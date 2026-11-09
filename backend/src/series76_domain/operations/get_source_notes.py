"""The ``get_source_notes`` domain operation (Task 11.1, Req 8.*).

Returns each applicable note for a target (PN / configuration / fact / section)
as a **separate** item with its literal text unchanged and covered scope equal
to exactly the covered source rows — no merge, summary, inference, or
forward-fill (Property 26). A requested note that does not exist yields
``NOT_DOCUMENTED`` (a :class:`~series76_domain.model.enums.DataStatus` state,
distinct from ``UNVERIFIED``).
"""

from __future__ import annotations

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.operations.pn import is_well_formed_pn, normalize_pn
from series76_domain.operations.results import SourceNotesResult
from series76_domain.repository.port import TypedRepository


def get_source_notes(
    repository: TypedRepository,
    part_number: str,
    *,
    note_type: str | None = None,
) -> SourceNotesResult:
    """Return the literal notes for a part, filtered by optional note type.

    Args:
        repository: the edition-pinned read port.
        part_number: the canonical PN whose notes are requested.
        note_type: when given, restrict to notes of this type; if none match,
            the result is ``NOT_DOCUMENTED``.

    Returns:
        A :class:`SourceNotesResult` carrying each note separately, or a
        ``NOT_DOCUMENTED`` / ``PART_NOT_LISTED`` / ``INVALID_PN`` failure.
    """

    if not is_well_formed_pn(part_number):
        return SourceNotesResult(failure=SemanticFailureCode.INVALID_PN)

    part = repository.find_part_number(normalize_pn(part_number))
    if part is None:
        return SourceNotesResult(failure=SemanticFailureCode.PART_NOT_LISTED)

    notes = repository.notes_for_part(part)
    if note_type is not None:
        notes = tuple(n for n in notes if n.note_type == note_type)

    if not notes:
        # Requested note(s) do not exist — NOT_DOCUMENTED, never UNVERIFIED.
        return SourceNotesResult(not_documented=True)

    return SourceNotesResult(notes=notes)
