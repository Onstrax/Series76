"""The ``(value, status)`` metric-pair abstraction (Req 4.1, 5.1-5.3).

A technical metric is never a bare number. It is a :class:`MetricValue`
pairing a :class:`~decimal.Decimal` (or ``None``) with an
:class:`~series76_data.models.enums.AvailabilityStatus`. The pairing enforces,
in Python, the same invariant the database ``CHECK`` enforces:

    status == AVAILABLE  <=>  value is not None

Consequences (Property 14):

* a documented numeric zero is ``MetricValue(Decimal("0"), AVAILABLE)``;
* a printed "N/A" is ``MetricValue(None, NOT_APPLICABLE)``;
* a missing value is ``MetricValue(None, NOT_DOCUMENTED)``;

...and these three are pairwise distinguishable by direct inspection. Distinct
absence reasons are carried by ``status`` and are never collapsed into one
undifferentiated ``None``.

``Decimal`` is used deliberately: measured quantities are stored verbatim with
no implicit float rounding or coercion (Req 4.1, 4.8).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_data.models.enums import AvailabilityStatus


class ValueStatusError(ValueError):
    """Raised when a ``(value, status)`` pair violates the core invariant."""


@dataclass(frozen=True, slots=True)
class MetricValue:
    """An immutable documented technical metric.

    Args:
        value: the printed numeric value as a :class:`~decimal.Decimal`, or
            ``None`` when ``status`` is not ``AVAILABLE``.
        status: the availability status carrying the reason of any absence.

    Raises:
        ValueStatusError: if the AVAILABLE<=>value-present invariant is broken.
    """

    value: Decimal | None
    status: AvailabilityStatus

    def __post_init__(self) -> None:
        if self.status is AvailabilityStatus.AVAILABLE and self.value is None:
            raise ValueStatusError("AVAILABLE status requires a non-null value")
        if self.status is not AvailabilityStatus.AVAILABLE and self.value is not None:
            raise ValueStatusError(
                f"status {self.status.value} requires a null value, got {self.value!r}"
            )
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueStatusError("value must be a finite Decimal")

    # --- Distinguishing predicates (Property 14) ---

    @property
    def is_available(self) -> bool:
        """True iff a value is documented (including a documented zero)."""
        return self.status is AvailabilityStatus.AVAILABLE

    @property
    def is_documented_zero(self) -> bool:
        """True iff this is a documented numeric zero — distinct from N/A/absence."""
        return self.is_available and self.value == Decimal(0)

    @property
    def is_not_applicable(self) -> bool:
        """True iff the source printed N/A for this field."""
        return self.status is AvailabilityStatus.NOT_APPLICABLE

    @property
    def is_absent(self) -> bool:
        """True iff the source printed no value (NOT_DOCUMENTED)."""
        return self.status is AvailabilityStatus.NOT_DOCUMENTED

    @property
    def is_unverified(self) -> bool:
        """True iff the value is pending manual audit."""
        return self.status is AvailabilityStatus.NOT_VERIFIED

    # --- Constructors expressing intent at call sites ---

    @classmethod
    def available(cls, value: Decimal | int | str) -> MetricValue:
        """Build a documented ``AVAILABLE`` value (accepts Decimal/int/str, never float)."""
        if isinstance(value, float):
            raise ValueStatusError(
                "refusing float input; pass Decimal/int/str to avoid silent rounding"
            )
        return cls(Decimal(value), AvailabilityStatus.AVAILABLE)

    @classmethod
    def not_applicable(cls) -> MetricValue:
        """Build a printed-N/A value."""
        return cls(None, AvailabilityStatus.NOT_APPLICABLE)

    @classmethod
    def not_documented(cls) -> MetricValue:
        """Build an absence (no printed value)."""
        return cls(None, AvailabilityStatus.NOT_DOCUMENTED)

    @classmethod
    def not_verified(cls) -> MetricValue:
        """Build a value pending manual audit."""
        return cls(None, AvailabilityStatus.NOT_VERIFIED)


@dataclass(frozen=True, slots=True)
class Measured:
    """A :class:`MetricValue` paired with its printed unit (verbatim).

    The unit text is preserved exactly as printed; unrecognized units are never
    coerced (Req 4.8) — that decision belongs to the Normalizer, which raises
    ``UNSUPPORTED_UNIT`` rather than silently converting.
    """

    metric: MetricValue
    unit: str | None
