"""Deterministic Recommendation coordinator (Req 7.1-7.9).

* The grade comes from the Spec 2 ``evaluate_completeness`` over the four
  requirement groups: ``verified`` iff all four are ``SPECIFIED`` with a
  catalog-backed match, else ``preliminary`` naming every unmet group.
* A ``DELEGATED`` group is a proposed preference; no physical value is ever
  synthesized for it (the coordinator never creates a ``SPECIFIED`` input).
* Ranking is obtained **only** from the Spec 2 ``rank_candidates`` service,
  and only under a user-accepted priority. A priority whose metric context
  differs across candidates yields no winner and a distinct indeterminate
  group; an N/A / absent priority value is never a winner.
* Top-1 returns the winner and the integer eligible count only; the winner is
  the head of the full Spec 2 ranking over the same inputs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from series76_agent.domain.enums import RecommendationGrade
from series76_agent.domain.figures import BoundFigure, VerifiedFigureSet
from series76_agent.domain.plan import Criterion
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.metric_value import MetricValue
from series76_domain.services.completeness import (
    CompletenessResult,
    GroupInput,
    evaluate_completeness,
)
from series76_domain.services.rank_candidates import (
    RankCandidate,
    RankingResult,
    RankPriority,
    rank_candidates,
)

ALL_GROUPS: tuple[RequirementGroup, ...] = (
    RequirementGroup.ENVIRONMENT_ENCLOSURE,
    RequirementGroup.POWER_SUPPLY,
    RequirementGroup.SERVICE_TYPE,
    RequirementGroup.REQUIRED_TORQUE,
)

#: Language that must never describe a preliminary set (Req 7.8).
WARRANTY_PHRASES: tuple[str, ...] = (
    "guarantee",
    "guaranteed",
    "warranty",
    "fit for purpose",
    "fully compatible",
    "certified fit",
    "integral compatibility",
    "garantiza",
    "garantizado",
    "garantía",
    "totalmente compatible",
    "compatibilidad integral",
    "apto para el uso",
)


def group_statuses(criteria: tuple[Criterion, ...]) -> dict[RequirementGroup, CoverageStatus]:
    """Resolve one Coverage_Status per group from the plan criteria.

    Several criteria for one group with differing statuses (or any
    ``CONFLICTING``) resolve to ``CONFLICTING``; a group with no criterion is
    ``UNSPECIFIED``.
    """

    out: dict[RequirementGroup, CoverageStatus] = {}
    for group in ALL_GROUPS:
        statuses = {c.status for c in criteria if c.group is group}
        if not statuses:
            out[group] = CoverageStatus.UNSPECIFIED
        elif CoverageStatus.CONFLICTING in statuses or len(statuses) > 1:
            out[group] = CoverageStatus.CONFLICTING
        else:
            out[group] = next(iter(statuses))
    return out


def evaluate_coverage(
    criteria: tuple[Criterion, ...],
    groups_with_predicates: frozenset[RequirementGroup],
    has_verified_match: bool,
) -> CompletenessResult:
    """Evaluate the four groups via the Spec 2 completeness primitive.

    A ``SPECIFIED`` group has a catalog-backed match iff it contributed a
    predicate to the executed search and that search returned at least one
    fully-documented (verified) match.
    """

    statuses = group_statuses(criteria)
    inputs = tuple(
        GroupInput(
            group=g,
            status=statuses[g],
            has_catalog_match=(
                statuses[g] is CoverageStatus.SPECIFIED
                and g in groups_with_predicates
                and has_verified_match
            ),
        )
        for g in ALL_GROUPS
    )
    return evaluate_completeness(inputs)


@dataclass(frozen=True, slots=True)
class RecommendationInput:
    """Everything the coordinator decides on (all deterministic inputs)."""

    criteria: tuple[Criterion, ...]
    groups_with_predicates: frozenset[RequirementGroup]
    verified_matches: tuple[str, ...]
    preliminary_matches: tuple[str, ...]
    accepted_priorities: tuple[RankPriority, ...] = ()
    top_one: bool = False
    ranking_requested: bool = False
    service: str | None = None


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """The coordinator's decision."""

    grade: RecommendationGrade
    completeness: CompletenessResult
    unmet_groups: tuple[RequirementGroup, ...]
    delegated_groups: tuple[RequirementGroup, ...]
    eligible: tuple[str, ...]
    ranked: tuple[str, ...] = ()
    indeterminate: tuple[str, ...] = ()
    winner: str | None = None
    eligible_count: int = 0
    no_eligible: bool = False
    needs_priority: bool = False
    non_comparable_metric: str | None = None
    ranking: RankingResult | None = None
    excluded_na: tuple[str, ...] = field(default=())


