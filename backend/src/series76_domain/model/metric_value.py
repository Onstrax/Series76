"""The Spec 2 ``MetricValue`` (value, status, unit) triple (design § Data Models).

This mirrors the Spec 1 ``(value, status)`` encoding but carries the Spec 2
:class:`~series76_domain.model.enums.DataStatus` and an optional
:class:`~series76_domain.model.units.Unit`. The core invariant is:

    status == AVAILABLE  <=>  value is not None

A documented numeric **zero** (``AVAILABLE``, ``0``), an **N/A**
(``NOT_APPLICABLE``), and an **absence** (``NOT_DOCUMENTED``) are three
distinguishable states; no code path coerces N/A or absence to zero or a
default (Req 1.7, 2.6, 2.7, 3.4; Property 3, Property 10). ``Decimal`` only —
``float`` is rejected at construction to avoid silent rounding.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_data.models.enums import AvailabilityStatus
from series76_domain.model.enums import DataStatus
from series76_domain.model.units import Unit


class MetricValueError(ValueError):
    """Raised when a ``(value, status)`` pair violates the core invariant."""


def data_status_from_availability(status: AvailabilityStatus) -> DataStatus:
    """Map a Spec 1 ``AvailabilityStatus`` to a Spec 2 ``DataStatus``.

    ``NOT_VERIFIED`` is renamed to ``UNVERIFIED``; the other three states keep
    their meaning. ``NOT_LISTED`` has no Spec 1 persistence analogue (it is a
    whole-entity absence decided by the operations layer), so it is never
    produced by this mapping.
    """

    return _AVAILABILITY_TO_DATA_STATUS[status]


_AVAILABILITY_TO_DATA_STATUS: dict[AvailabilityStatus, DataStatus] = {
    AvailabilityStatus.AVAILABLE: DataStatus.AVAILABLE,
    AvailabilityStatus.NOT_APPLICABLE: DataStatus.NOT_APPLICABLE,
    AvailabilityStatus.NOT_DOCUMENTED: DataStatus.NOT_DOCUMENTED,
    AvailabilityStatus.NOT_VERIFIED: DataStatus.UNVERIFIED,
}


@dataclass(frozen=True, slots=True)
class MetricValue:
    """An immutable documented technical metric with status and unit.

    Args:
        value: the printed numeric value as a :class:`~decimal.Decimal`, or
            ``None`` when ``status`` is not ``AVAILABLE``.
        status: the documented status carrying the reason of any absence.
        unit: the documented unit, or ``None`` for a dimensionless/absent value.

    Raises:
        MetricValueError: if the ``AVAILABLE <=> value present`` invariant is
            broken, or if ``value`` is a non-finite Decimal or a ``float``.
    """

    value: Decimal | None
    status: DataStatus
    unit: Unit | None = None

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            raise MetricValueError(
                "refusing float value; pass Decimal/int/str to avoid silent rounding"
            )
        if self.status is DataStatus.AVAILABLE and self.value is None:
            raise MetricValueError("AVAILABLE status requires a non-null value")
        if self.status is not DataStatus.AVAILABLE and self.value is not None:
            raise MetricValueError(
                f"status {self.status.value} requires a null value, got {self.value!r}"
            )
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise MetricValueError("value must be a finite Decimal")

    # --- distinguishing predicates (Property 3, Property 10) --------------

    @property
    def is_available(self) -> bool:
        """True iff a value is documented (including a documented zero)."""
        return self.status is DataStatus.AVAILABLE

    @property
    def is_documented_zero(self) -> bool:
        """True iff a documented numeric zero — distinct from N/A and absence."""
        return self.is_available and self.value == Decimal(0)

    @property
    def is_not_applicable(self) -> bool:
        """True iff the source printed N/A for this field."""
        return self.status is DataStatus.NOT_APPLICABLE

    @property
    def is_absent(self) -> bool:
        """True iff the source printed no value (NOT_DOCUMENTED)."""
        return self.status is DataStatus.NOT_DOCUMENTED

    @property
    def is_unverified(self) -> bool:
        """True iff the value is present but not audit-confirmed."""
        return self.status is DataStatus.UNVERIFIED

    @property
    def satisfies_numeric_predicate_eligible(self) -> bool:
        """True iff this value may participate in a numeric predicate.

        Only an ``AVAILABLE`` value is eligible; N/A and absent values never
        satisfy a numeric predicate and are never coerced (Property 10).
        """
        return self.is_available

    # --- constructors expressing intent at call sites ---------------------

    @classmethod
    def available(cls, value: Decimal | int | str, unit: Unit | None = None) -> MetricValue:
        """Build a documented ``AVAILABLE`` value (Decimal/int/str, never float)."""
        if isinstance(value, float):
            raise MetricValueError(
                "refusing float input; pass Decimal/int/str to avoid silent rounding"
            )
        return cls(Decimal(value), DataStatus.AVAILABLE, unit)

    @classmethod
    def not_applicable(cls, unit: Unit | None = None) -> MetricValue:
        """Build a printed-N/A value."""
        return cls(None, DataStatus.NOT_APPLICABLE, unit)

    @classmethod
    def not_documented(cls, unit: Unit | None = None) -> MetricValue:
        """Build an absence (no printed value)."""
        return cls(None, DataStatus.NOT_DOCUMENTED, unit)

    @classmethod
    def unverified(cls, unit: Unit | None = None) -> MetricValue:
        """Build a value present but pending audit confirmation."""
        return cls(None, DataStatus.UNVERIFIED, unit)
