"""Properties 12, 13, 14 — search over seeded PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from series76_domain.model.filter_ast import AllowlistField, And, Operator, Predicate
from series76_domain.operations.search_parts import search_parts
from series76_domain.repository.pg_adapter import PostgresTypedRepository

from .seed import SeededCatalog

pytestmark = pytest.mark.integration

SeededFixture = tuple[SeededCatalog, Callable[[], Session], Engine]


# Feature: domain-and-tools, Property 12: full enumeration via the transport
# equals total_matches.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(page_size=st.integers(min_value=1, max_value=4))
def test_property_12_full_enumeration(
    seeded_catalog: SeededFixture, page_size: int
) -> None:
    _seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        # Match-all over a documented numeric field present on most parts.
        node = Predicate(AllowlistField.MOTOR_POWER, Operator.GE, Decimal(0))

        seen: list[str] = []
        cursor: int | None = None
        total = None
        guard = 0
        while True:
            guard += 1
            assert guard < 1000
            result = search_parts(repo, node, cursor=cursor, page_size=page_size)
            if result.is_no_results:
                total = 0
                break
            total = result.total_matches
            seen.extend(c.part_number.canonical_pn for c in result.page)
            if result.next_cursor is None:
                break
            cursor = result.next_cursor
        assert total == len(seen)
        assert len(set(seen)) == len(seen)


# Feature: domain-and-tools, Property 13: verified and indeterminate sets
# partition correctly (disjoint).
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(threshold=st.integers(min_value=0, max_value=400))
def test_property_13_partition_disjoint(
    seeded_catalog: SeededFixture, threshold: int
) -> None:
    _seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        node = Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(threshold))
        result = search_parts(repo, node)
        if result.is_no_results:
            return
        verified = {p.canonical_pn for p in result.verified}
        preliminary = {p.canonical_pn for p in result.preliminary}
        assert verified.isdisjoint(preliminary)
        assert len(verified) + len(preliminary) == result.total_matches


# Feature: domain-and-tools, Property 14: empty match is NO_RESULTS success;
# invalid filter is INVALID_FILTER rejection with no totals.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(big=st.integers(min_value=100_000, max_value=10_000_000))
def test_property_14_no_results_vs_invalid(
    seeded_catalog: SeededFixture, big: int
) -> None:
    _seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)

        # Matches nothing -> NO_RESULTS success with total 0 and applied filters.
        unmatched = Predicate(AllowlistField.TORQUE_INLBS, Operator.GT, Decimal(big))
        no_results = search_parts(repo, unmatched)
        assert no_results.is_no_results
        assert no_results.total_matches == 0
        assert no_results.applied_filters is unmatched

        # Structurally invalid (ordered operator on a string field) ->
        # INVALID_FILTER, no execution, no totals.
        invalid = And(
            children=(Predicate(AllowlistField.ENCLOSURE, Operator.LT, "x"),)
        )
        rejected = search_parts(repo, invalid)
        assert rejected.is_invalid_filter
        assert rejected.total_matches == 0
        assert rejected.page == ()
