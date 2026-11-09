"""Properties 4, 5, 10 (get_part slice) — exact lookup over seeded PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from series76_domain.model.enums import DataStatus, SemanticFailureCode
from series76_domain.operations.get_part import get_part
from series76_domain.repository.pg_adapter import PostgresTypedRepository

from .seed import SeededCatalog

pytestmark = pytest.mark.integration

SeededFixture = tuple[SeededCatalog, Callable[[], Session], Engine]

_MALFORMED = st.sampled_from(["", "  ", "bad pn!!", "DROP TABLE", "a b c", "x'--"])


# Feature: domain-and-tools, Property 4: get_part never silently substitutes and
# classifies absence precisely (INVALID_PN / PART_NOT_LISTED / PART_FOUND).
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(choice=st.sampled_from(["present", "absent", "malformed"]), malformed=_MALFORMED)
def test_property_4_classification(
    seeded_catalog: SeededFixture, choice: str, malformed: str
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        if choice == "present":
            result = get_part(repo, seeded.dual_unit_pn)
            assert result.is_found
            assert result.failure is None
        elif choice == "absent":
            result = get_part(repo, seeded.unlisted_pn)
            assert result.failure is SemanticFailureCode.PART_NOT_LISTED
            # No substitution: no view, no suggested PN.
            assert result.view is None
        else:
            result = get_part(repo, malformed)
            assert result.failure is SemanticFailureCode.INVALID_PN
            assert result.view is None


# Feature: domain-and-tools, Property 5: explicit service/frequency facts are the
# bound facts and labeled; multiple applicable measurements all returned labeled
# with none silently selected.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(frequency=st.sampled_from([None, Decimal(50), Decimal(60)]))
def test_property_5_labeled_measurements(
    seeded_catalog: SeededFixture, frequency: Decimal | None
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        result = get_part(repo, seeded.multi_freq_pn, frequency_hz=frequency)
        assert result.is_found
        assert result.view is not None
        measurements = result.view.measurements
        if frequency is None:
            # No frequency given: BOTH 50 Hz and 60 Hz returned, none selected.
            freqs = {
                m.frequency_hz.value for m in measurements if m.frequency_hz.value is not None
            }
            assert freqs == {Decimal(50), Decimal(60)}
        else:
            # Explicit frequency: only measurements bound to that condition.
            for m in measurements:
                assert m.frequency_hz.value == frequency


# Feature: domain-and-tools, Property 10 (get_part slice): N/A and absent fields
# are never coerced to zero and stay distinguishable in results.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_n=st.integers(min_value=0, max_value=3))
def test_property_10_get_part_na_absent_distinct(
    seeded_catalog: SeededFixture, _n: int
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        result = get_part(repo, seeded.absent_pn)
        assert result.is_found
        assert result.view is not None
        # The absent part has a Modulating service: torque_inlbs is N/A and
        # torque_nm is absent (NOT_DOCUMENTED) — distinct, neither is zero.
        services = result.view.service_performance
        assert services
        sp = services[0]
        assert sp.torque_inlbs.status is DataStatus.NOT_APPLICABLE
        assert sp.torque_nm.status is DataStatus.NOT_DOCUMENTED
        assert sp.torque_inlbs.value is None
        assert sp.torque_nm.value is None
        # Distinguishable: N/A != absent.
        assert sp.torque_inlbs.status is not sp.torque_nm.status
