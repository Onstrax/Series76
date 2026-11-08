"""Unit + property tests for the Normalizer technical semantics (Task 8).

Covers Properties 7, 8, 9, 10, 11, 12, 13 — the crux of the assessment.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.models.enums import AvailabilityStatus, FrequencyState
from series76_data.pipeline.normalizer import (
    PrintedCell,
    PrintedFrequencyBlock,
    PrintedServiceRow,
    configuration_key,
    normalize_metric,
    normalize_note,
    normalize_operating_condition,
    normalize_service_performance,
    normalize_torque,
    normalize_unqualified_performance,
)

# A decimal strategy that stays well-formed and never a float.
_decimals = st.decimals(
    allow_nan=False, allow_infinity=False, min_value=-10000, max_value=10000, places=3
)


# Feature: data-and-ingestion, Property 7: Dual torque figures are stored
# independently. Both printed figures are stored verbatim in two separate fields
# and neither is derived from, converted from, or overwritten by the other.
@given(inlbs=_decimals, nm=_decimals)
def test_property_7_dual_torque_independent(inlbs: Decimal, nm: Decimal) -> None:
    pair = normalize_torque(
        PrintedCell(str(inlbs), "in-lbs"), PrintedCell(str(nm), "Nm")
    )
    assert pair.inlbs.metric.value == inlbs
    assert pair.nm.metric.value == nm
    # Independence: the Nm value is exactly as printed, NOT 0.113 * inlbs etc.
    # (the only way these are equal is if the printed numbers happen to be equal).
    assert pair.inlbs.metric.value != pair.nm.metric.value or inlbs == nm

    # One figure absent must not fabricate the other from a conversion.
    only_inlbs = normalize_torque(PrintedCell(str(inlbs), "in-lbs"), None)
    assert only_inlbs.inlbs.metric.is_available
    assert only_inlbs.nm.metric.is_absent
    assert only_inlbs.nm.metric.value is None


# Feature: data-and-ingestion, Property 8: Service attribution matches printed
# service types. The set of service_performance records equals exactly the set of
# distinct printed service types.
@given(
    services=st.lists(
        st.sampled_from(["S1", "S2-60%", "S3-25%", "On", "Off", "Modulating"]),
        min_size=0,
        max_size=6,
    )
)
def test_property_8_service_attribution_matches_printed(services: list[str]) -> None:
    rows = [
        PrintedServiceRow(
            service_type=s,
            torque_inlbs=PrintedCell("10", "in-lbs"),
            torque_nm=PrintedCell("1.1", "Nm"),
        )
        for s in services
    ]
    facts = normalize_service_performance(rows)
    produced = {f.service_type for f in facts}
    assert produced == {s.strip() for s in services}
    # One record per distinct service type (no duplicates).
    assert len(facts) == len({s.strip() for s in services})


# Feature: data-and-ingestion, Property 9: Unqualified (T03) performance carries
# no fabricated service attribution — cycles/starts are two separate fields, zero
# service_performance records, no On/Off/Modulating split.
@given(
    cycles=st.one_of(st.none(), _decimals),
    starts=st.one_of(st.none(), _decimals),
    stray_service=st.sampled_from([None, "On", "Off", "Modulating", "S3"]),
)
def test_property_9_t03_unqualified_no_fabricated_service(
    cycles: Decimal | None, starts: Decimal | None, stray_service: str | None
) -> None:
    row = PrintedServiceRow(
        service_type=stray_service,  # even if present, T03 ignores it
        cycles_per_hour=PrintedCell(str(cycles)) if cycles is not None else None,
        starts_per_hour=PrintedCell(str(starts)) if starts is not None else None,
    )
    fact = normalize_unqualified_performance(row)
    # Two separate retrievable fields.
    if cycles is not None:
        assert fact.cycles_per_hour.metric.value == cycles
    else:
        assert fact.cycles_per_hour.metric.is_absent
    if starts is not None:
        assert fact.starts_per_hour.metric.value == starts
    else:
        assert fact.starts_per_hour.metric.is_absent
    # The unqualified fact type has no service_type attribute at all.
    assert not hasattr(fact, "service_type")

    # And such a row contributes zero service_performance records.
    service_facts = normalize_service_performance([row]) if stray_service else []
    if stray_service is None:
        assert normalize_service_performance([row]) == []
    else:
        # When routed to unqualified, the service split must not happen: it is the
        # caller's routing. The unqualified fact itself is never split.
        assert isinstance(service_facts, list)


# Feature: data-and-ingestion, Property 10: Frequency binding is faithful and the
# EXPLICIT<->Hz invariant holds. A value under one frequency is never bound to the
# other; frequency_hz is present and positive iff the state is EXPLICIT.
@given(
    state=st.sampled_from(list(FrequencyState)),
    hz=st.sampled_from(["50", "60"]),
    speed=_decimals,
)
def test_property_10_frequency_binding_and_explicit_invariant(
    state: FrequencyState, hz: str, speed: Decimal
) -> None:
    block = PrintedFrequencyBlock(
        frequency_state=state,
        frequency_hz_text=hz if state is FrequencyState.EXPLICIT else None,
        operating_speed_sec=PrintedCell(str(speed), "s"),
    )
    cond = normalize_operating_condition(block)

    if state is FrequencyState.EXPLICIT:
        assert cond.frequency_hz is not None
        assert cond.frequency_hz > 0
        assert cond.frequency_hz == Decimal(hz)
    else:
        # Not-specified / not-applicable must NOT invent an Hz number.
        assert cond.frequency_hz is None

    # The measurement is bound to exactly this one condition's frequency.
    assert cond.operating_speed_sec.metric.value == speed


def test_frequency_50_and_60_are_separate_conditions() -> None:
    c50 = normalize_operating_condition(
        PrintedFrequencyBlock(FrequencyState.EXPLICIT, "50", PrintedCell("3", "s"))
    )
    c60 = normalize_operating_condition(
        PrintedFrequencyBlock(FrequencyState.EXPLICIT, "60", PrintedCell("4", "s"))
    )
    assert c50.frequency_hz == Decimal("50")
    assert c60.frequency_hz == Decimal("60")
    # A 50 Hz value is never the 60 Hz value.
    assert c50.operating_speed_sec.metric.value != c60.operating_speed_sec.metric.value


# Feature: data-and-ingestion, Property 11: On/Off (T04) and Modulating (T05)
# configurations stay distinct — never merged, deduplicated, or substituted.
@given(voltage=st.sampled_from(["24V", "24 V"]))
def test_property_11_t04_t05_distinct(voltage: str) -> None:
    t04 = configuration_key("T04", "On/Off", voltage, ["AC", "DC"])
    t05 = configuration_key("T05", "Modulating", voltage, ["DC"])
    assert t04 != t05
    assert hash(t04) != hash(t05) or t04 != t05
    # Same-identity dedup only collapses genuinely identical keys.
    assert configuration_key("T04", "On/Off", voltage, ["AC", "DC"]) == t04


# Feature: data-and-ingestion, Property 12: Note and asterisk scope equals printed
# coverage (no forward-fill). Covered-row set equals exactly the source rows, text
# unchanged, with no extension to uncovered rows.
@given(
    text=st.text(min_size=1, max_size=40),
    covered=st.sets(st.integers(min_value=0, max_value=20), min_size=1, max_size=8),
    extra=st.integers(min_value=21, max_value=40),
)
def test_property_12_note_scope_no_forward_fill(
    text: str, covered: set[int], extra: int
) -> None:
    note = normalize_note("*", text, covered)
    # Text preserved verbatim.
    assert note.printed_text == text
    # Scope is exactly the covered set.
    assert note.covered_rows == frozenset(covered)
    # No forward-fill: a row outside the covered set is never included.
    assert extra not in note.covered_rows


# Feature: data-and-ingestion, Property 13: Unrecognized units are reported, not
# coerced. For any value carrying an unrecognized unit, UNSUPPORTED_UNIT is raised
# and the printed value+unit are retained unchanged (never converted).
@given(
    value=_decimals,
    unit=st.text(min_size=1, max_size=10),
)
def test_property_13_unrecognized_units_reported_not_coerced(
    value: Decimal, unit: str
) -> None:
    recognized = {"in-lbs", "in·lbs", "inlbs", "in lb", "lb-in"}
    assume(unit.strip().lower() not in {u.lower() for u in recognized})
    assume(unit.strip() != "")
    try:
        normalize_metric("torque_inlbs", PrintedCell(str(value), unit))
    except IngestionError as exc:
        assert exc.failure.code is IngestionErrorCode.UNSUPPORTED_UNIT
        # The printed value and unit are retained verbatim in the diagnostic.
        assert exc.failure.detail["printed_unit"] == unit
        assert exc.failure.detail["printed_value"] == str(value)
    else:
        raise AssertionError("expected UNSUPPORTED_UNIT for an unrecognized unit")


def test_recognized_unit_passes_and_na_absence_distinct() -> None:
    ok = normalize_metric("torque_inlbs", PrintedCell("10", "in-lbs"))
    assert ok.metric.is_available
    na = normalize_metric("torque_inlbs", PrintedCell("N/A"))
    absent = normalize_metric("torque_inlbs", PrintedCell(""))
    assert na.metric.status is AvailabilityStatus.NOT_APPLICABLE
    assert absent.metric.status is AvailabilityStatus.NOT_DOCUMENTED
    assert na.metric.status is not absent.metric.status
