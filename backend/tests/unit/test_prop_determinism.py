"""Properties 30, 31 — verified figure set traceability and determinism (Spec 2).

Pure-logic half: every :class:`Figure` traces to a source cell (direct) or
derivation-input cells (derived); an unsupported fact is an explicit no-number
state, never fabricated; building the same figures twice yields equal figure
sets. The withdrawn-edition half of determinism (Property 32) is an integration
test against seeded PostgreSQL.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from series76_domain.figures.contract import (
    Figure,
    build_figure_set,
    derived_figure,
    direct_figure,
    no_number,
)
from series76_domain.model.derived import DerivedValue
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit


@st.composite
def figures(draw: st.DrawFn) -> list[Figure]:
    out: list[Figure] = []
    for i in range(draw(st.integers(min_value=1, max_value=5))):
        kind = draw(st.sampled_from(["direct", "derived", "absent"]))
        evidence = EvidenceReference(cell_refs=(i + 1,))
        if kind == "direct":
            value = draw(st.integers(min_value=0, max_value=1000))
            metric = MetricValue.available(Decimal(value), Unit.IN_LBS)
            out.append(direct_figure(f"f{i}", metric, evidence))
        elif kind == "derived":
            value = draw(st.integers(min_value=0, max_value=1000))
            derived = DerivedValue(
                value=Decimal(value),
                unit=Unit.NM,
                formula="x * k",
                precision_decimals=4,
                input_evidence=(evidence,),
            )
            out.append(derived_figure(f"f{i}", derived))
        else:
            status = draw(
                st.sampled_from([DataStatus.NOT_APPLICABLE, DataStatus.NOT_DOCUMENTED])
            )
            out.append(no_number(f"f{i}", status, evidence))
    return out


# Feature: domain-and-tools, Property 30: every number traces to the catalog or
# a deterministic derivation; unsupported facts return an explicit no-number
# state and nothing is fabricated.
@given(figs=figures())
def test_property_30_traceability_no_fabrication(figs: list[Figure]) -> None:
    for figure in figs:
        if figure.has_number:
            # A present number is either direct (source cell) or derived
            # (derivation-input cells) — always with resolvable evidence.
            assert figure.evidence.is_resolvable
            assert figure.magnitude is not None
            if figure.is_derived:
                assert figure.derived is not None
                assert figure.derived.input_evidence
            else:
                assert figure.direct is not None
        else:
            # No supporting value -> explicit no-number state, not fabricated.
            assert figure.magnitude is None
            assert figure.status is not DataStatus.AVAILABLE


# Feature: domain-and-tools, Property 31: repeated identical queries return equal
# verified figures (exactly for direct, to attached precision for derived).
@given(figs=figures())
def test_property_31_repeated_queries_equal(figs: list[Figure]) -> None:
    first = build_figure_set(tuple(figs))
    second = build_figure_set(tuple(figs))
    assert first == second
    for a, b in zip(first.figures, second.figures, strict=True):
        assert a.magnitude == b.magnitude
        if a.is_derived and a.derived is not None and b.derived is not None:
            # Derived equality holds to the attached fixed precision.
            assert a.derived.precision_decimals == b.derived.precision_decimals
            assert a.magnitude == b.magnitude
