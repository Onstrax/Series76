"""``DerivedValue`` — a labeled deterministic computation over published values.

A :class:`DerivedValue` is produced by a deterministic computation (e.g. a unit
conversion) over documented values. It is **labeled as derived** with its
formula and applied rounding precision (as a fixed number of decimal places),
and is a **distinct type** from :class:`~series76_domain.model.metric_value.MetricValue`
so it can never be silently substituted for an official documented figure
(Req 6.1, 6.3, 10.3; Property 22).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.units import Unit


class DerivedValueError(ValueError):
    """Raised when a :class:`DerivedValue` is constructed inconsistently."""


@dataclass(frozen=True, slots=True)
class DerivedValue:
    """A value computed deterministically from documented values.

    Args:
        value: the computed magnitude (always a :class:`~decimal.Decimal`).
        unit: the unit of the computed value.
        formula: a human-readable label of the computation performed.
        precision_decimals: the fixed number of decimal places applied.
        input_evidence: evidence references for the values the computation
            consumed; at least one is required so the derivation is traceable.

    Raises:
        DerivedValueError: if ``value`` is not a finite Decimal, if
            ``precision_decimals`` is negative, or if ``input_evidence`` is
            empty (an untraceable derivation).
    """

    value: Decimal
    unit: Unit
    formula: str
    precision_decimals: int
    input_evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        if isinstance(self.value, float) or not isinstance(self.value, Decimal):
            raise DerivedValueError("DerivedValue.value must be a Decimal, never a float")
        if not self.value.is_finite():
            raise DerivedValueError("DerivedValue.value must be a finite Decimal")
        if self.precision_decimals < 0:
            raise DerivedValueError("precision_decimals must be non-negative")
        if not self.input_evidence:
            raise DerivedValueError("a DerivedValue must carry at least one input evidence")

    @property
    def is_derived(self) -> bool:
        """Always ``True`` — a label marking this value as *not* official."""
        return True
