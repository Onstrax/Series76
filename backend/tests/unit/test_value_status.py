"""Unit + property tests for the (value, status) metric-pair encoding (Spec 1)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from series76_data.models import AvailabilityStatus, MetricValue
from series76_data.models.value_status import ValueStatusError


def test_documented_zero_is_available_not_absence() -> None:
    zero = MetricValue.available(0)
    assert zero.is_available
    assert zero.is_documented_zero
    assert not zero.is_not_applicable
    assert not zero.is_absent


def test_na_absence_zero_are_pairwise_distinct() -> None:
    zero = MetricValue.available(0)
    na = MetricValue.not_applicable()
    absent = MetricValue.not_documented()
    states = {zero.status, na.status, absent.status}
    assert len(states) == 3  # three distinguishable states


def test_available_requires_value() -> None:
    with pytest.raises(ValueStatusError):
        MetricValue(None, AvailabilityStatus.AVAILABLE)


def test_non_available_forbids_value() -> None:
    with pytest.raises(ValueStatusError):
        MetricValue(Decimal("1"), AvailabilityStatus.NOT_APPLICABLE)


def test_float_input_rejected_to_avoid_rounding() -> None:
    with pytest.raises(ValueStatusError):
        MetricValue.available(1.23)  # type: ignore[arg-type]


# Property 14: Zero, N/A, and absence are three distinguishable states.
# Feature: data-and-ingestion, Property 14: a documented numeric zero, a
# not-applicable state, and an absence state are pairwise distinguishable and
# distinct absence reasons are never collapsed into one undifferentiated null.
@given(
    numeric=st.decimals(allow_nan=False, allow_infinity=False, places=3).map(
        lambda d: d if d != 0 else Decimal("0")
    )
)
def test_property_14_three_distinguishable_states(numeric: Decimal) -> None:
    documented = MetricValue(numeric, AvailabilityStatus.AVAILABLE)
    na = MetricValue.not_applicable()
    absent = MetricValue.not_documented()

    # Availability partitions documented values from both absence reasons.
    assert documented.is_available
    assert not na.is_available
    assert not absent.is_available

    # The two absence reasons are never the same status.
    assert na.status is not absent.status

    # A documented zero is distinguishable from N/A and absence.
    zero = MetricValue.available(0)
    assert zero.is_documented_zero
    assert not na.is_documented_zero
    assert not absent.is_documented_zero
