"""Domain operations over the read-only repository (Spec 2 § Components).

The three operations — :func:`get_part`, :func:`search_parts`,
:func:`get_source_notes` — are the shared core both tool assemblies (set A and
set B) call. Each returns a typed result carrying either facts (with
:class:`~series76_domain.model.enums.DataStatus` and
:class:`~series76_domain.model.evidence.EvidenceReference`) or exactly one
:class:`~series76_domain.model.enums.SemanticFailureCode`.
"""

from __future__ import annotations

from series76_domain.operations.get_part import get_part
from series76_domain.operations.get_source_notes import get_source_notes
from series76_domain.operations.results import (
    GetPartResult,
    PartView,
    SearchCandidate,
    SearchResult,
    SourceNotesResult,
)
from series76_domain.operations.search_parts import search_parts

__all__ = [
    "GetPartResult",
    "PartView",
    "SearchCandidate",
    "SearchResult",
    "SourceNotesResult",
    "get_part",
    "get_source_notes",
    "search_parts",
]
