"""Spec 4 Properties 22-25: the deterministic Recommendation coordinator."""

from __future__ import annotations

import uuid
from decimal import Decimal

from _agent_fakes import make_part
from _fakes import FakeRepository
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.composer import ResponseComposer, edition_label
from series76_agent.domain.enums import Intent, Language, RecommendationGrade, Strength
from series76_agent.domain.figures import VerifiedFigureSet
from series76_agent.domain.plan import Criterion, DraftPlan
from series76_agent.i18n import GROUP_LABELS
from series76_agent.policy import FIELD_GROUP, PolicyEngine, SessionContext
from series76_agent.recommendation import (
    ALL_GROUPS,
    WARRANTY_PHRASES,
    RecommendationCoordinator,
    RecommendationInput,
)
from series76_data.models.enums import SupplyMode
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, And, Operator, Predicate
from series76_domain.operations.get_part import get_part
from series76_domain.repository.port import PinnedEdition
from series76_domain.services.rank_candidates import (
    RankCandidate,
    RankPriority,
    SortDirection,
    rank_candidates,
    rank_top_one,
)

statuses = st.sampled_from(list(CoverageStatus))
TORQUE_DESC = RankPriority("torque_inlbs", SortDirection.DESC)


def _criteria(sts: tuple[CoverageStatus, ...]) -> tuple[Criterion, ...]:
    return tuple(Criterion("c", s, Strength.HARD, g) for s, g in zip(sts, ALL_GROUPS, strict=True))


def _figset(parts: list[tuple[str, int | None, int]]) -> tuple[VerifiedFigureSet, list[str]]:
    """Parts as (pn, torque_inlbs | None (N/A), voltage)."""

    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True)
    repo = FakeRepository(pinned=edition)
    for pn, torque, volts in parts:
        repo.add(
            make_part(
                pn,
                edition.edition_id,
                services={"On/Off": (torque, None)},
                voltage=volts,
                modes=frozenset({SupplyMode.AC}),
            )
        )
    figset = VerifiedFigureSet(edition_id=edition.edition_id)
    for pn, _, _ in parts:
        view = get_part(repo, pn).view
        assert view is not None
        figset.add_part_view(view)
    return figset, [p for p, _, _ in parts]


def _compose(draft: DraftPlan, rec, figset: VerifiedFigureSet, verified, preliminary, total):
    composer = ResponseComposer()
    ctx = composer.context(figset, Language.EN, edition_label(figset.edition_id))
    return composer.recommendation(
        ctx, draft, rec, verified=verified, preliminary=preliminary, total=total
    )


# Feature: agent-orchestration-response, Property 22: A recommendation is verified if and
# only if all four groups are SPECIFIED with a backed match
@given(
    sts=st.tuples(statuses, statuses, statuses, statuses),
    with_predicates=st.sets(st.sampled_from(ALL_GROUPS)),
    has_match=st.booleans(),
)
def test_property_22_verified_iff_four_specified_and_backed(
    sts: tuple[CoverageStatus, ...], with_predicates: set[RequirementGroup], has_match: bool
) -> None:
    figset, pns = _figset([("76-A1", 100, 24)])
    verified = tuple(pns) if has_match else ()
    rec = RecommendationCoordinator().decide(
        RecommendationInput(
            criteria=_criteria(sts),
            groups_with_predicates=frozenset(with_predicates),
            verified_matches=verified,
            preliminary_matches=(),
        ),
        figset,
    )
    expect_verified = (
        all(s is CoverageStatus.SPECIFIED for s in sts)
        and set(ALL_GROUPS) <= with_predicates
        and has_match
    )
    assert (rec.grade is RecommendationGrade.VERIFIED) == expect_verified
    not_specified = {
        g for g, s in zip(ALL_GROUPS, sts, strict=True) if s is not CoverageStatus.SPECIFIED
    }
    assert not_specified <= set(rec.unmet_groups)
    draft = DraftPlan(
        intent=Intent.RECOMMENDATION, response_language=Language.EN, criteria=_criteria(sts)
    )
    resp = _compose(draft, rec, figset, verified, (), len(verified))
    text = resp.answer.text.lower()
    if rec.grade is RecommendationGrade.PRELIMINARY:
        for g in rec.unmet_groups:
            assert GROUP_LABELS[g][Language.EN] in resp.answer.text
        assert not any(phrase in text for phrase in WARRANTY_PHRASES)