class RecommendationCoordinator:
    """Applies the four-group gate, ranking, and top-1 rules (zero LLM)."""

    def decide(self, data: RecommendationInput, figures: VerifiedFigureSet) -> RecommendationResult:
        """Classify, and rank only under an accepted priority."""

        completeness = evaluate_coverage(
            data.criteria, data.groups_with_predicates, bool(data.verified_matches)
        )
        grade = (
            RecommendationGrade.VERIFIED
            if completeness.is_verified
            else RecommendationGrade.PRELIMINARY
        )
        statuses = group_statuses(data.criteria)
        delegated = tuple(g for g in ALL_GROUPS if statuses[g] is CoverageStatus.DELEGATED)
        eligible = data.verified_matches
        base = RecommendationResult(
            grade=grade,
            completeness=completeness,
            unmet_groups=completeness.unmet_groups,
            delegated_groups=delegated,
            eligible=eligible,
            eligible_count=len(eligible),
        )
        wants_ranking = data.top_one or data.ranking_requested
        if not wants_ranking:
            return base
        if not eligible:
            return _replace(base, no_eligible=True)
        if not data.accepted_priorities:
            return _replace(base, needs_priority=True)
        return self._rank(base, data, figures)

    def _rank(
        self,
        base: RecommendationResult,
        data: RecommendationInput,
        figures: VerifiedFigureSet,
    ) -> RecommendationResult:
        priorities = data.accepted_priorities
        chosen: dict[str, dict[str, BoundFigure]] = {pn: {} for pn in base.eligible}
        ambiguous: dict[str, set[str]] = {pn: set() for pn in base.eligible}
        for pn in base.eligible:
            for prio in priorities:
                options = figures.select(pn, prio.key, service=data.service)
                if len(options) == 1:
                    chosen[pn][prio.key] = options[0]
                elif len(options) > 1:
                    ambiguous[pn].add(prio.key)

        # Plurality context per priority key; any heterogeneity => no winner.
        heterogeneous_metric: str | None = None
        comparable_keys: dict[str, set[str]] = {pn: set() for pn in base.eligible}
        for prio in priorities:
            contexts = Counter(
                chosen[pn][prio.key].context_key for pn in base.eligible if prio.key in chosen[pn]
            )
            if not contexts:
                continue
            ranked_ctx = contexts.most_common()
            plurality, top = ranked_ctx[0]
            tie = len(ranked_ctx) > 1 and ranked_ctx[1][1] == top
            heterogeneous = len(ranked_ctx) > 1 or any(
                prio.key in ambiguous[pn] for pn in base.eligible
            )
            if heterogeneous and heterogeneous_metric is None:
                heterogeneous_metric = prio.key
            for pn in base.eligible:
                fig = chosen[pn].get(prio.key)
                if fig is None:
                    continue
                if not tie and fig.context_key == plurality:
                    comparable_keys[pn].add(prio.key)

        candidates = tuple(
            RankCandidate(
                base_pn=pn,
                metrics={
                    k: (f.figure.direct if f.figure.direct is not None else _absent(f))
                    for k, f in chosen[pn].items()
                },
                comparable_keys=frozenset(comparable_keys[pn]),
            )
            for pn in base.eligible
        )
        ranking = rank_candidates(candidates, priorities)
        ranked = tuple(c.base_pn for c in ranking.ranked)
        indeterminate = tuple(c.base_pn for c in ranking.indeterminate)
        excluded_na = tuple(
            c.base_pn
            for c in ranking.ranked
            if any((m := c.metrics.get(p.key)) is None or not m.is_available for p in priorities)
        )

        winner: str | None = None
        head = ranking.winner
        if heterogeneous_metric is None and head is not None:
            head_values = [head.metrics.get(p.key) for p in priorities]
            if all(m is not None and m.is_available for m in head_values):
                winner = head.base_pn

        return _replace(
            base,
            ranked=ranked,
            indeterminate=indeterminate,
            winner=winner,
            eligible_count=ranking.eligible_count,
            non_comparable_metric=heterogeneous_metric,
            ranking=ranking,
            excluded_na=excluded_na,
        )


def _absent(f: BoundFigure) -> MetricValue:
    """The explicit no-number metric of a bound figure (never zero)."""
    return MetricValue(None, f.figure.status, None)


def _replace(result: RecommendationResult, **changes: object) -> RecommendationResult:
    from dataclasses import replace

    return replace(result, **changes)  # type: ignore[arg-type]
