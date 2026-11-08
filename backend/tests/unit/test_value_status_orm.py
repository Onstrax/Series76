"""Property test: dual torque is stored as two independent values (Task 4.2).

Operates at the ORM-model level (no database): a ``ServicePerformance`` instance
carries ``torque_inlbs_*`` and ``torque_nm_*`` as two independent
``(value, status)`` column pairs. Setting one pair never changes the other, and
neither value is a conversion of the other (no in-lbs↔Nm derivation).

Requirements: 4.1
Properties: 7
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from series76_data.models.enums import AvailabilityStatus
from series76_data.models.orm import ServicePerformance

_IN_LBS_TO_NM = Decimal("0.112984829")  # a plausible unit conversion factor


def _decimals() -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("100000"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    )


# Feature: data-and-ingestion, Property 7: Dual torque figures are stored
# independently — both in-lbs and Nm are kept verbatim in two separate fields,
# and neither is overwritten, rounded, or replaced by a value derived from
# converting the other.
@settings(max_examples=100, deadline=None)
@given(inlbs=_decimals(), nm=_decimals())
def test_property_7_dual_torque_independent(inlbs: Decimal, nm: Decimal) -> None:
    perf = ServicePerformance(
        torque_inlbs_value=inlbs,
        torque_inlbs_status=AvailabilityStatus.AVAILABLE,
        torque_nm_value=nm,
        torque_nm_status=AvailabilityStatus.AVAILABLE,
    )

    # Both figures are stored verbatim — neither is coerced into the other.
    assert perf.torque_inlbs_value == inlbs
    assert perf.torque_nm_value == nm

    # Mutating one pair leaves the other untouched (independence).
    new_inlbs = inlbs + Decimal("1")
    perf.torque_inlbs_value = new_inlbs
    assert perf.torque_inlbs_value == new_inlbs
    assert perf.torque_nm_value == nm  # unchanged

    new_nm = nm + Decimal("2")
    perf.torque_nm_value = new_nm
    assert perf.torque_nm_value == new_nm
    assert perf.torque_inlbs_value == new_inlbs  # unchanged

    # Neither value is a conversion of the other: the model performs no
    # derivation, so nm is not inlbs * factor unless the random inputs happen to
    # coincide (which the exact-Decimal conversion makes effectively impossible).
    assert perf.torque_nm_value != perf.torque_inlbs_value * _IN_LBS_TO_NM


def test_dual_torque_status_independent() -> None:
    """One torque may be AVAILABLE while the other is NOT_APPLICABLE."""

    perf = ServicePerformance(
        torque_inlbs_value=Decimal("125"),
        torque_inlbs_status=AvailabilityStatus.AVAILABLE,
        torque_nm_value=None,
        torque_nm_status=AvailabilityStatus.NOT_APPLICABLE,
    )
    assert perf.torque_inlbs_status is AvailabilityStatus.AVAILABLE
    assert perf.torque_nm_status is AvailabilityStatus.NOT_APPLICABLE
    assert perf.torque_inlbs_value == Decimal("125")
    assert perf.torque_nm_value is None