# Feature: agent-orchestration-response, Property 23: A delegated group is a proposed
# preference and never a synthesized physical condition
@given(sts=st.tuples(statuses, statuses, statuses, statuses))
def test_property_23_delegated_is_preference_not_condition(sts: tuple[CoverageStatus, ...]) -> None:
    predicates = (
        Predicate(AllowlistField.ENCLOSURE, Operator.EQ, "NEMA 4X"),
        Predicate(AllowlistField.NOMINAL_VOLTAGE, Operator.EQ, Decimal(24)),
        Predicate(AllowlistField.SERVICE, Operator.EQ, "On/Off"),
        Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(100)),
    )
    draft = DraftPlan(
        intent=Intent.RECOMMENDATION,
        response_language=Language.EN,
        criteria=_criteria(sts),
        filter_ast=And(children=predicates),
    )
    session = SessionContext(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    decision = PolicyEngine().decide(draft, session, plan_id="p")
    delegated = {g for g, s in zip(ALL_GROUPS, sts, strict=True) if s is CoverageStatus.DELEGATED}
    if decision.plan is not None:
        from series76_agent.domain.serialization import predicates_of

        kept = {FIELD_GROUP[p.field] for p in predicates_of(decision.plan.draft.filter_ast)}
        assert not (kept & delegated)  # no condition synthesized for a delegated group
    figset, pns = _figset([("76-B1", 120, 24)])
    rec = RecommendationCoordinator().decide(
        RecommendationInput(
            criteria=_criteria(sts),
            groups_with_predicates=frozenset(),
            verified_matches=tuple(pns),
            preliminary_matches=(),
        ),
        figset,
    )
    assert rec.completeness.synthesized_conditions == ()
    assert set(rec.delegated_groups) == delegated
    resp = _compose(draft, rec, figset, tuple(pns), (), 1)
    if delegated:
        assert "proposed preference" in resp.answer.text


candidates = st.lists(
    st.tuples(st.one_of(st.none(), st.integers(10, 400)), st.sampled_from([24, 120])),
    min_size=1,
    max_size=5,
)


# Feature: agent-orchestration-response, Property 24: Ranking uses only an accepted
# priority via Spec 2, and non-comparable metrics yield no winner
@given(cands=candidates, accepted=st.booleans())
def test_property_24_ranking_only_accepted_and_comparable(
    cands: list[tuple[int | None, int]], accepted: bool
) -> None:
    parts = [(f"76-R{i}", t, v) for i, (t, v) in enumerate(cands)]
    figset, pns = _figset(parts)
    priorities = (TORQUE_DESC,) if accepted else ()
    rec = RecommendationCoordinator().decide(
        RecommendationInput(
            criteria=(),
            groups_with_predicates=frozenset(),
            verified_matches=tuple(pns),
            preliminary_matches=(),
            accepted_priorities=priorities,
            ranking_requested=True,
        ),
        figset,
    )
    if not accepted:
        assert rec.needs_priority and rec.winner is None and rec.ranked == ()
        return
    supplies = {v for _, v in cands}
    if len(supplies) > 1:
        assert rec.winner is None
        assert rec.non_comparable_metric == "torque_inlbs"
        assert rec.indeterminate or len({v for _, v in cands}) > 1
        return
    expected = rank_candidates(
        tuple(
            RankCandidate(
                pn,
                {"torque_inlbs": figset.select(pn, "torque_inlbs")[0].figure.direct or _na()},
                frozenset({"torque_inlbs"}),
            )
            for pn in pns
        ),
        priorities,
    )
    assert rec.ranked == tuple(c.base_pn for c in expected.ranked)
    head_available = cands[pns.index(rec.ranked[0])][0] is not None
    assert rec.winner == (rec.ranked[0] if head_available else None)


def _na():
    from series76_domain.model.metric_value import MetricValue

    return MetricValue.not_applicable()


# Feature: agent-orchestration-response, Property 25: Top-1 returns only the winner and
# eligible count and equals the head of the full ranking
@given(torques=st.lists(st.integers(10, 400), min_size=0, max_size=5))
def test_property_25_top_one(torques: list[int]) -> None:
    parts = [(f"76-T{i}", t, 24) for i, t in enumerate(torques)]
    figset, pns = _figset(parts) if parts else (VerifiedFigureSet(uuid.uuid4()), [])
    rec = RecommendationCoordinator().decide(
        RecommendationInput(
            criteria=(),
            groups_with_predicates=frozenset(),
            verified_matches=tuple(pns),
            preliminary_matches=(),
            accepted_priorities=(TORQUE_DESC,),
            top_one=True,
        ),
        figset,
    )
    draft = DraftPlan(intent=Intent.RECOMMENDATION, response_language=Language.EN, top_one=True)
    if not pns:
        assert rec.no_eligible and rec.winner is None and rec.eligible == ()
        return
    head = rank_top_one(
        tuple(
            RankCandidate(
                pn,
                {"torque_inlbs": figset.select(pn, "torque_inlbs")[0].figure.direct},
                frozenset({"torque_inlbs"}),
            )
            for pn in pns
        ),
        (TORQUE_DESC,),
    )
    assert head.winner is not None and rec.winner == head.winner.base_pn
    assert rec.eligible_count == head.eligible_count == len(pns)
    resp = _compose(draft, rec, figset, tuple(pns), (), len(pns))
    listing = [b for b in resp.blocks if b.kind.value == "matching_part_numbers"]
    assert listing and listing[0].part_numbers == [rec.winner] and listing[0].top_one
    for other in pns:
        if other != rec.winner:
            assert other not in resp.answer.text
    assert str(len(pns)) in resp.answer.text  # the integer eligible count
