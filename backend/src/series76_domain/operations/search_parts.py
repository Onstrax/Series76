"""The ``search_parts`` domain operation (Task 6.1, 6.2, Req 3.*).

Evaluates a validated ``Filter_AST`` over every part in the pinned edition
using the shared boolean evaluator (:mod:`series76_domain.model.evaluation`),
then:

* returns an exact ``total_matches`` and a cursor-paged page of matched PNs
  that enumerates all matches to exhaustion with none omitted or fabricated
  (Property 12);
* partitions the matched PNs into a **verified** set (all referenced hard
  constraints satisfied with documented values) disjoint from a
  **preliminary/indeterminate** set (a referenced field is N/A, absent, or
  non-comparable) (Property 13);
* reports ``NO_RESULTS`` as a *success* with ``total_matches == 0`` and the
  applied filters (distinct from ``INVALID_FILTER``) (Property 14);
* rejects an invalid AST with ``INVALID_FILTER`` **without executing** the
  search and with no totals (Property 14).

A model-supplied ``sort_hint`` is accepted but **non-authoritative**: it never
changes the matched set or totals (the ranking service owns ordering).
There is **no** card limit on the full matched set (that rule is Spec 5).
"""

from __future__ import annotations

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.evaluation import CandidateFields, evaluate
from series76_domain.model.filter_ast import (
    AllowlistField,
    And,
    FieldKind,
    Node,
    Not,
    Operator,
    Or,
    Predicate,
)
from series76_domain.model.filter_validation import validate_filter
from series76_domain.model.types import (
    ElectricalMeasurement,
    ServicePerformance,
    UnqualifiedPerformance,
)
from series76_domain.operations.candidate_fields import build_candidate_fields
from series76_domain.operations.results import SearchCandidate, SearchResult
from series76_domain.repository.port import TypedRepository

_DEFAULT_PAGE_SIZE = 50


def search_parts(
    repository: TypedRepository,
    filter_ast: Node,
    *,
    sort_hint: str | None = None,  # noqa: ARG001  (non-authoritative; ignored)
    cursor: int | None = None,
    page_size: int = _DEFAULT_PAGE_SIZE,
    allow_withdrawn: bool = True,
) -> SearchResult:
    """Run a filtered search and return matches, totals, and partition sets.

    Args:
        repository: the edition-pinned read port.
        filter_ast: the typed filter to evaluate (validated first).
        sort_hint: a non-authoritative model hint; it does not affect results.
        cursor: an opaque offset cursor for pagination (``None`` = first page).
        page_size: maximum matched PNs per page (transport only, not a card
            limit on the full matched set).
        allow_withdrawn: when ``False``, a withdrawn edition yields
            ``SOURCE_WITHDRAWN``.

    Returns:
        A :class:`SearchResult`.
    """

    validation = validate_filter(filter_ast)
    if not validation.ok:
        return SearchResult(
            failure=SemanticFailureCode.INVALID_FILTER,
            offending_predicate=validation.offending_predicate,
        )

    if not allow_withdrawn and repository.pinned_edition.is_withdrawn:
        return SearchResult(failure=SemanticFailureCode.SOURCE_WITHDRAWN)

    referenced = _referenced_fields(filter_ast)

    matches: list[SearchCandidate] = []
    for part in repository.list_part_numbers():
        configurations = repository.configurations_for(part)
        service_perf: list[ServicePerformance] = []
        unqualified: list[UnqualifiedPerformance] = []
        measurements: list[ElectricalMeasurement] = []
        for cfg in configurations:
            service_perf.extend(repository.service_performance_for(cfg))
            unqualified.extend(repository.unqualified_performance_for(cfg))
            for cond in repository.operating_conditions_for(cfg):
                measurements.extend(repository.measurements_for(cond))
        notes = repository.notes_for_part(part)
        fields = build_candidate_fields(
            part,
            configurations,
            tuple(service_perf),
            tuple(unqualified),
            tuple(measurements),
            notes,
        )
        if evaluate(filter_ast, fields):
            is_verified = _is_fully_documented(referenced, fields)
            matches.append(SearchCandidate(part_number=part, is_verified=is_verified))

    total = len(matches)
    if total == 0:
        return SearchResult(
            total_matches=0,
            failure=SemanticFailureCode.NO_RESULTS,
            applied_filters=filter_ast,
        )

    verified = tuple(c.part_number for c in matches if c.is_verified)
    preliminary = tuple(c.part_number for c in matches if not c.is_verified)

    start = cursor or 0
    page = tuple(matches[start : start + page_size])
    next_cursor = start + page_size if start + page_size < total else None

    return SearchResult(
        total_matches=total,
        page=page,
        next_cursor=next_cursor,
        verified=verified,
        preliminary=preliminary,
        applied_filters=filter_ast,
    )


def _referenced_fields(node: Node) -> frozenset[AllowlistField]:
    """Collect every allowlisted field referenced by the AST."""

    if isinstance(node, Predicate):
        return frozenset({node.field})
    if isinstance(node, And | Or):
        fields: set[AllowlistField] = set()
        for child in node.children:
            fields |= _referenced_fields(child)
        return frozenset(fields)
    if isinstance(node, Not):
        return _referenced_fields(node.child)
    return frozenset()


def _is_fully_documented(
    referenced: frozenset[AllowlistField], fields: CandidateFields
) -> bool:
    """A candidate is verified iff every referenced field it carries has at

    least one documented value and none of its referenced numeric fields is
    solely N/A/absent. A matched candidate that carries only an indeterminate
    value for a referenced field is preliminary (Property 13).
    """

    for field in referenced:
        values = fields.get(field, ())
        if not values:
            # The field is not present on the candidate at all; since it
            # matched, the match came from another branch (e.g. an OR / NOT).
            # Treat a missing referenced field as indeterminate.
            return False
        if field.kind is FieldKind.NUMERIC:
            if not any(v.metric is not None and v.metric.is_available for v in values):
                return False
        else:
            if not any(v.is_documented for v in values):
                return False
    return True


# Re-exported for callers that build simple predicates.
__all__ = ["search_parts", "And", "Or", "Not", "Predicate", "Operator"]
