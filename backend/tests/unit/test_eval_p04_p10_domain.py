"""Spec 6 Properties 4-10: the domain property matrix (Test_Level 2).

Imports only the Spec 2 pure domain (no FastAPI, no DB driver, no LLM client).
"""

from __future__ import annotations

import random
import subprocess
import sys
import uuid
from decimal import Decimal

from _builders import build_part
from _fakes import FakeRepository, make_edition
from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import DataStatus, SemanticFailureCode
from series76_domain.model.evaluation import FieldValue, evaluate
from series76_domain.model.filter_ast import AllowlistField, And, Operator, Predicate
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit
from series76_domain.operations.get_part import get_part
from series76_domain.operations.search_parts import search_parts
from series76_domain.services.compare_parts import (
    ComparableMetric,
    PartComparisonInput,
    compare_parts,
)
from series76_domain.services.convert_units import convert_units
from series76_domain.services.rank_candidates import (
    RankCandidate,
    RankPriority,
    SortDirection,
    rank_candidates,
)

NUMERIC = [AllowlistField.TORQUE_INLBS, AllowlistField.FLA, AllowlistField.OPERATING_SPEED]
OPS = [Operator.LT, Operator.LE, Operator.GT, Operator.GE, Operator.EQ]

metric = st.one_of(
    st.integers(0, 500).map(lambda v: MetricValue.available(v)),
    st.just(MetricValue.not_applicable()),
    st.just(MetricValue.not_documented()),
)
candidate = st.fixed_dictionaries({f: metric for f in NUMERIC}).map(
    lambda d: {f: (FieldValue(status=m.status, metric=m),) for f, m in d.items()}
)
predicate = st.builds(
    lambda f, op, v: Predicate(f, op, Decimal(v)),
    st.sampled_from(NUMERIC),
    st.sampled_from(OPS),
    st.integers(0, 500),
)


