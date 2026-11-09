"""Typed result DTOs shared by the domain operations (design § Components).

Every defined non-success business outcome is carried as a
:class:`~series76_domain.model.enums.SemanticFailureCode` on a result object —
never a bare exception (guard violations at the repository boundary are the
only exceptions). ``NO_RESULTS`` is the one success-signalling code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.filter_ast import Node, Predicate
from series76_domain.model.types import (
    Configuration,
    ElectricalMeasurement,
    Note,
    OperatingCondition,
    Part,
    PartNumber,
    ServicePerformance,
    UnqualifiedPerformance,
)


@dataclass(frozen=True, slots=True)
class PartView:
    """The labeled facts returned for a found part (``PART_FOUND``).

    Facts bound to an explicit service/frequency are carried in
    :attr:`bound_measurements` / :attr:`bound_service`; when no service or
    frequency is requested and several measurements apply, *all* applicable
    measurements are returned in :attr:`measurements` with none silently
    selected (Property 5).
    """

    part: Part
    configurations: tuple[Configuration, ...] = ()
    service_performance: tuple[ServicePerformance, ...] = ()
    unqualified_performance: tuple[UnqualifiedPerformance, ...] = ()
    operating_conditions: tuple[OperatingCondition, ...] = ()
    measurements: tuple[ElectricalMeasurement, ...] = ()
    notes: tuple[Note, ...] = ()
    requested_service: str | None = None
    requested_frequency_hz: object | None = None


@dataclass(frozen=True, slots=True)
class GetPartResult:
    """Outcome of :func:`series76_domain.operations.get_part.get_part`.

    Exactly one of :attr:`view` (success) or :attr:`failure` (a typed
    :class:`SemanticFailureCode`) is set.
    """

    view: PartView | None = None
    failure: SemanticFailureCode | None = None
    offending_input: str | None = None

    @property
    def is_found(self) -> bool:
        """True iff a part was found and labeled facts are present."""
        return self.view is not None and self.failure is None


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """One matched part in a :class:`SearchResult`.

    Attributes:
        part_number: the matched part.
        is_verified: ``True`` iff every verifiable hard constraint is satisfied;
            ``False`` places the candidate in the preliminary/indeterminate set
            (missing/N/A/non-comparable relevant field).
    """

    part_number: PartNumber
    is_verified: bool


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Outcome of :func:`series76_domain.operations.search_parts.search_parts`.

    ``NO_RESULTS`` is reported as a **success** with ``total_matches == 0`` and
    the applied filters recorded. ``INVALID_FILTER`` is a rejection carrying no
    totals and no matched PNs (Property 14).
    """

    total_matches: int = 0
    page: tuple[SearchCandidate, ...] = ()
    next_cursor: int | None = None
    verified: tuple[PartNumber, ...] = ()
    preliminary: tuple[PartNumber, ...] = ()
    applied_filters: Node | None = None
    failure: SemanticFailureCode | None = None
    offending_predicate: Predicate | None = None

    @property
    def is_invalid_filter(self) -> bool:
        """True iff the filter was rejected before execution."""
        return self.failure is SemanticFailureCode.INVALID_FILTER

    @property
    def is_no_results(self) -> bool:
        """True iff the search ran and matched nothing (a success)."""
        return self.failure is SemanticFailureCode.NO_RESULTS


@dataclass(frozen=True, slots=True)
class SourceNotesResult:
    """Outcome of :func:`series76_domain.operations.get_source_notes.get_source_notes`.

    On success, :attr:`notes` carries each applicable note as a *separate* item
    with literal text and exact covered-row scope. A requested note that does
    not exist yields :attr:`not_documented` (``DataStatus.NOT_DOCUMENTED``,
    distinct from ``UNVERIFIED`` — Property 26). A malformed/absent PN yields a
    :class:`SemanticFailureCode` on :attr:`failure`.
    """

    notes: tuple[Note, ...] = field(default=())
    not_documented: bool = False
    failure: SemanticFailureCode | None = None

    @property
    def is_documented(self) -> bool:
        """True iff at least one note was returned."""
        return bool(self.notes) and not self.not_documented and self.failure is None
