"""Unit + property tests for the GoldenDatasetExporter (Task 14).

Covers Property 24 (one versioned artifact per edition with complete attributes),
Property 25 (bound to exactly one edition), Property 26 (round-trip equivalence),
and Property 14 re-exercised (N/A vs absence as two distinct explicit markers).
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from series76_data.golden.exporter import (
    ABSENT_MARKER,
    NA_MARKER,
    GoldenDatasetExporter,
    GoldenValue,
    golden_value_from_measured,
    printed_value_marker,
)
from series76_data.models.value_status import Measured, MetricValue


def _value(i: int) -> GoldenValue:
    return GoldenValue(
        printed_value=str(i),
        unit="Nm",
        row_ref=f"row:{i}",
        cell_ref=f"cell:{i}",
    )


# Feature: data-and-ingestion, Property 14 (re-exercised in the golden set):
# documented zero, N/A, and absence are three distinct explicit markers in the
# golden dataset — never collapsed to zero/empty.
def test_property_14_golden_markers_distinct() -> None:
    zero = printed_value_marker(Measured(MetricValue.available(0), "Nm"))
    na = printed_value_marker(Measured(MetricValue.not_applicable(), None))
    absent = printed_value_marker(Measured(MetricValue.not_documented(), None))
    assert zero == "0"
    assert na == NA_MARKER
    assert absent == ABSENT_MARKER
    assert len({zero, na, absent}) == 3


# Feature: data-and-ingestion, Property 24: One versioned golden artifact per
# edition with complete attributes. The version is monotonically increasing and
# unique within the edition, and all four attributes are non-null for every value.
@given(
    n_values=st.integers(min_value=1, max_value=10),
    existing=st.sets(st.integers(min_value=1, max_value=20), min_size=0, max_size=5),
)
def test_property_24_versioned_artifact_complete_attributes(
    n_values: int, existing: set[int]
) -> None:
    values = [_value(i) for i in range(n_values)]
    exporter = GoldenDatasetExporter()
    artifact = exporter.export(
        edition_id="ed-1",
        manifest_digest="dig-1",
        values=values,
        existing_versions=frozenset(existing),
    )
    # Monotonic + unique within the edition.
    if existing:
        assert artifact.version == max(existing) + 1
        assert artifact.version not in existing
    else:
        assert artifact.version == 1
    # Four non-null attributes for 100% of values.
    for v in artifact.values:
        assert v.printed_value and v.unit and v.row_ref and v.cell_ref


# Feature: data-and-ingestion, Property 25: Golden artifact is bound to exactly
# one edition — it records exactly one edition_id and that edition's digest.
@given(
    edition_id=st.text(min_size=1, max_size=12), digest=st.text(min_size=1, max_size=16)
)
def test_property_25_bound_to_exactly_one_edition(edition_id: str, digest: str) -> None:
    artifact = GoldenDatasetExporter().export(
        edition_id=edition_id, manifest_digest=digest, values=[_value(1)]
    )
    assert artifact.edition_id == edition_id
    assert artifact.manifest_digest == digest


# Feature: data-and-ingestion, Property 26: Golden-dataset round-trip equivalence
# under verified_replay. A reconstruction equal to the golden set is accepted;
# any difference is rejected with a mismatch report and leaves the artifact
# unchanged.
@given(
    n=st.integers(min_value=1, max_value=8),
    drop=st.booleans(),
    add_extra=st.booleans(),
)
def test_property_26_round_trip_equivalence(
    n: int, drop: bool, add_extra: bool
) -> None:
    values = [_value(i) for i in range(n)]
    exporter = GoldenDatasetExporter()
    artifact = exporter.export("ed", "dig", values)

    reconstructed = list(values)
    if drop and len(reconstructed) > 1:
        reconstructed.pop()
    if add_extra:
        reconstructed.append(_value(9999))

    report = exporter.verify_round_trip(artifact, reconstructed)
    expect_equivalent = not ((drop and len(values) > 1) or add_extra)
    assert report.equivalent is expect_equivalent
    if not report.equivalent:
        assert report.missing_from_reconstruction or report.unexpected_in_reconstruction
    # The artifact is never altered by a round-trip check.
    assert artifact.values == tuple(values)


def test_golden_value_from_measured_fills_markers() -> None:
    gv = golden_value_from_measured(
        Measured(MetricValue.available(Decimal("1.5")), "Nm"), "row:1", "cell:1"
    )
    assert gv.printed_value == "1.5"
    assert gv.unit == "Nm"
    na = golden_value_from_measured(
        Measured(MetricValue.not_applicable(), None), "row:2", "cell:2"
    )
    assert na.printed_value == NA_MARKER
    assert na.unit  # non-null NO_UNIT_MARKER
