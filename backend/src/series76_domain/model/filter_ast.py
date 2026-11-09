"""The ``Filter_AST`` — a typed, validated boolean filter (F2 §4, design § Data Models).

A filter is a tree of :class:`And` / :class:`Or` / :class:`Not` combinators over
:class:`Predicate` leaves. **Raw SQL is never a representable node** — there is
no free-text node kind — so a model can only express a filter through this
typed surface (Property 6, Property 14).

Each :class:`Predicate` references an :class:`AllowlistField` (only fields in the
allowlist can be filtered), applies a typed :class:`Operator`, and carries a
typed value (and optional unit for unit-qualified matching). Range bounds are
explicitly inclusive or exclusive and are applied exactly at equality
(Property 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from series76_domain.model.units import Dimension, Unit


class FieldKind(str, Enum):
    """The value kind a field carries, used for operator/value compatibility."""

    NUMERIC = "NUMERIC"
    STRING = "STRING"
    ENUM = "ENUM"
    BOOLEAN = "BOOLEAN"


class AllowlistField(str, Enum):
    """The closed allowlist of filterable fields (design § Filter_AST).

    A field may act as a hard filter, a preference, or a response field; this
    enum defines *which* fields may ever appear in a predicate. Anything outside
    this set yields ``INVALID_FILTER``.
    """

    EXACT_PN = "exact_pn"
    ENCLOSURE = "enclosure"
    NOMINAL_VOLTAGE = "nominal_voltage"
    CURRENT_MODE = "current_mode"
    PHASE = "phase"
    SERVICE = "service"
    TORQUE_INLBS = "torque_inlbs"
    TORQUE_NM = "torque_nm"
    DUTY_S4 = "duty_s4"
    CYCLES_PER_HOUR = "cycles_per_hour"
    STARTS_PER_HOUR = "starts_per_hour"
    OPERATING_SPEED = "operating_speed"
    FLA = "fla"
    LRA = "lra"
    MOTOR_POWER = "motor_power"
    NOTE = "note"
    CERTIFICATION = "certification"

    @property
    def kind(self) -> FieldKind:
        """The value kind this field carries."""
        return _FIELD_KIND[self]

    @property
    def dimension(self) -> Dimension | None:
        """The physical dimension of a numeric field, else ``None``."""
        return _FIELD_DIMENSION.get(self)


_FIELD_KIND: dict[AllowlistField, FieldKind] = {
    AllowlistField.EXACT_PN: FieldKind.STRING,
    AllowlistField.ENCLOSURE: FieldKind.STRING,
    AllowlistField.NOMINAL_VOLTAGE: FieldKind.NUMERIC,
    AllowlistField.CURRENT_MODE: FieldKind.ENUM,
    AllowlistField.PHASE: FieldKind.STRING,
    AllowlistField.SERVICE: FieldKind.STRING,
    AllowlistField.TORQUE_INLBS: FieldKind.NUMERIC,
    AllowlistField.TORQUE_NM: FieldKind.NUMERIC,
    AllowlistField.DUTY_S4: FieldKind.NUMERIC,
    AllowlistField.CYCLES_PER_HOUR: FieldKind.NUMERIC,
    AllowlistField.STARTS_PER_HOUR: FieldKind.NUMERIC,
    AllowlistField.OPERATING_SPEED: FieldKind.NUMERIC,
    AllowlistField.FLA: FieldKind.NUMERIC,
    AllowlistField.LRA: FieldKind.NUMERIC,
    AllowlistField.MOTOR_POWER: FieldKind.NUMERIC,
    AllowlistField.NOTE: FieldKind.STRING,
    AllowlistField.CERTIFICATION: FieldKind.STRING,
}

_FIELD_DIMENSION: dict[AllowlistField, Dimension] = {
    AllowlistField.NOMINAL_VOLTAGE: Dimension.VOLTAGE,
    AllowlistField.TORQUE_INLBS: Dimension.TORQUE,
    AllowlistField.TORQUE_NM: Dimension.TORQUE,
    AllowlistField.DUTY_S4: Dimension.DIMENSIONLESS,
    AllowlistField.CYCLES_PER_HOUR: Dimension.DIMENSIONLESS,
    AllowlistField.STARTS_PER_HOUR: Dimension.DIMENSIONLESS,
    AllowlistField.OPERATING_SPEED: Dimension.TIME,
    AllowlistField.FLA: Dimension.CURRENT,
    AllowlistField.LRA: Dimension.CURRENT,
    AllowlistField.MOTOR_POWER: Dimension.POWER,
}


class Operator(str, Enum):
    """Typed comparison operators (design § Filter_AST).

    * ``EQ`` / ``NE`` — typed equality (any kind).
    * ``LT`` / ``LE`` / ``GT`` / ``GE`` — ordered comparisons (numeric only).
      ``LE`` and ``GE`` are inclusive bounds (satisfied at equality); ``LT`` and
      ``GT`` are exclusive bounds (not satisfied at equality).
    * ``IN`` — set membership (value is a tuple of candidates).
    """

    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    IN = "IN"

    @property
    def is_ordered(self) -> bool:
        """True iff the operator is an ordered (numeric) comparison."""
        return self in (Operator.LT, Operator.LE, Operator.GT, Operator.GE)

    @property
    def is_inclusive_bound(self) -> bool:
        """True iff an ordered bound that is satisfied at equality."""
        return self in (Operator.LE, Operator.GE)


# A typed predicate value: a scalar, or a tuple for IN membership.
TypedValue = Decimal | int | str | bool | tuple[Decimal | int | str | bool, ...]


class Node:
    """Marker base class for every ``Filter_AST`` node (no SQL node exists)."""


@dataclass(frozen=True, slots=True)
class Predicate(Node):
    """A leaf predicate over a single allowlisted field.

    Args:
        field: the allowlisted field being filtered.
        operator: the typed comparison operator.
        value: the typed comparison value (tuple for ``IN``).
        unit: optional unit for unit-qualified numeric matching.
    """

    field: AllowlistField
    operator: Operator
    value: TypedValue
    unit: Unit | None = None


@dataclass(frozen=True, slots=True)
class And(Node):
    """Conjunction: satisfied iff *every* child is satisfied."""

    children: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Or(Node):
    """Disjunction: satisfied iff *any* child is satisfied."""

    children: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Not(Node):
    """Negation over a bounded domain: satisfied iff the child is not."""

    child: Node