def test_level_2_imports_no_api_db_driver_or_llm() -> None:
    code = (
        "import sys, series76_domain.model.evaluation, series76_domain.services, "
        "series76_domain.operations.search_parts\n"
        "bad={m.split('.')[0] for m in sys.modules} & "
        "{'fastapi','psycopg','asyncpg','openai','langchain','langchain_core','langgraph'}\n"
        "print(sorted(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


# Feature: evaluation-and-reproducibility, Property 4: AND-constraint monotonicity
@given(cands=st.lists(candidate, min_size=1, max_size=12), base=predicate, extra=predicate)
def test_property_4_and_monotonicity(cands, base, extra) -> None:  # type: ignore[no-untyped-def]
    before = [c for c in cands if evaluate(base, c)]
    after = [c for c in cands if evaluate(And(children=(base, extra)), c)]
    assert len(after) <= len(before)
    assert all(c in before for c in after)


# Feature: evaluation-and-reproducibility, Property 5: N/A never satisfies a numeric predicate
@given(
    pred=predicate, status=st.sampled_from([DataStatus.NOT_APPLICABLE, DataStatus.NOT_DOCUMENTED])
)
def test_property_5_na_never_satisfies(pred: Predicate, status: DataStatus) -> None:
    m = MetricValue(None, status, None)
    fields = {pred.field: (FieldValue(status=status, metric=m),)}
    assert not evaluate(pred, fields)


# Feature: evaluation-and-reproducibility, Property 6: Reordered AND operands yield an equal set
@given(
    cands=st.lists(candidate, min_size=1, max_size=12),
    preds=st.lists(predicate, min_size=2, max_size=4),
    seed=st.integers(0, 10_000),
)
def test_property_6_and_reorder(cands, preds, seed) -> None:  # type: ignore[no-untyped-def]
    shuffled = list(preds)
    random.Random(seed).shuffle(shuffled)
    a = [i for i, c in enumerate(cands) if evaluate(And(children=tuple(preds)), c)]
    b = [i for i, c in enumerate(cands) if evaluate(And(children=tuple(shuffled)), c)]
    assert a == b


# Feature: evaluation-and-reproducibility, Property 7: Inverse conversion round-trips derived values only
@given(v=st.integers(1, 5000), decimals=st.integers(4, 6))
def test_property_7_inverse_conversion_derived_only(v: int, decimals: int) -> None:
    official = MetricValue.available(v, Unit.IN_LBS)
    ev = __import__(
        "series76_domain.model.evidence", fromlist=["EvidenceReference"]
    ).EvidenceReference
    forward = convert_units(official, Unit.NM, evidence=ev.of_cells(1), precision_decimals=decimals)
    assert forward.derived is not None and forward.derived.is_derived
    back = convert_units(
        MetricValue.available(forward.derived.value, Unit.NM),
        Unit.IN_LBS,
        evidence=ev.of_cells(1),
        precision_decimals=decimals,
    )
    assert back.derived is not None
    tolerance = Decimal(1).scaleb(-decimals) * Decimal(10)  # recorded for this conversion
    assert abs(back.derived.value - official.value) <= tolerance  # type: ignore[operator]
    # The official value is never replaced by the converted one.
    assert official == MetricValue.available(v, Unit.IN_LBS)
    assert type(forward.derived) is not MetricValue


# Feature: evaluation-and-reproducibility, Property 8: Lexicographic ranking is stable
@given(
    values=st.lists(st.one_of(st.none(), st.integers(0, 50)), min_size=1, max_size=10),
    seed=st.integers(0, 10_000),
    direction=st.sampled_from(list(SortDirection)),
)
def test_property_8_ranking_stable(values, seed, direction) -> None:  # type: ignore[no-untyped-def]
    cands = [
        RankCandidate(
            f"PN-{i:02d}",
            {"t": MetricValue.available(v) if v is not None else MetricValue.not_applicable()},
            frozenset({"t"}),
        )
        for i, v in enumerate(values)
    ]
    prio = (RankPriority("t", direction),)
    first = [c.base_pn for c in rank_candidates(tuple(cands), prio).ranked]
    again = [c.base_pn for c in rank_candidates(tuple(cands), prio).ranked]
    shuffled = list(cands)
    random.Random(seed).shuffle(shuffled)
    other = [c.base_pn for c in rank_candidates(tuple(shuffled), prio).ranked]
    assert first == again == other


ctx = st.tuples(
    st.sampled_from(["On/Off", "Modulating"]),
    st.sampled_from([None, Decimal(50), Decimal(60)]),
    st.sampled_from(["24 V AC/DC", "120 V AC"]),
    st.sampled_from([Unit.IN_LBS, Unit.NM]),
)


# Feature: evaluation-and-reproducibility, Property 9: Comparison declares a winner only under compatible conditions
@given(a=ctx, b=ctx, va=st.integers(1, 300), vb=st.integers(1, 300))
def test_property_9_winner_only_compatible(a, b, va, vb) -> None:  # type: ignore[no-untyped-def]
    edition = uuid.uuid4()

    def part(pn: str, c: tuple, v: int) -> PartComparisonInput:  # type: ignore[type-arg]
        return PartComparisonInput(
            pn,
            edition,
            (
                ComparableMetric(
                    pn,
                    "torque",
                    MetricValue.available(v, c[3]),
                    c[3],
                    service_context=c[0],
                    frequency_context=c[1],
                    supply_context=c[2],
                ),
            ),
        )

    result = compare_parts((part("PN-A", a, va), part("PN-B", b, vb)))
    for pair in result.pairs:
        if pair.has_winner:
            assert pair.left.context_matches(pair.right)
        if a != b:
            assert not pair.has_winner


# Feature: evaluation-and-reproducibility, Property 10: Edition withdrawal blocks new recommendations and preserves history
@given(
    torques=st.lists(st.integers(10, 300), min_size=1, max_size=5), threshold=st.integers(0, 300)
)
def test_property_10_withdrawal(torques: list[int], threshold: int) -> None:
    live = make_edition()
    withdrawn = make_edition(withdrawn=True)
    snapshots = []
    for edition in (live, withdrawn):
        repo = FakeRepository(pinned=edition)
        for i, t in enumerate(torques):
            repo.add(build_part(f"PN-{i}", edition.edition_id, torque_inlbs=t))
        node = Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(threshold))
        rec = search_parts(repo, node, allow_withdrawn=False)
        if edition.is_withdrawn:
            assert rec.failure is SemanticFailureCode.SOURCE_WITHDRAWN  # no new recommendation
            assert rec.total_matches == 0 and rec.page == ()
        # Pinned historical reads of the same edition remain retrievable, unchanged.
        view = get_part(repo, "PN-0").view
        assert view is not None
        snapshots.append([sp.torque_inlbs for sp in view.service_performance])
    assert snapshots[0] == snapshots[1]
