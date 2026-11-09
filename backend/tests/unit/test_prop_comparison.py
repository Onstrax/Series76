"""Properties 19, 20, 21 — deterministic comparison (Spec 2)."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit
from series76_domain.services.compare_parts import (
    ComparableMetric,
    PartComparisonInput,
    compare_parts,
)

_KEY = "fla"


def _part(
    pn: str,
    edition: str,
    value: int,
    *,
    supply: str,
    frequency: Decimal | None = None,
) -> PartComparisonInput:
    return PartComparisonInput(
        base_pn=pn,
        edition_id=edition,
        metrics=(
            ComparableMetric(
                base_pn=pn,
                metric_key=_KEY,
                value=MetricValue.available(Decimal(value), Unit.AMPERE),
                unit=Unit.AMPERE,
                supply_context=supply,
                frequency_context=frequency,
            ),
        ),
    )


# Feature: domain-and-tools, Property 19: comparison is edition-isolated and
# marks incompatible pairs NOT_COMPARABLE with no winner on such pairs.
@given(
    same_supply=st.booleans(),
    v1=st.integers(min_value=1, max_value=20),
    v2=st.integers(min_value=1, max_value=20),
)
def test_property_19_edition_isolation_and_comparability(
    same_supply: bool, v1: int, v2: int
) -> None:
    supply_b = "120V-1ph" if same_supply else "240V-3ph"
    left = _part("A", "E1", v1, supply="120V-1ph")
    right = _part("B", "E1", v2, supply=supply_b)

    result = compare_parts((left, right))
    assert result.ok
    pair = result.pairs[0]
    assert pair.comparable == same_supply
    if not pair.comparable:
        assert pair.warning is not None
        assert pair.has_winner is False  # no winner on a NOT_COMPARABLE pair

    # Cross-edition set is rejected with no side-by-side set.
    cross = compare_parts((_part("A", "E1", v1, supply="x"), _part("B", "E2", v2, supply="x")))
    assert not cross.ok
    assert cross.failure is SemanticFailureCode.NOT_COMPARABLE
    assert cross.pairs == ()


# Feature: domain-and-tools, Property 20: heterogeneous-supply FLA carries no
# efficiency claim (each value shown with its supply condition, never framed as
# lower-consumption).
@given(v1=st.integers(min_value=1, max_value=50), v2=st.integers(min_value=1, max_value=50))
def test_property_20_heterogeneous_supply_no_efficiency_claim(v1: int, v2: int) -> None:
    left = _part("A", "E1", v1, supply="120V-1ph")
    right = _part("B", "E1", v2, supply="240V-3ph")
    result = compare_parts((left, right))
    pair = result.pairs[0]
    assert pair.is_supply_heterogeneous is True
    # Heterogeneous supply means not comparable: no winner, hence no efficiency
    # or lower-consumption claim can be derived from the pair.
    assert pair.comparable is False
    assert pair.has_winner is False
    # Each value retains its own supply context (never merged/normalized).
    assert pair.left.supply_context == "120V-1ph"
    assert pair.right.supply_context == "240V-3ph"


# Feature: domain-and-tools, Property 21: comparison rejects invalid arity
# (<2/>3/duplicate/unlisted) and is deterministic on repeat.
@given(data=st.data())
def test_property_21_arity_and_determinism(data: st.DataObject) -> None:
    valid = (
        _part("A", "E1", 1, supply="s"),
        _part("B", "E1", 2, supply="s"),
    )
    # Deterministic on repeat.
    first = compare_parts(valid)
    second = compare_parts(valid)
    assert first.part_order == second.part_order
    assert [p.metric_key for p in first.pairs] == [p.metric_key for p in second.pairs]

    # Too few.
    assert compare_parts((valid[0],)).failure is SemanticFailureCode.NOT_COMPARABLE
    # Too many.
    too_many = valid + (
        _part("C", "E1", 3, supply="s"),
        _part("D", "E1", 4, supply="s"),
    )
    assert compare_parts(too_many).failure is SemanticFailureCode.NOT_COMPARABLE
    # Duplicate PN.
    dup = (valid[0], _part("A", "E1", 9, supply="s"))
    dup_result = compare_parts(dup)
    assert dup_result.failure is SemanticFailureCode.NOT_COMPARABLE
    assert dup_result.pairs == ()  # no partial set
