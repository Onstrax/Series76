"""Search operation unit tests over a fake repository (Task 6.2 example/slice).

Covers the pure-logic slices of Properties 12-14: full enumeration via the
cursor transport equals total_matches; verified and preliminary sets partition
disjointly; NO_RESULTS is a success distinct from INVALID_FILTER; there is no
card limit on the full matched set. The DB-backed versions run against seeded
PostgreSQL in the integration suite.
"""

from __future__ import annotations

from decimal import Decimal

from _builders import build_part
from _fakes import FakeRepository, make_edition

from series76_domain.model.filter_ast import AllowlistField, Operator, Predicate
from series76_domain.operations.search_parts import search_parts


def _repo(n: int) -> FakeRepository:
    edition = make_edition()
    repo = FakeRepository(pinned=edition)
    for i in range(n):
        repo.add(build_part(f"PN-{i:03d}", edition.edition_id, torque_inlbs=100 + i))
    return repo


def test_pagination_enumerates_full_set() -> None:
    repo = _repo(25)
    node = Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(0))

    seen: list[str] = []
    cursor: int | None = None
    total = None
    while True:
        result = search_parts(repo, node, cursor=cursor, page_size=7)
        total = result.total_matches
        seen.extend(c.part_number.canonical_pn for c in result.page)
        if result.next_cursor is None:
            break
        cursor = result.next_cursor

    assert total == 25
    assert len(seen) == 25
    assert len(set(seen)) == 25  # none omitted, none fabricated/duplicated


def test_no_results_is_success_distinct_from_invalid_filter() -> None:
    repo = _repo(3)
    unmatched = Predicate(AllowlistField.TORQUE_INLBS, Operator.GT, Decimal(10_000))
    result = search_parts(repo, unmatched)
    assert result.is_no_results
    assert result.total_matches == 0
    assert result.applied_filters is unmatched
    assert not result.is_invalid_filter


def test_verified_and_preliminary_are_disjoint() -> None:
    edition = make_edition()
    repo = FakeRepository(pinned=edition)
    # A part whose torque is documented (verifiable) and one whose fla is N/A.
    repo.add(build_part("PN-OK", edition.edition_id, torque_inlbs=100, fla=2))
    repo.add(build_part("PN-NA", edition.edition_id, torque_inlbs=100, fla=None))

    # Filter references only a documented field for both -> both verified.
    node = Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(50))
    result = search_parts(repo, node)
    assert set(p.canonical_pn for p in result.verified).isdisjoint(
        p.canonical_pn for p in result.preliminary
    )
    assert result.total_matches == 2


def test_no_card_limit_full_set_exposed() -> None:
    repo = _repo(120)
    node = Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(0))
    result = search_parts(repo, node, page_size=1000)
    # The full matched set is exposed with no card-limit truncation here.
    assert result.total_matches == 120
    assert len(result.page) == 120
