"""The ``rank_candidates`` deterministic service (Task 7.1, Req 4.*).

A **pure** function over already-retrieved facts. It orders an eligible
candidate set lexicographically by the explicit, confirmed priorities (each
with a comparison direction), resolves ties by Base Part Number in a single
fixed ascending order, and is reproducible on identical inputs (Property 15).

Semantics:

* N/A and absent values are excluded from a priority's comparison and such
  candidates are placed **after** all comparable ones; they are never coerced
  to zero or a default (Property 10).
* a priority metric that is not comparable across the candidate set (differing
  service / frequency / supply / unit context) is not used to order; the
  affected candidates are returned in a **distinct indeterminate group**
  (Property 16).
* top-1 mode returns only the winner plus the eligible count and equals the
  head of the full ranking (Property 17).
* a model ``sort_hint`` is ignored; an empty eligible set or a missing
  confirmed priority yields a non-exception precondition indication with the
  input left unmodified (Property 18).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from series76_domain.model.metric_value import MetricValue


class SortDirection(str, Enum):
    """The direction a priority is compared in."""

    ASC = "ASC"
    DESC = "DESC"


@dataclass(frozen=True, slots=True)
class RankPriority:
    """One confirmed ranking priority.

    Attributes:
        key: the metric key naming which candidate value to compare.
        direction: ascending (smaller is better) or descending (larger).
    """

    key: str
    direction: SortDirection


@dataclass(frozen=True, slots=True)
class RankCandidate:
    """A candidate for ranking.

    Attributes:
        base_pn: the Base Part Number (the fixed ascending tiebreak key).
        metrics: the candidate's comparable metric values keyed by priority key.
        comparable_keys: the metric keys that are comparable for this candidate
            across the set's shared context; a key outside this set is treated
            as non-comparable and routes the candidate to the indeterminate
            group when used as a priority.
    """

    base_pn: str
    metrics: dict[str, MetricValue]
    comparable_keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class RankingResult:
    """The outcome of ranking.

    Attributes:
        ranked: candidates in final order (comparable ones first, then those
            excluded from a priority comparison, all tiebroken by Base PN).
        indeterminate: candidates excluded from ordering because a priority
            metric is non-comparable for them (a distinct group).
        precondition_unmet: ``True`` iff the eligible set was empty or no
            confirmed priority was supplied; then no ranking is produced.
        eligible_count: the number of eligible (ranked) candidates.
    """

    ranked: tuple[RankCandidate, ...] = ()
    indeterminate: tuple[RankCandidate, ...] = ()
    precondition_unmet: bool = False
    eligible_count: int = 0

    @property
    def winner(self) -> RankCandidate | None:
        """The head of the full ranking, or ``None`` if none."""
        return self.ranked[0] if self.ranked else None


@dataclass(frozen=True, slots=True)
class TopOneResult:
    """A top-1 ranking: only the winner and the eligible count (Property 17)."""

    winner: RankCandidate | None
    eligible_count: int


def rank_candidates(
    candidates: tuple[RankCandidate, ...],
    priorities: tuple[RankPriority, ...],
    *,
    sort_hint: str | None = None,  # noqa: ARG001  (ignored; non-authoritative)
) -> RankingResult:
    """Rank ``candidates`` by ``priorities``; input is never mutated.

    Returns a :class:`RankingResult`. If ``candidates`` is empty or
    ``priorities`` is empty, returns a precondition-unmet result (no ranking,
    no winner).
    """

    if not candidates or not priorities:
        return RankingResult(precondition_unmet=True)

    # A priority metric must be comparable for *every* candidate that carries
    # it; a candidate for which any used priority key is non-comparable is
    # routed to the distinct indeterminate group (Property 16).
    used_keys = frozenset(p.key for p in priorities)
    comparable: list[RankCandidate] = []
    indeterminate: list[RankCandidate] = []
    for cand in candidates:
        if used_keys <= cand.comparable_keys:
            comparable.append(cand)
        else:
            indeterminate.append(cand)

    def sort_key(cand: RankCandidate) -> tuple[object, ...]:
        key: list[object] = []
        for priority in priorities:
            metric = cand.metrics.get(priority.key)
            # N/A / absent: excluded from comparison, placed after comparables.
            if metric is None or not metric.is_available or metric.value is None:
                key.append((1, Decimal(0)))
                continue
            value = metric.value
            ordered = value if priority.direction is SortDirection.ASC else -value
            key.append((0, ordered))
        # Base-PN ascending tiebreak (single fixed order), reproducible.
        key.append(cand.base_pn)
        return tuple(key)

    ranked = tuple(sorted(comparable, key=sort_key))
    indeterminate_sorted = tuple(sorted(indeterminate, key=lambda c: c.base_pn))
    return RankingResult(
        ranked=ranked,
        indeterminate=indeterminate_sorted,
        precondition_unmet=False,
        eligible_count=len(ranked),
    )


def rank_top_one(
    candidates: tuple[RankCandidate, ...],
    priorities: tuple[RankPriority, ...],
    *,
    sort_hint: str | None = None,
) -> TopOneResult:
    """Return only the winner and the eligible count (Property 17).

    The winner equals the head of the full ranking computed from the same
    inputs. The other eligible PNs are not returned.
    """

    full = rank_candidates(candidates, priorities, sort_hint=sort_hint)
    return TopOneResult(winner=full.winner, eligible_count=full.eligible_count)
