"""Shared Hypothesis strategies for Filter_AST and candidate fields.

Used by the search-semantics property tests (Properties 6-11). Generates valid
ASTs over numeric fields and candidate field maps with documented / N/A /
absent / zero states so N/A-coercion and bound-equality edges are exercised.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import strategies as st

from series76_domain.model.enums import DataStatus
from series76_domain.model.evaluation import CandidateFields, FieldValue
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
from series76_domain.model.metric_value import MetricValue

# A small set of numeric fields (same dimension handling) for AST generation.
NUMERIC_FIELDS = [
    f for f in AllowlistField if f.kind is FieldKind.NUMERIC
]

_NUMERIC_OPERATORS = [
    Operator.EQ,
    Operator.NE,
    Operator.LT,
    Operator.LE,
    Operator.GT,
    Operator.GE,
]

_SMALL_INTS = st.integers(min_value=0, max_value=10)


def numeric_predicates() -> st.SearchStrategy[Predicate]:
    """Valid numeric predicates without units (kept unit-free for simplicity)."""

    return st.builds(
        Predicate,
        field=st.sampled_from(NUMERIC_FIELDS),
        operator=st.sampled_from(_NUMERIC_OPERATORS),
        value=_SMALL_INTS.map(Decimal),
        unit=st.none(),
    )


def filter_asts(max_leaves: int = 4) -> st.SearchStrategy[Node]:
    """Generate a valid boolean AST over numeric predicates."""

    leaves = numeric_predicates()

    def extend(children: st.SearchStrategy[Node]) -> st.SearchStrategy[Node]:
        node_list = st.lists(children, min_size=1, max_size=3).map(tuple)
        return st.one_of(
            children,
            st.builds(And, children=node_list),
            st.builds(Or, children=node_list),
            st.builds(Not, child=children),
        )

    return st.recursive(leaves, extend, max_leaves=max_leaves)


def _field_value_for(field: AllowlistField) -> st.SearchStrategy[FieldValue]:
    """A documented/N-A/absent FieldValue for a numeric field."""

    documented = _SMALL_INTS.map(
        lambda v: FieldValue(
            status=DataStatus.AVAILABLE,
            metric=MetricValue.available(Decimal(v)),
        )
    )
    na = st.just(
        FieldValue(status=DataStatus.NOT_APPLICABLE, metric=MetricValue.not_applicable())
    )
    absent = st.just(
        FieldValue(status=DataStatus.NOT_DOCUMENTED, metric=MetricValue.not_documented())
    )
    return st.one_of(documented, documented, na, absent)


def candidate_fields() -> st.SearchStrategy[CandidateFields]:
    """Generate a candidate's field map over the numeric fields."""

    def build(chosen: list[AllowlistField]) -> st.SearchStrategy[CandidateFields]:
        if not chosen:
            return st.just({})
        value_strategies = {
            field: st.lists(_field_value_for(field), min_size=1, max_size=2).map(tuple)
            for field in chosen
        }
        return st.fixed_dictionaries(value_strategies)

    return st.lists(
        st.sampled_from(NUMERIC_FIELDS), min_size=0, max_size=len(NUMERIC_FIELDS), unique=True
    ).flatmap(build)
