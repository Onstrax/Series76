"""Abstention / Fallback policy (Req 10.1-10.7, F2 §10).

* :data:`FALLBACK_MATRIX` maps each F2 §10 condition to exactly one business
  response (outcome code + message), its turn state, and its execution rule
  (whether a lookup tool may run, whether a retry is ever permitted).
* :func:`retry_idempotent` retries **only** transient errors of idempotent
  operations, a bounded number of times with exponentially increasing backoff,
  and only while the turn budget has capacity. Semantic outcomes are values,
  not exceptions, so they can never be retried by this helper.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from series76_agent.domain.enums import FallbackCondition, OutcomeCode, TurnState

T = TypeVar("T")


class TransientError(Exception):
    """A transient network / provider / database error (retryable if idempotent)."""


@dataclass(frozen=True, slots=True)
class FallbackRule:
    """The defined business response and execution rule of one condition."""

    outcome: OutcomeCode
    terminal_state: TurnState
    message_key: str
    lookup_allowed: bool
    retry_allowed: bool
    is_business_success: bool = False


FALLBACK_MATRIX: dict[FallbackCondition, FallbackRule] = {
    # (a) invalid PN format: request correction, no lookup tool call.
    FallbackCondition.INVALID_PN_FORMAT: FallbackRule(
        OutcomeCode.INVALID_PN, TurnState.NEEDS_CLARIFICATION, "invalid_pn", False, False
    ),
    # (b) well formed, not listed: report not listed (exact lookup ran).
    FallbackCondition.PART_NOT_LISTED: FallbackRule(
        OutcomeCode.PART_NOT_LISTED, TurnState.COMPLETED, "not_listed", True, False
    ),
    # (c) listed with N/A attributes: existence + absence, a business success.
    FallbackCondition.PART_LISTED_NA: FallbackRule(
        OutcomeCode.N_A, TurnState.COMPLETED, "part_na", True, False, True
    ),
    # (d) zero matches: report constraints, allow adjusting; a success.
    FallbackCondition.ZERO_MATCHES: FallbackRule(
        OutcomeCode.NO_RESULTS, TurnState.COMPLETED, "no_results", True, False, True
    ),
    # (e) incomplete recommendation: preliminary + outstanding questions.
    FallbackCondition.INCOMPLETE_RECOMMENDATION: FallbackRule(
        OutcomeCode.OK, TurnState.COMPLETED, "rec_preliminary", True, False, True
    ),
    # (f) ambiguous AND/OR: confirmation of the exact grouping.
    FallbackCondition.AMBIGUOUS_BOOLEAN: FallbackRule(
        OutcomeCode.AWAITING_CONFIRMATION,
        TurnState.AWAITING_CONFIRMATION,
        "confirm_boolean",
        False,
        False,
    ),
    # (g) frequency/service without evidence: documented scope, no extrapolation.
    FallbackCondition.SCOPE_WITHOUT_EVIDENCE: FallbackRule(
        OutcomeCode.OK, TurnState.COMPLETED, "scope_without_evidence", True, False, True
    ),
    # (h) out of scope: abstain, no external lookup.
    FallbackCondition.OUT_OF_SCOPE: FallbackRule(
        OutcomeCode.OUT_OF_SCOPE, TurnState.COMPLETED, "abstain", False, False
    ),
    # (i) withdrawn edition: alert, keep history, block new recommendation.
    FallbackCondition.SOURCE_WITHDRAWN: FallbackRule(
        OutcomeCode.SOURCE_WITHDRAWN, TurnState.SOURCE_WITHDRAWN, "withdrawn", False, False
    ),
    # (j) tool / DB unavailable: recoverable error with correlation id.
    FallbackCondition.TOOL_UNAVAILABLE: FallbackRule(
        OutcomeCode.TOOL_UNAVAILABLE, TurnState.FAILED, "tool_unavailable", True, True
    ),
    # (k) provider 402 / quota: clear error, no invented answer, no switch.
    FallbackCondition.PROVIDER_QUOTA: FallbackRule(
        OutcomeCode.PROVIDER_QUOTA_EXCEEDED, TurnState.FAILED, "provider_quota", False, False
    ),
    # (l) injection / escalation: ignore it, keep the enforced policy.
    FallbackCondition.PROMPT_INJECTION: FallbackRule(
        OutcomeCode.OK, TurnState.COMPLETED, "injection_note", True, False, True
    ),
    # (m) stale confirmation: plan changed, show current, do not execute.
    FallbackCondition.STALE_CONFIRMATION: FallbackRule(
        OutcomeCode.STALE_PLAN, TurnState.STALE_PLAN, "stale", False, False
    ),
    # (n) delete vs late job: cancelled, durable write guard (Spec 3 fencing).
    FallbackCondition.DELETE_VS_LATE_JOB: FallbackRule(
        OutcomeCode.CANCELLED, TurnState.CANCELLED, "cancelled", False, False
    ),
}


def rule_for(condition: FallbackCondition) -> FallbackRule:
    """The single rule defined for ``condition``."""
    return FALLBACK_MATRIX[condition]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential backoff (constants are a delegated detail)."""

    max_attempts: int = 3
    base_delay_s: float = 0.25
    factor: float = 2.0
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    def delays(self) -> list[float]:
        """The backoff delays between attempts (strictly increasing)."""
        return [self.base_delay_s * (self.factor**i) for i in range(self.max_attempts - 1)]


async def retry_idempotent(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    idempotent: bool = True,
    can_continue: Callable[[], bool] = lambda: True,
) -> T:
    """Run ``operation``; retry transient errors only if idempotent and budgeted.

    A non-idempotent operation is attempted exactly once. Only
    :class:`TransientError` is retried; every other exception propagates
    immediately. The last transient error is re-raised once attempts run out.
    """

    attempts = policy.max_attempts if idempotent else 1
    delays = policy.delays()
    last: TransientError | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except TransientError as exc:
            last = exc
            if attempt + 1 >= attempts or not can_continue():
                break
            await policy.sleep(delays[attempt])
    assert last is not None
    raise last
