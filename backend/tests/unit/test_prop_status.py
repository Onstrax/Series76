"""Property 3 (status half) and MetricValue example tests (Spec 2).

Pure-logic half of Property 3: every fact carries exactly one DataStatus;
documented-zero, N/A, and absent are pairwise distinguishable; NOT_DOCUMENTED
never collapses into NOT_APPLICABLE. The evidence/DB half of Property 3 is
exercised as an integration test against seeded PostgreSQL.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import DataStatus
from series76_domain.model.metric_value import MetricValue, MetricValueError
from series76_domain.model.units import Unit


def _metric_states() -> st.SearchStrategy[MetricValue]:
    zeros = st.just(MetricValue.available(Decimal(0), Unit.IN_LBS))
    positives = st.decimals(
        min_value=Decimal("0.001"), max_value=Decimal("100000"), places=3
    ).map(lambda d: MetricValue.available(d, Unit.IN_LBS))
    na = st.just(MetricValue.not_applicable(Unit.IN_LBS))
    absent = st.just(MetricValue.not_documented(Unit.IN_LBS))
    unverified = st.just(MetricValue.unverified(Unit.IN_LBS))
    return st.one_of(zeros, positives, na, absent, unverified)


# Feature: domain-and-tools, Property 3: every fact carries exactly one
# DataStatus; documented-zero, N/A, and absent are pairwise distinguishable and
# NOT_DOCUMENTED never collapses into NOT_APPLICABLE.
@given(metric=_metric_states())
def test_property_3_status_half(metric: MetricValue) -> None:
    # Exactly one DataStatus, and AVAILABLE iff a value is present.
    assert isinstance(metric.status, DataStatus)
    assert metric.is_available == (metric.value is not None)

    # Documented zero, N/A, and absent are pairwise distinguishable.
    zero = MetricValue.available(Decimal(0), Unit.IN_LBS)
    na = MetricValue.not_applicable(Unit.IN_LBS)
    absent = MetricValue.not_documented(Unit.IN_LBS)
    assert zero != na
    assert zero != absent
    assert na != absent
    assert zero.is_documented_zero and not na.is_documented_zero
    assert na.is_not_applicable and not absent.is_not_applicable
    assert absent.is_absent and not na.is_absent

    # NOT_DOCUMENTED never collapses into NOT_APPLICABLE.
    assert DataStatus.NOT_DOCUMENTED is not DataStatus.NOT_APPLICABLE
    if metric.is_absent:
        assert not metric.is_not_applicable


def test_available_requires_value() -> None:
    with pytest.raises(MetricValueError):
        MetricValue(None, DataStatus.AVAILABLE, Unit.IN_LBS)


def test_non_available_rejects_value() -> None:
    with pytest.raises(MetricValueError):
        MetricValue(Decimal(1), DataStatus.NOT_APPLICABLE, Unit.IN_LBS)


def test_float_is_rejected() -> None:
    with pytest.raises(MetricValueError):
        MetricValue.available(1.5)  # type: ignore[arg-type]
