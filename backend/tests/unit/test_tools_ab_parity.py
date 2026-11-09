"""A/B assembly parity example tests (Task 13.2) — NO winner asserted.

Assert both assemblies exist with their specified shapes and that Set A and
Set B return identical facts over identical inputs (parity of the shared core).
This spec asserts **no** winner and runs **no** benchmark. Zero LLM cost.
"""

from __future__ import annotations

from _builders import build_part
from _fakes import FakeRepository, make_edition

from series76_domain.tools import build_set_a, build_set_b
from series76_domain.tools.context import ToolContext
from series76_domain.tools.core import run_get_part, run_query_parts, run_search
from series76_domain.tools.schemas import GetPartInput, QueryPartsInput, SearchInput


def _ctx_and_repo() -> tuple[ToolContext, FakeRepository]:
    edition = make_edition()
    repo = FakeRepository(pinned=edition)
    repo.add(build_part("PN-1", edition.edition_id, torque_inlbs=100))
    repo.add(build_part("PN-2", edition.edition_id, torque_inlbs=200))
    return ToolContext(edition_id=edition.edition_id, trace_id="t"), repo


def test_both_assemblies_exist_with_specified_shapes() -> None:
    edition = make_edition()
    ctx = ToolContext(edition_id=edition.edition_id)
    set_b = build_set_b(lambda: ctx, lambda _c: FakeRepository(pinned=edition))
    set_a = build_set_a(lambda: ctx, lambda _c: FakeRepository(pinned=edition))

    assert set(set_b) == {"get_part_details", "search_parts", "get_source_notes"}
    assert set(set_a) == {"query_parts"}


def test_set_a_get_equals_set_b_get_part() -> None:
    ctx, repo = _ctx_and_repo()
    factory = lambda _c: repo  # noqa: E731

    b_result = run_get_part(GetPartInput(part_number="PN-1"), ctx, factory)
    a_result = run_query_parts(
        QueryPartsInput(op="GET", part_number="PN-1"), ctx, factory
    )
    assert a_result == b_result  # identical facts for identical inputs


def test_set_a_search_equals_set_b_search() -> None:
    ctx, repo = _ctx_and_repo()
    factory = lambda _c: repo  # noqa: E731
    filter_ast = {
        "type": "predicate",
        "field": "torque_inlbs",
        "operator": "GE",
        "value": "100",
    }

    b_result = run_search(SearchInput(filter_ast=filter_ast), ctx, factory)
    a_result = run_query_parts(
        QueryPartsInput(op="SEARCH", filter_ast=filter_ast), ctx, factory
    )
    assert a_result == b_result


def test_no_winner_is_declared() -> None:
    """This spec declares no A/B winner (deferred to Spec 6)."""
    import series76_domain.tools.set_a as set_a
    import series76_domain.tools.set_b as set_b

    for module in (set_a, set_b):
        source = (module.__doc__ or "").lower()
        # Each assembly documents that no winner is declared and the A/B
        # comparison is deferred to Spec 6.
        assert "winner is declared" in source or "no winner" in source
        assert "spec 6" in source
