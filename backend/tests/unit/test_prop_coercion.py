"""Property 10 — N/A and absent never satisfy/coerce across the stack (Spec 2).

A single property covers the filtering, ranking, and comparison slices: an N/A
or absent value never satisfies a numeric predicate, is never coerced to zero,
is never a ranking value, and is never a comparison winner, and the N/A state
stays distinguishable from the absent state throughout.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import DataStatus
from series76_domain.model.evaluation import CandidateFields, FieldValue, evaluate
from series76_domain.model.filter_ast import AllowlistField, Operator, Predicate
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit
from series76_domain.services.compare_parts import (
    ComparableMetric,
    PartComparisonInput,
    compare_parts,
)
from series76_domain.services.rank_candidates import (
    RankCandidate,
    RankPriority,
    SortDirection,
    rank_candidates,
)

_FIELD = AllowlistField.TORQUE_INLBS
_KEY = "torque_inlbs"


def _indeterminate() -> st.SearchStrategy[MetricValue]:
    return st.sampled_from(
        [MetricValue.not_applicable(Unit.IN_LBS), MetricValue.not_documented(Unit.IN_LBS)]
    )


# Feature: domain-and-tools, Property 10: N/A and absent values never satisfy a
# numeric predicate, are never coerced to zero/default, never rank, never win a
# comparison, and keep N/A distinguishable from absent throughout.
@given(
    indeterminate=_indeterminate(),
    threshold=st.integers(min_value=-5, max_value=5).map(Decimal),
    operator=st.sampled_from(
        [Operator.EQ, Operator.GE, Operator.LE, Operator.GT, Operator.LT]
    ),
)
def test_property_10(
    indeterminate: MetricValue, threshold: Decimal, operator: Operator
) -> None:
    # --- filtering slice: never satisfies a numeric predicate ---------------
    fields: CandidateFields = {
        _FIELD: (FieldValue(status=indeterminate.status, metric=indeterminate),)
    }
    predicate = Predicate(field=_FIELD, operator=operator, value=threshold)
    assert evaluate(predicate, fields) is False

    # Not coerced to zero: a predicate matching zero must not match it.
    zero_pred = Predicate(field=_FIELD, operator=Operator.EQ, value=Decimal(0))
    assert evaluate(zero_pred, fields) is False

    # --- ranking slice: excluded from comparison, placed after comparables --
    comparable = RankCandidate(
        base_pn="A", metrics={_KEY: MetricValue.available(Decimal(1), Unit.IN_LBS)},
        comparable_keys=frozenset({_KEY}),
    )
    indeterminate_cand = RankCandidate(
        base_pn="B", metrics={_KEY: indeterminate}, comparable_keys=frozenset({_KEY})
    )
    result = rank_candidates(
        (indeterminate_cand, comparable),
        (RankPriority(_KEY, SortDirection.ASC),),
    )
    assert result.ranked[0].base_pn == "A"  # comparable first, indeterminate after
    assert result.ranked[-1].base_pn == "B"

    # --- comparison slice: never a winner, shown with explicit state --------
    left = PartComparisonInput(
        base_pn="A",
        edition_id="E",
        metrics=(
            ComparableMetric(
                base_pn="A",
                metric_key=_KEY,
                value=MetricValue.available(Decimal(1), Unit.IN_LBS),
                unit=Unit.IN_LBS,
            ),
        ),
    )
    right = PartComparisonInput(
        base_pn="B",
        edition_id="E",
        metrics=(
            ComparableMetric(
                base_pn="B", metric_key=_KEY, value=indeterminate, unit=Unit.IN_LBS
            ),
        ),
    )
    comparison = compare_parts((left, right))
    assert comparison.ok
    pair = comparison.pairs[0]
    assert pair.has_winner is False  # an N/A/absent field is never a winner

    # --- N/A stays distinguishable from absent ------------------------------
    assert MetricValue.not_applicable() != MetricValue.not_documented()
    assert (indeterminate.status is DataStatus.NOT_APPLICABLE) != (
        indeterminate.status is DataStatus.NOT_DOCUMENTED
    )
