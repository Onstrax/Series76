"""Properties 15, 16, 17, 18 — deterministic ranking (Spec 2)."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit
from series76_domain.services.rank_candidates import (
    RankCandidate,
    RankPriority,
    SortDirection,
    rank_candidates,
    rank_top_one,
)

_KEY = "torque_inlbs"


def _candidates(
    draw: st.DrawFn, *, comparable_only: bool = True
) -> tuple[RankCandidate, ...]:
    n = draw(st.integers(min_value=1, max_value=6))
    cands = []
    for i in range(n):
        base = f"PN{draw(st.integers(min_value=0, max_value=20)):02d}-{i}"
        value = draw(st.integers(min_value=0, max_value=10))
        metric = MetricValue.available(Decimal(value), Unit.IN_LBS)
        keys = frozenset({_KEY}) if comparable_only else frozenset()
        cands.append(RankCandidate(base_pn=base, metrics={_KEY: metric}, comparable_keys=keys))
    return tuple(cands)


@st.composite
def comparable_candidates(draw: st.DrawFn) -> tuple[RankCandidate, ...]:
    return _candidates(draw, comparable_only=True)


# Feature: domain-and-tools, Property 15: ranking is lexicographic, reproducible,
# with a Base-PN ascending tiebreak.
@given(candidates=comparable_candidates(), direction=st.sampled_from(list(SortDirection)))
def test_property_15_lexicographic_reproducible(
    candidates: tuple[RankCandidate, ...], direction: SortDirection
) -> None:
    priorities = (RankPriority(_KEY, direction),)
    first = rank_candidates(candidates, priorities)
    second = rank_candidates(candidates, priorities)
    # Reproducible: identical ordering on repeat.
    assert [c.base_pn for c in first.ranked] == [c.base_pn for c in second.ranked]

    # Lexicographic by the metric, then Base-PN ascending tiebreak.
    for a, b in zip(first.ranked, first.ranked[1:], strict=False):
        va = a.metrics[_KEY].value
        vb = b.metrics[_KEY].value
        assert va is not None and vb is not None
        if direction is SortDirection.ASC:
            ordered = va < vb or (va == vb and a.base_pn <= b.base_pn)
        else:
            ordered = va > vb or (va == vb and a.base_pn <= b.base_pn)
        assert ordered


# Feature: domain-and-tools, Property 16: no ranking by a non-comparable metric;
# affected candidates are returned in a distinct indeterminate group.
@given(data=st.data())
def test_property_16_non_comparable_indeterminate(data: st.DataObject) -> None:
    comparable = data.draw(comparable_candidates())
    # Non-comparable candidates lack the priority key in comparable_keys.
    non_comp = tuple(
        RankCandidate(
            base_pn=f"NC{i}",
            metrics={_KEY: MetricValue.available(Decimal(i), Unit.IN_LBS)},
            comparable_keys=frozenset(),
        )
        for i in range(data.draw(st.integers(min_value=1, max_value=3)))
    )
    result = rank_candidates(comparable + non_comp, (RankPriority(_KEY, SortDirection.ASC),))
    ranked_pns = {c.base_pn for c in result.ranked}
    indeterminate_pns = {c.base_pn for c in result.indeterminate}
    for nc in non_comp:
        assert nc.base_pn in indeterminate_pns
        assert nc.base_pn not in ranked_pns
    # The two groups are disjoint.
    assert ranked_pns.isdisjoint(indeterminate_pns)


# Feature: domain-and-tools, Property 17: top-1 equals the head of the full
# ranking and returns only the winner and the eligible count.
@given(candidates=comparable_candidates(), direction=st.sampled_from(list(SortDirection)))
def test_property_17_top_one(
    candidates: tuple[RankCandidate, ...], direction: SortDirection
) -> None:
    priorities = (RankPriority(_KEY, direction),)
    full = rank_candidates(candidates, priorities)
    top = rank_top_one(candidates, priorities)
    assert top.winner == full.winner
    assert top.eligible_count == full.eligible_count
    # Top-1 carries only the winner + count — no nominal list of other PNs.
    assert not hasattr(top, "ranked")


# Feature: domain-and-tools, Property 18: ranking ignores a model sort_hint and
# requires a confirmed priority; empty/no-priority leaves input unmodified.
@given(candidates=comparable_candidates(), hint=st.text(max_size=10))
def test_property_18_sort_hint_ignored_and_precondition(
    candidates: tuple[RankCandidate, ...], hint: str
) -> None:
    priorities = (RankPriority(_KEY, SortDirection.ASC),)
    with_hint = rank_candidates(candidates, priorities, sort_hint=hint)
    without_hint = rank_candidates(candidates, priorities)
    assert [c.base_pn for c in with_hint.ranked] == [
        c.base_pn for c in without_hint.ranked
    ]

    # No confirmed priority -> precondition unmet, no ranking, input unmodified.
    snapshot = tuple(candidates)
    empty_priority = rank_candidates(candidates, ())
    assert empty_priority.precondition_unmet
    assert not empty_priority.ranked
    assert candidates == snapshot

    # Empty eligible set -> precondition unmet.
    empty_set = rank_candidates((), priorities)
    assert empty_set.precondition_unmet
