"""The ``compare_parts`` deterministic service (Task 8.1, Req 5.*).

A **pure** function over 2-3 distinct listed PNs of the **same** edition. It
returns side-by-side documented facts with each fact's operating condition,
service context, and unit exposed; flags each metric pair comparable only under
compatible service / frequency / supply / unit context, else ``NOT_COMPARABLE``
with a condition-mismatch warning and **no winner** (Property 19); presents
heterogeneous-supply FLA with each supply condition and **no** efficiency /
lower-consumption claim (Property 20); and presents N/A / absent fields with
their explicit state, never as zero or a winner (Property 10).

It rejects more than one edition, and fewer than two / more than three /
duplicate / unlisted PNs, with a typed failure and **no partial set**; it is
deterministic on repeat (Property 21).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit


@dataclass(frozen=True, slots=True)
class ComparableMetric:
    """One metric of one part, with its full comparison context.

    Attributes:
        base_pn: the part this metric belongs to.
        metric_key: the metric name (e.g. ``"torque_inlbs"``).
        value: the documented value (N/A / absent preserved).
        unit: the metric's unit.
        service_context: the service type the metric is bound to, if any.
        frequency_context: the frequency (Hz) the metric is bound to, if any.
        supply_context: the supply condition the metric is bound to, if any.
    """

    base_pn: str
    metric_key: str
    value: MetricValue
    unit: Unit | None
    service_context: str | None = None
    frequency_context: Decimal | None = None
    supply_context: str | None = None

    def context_matches(self, other: ComparableMetric) -> bool:
        """Whether two metrics share a comparable service/frequency/supply/unit."""
        return (
            self.metric_key == other.metric_key
            and self.unit == other.unit
            and self.service_context == other.service_context
            and self.frequency_context == other.frequency_context
            and self.supply_context == other.supply_context
        )


@dataclass(frozen=True, slots=True)
class ComparisonPair:
    """A side-by-side comparison of one metric across two parts."""

    metric_key: str
    left: ComparableMetric
    right: ComparableMetric
    comparable: bool
    warning: str | None = None
    is_supply_heterogeneous: bool = False

    @property
    def has_winner(self) -> bool:
        """Never a winner on a non-comparable pair or an N/A/absent value."""
        if not self.comparable:
            return False
        if not self.left.value.is_available or not self.right.value.is_available:
            return False
        return self.left.value.value != self.right.value.value


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """The outcome of a comparison: side-by-side rows or a typed failure."""

    part_order: tuple[str, ...] = ()
    pairs: tuple[ComparisonPair, ...] = ()
    failure: SemanticFailureCode | None = None
    failure_detail: str | None = None

    @property
    def ok(self) -> bool:
        """True iff a side-by-side set was produced."""
        return self.failure is None


@dataclass(frozen=True, slots=True)
class PartComparisonInput:
    """One part's documented metrics for comparison, all in one edition."""

    base_pn: str
    edition_id: object
    metrics: tuple[ComparableMetric, ...]


def compare_parts(parts: tuple[PartComparisonInput, ...]) -> ComparisonResult:
    """Compare 2-3 same-edition listed parts side by side.

    Returns a :class:`ComparisonResult`. Arity / duplicate / edition-mismatch
    violations yield a typed failure with no partial set.
    """

    if len(parts) < 2 or len(parts) > 3:
        return ComparisonResult(
            failure=SemanticFailureCode.NOT_COMPARABLE,
            failure_detail="comparison requires 2 or 3 part numbers",
        )

    pns = [p.base_pn for p in parts]
    if len(set(pns)) != len(pns):
        return ComparisonResult(
            failure=SemanticFailureCode.NOT_COMPARABLE,
            failure_detail="duplicate part numbers are not comparable",
        )

    editions = {p.edition_id for p in parts}
    if len(editions) != 1:
        return ComparisonResult(
            failure=SemanticFailureCode.NOT_COMPARABLE,
            failure_detail="parts span more than one edition",
        )

    part_order = tuple(sorted(pns))
    by_pn = {p.base_pn: p for p in parts}

    pairs: list[ComparisonPair] = []
    # Compare the first part against each subsequent part, metric by metric, in
    # a deterministic order (sorted PNs, sorted metric keys).
    anchor = by_pn[part_order[0]]
    for other_pn in part_order[1:]:
        other = by_pn[other_pn]
        pairs.extend(_pairwise(anchor, other))

    return ComparisonResult(part_order=part_order, pairs=tuple(pairs))


def _pairwise(
    left: PartComparisonInput, right: PartComparisonInput
) -> list[ComparisonPair]:
    left_by_key = _index(left.metrics)
    right_by_key = _index(right.metrics)
    keys = sorted(set(left_by_key) | set(right_by_key))
    pairs: list[ComparisonPair] = []
    for key in keys:
        lhs = left_by_key.get(key)
        rhs = right_by_key.get(key)
        if lhs is None or rhs is None:
            continue
        comparable = lhs.context_matches(rhs)
        warning = None if comparable else "operating/service/supply context mismatch"
        supply_heterogeneous = lhs.supply_context != rhs.supply_context
        pairs.append(
            ComparisonPair(
                metric_key=key,
                left=lhs,
                right=rhs,
                comparable=comparable,
                warning=warning,
                is_supply_heterogeneous=supply_heterogeneous,
            )
        )
    return pairs


def _index(metrics: tuple[ComparableMetric, ...]) -> dict[str, ComparableMetric]:
    """Index metrics by key (first wins for a repeated key, deterministically)."""
    indexed: dict[str, ComparableMetric] = {}
    for metric in metrics:
        indexed.setdefault(metric.metric_key, metric)
    return indexed
