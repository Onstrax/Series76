"""The ``convert_units`` deterministic service (Task 9.1, Req 6.*).

Converts a documented :class:`~series76_domain.model.metric_value.MetricValue`
between a compatible unit pair using **Decimal** arithmetic and returns a
:class:`~series76_domain.model.derived.DerivedValue` labeled with its formula
and fixed decimal precision (Property 22). It is a **pure** function: it never
touches the database, never mutates its input, and never substitutes a
``DerivedValue`` for an official documented value.

An incompatible unit pair, or a missing / non-numeric / out-of-domain source
magnitude, returns an explicit :class:`ConversionError` carrying no converted
value and leaving the source unchanged (Property 23).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from series76_domain.model.derived import DerivedValue
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import CONVERSION_FACTORS, Unit

_DEFAULT_PRECISION = 4


@dataclass(frozen=True, slots=True)
class ConversionError:
    """An explicit, non-exception conversion failure (source unchanged).

    Attributes:
        reason: a short, secret-free description of why the conversion failed.
        source: the untouched source value.
    """

    reason: str
    source: MetricValue


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """The outcome of a conversion: a derived value or an explicit error."""

    derived: DerivedValue | None = None
    error: ConversionError | None = None

    @property
    def ok(self) -> bool:
        """True iff a :class:`DerivedValue` was produced."""
        return self.derived is not None


def convert_units(
    source: MetricValue,
    target_unit: Unit,
    *,
    evidence: EvidenceReference,
    precision_decimals: int = _DEFAULT_PRECISION,
) -> ConversionResult:
    """Convert ``source`` into ``target_unit`` as a labeled ``DerivedValue``.

    Args:
        source: the documented value to convert (must be ``AVAILABLE`` with a
            unit).
        target_unit: the unit to convert into (must share the source's
            dimension).
        evidence: the evidence reference of the source value (carried onto the
            derivation so it stays traceable).
        precision_decimals: the fixed number of decimal places to round to
            (half-even).

    Returns:
        A :class:`ConversionResult` with either a :class:`DerivedValue` or a
        :class:`ConversionError`. The source is never mutated.
    """

    if source.status.name != "AVAILABLE" or source.value is None:
        return ConversionResult(
            error=ConversionError("source magnitude is missing or non-numeric", source)
        )
    if source.unit is None:
        return ConversionResult(
            error=ConversionError("source has no unit to convert from", source)
        )
    if precision_decimals < 0:
        return ConversionResult(
            error=ConversionError("precision must be non-negative", source)
        )

    from_unit = source.unit
    if from_unit is target_unit:
        factor = Decimal(1)
    elif not from_unit.is_convertible_to(target_unit):
        return ConversionResult(
            error=ConversionError(
                f"units {from_unit.value} and {target_unit.value} are incompatible",
                source,
            )
        )
    else:
        looked_up = CONVERSION_FACTORS.get((from_unit, target_unit))
        if looked_up is None:
            return ConversionResult(
                error=ConversionError(
                    f"no conversion factor from {from_unit.value} to {target_unit.value}",
                    source,
                )
            )
        factor = looked_up

    quantum = Decimal(1).scaleb(-precision_decimals)
    computed = (source.value * factor).quantize(quantum, rounding=ROUND_HALF_EVEN)
    formula = (
        f"{source.value} {from_unit.value} x {factor} = "
        f"{computed} {target_unit.value} (round half-even, {precision_decimals} dp)"
    )
    derived = DerivedValue(
        value=computed,
        unit=target_unit,
        formula=formula,
        precision_decimals=precision_decimals,
        input_evidence=(evidence,),
    )
    return ConversionResult(derived=derived)
