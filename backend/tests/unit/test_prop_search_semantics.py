"""Properties 6, 7, 8, 9, 11 — Filter_AST boolean/range/unit semantics (Spec 2).

These are pure-logic properties over the shared boolean evaluator
(:func:`series76_domain.model.evaluation.evaluate`). Property 6-8 use an
*independent* reference boolean evaluator (re-implemented here) as the oracle so
the production evaluator is checked against a second implementation of the
grouped semantics.
"""

from __future__ import annotations

from decimal import Decimal

from _strategies import candidate_fields, filter_asts
from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import DataStatus
from series76_domain.model.evaluation import CandidateFields, FieldValue, evaluate
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
from series76_domain.model.units import Unit

# --- independent reference oracle (second implementation) -----------------


def reference_eval(node: Node, fields: CandidateFields) -> bool:
    """A second, independent boolean evaluator used as the Property 6-8 oracle."""

    match node:
        case Predicate():
            return _ref_predicate(node, fields)
        case And(children=children):
            result = True
            for child in children:
                result = result and reference_eval(child, fields)
            return result
        case Or(children=children):
            result = False
            for child in children:
                result = result or reference_eval(child, fields)
            return result
        case Not(child=child):
            return not reference_eval(child, fields)
    raise AssertionError("unreachable")


def _ref_predicate(predicate: Predicate, fields: CandidateFields) -> bool:
    for value in fields.get(predicate.field, ()):
        if predicate.field.kind is FieldKind.NUMERIC:
            metric = value.metric
            if metric is None or metric.value is None or not metric.is_available:
                continue
            target = Decimal(predicate.value)  # type: ignore[arg-type]
            candidate = metric.value
            op = predicate.operator
            if op is Operator.EQ and candidate == target:
                return True
            if op is Operator.NE and candidate != target:
                return True
            if op is Operator.LT and candidate < target:
                return True
            if op is Operator.LE and candidate <= target:
                return True
            if op is Operator.GT and candidate > target:
                return True
            if op is Operator.GE and candidate >= target:
                return True
    return False


# Feature: domain-and-tools, Property 6: boolean AST evaluation equals its
# grounded grouping (each AND/OR/NOT applied strictly by explicit grouping,
# no implicit re-association or precedence substitution).
@given(node=filter_asts(), fields=candidate_fields())
def test_property_6_grouped_evaluation_equals_oracle(
    node: Node, fields: CandidateFields
) -> None:
    assert evaluate(node, fields) == reference_eval(node, fields)


# Feature: domain-and-tools, Property 7: adding an AND constraint never grows
# the matched set (monotonicity).
@given(base=filter_asts(), extra=filter_asts(), fields=candidate_fields())
def test_property_7_and_monotonicity(
    base: Node, extra: Node, fields: CandidateFields
) -> None:
    conjoined = And(children=(base, extra))
    if evaluate(conjoined, fields):
        # A conjunction can only match where the original already matched.
        assert evaluate(base, fields)


# Feature: domain-and-tools, Property 8: reordering AND operands does not change
# the matched set or total.
@given(
    a=filter_asts(),
    b=filter_asts(),
    c=filter_asts(),
    fields=candidate_fields(),
)
def test_property_8_and_commutative(
    a: Node, b: Node, c: Node, fields: CandidateFields
) -> None:
    forward = And(children=(a, b, c))
    reordered = And(children=(c, a, b))
    assert evaluate(forward, fields) == evaluate(reordered, fields)


# Feature: domain-and-tools, Property 9: range inclusive/exclusive semantics are
# exact at equality.
@given(bound=st.integers(min_value=0, max_value=10))
def test_property_9_bound_equality(bound: int) -> None:
    field = AllowlistField.TORQUE_INLBS
    value = FieldValue(
        status=DataStatus.AVAILABLE, metric=MetricValue.available(Decimal(bound))
    )
    fields: CandidateFields = {field: (value,)}
    target = Decimal(bound)

    le = Predicate(field=field, operator=Operator.LE, value=target)
    ge = Predicate(field=field, operator=Operator.GE, value=target)
    lt = Predicate(field=field, operator=Operator.LT, value=target)
    gt = Predicate(field=field, operator=Operator.GT, value=target)

    assert evaluate(le, fields) is True  # inclusive satisfied at equality
    assert evaluate(ge, fields) is True
    assert evaluate(lt, fields) is False  # exclusive not satisfied at equality
    assert evaluate(gt, fields) is False


# Feature: domain-and-tools, Property 11: unit-qualified matching only under
# convertible units (a non-convertible unit rejects the comparison).
@given(magnitude=st.integers(min_value=1, max_value=100))
def test_property_11_unit_convertible_only(magnitude: int) -> None:
    field = AllowlistField.TORQUE_INLBS  # TORQUE dimension
    # Candidate documented in in-lbs.
    value = FieldValue(
        status=DataStatus.AVAILABLE,
        metric=MetricValue.available(Decimal(magnitude), Unit.IN_LBS),
    )
    fields: CandidateFields = {field: (value,)}

    # Predicate in Nm (convertible to in-lbs): comparison runs after conversion.
    nm_target = (Decimal(magnitude) * Decimal("0.112984829")).quantize(Decimal("0.000001"))
    convertible = Predicate(
        field=field, operator=Operator.LE, value=nm_target + 1, unit=Unit.NM
    )
    assert evaluate(convertible, fields) is True

    # Predicate in a non-convertible unit (Amperes): comparison is rejected,
    # never matched.
    non_convertible = Predicate(
        field=field, operator=Operator.GE, value=Decimal(0), unit=Unit.AMPERE
    )
    assert evaluate(non_convertible, fields) is False
