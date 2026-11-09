"""Unit type and the dimension taxonomy used across metrics and conversions.

Units are modeled as a closed enumeration grouped by *dimension*. Two units are
convertible if and only if they share a dimension (Property 11, Property 22).
The ``DIMENSIONLESS`` dimension holds counts/percentages that have no unit
conversion partner other than themselves.

Decimal only: no conversion factor is ever a ``float`` (Req 6.1).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum


class Dimension(str, Enum):
    """The physical dimension a :class:`Unit` measures."""

    TORQUE = "TORQUE"
    POWER = "POWER"
    CURRENT = "CURRENT"
    FREQUENCY = "FREQUENCY"
    VOLTAGE = "VOLTAGE"
    TIME = "TIME"
    DIMENSIONLESS = "DIMENSIONLESS"


class Unit(str, Enum):
    """A closed set of units documented by the Series 76 catalog.

    The string value is the canonical printed form. Every unit maps to exactly
    one :class:`Dimension`; conversion is only defined within a dimension.
    """

    # Torque
    IN_LBS = "in-lbs"
    NM = "Nm"
    # Power
    WATT = "W"
    # Current
    AMPERE = "A"
    # Frequency
    HERTZ = "Hz"
    # Voltage
    VOLT = "V"
    # Time
    SECOND = "s"
    # Dimensionless
    PERCENT = "%"
    COUNT = "count"

    @property
    def dimension(self) -> Dimension:
        """Return the physical dimension this unit measures."""
        return _UNIT_DIMENSION[self]

    def is_convertible_to(self, other: Unit) -> bool:
        """True iff ``self`` and ``other`` share a dimension (Property 11)."""
        return self.dimension is other.dimension


_UNIT_DIMENSION: dict[Unit, Dimension] = {
    Unit.IN_LBS: Dimension.TORQUE,
    Unit.NM: Dimension.TORQUE,
    Unit.WATT: Dimension.POWER,
    Unit.AMPERE: Dimension.CURRENT,
    Unit.HERTZ: Dimension.FREQUENCY,
    Unit.VOLT: Dimension.VOLTAGE,
    Unit.SECOND: Dimension.TIME,
    Unit.PERCENT: Dimension.DIMENSIONLESS,
    Unit.COUNT: Dimension.DIMENSIONLESS,
}


# Exact conversion factors (Decimal) keyed by (from_unit, to_unit). Only
# in-dimension pairs are present. 1 in-lbs = 0.1129848290276167 Nm is the exact
# SI definition rounded to the documented precision; stored as Decimal so no
# float enters the pipeline. Conversions missing from this table are rejected.
CONVERSION_FACTORS: dict[tuple[Unit, Unit], Decimal] = {
    (Unit.IN_LBS, Unit.NM): Decimal("0.112984829"),
    (Unit.NM, Unit.IN_LBS): Decimal("8.850745792"),
}


def parse_unit(printed: str | None) -> Unit | None:
    """Resolve a printed unit string to a :class:`Unit`, or ``None`` if blank.

    Raises:
        KeyError: if the printed form is non-empty but unrecognized. Callers
            that must not coerce an unknown unit surface this as a typed error.
    """

    if printed is None:
        return None
    normalized = printed.strip()
    if not normalized:
        return None
    return _PRINTED_TO_UNIT[normalized]


_PRINTED_TO_UNIT: dict[str, Unit] = {u.value: u for u in Unit}
