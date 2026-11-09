"""Spec 6 Properties 1-3: the golden oracle and documental verification (fixtures).

The comparator is validated with generated golden datasets; the real audited
dataset (Spec 1 manual PDF audit) is an [EXPERIMENT] not present yet.
"""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given
from hypothesis import strategies as st

from series76_eval.oracle import (
    ExpectedValue,
    GoldenCell,
    GoldenOracle,
    Provenance,
    ProvenanceError,
    dataset_digest,
)

values = st.one_of(
    st.integers(0, 9999).map(str),
    st.tuples(st.integers(0, 999), st.integers(0, 99)).map(lambda t: f"{t[0]}.{t[1]:02d}"),
)
cells = st.lists(
    st.builds(
        GoldenCell,
        table=st.sampled_from([f"T{i:02d}" for i in range(1, 8)]),
        row=st.integers(1, 68),
        column=st.sampled_from(["pn", "torque_inlbs", "torque_nm", "fla", "lra", "speed", "note"]),
        printed_value=values,
        unit=st.sampled_from(["", "in-lbs", "Nm", "A", "s", "Hz"]),
        not_applicable=st.booleans(),
        note=st.sampled_from(["", "*", "Note 1"]),
    ),
    min_size=1,
    max_size=40,
    unique_by=lambda c: c.key,
).map(tuple)


# Feature: evaluation-and-reproducibility, Property 1: Golden dataset is the sole oracle
@given(prov=st.sampled_from(list(Provenance)), value=values)
def test_property_1_golden_sole_oracle(prov: Provenance, value: str) -> None:
    digest = "a" * 64
    if prov is Provenance.GOLDEN_DATASET:
        assert ExpectedValue("T01:1:fla", value, prov, digest).value == value
    else:
        with pytest.raises(ProvenanceError):
            ExpectedValue("T01:1:fla", value, prov, digest)
    with pytest.raises(ProvenanceError):
        ExpectedValue("T01:1:fla", value, Provenance.GOLDEN_DATASET, "not-a-sha256")


# Feature: evaluation-and-reproducibility, Property 2: 100% cell-by-cell field coverage against the manifest
@given(golden=cells)
def test_property_2_full_coverage(golden: tuple[GoldenCell, ...]) -> None:
    published = tuple(dataclasses.replace(c) for c in golden)
    report = GoldenOracle().verify(published, golden, dataset_digest(golden))
    assert report.passed
    assert report.field_coverage == f"{len(golden)}/{len(golden)}"
    # A different manifest (e.g. another PDF edition) never verifies.
    assert not GoldenOracle().verify(published, golden, "0" * 64).passed


mutations = st.sampled_from(["value", "unit", "na", "note", "missing", "extra", "precision"])


# Feature: evaluation-and-reproducibility, Property 3: Any documental mismatch fails closed and preserves the oracle
@given(golden=cells, mutation=mutations, index=st.integers(0, 39))
def test_property_3_mismatch_fails_closed(
    golden: tuple[GoldenCell, ...], mutation: str, index: int
) -> None:
    before = dataset_digest(golden)
    target = golden[index % len(golden)]
    published = list(golden)
    i = published.index(target)
    if mutation == "value":
        published[i] = dataclasses.replace(target, printed_value=target.printed_value + "1")
    elif mutation == "precision":  # "12.50" vs "12.5": no normalization is applied
        published[i] = dataclasses.replace(target, printed_value=target.printed_value + "0")
    elif mutation == "unit":
        published[i] = dataclasses.replace(target, unit=target.unit + "x")
    elif mutation == "na":
        published[i] = dataclasses.replace(target, not_applicable=not target.not_applicable)
    elif mutation == "note":
        published[i] = dataclasses.replace(target, note=target.note + "!")
    elif mutation == "missing":
        published.pop(i)
    else:
        published.append(GoldenCell("T99", 1, "extra", "1"))
    report = GoldenOracle().verify(tuple(published), golden, before)
    assert not report.passed
    assert report.mismatches
    flagged = {m.cell for m in report.mismatches}
    assert (target.key in flagged) or (mutation == "extra" and "T99:1:extra" in flagged)
    for m in report.mismatches:
        assert m.expected and m.observed  # both contents reported
    assert dataset_digest(golden) == before  # the oracle is never modified
