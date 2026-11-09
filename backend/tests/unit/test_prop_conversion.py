"""Properties 22, 23 — deterministic unit conversion (Spec 2)."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.derived import DerivedValue
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit
from series76_domain.services.convert_units import convert_units

_EVIDENCE = EvidenceReference(cell_refs=(1,))


# Feature: domain-and-tools, Property 22: unit conversion is a labeled derivation
# that never overwrites an official figure; no DerivedValue is substituted for an
# official value.
@given(magnitude=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("9999"), places=2))
def test_property_22_labeled_derivation_preserves_official(magnitude: Decimal) -> None:
    # Dual-unit official figures (both documented independently).
    official_inlbs = MetricValue.available(magnitude, Unit.IN_LBS)
    official_nm = MetricValue.available(magnitude * 2, Unit.NM)  # arbitrary, independent

    result = convert_units(official_inlbs, Unit.NM, evidence=_EVIDENCE)
    assert result.ok
    derived = result.derived
    assert isinstance(derived, DerivedValue)
    assert derived.is_derived
    assert derived.unit is Unit.NM
    assert derived.formula  # labeled with a formula
    assert derived.precision_decimals >= 0

    # The derived value is a distinct type, never an official MetricValue.
    assert not isinstance(derived, MetricValue)

    # Both official figures are untouched by converting one of them.
    assert official_inlbs.value == magnitude
    assert official_nm.value == magnitude * 2
    assert official_inlbs.unit is Unit.IN_LBS
    assert official_nm.unit is Unit.NM


# Feature: domain-and-tools, Property 23: invalid conversions error without
# altering the source.
@given(magnitude=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("9999"), places=2))
def test_property_23_invalid_conversion_leaves_source(magnitude: Decimal) -> None:
    # Incompatible unit pair (torque -> current): explicit error, no value.
    source = MetricValue.available(magnitude, Unit.IN_LBS)
    result = convert_units(source, Unit.AMPERE, evidence=_EVIDENCE)
    assert not result.ok
    assert result.derived is None
    assert result.error is not None
    assert result.error.source is source  # source unchanged (same object)
    assert result.error.source.value == magnitude

    # Missing/non-numeric source magnitude (N/A): explicit error, no value.
    na = MetricValue.not_applicable(Unit.IN_LBS)
    na_result = convert_units(na, Unit.NM, evidence=_EVIDENCE)
    assert not na_result.ok
    assert na_result.derived is None
    assert na_result.error is not None
    assert na_result.error.source is na
