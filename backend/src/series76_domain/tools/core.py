"""Shared tool core: validation, server-merge, dispatch, sanitization.

Both tool assemblies (set A and set B) call this core, so the facts returned,
the repository used, the validation applied, and the
:class:`~series76_domain.model.enums.SemanticFailureCode` emitted are identical
regardless of the model-visible surface (that is what keeps the Spec 6 A/B test
fair). This module:

* validates every model-visible input against its typed schema **before** any
  catalog query (Property 27);
* merges the server-injected :class:`~series76_domain.tools.context.ToolContext`
  server-side and ignores any model-supplied server value (Property 27);
* dispatches to the shared domain operations;
* returns sanitized typed :class:`~series76_domain.tools.context.ToolResult`
  facts carrying :class:`DataStatus` + :class:`EvidenceReference`, with any
  instruction-like string inert as data (Property 28);
* returns exactly one failure code per defined non-success (Property 29).
"""

from __future__ import annotations

from pydantic import ValidationError

from series76_domain.model.enums import DataStatus
from series76_domain.model.metric_value import MetricValue
from series76_domain.operations.get_part import get_part
from series76_domain.operations.get_source_notes import get_source_notes
from series76_domain.operations.results import GetPartResult, SearchResult, SourceNotesResult
from series76_domain.operations.search_parts import search_parts
from series76_domain.repository.port import TypedRepository
from series76_domain.tools.context import (
    RepositoryFactory,
    SanitizedFact,
    ToolContext,
    ToolResult,
    fact_value_str,
)
from series76_domain.tools.schemas import (
    FilterParseError,
    GetPartInput,
    QueryPartsInput,
    SearchInput,
    SourceNotesInput,
    parse_filter_ast,
)


class ToolInputError(Exception):
    """A typed validation failure: input did not conform; no query ran."""


# --- model-visible input validation (before any catalog query) ------------


def validate_get_part(payload: dict[str, object]) -> GetPartInput:
    """Validate a part-lookup payload; raise :class:`ToolInputError` if invalid."""
    try:
        return GetPartInput.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError("get_part input failed schema validation") from exc


def validate_search(payload: dict[str, object]) -> SearchInput:
    """Validate a search payload; raise :class:`ToolInputError` if invalid."""
    try:
        return SearchInput.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError("search input failed schema validation") from exc


def validate_source_notes(payload: dict[str, object]) -> SourceNotesInput:
    """Validate a source-notes payload; raise :class:`ToolInputError` if invalid."""
    try:
        return SourceNotesInput.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError("source_notes input failed schema validation") from exc


def validate_query_parts(payload: dict[str, object]) -> QueryPartsInput:
    """Validate the Set A generic payload; raise :class:`ToolInputError`."""
    try:
        return QueryPartsInput.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError("query_parts input failed schema validation") from exc


# --- dispatch to shared operations -----------------------------------------


def run_get_part(
    validated: GetPartInput, context: ToolContext, factory: RepositoryFactory
) -> ToolResult:
    """Run the shared ``get_part`` path and sanitize its result."""

    repository = factory(context)
    result = get_part(
        repository,
        validated.part_number,
        service=validated.service,
        frequency_hz=validated.frequency_hz,
        allow_withdrawn=context.allow_new_recommendation
        or not repository.pinned_edition.is_withdrawn,
    )
    return _sanitize_get_part(result, context)


def run_search(
    validated: SearchInput, context: ToolContext, factory: RepositoryFactory
) -> ToolResult:
    """Run the shared ``search_parts`` path and sanitize its result."""

    try:
        node = parse_filter_ast(validated.filter_ast)
    except FilterParseError:
        # A malformed/out-of-allowlist filter never executes; INVALID_FILTER.
        from series76_domain.model.enums import SemanticFailureCode

        return ToolResult(
            failure=SemanticFailureCode.INVALID_FILTER, trace_id=context.trace_id
        )
    repository = factory(context)
    result = search_parts(
        repository,
        node,
        sort_hint=validated.sort_hint,
        cursor=validated.cursor,
        page_size=context.max_results,
        allow_withdrawn=context.allow_new_recommendation
        or not repository.pinned_edition.is_withdrawn,
    )
    return _sanitize_search(result, context)


def run_source_notes(
    validated: SourceNotesInput, context: ToolContext, factory: RepositoryFactory
) -> ToolResult:
    """Run the shared ``get_source_notes`` path and sanitize its result."""

    repository = factory(context)
    result = get_source_notes(
        repository, validated.part_number, note_type=validated.note_type
    )
    return _sanitize_notes(result, context)


