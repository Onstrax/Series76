"""Boolean evaluation of a validated ``Filter_AST`` over a candidate's fields.

This module is the single, shared semantics of what it means for a candidate
to *satisfy* a filter. It is used by:

* the real :mod:`series76_domain.operations.search_parts` path, and
* the test oracle for Properties 6-8 (a candidate satisfies the fully
  parenthesized boolean expression exactly when this evaluator says so).

A candidate exposes its filterable fields as a mapping of
:class:`~series76_domain.model.filter_ast.AllowlistField` to a
:class:`FieldValue`. The evaluator applies ``AND``/``OR``/``NOT`` strictly by
explicit grouping with **no** implicit re-association or precedence
substitution (Property 6), inclusive/exclusive bounds exactly at equality
(Property 9), unit-qualified matching only under convertible units
(Property 11), and treats N/A and absent fields as **not** satisfying any
predicate while never coercing them to a default (Property 10).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_domain.model.enums import DataStatus
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
from series76_domain.model.units import CONVERSION_FACTORS, Unit


@dataclass(frozen=True, slots=True)
class FieldValue:
    """A candidate's value for one allowlisted field.

    A numeric field carries a :class:`MetricValue` (so N/A/absent states are
    preserved). A string/enum/boolean field carries a scalar and a
    :class:`DataStatus`.

    Exactly one of ``metric`` / ``scalar`` is meaningful depending on the
    field kind. ``status`` reflects whether the value is documented.
    """

    status: DataStatus
    metric: MetricValue | None = None
    scalar: str | bool | None = None

    @property
    def is_documented(self) -> bool:
        """True iff the field carries a documented value (not N/A/absent)."""
        return self.status is DataStatus.AVAILABLE


# A candidate's filterable surface: field -> value (possibly multiple values
# for a field that repeats, e.g. a service appearing in several rows). A field
# absent from the mapping is treated as NOT_DOCUMENTED for that candidate.
CandidateFields = dict[AllowlistField, tuple[FieldValue, ...]]


def evaluate(node: Node, fields: CandidateFields) -> bool:
    """Return whether ``fields`` satisfy ``node`` under strict grouping.

    Args:
        node: a *validated* ``Filter_AST`` node (validate before evaluating).
        fields: the candidate's filterable field values.

    Returns:
        ``True`` iff the candidate satisfies the boolean expression exactly as
        grouped; ``AND`` requires all children, ``OR`` requires any child,
        ``NOT`` inverts its child.
    """

    if isinstance(node, Predicate):
        return _satisfies_predicate(node, fields)
    if isinstance(node, And):
        return all(evaluate(child, fields) for child in node.children)
    if isinstance(node, Or):
        return any(evaluate(child, fields) for child in node.children)
    if isinstance(node, Not):
        return not evaluate(node.child, fields)
    raise TypeError(f"cannot evaluate unknown node kind {type(node).__name__!r}")


def _satisfies_predicate(predicate: Predicate, fields: CandidateFields) -> bool:
    """A field satisfies a predicate iff *any* of its values match.

    An absent field (not in the mapping) never satisfies a predicate.
    """

    values = fields.get(predicate.field, ())
    return any(_value_matches(predicate, value) for value in values)


def _value_matches(predicate: Predicate, value: FieldValue) -> bool:
    """Whether a single :class:`FieldValue` matches a predicate."""

    kind = predicate.field.kind
    if kind is FieldKind.NUMERIC:
        return _numeric_match(predicate, value)
    return _scalar_match(predicate, value)


def _numeric_match(predicate: Predicate, value: FieldValue) -> bool:
    metric = value.metric
    # N/A and absent never satisfy a numeric predicate; never coerced.
    if metric is None or not metric.is_available or metric.value is None:
        return False

    candidate = metric.value
    # Unit-qualified matching: convert the candidate into the predicate's unit
    # when a unit is declared; a non-convertible unit rejects the comparison.
    if predicate.unit is not None:
        converted = _convert(candidate, metric.unit, predicate.unit)
        if converted is None:
            return False
        candidate = converted

    target = predicate.value
    operator = predicate.operator
    if operator is Operator.IN:
        if not isinstance(target, tuple):
            return False
        return any(candidate == _as_decimal(item) for item in target)

    scalar = _as_decimal(target)
    if scalar is None:
        return False
    if operator is Operator.EQ:
        return candidate == scalar
    if operator is Operator.NE:
        return candidate != scalar
    if operator is Operator.LT:
        return candidate < scalar
    if operator is Operator.LE:
        return candidate <= scalar
    if operator is Operator.GT:
        return candidate > scalar
    if operator is Operator.GE:
        return candidate >= scalar
    return False


def _scalar_match(predicate: Predicate, value: FieldValue) -> bool:
    if not value.is_documented or value.scalar is None:
        return False
    candidate = value.scalar
    target = predicate.value
    operator = predicate.operator
    if operator is Operator.IN:
        if not isinstance(target, tuple):
            return False
        return candidate in target
    if operator is Operator.EQ:
        return candidate == target
    if operator is Operator.NE:
        return candidate != target
    # Ordered operators are rejected on non-numeric fields by the validator;
    # defensively they never match here.
    return False


def _convert(value: Decimal, from_unit: Unit | None, to_unit: Unit) -> Decimal | None:
    """Convert ``value`` from ``from_unit`` to ``to_unit`` (Decimal), or ``None``.

    Same unit is an identity; a different unit requires a known conversion
    factor in the same dimension; otherwise the comparison is rejected.
    """

    if from_unit is None:
        return None
    if from_unit is to_unit:
        return value
    if not from_unit.is_convertible_to(to_unit):
        return None
    factor = CONVERSION_FACTORS.get((from_unit, to_unit))
    if factor is None:
        return None
    return value * factor


def _as_decimal(value: object) -> Decimal | None:
    """Coerce a typed scalar to :class:`Decimal` for numeric comparison."""

    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    return None
