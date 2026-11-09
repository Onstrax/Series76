"""Properties 27, 28, 29 — tool validation, injection resistance, failure codes.

Exercised against fake repositories with zero LLM cost (no OpenRouter calls).
"""

from __future__ import annotations

import uuid

import pytest
from _builders import build_part
from _fakes import FakeRepository, make_edition
from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.tools.context import ToolContext
from series76_domain.tools.core import (
    ToolInputError,
    run_get_part,
    run_search,
    validate_get_part,
    validate_search,
)


def _repo_with(edition, *pns: str) -> FakeRepository:
    repo = FakeRepository(pinned=edition)
    for pn in pns:
        repo.add(build_part(pn, edition.edition_id))
    return repo


# Feature: domain-and-tools, Property 27: tool inputs are schema-validated
# before execution and server-injected inputs are not overridable.
@given(
    model_edition=st.uuids(),
    bogus=st.dictionaries(
        st.sampled_from(["edition_id", "permissions", "trace_id", "max_results"]),
        st.text(max_size=8),
        min_size=1,
    ),
)
def test_property_27_validation_and_server_authority(
    model_edition: uuid.UUID, bogus: dict[str, str]
) -> None:
    server_edition = make_edition()
    repo = _repo_with(server_edition, "PN-1")
    server_ctx = ToolContext(
        edition_id=server_edition.edition_id, trace_id="server-trace"
    )

    # A model payload carrying server-injected keys is rejected by the schema
    # (extra=forbid) *before* any catalog query.
    payload = {"part_number": "PN-1", **bogus}
    with pytest.raises(ToolInputError):
        validate_get_part(payload)

    # The clean model payload runs; the server edition/trace are authoritative.
    validated = validate_get_part({"part_number": "PN-1"})
    result = run_get_part(validated, server_ctx, lambda _c: repo)
    assert result.ok
    assert result.trace_id == "server-trace"  # server value, never a model value


# Feature: domain-and-tools, Property 28: tool output is sanitized typed facts
# with evidence and is never executed as instruction.
@given(instruction=st.text(min_size=1, max_size=40))
def test_property_28_output_sanitized_inert(instruction: str) -> None:
    edition = make_edition()
    repo = FakeRepository(pinned=edition)
    # Embed an instruction-like string as a note's literal text.
    repo.add(build_part("PN-INSTR", edition.edition_id, note_text=instruction))
    ctx = ToolContext(edition_id=edition.edition_id)

    from series76_domain.tools.core import run_source_notes, validate_source_notes

    validated = validate_source_notes({"part_number": "PN-INSTR"})
    result = run_source_notes(validated, ctx, lambda _c: repo)
    assert result.ok
    for fact in result.facts:
        # The value is carried as inert string data with evidence; it is never
        # interpreted or executed as an instruction.
        assert isinstance(fact.value, str)
        assert fact.evidence.is_resolvable
        # The literal text is preserved verbatim (no execution, no mutation).
        assert fact.value == instruction


# Feature: domain-and-tools, Property 29: exactly one SemanticFailureCode per
# defined non-success outcome.
@given(
    scenario=st.sampled_from(
        ["invalid_pn", "part_not_listed", "no_results", "invalid_filter"]
    )
)
def test_property_29_one_failure_code(scenario: str) -> None:
    edition = make_edition()
    repo = _repo_with(edition, "PN-1")
    ctx = ToolContext(edition_id=edition.edition_id)
    factory = lambda _c: repo  # noqa: E731

    if scenario == "invalid_pn":
        result = run_get_part(
            validate_get_part({"part_number": "bad pn!!"}), ctx, factory
        )
        assert result.failure is SemanticFailureCode.INVALID_PN
    elif scenario == "part_not_listed":
        result = run_get_part(
            validate_get_part({"part_number": "PN-ABSENT"}), ctx, factory
        )
        assert result.failure is SemanticFailureCode.PART_NOT_LISTED
    elif scenario == "no_results":
        # A filter that matches nothing is NO_RESULTS (a success signal).
        search = validate_search(
            {
                "filter_ast": {
                    "type": "predicate",
                    "field": "torque_inlbs",
                    "operator": "GT",
                    "value": "999999",
                }
            }
        )
        result = run_search(search, ctx, factory)
        assert result.failure is SemanticFailureCode.NO_RESULTS
        assert result.total_matches == 0
    else:  # invalid_filter
        search = validate_search(
            {
                "filter_ast": {
                    "type": "predicate",
                    "field": "NOT_A_FIELD",
                    "operator": "EQ",
                    "value": "x",
                }
            }
        )
        result = run_search(search, ctx, factory)
        assert result.failure is SemanticFailureCode.INVALID_FILTER
        assert result.total_matches is None

    # Exactly one failure code is set (never a bare exception for a business
    # outcome); the NO_RESULTS case still sets a single code.
    if result.failure is not None:
        assert isinstance(result.failure, SemanticFailureCode)