def run_query_parts(
    validated: QueryPartsInput, context: ToolContext, factory: RepositoryFactory
) -> ToolResult:
    """Route the Set A generic payload to the same GET / SEARCH paths as Set B."""

    if validated.op == "GET":
        get_input = GetPartInput(
            part_number=validated.part_number or "",
            service=validated.service,
            frequency_hz=validated.frequency_hz,
            requested_fields=validated.requested_fields,
        )
        return run_get_part(get_input, context, factory)
    search_input = SearchInput(
        filter_ast=validated.filter_ast or {},
        sort_hint=validated.sort_hint,
        cursor=validated.cursor,
        requested_fields=validated.requested_fields,
    )
    return run_search(search_input, context, factory)


# --- sanitization -----------------------------------------------------------


def _metric_fact(key: str, metric: MetricValue, evidence_source: object) -> SanitizedFact:
    from series76_domain.model.evidence import EvidenceReference

    evidence = (
        evidence_source
        if isinstance(evidence_source, EvidenceReference)
        else EvidenceReference(row_refs=(0,))
    )
    return SanitizedFact(
        key=key,
        value=fact_value_str(metric.value),
        unit=metric.unit.value if metric.unit is not None else None,
        status=metric.status,
        evidence=evidence,
    )


def _sanitize_get_part(result: GetPartResult, context: ToolContext) -> ToolResult:
    if result.failure is not None:
        return ToolResult(
            failure=result.failure,
            trace_id=context.trace_id,
            offending_input=result.offending_input,
        )
    assert result.view is not None
    facts: list[SanitizedFact] = []
    for sp in result.view.service_performance:
        facts.append(_metric_fact(f"{sp.service_type}:torque_inlbs", sp.torque_inlbs, sp.evidence))
        facts.append(_metric_fact(f"{sp.service_type}:torque_nm", sp.torque_nm, sp.evidence))
        facts.append(_metric_fact(f"{sp.service_type}:duty_s4", sp.duty_s4, sp.evidence))
    for up in result.view.unqualified_performance:
        facts.append(_metric_fact("unqualified:torque_inlbs", up.torque_inlbs, up.evidence))
        facts.append(_metric_fact("unqualified:torque_nm", up.torque_nm, up.evidence))
    for m in result.view.measurements:
        facts.append(_metric_fact(f"measurement:{m.measurement_id}:fla", m.fla, m.evidence))
        facts.append(_metric_fact(f"measurement:{m.measurement_id}:lra", m.lra, m.evidence))
    return ToolResult(facts=tuple(facts), trace_id=context.trace_id)


def _sanitize_search(result: SearchResult, context: ToolContext) -> ToolResult:
    if result.failure is not None and result.failure.name == "INVALID_FILTER":
        return ToolResult(failure=result.failure, trace_id=context.trace_id)
    # NO_RESULTS is a success with total 0.
    return ToolResult(
        failure=result.failure,
        total_matches=result.total_matches,
        verified_pns=tuple(p.canonical_pn for p in result.verified),
        preliminary_pns=tuple(p.canonical_pn for p in result.preliminary),
        next_cursor=result.next_cursor,
        extra_pns=tuple(c.part_number.canonical_pn for c in result.page),
        trace_id=context.trace_id,
    )


def _sanitize_notes(result: SourceNotesResult, context: ToolContext) -> ToolResult:
    if result.failure is not None:
        return ToolResult(failure=result.failure, trace_id=context.trace_id)
    if result.not_documented:
        return ToolResult(not_documented=True, trace_id=context.trace_id)
    facts = tuple(
        SanitizedFact(
            key=f"note:{note.note_id}",
            # The literal note text is carried as inert string data (Property 28):
            # it is never executed or followed as an instruction.
            value=note.printed_text,
            unit=None,
            status=DataStatus.AVAILABLE,
            evidence=note.evidence,
        )
        for note in result.notes
    )
    return ToolResult(facts=facts, trace_id=context.trace_id)


def resolve_repository(context: ToolContext, repository: TypedRepository) -> TypedRepository:
    """Return the repository for the *server* edition, ignoring any model value.

    The repository is always pinned to :attr:`ToolContext.edition_id`; this
    function exists to make the server-authoritative edition explicit at the
    call site (Property 1, Property 27).
    """

    return repository
