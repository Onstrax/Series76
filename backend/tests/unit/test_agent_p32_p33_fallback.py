"""Spec 4 Properties 32-33: the fallback matrix, bounded retries, fail-closed budget."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from _agent_fakes import interp, make_harness, pred, visible_text
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.domain.budget import BudgetExceeded, BudgetLimit, BudgetTracker, TurnBudget
from series76_agent.domain.enums import FallbackCondition, OutcomeCode, TurnState
from series76_agent.fallback import (
    FALLBACK_MATRIX,
    RetryPolicy,
    TransientError,
    retry_idempotent,
    rule_for,
)

#: One concrete turn per condition that the orchestrator drives end to end.
DRIVEN = {
    FallbackCondition.INVALID_PN_FORMAT: (
        "show 76 100!!",
        interp("EXACT_LOOKUP", part_numbers=["76 100!!"]),
    ),
    FallbackCondition.PART_NOT_LISTED: (
        "show ZZ-9999",
        interp("EXACT_LOOKUP", part_numbers=["ZZ-9999"]),
    ),
    FallbackCondition.PART_LISTED_NA: (
        "show 76-T03",
        interp("EXACT_LOOKUP", part_numbers=["76-T03"]),
    ),
    FallbackCondition.ZERO_MATCHES: (
        "torque over 9000 in-lbs",
        interp("FILTER_SEARCH", filter_ast=pred("torque_inlbs", "GT", "9000", "in-lbs")),
    ),
    FallbackCondition.AMBIGUOUS_BOOLEAN: (
        "torque over 100 or On/Off and 24",
        interp(
            "FILTER_SEARCH",
            boolean_precedence_ambiguous=True,
            filter_ast={
                "type": "or",
                "children": [pred("torque_inlbs", "GT", "100"), pred("service", "EQ", "On/Off")],
            },
        ),
    ),
    FallbackCondition.OUT_OF_SCOPE: ("tell me a joke", interp("OUT_OF_SCOPE")),
}


# Feature: agent-orchestration-response, Property 32: Each fallback condition maps to only
# its defined response, and semantic outcomes are successes not retried
@given(condition=st.sampled_from(sorted(DRIVEN, key=lambda c: c.value)))
def test_property_32_fallback_mapping_and_no_semantic_retry(
    condition: FallbackCondition,
) -> None:
    rule = rule_for(condition)
    assert FALLBACK_MATRIX[condition] is rule  # exactly one defined rule
    message, out = DRIVEN[condition]
    h = make_harness({message: out})
    res = h.run(uuid.uuid4(), uuid.uuid4(), message)
    assert res.outcome is rule.outcome
    assert res.state is rule.terminal_state
    if not rule.lookup_allowed:
        assert res.invocations == [] and h.catalog.repo.reads == []
    if rule.is_business_success:
        assert res.outcome.is_business_success
    if rule.outcome in (OutcomeCode.NO_RESULTS, OutcomeCode.N_A):
        # A semantic outcome is a success: one interpretation + one tool-selection
        # call, the read performed exactly once, no retry of model or tool.
        assert res.model_calls == 2
        assert len(res.invocations) == 1
        assert len(h.interp.calls) == 1 and len(h.chat.calls) == 1


SECRETS = ("Traceback", "SELECT ", "sk-", "You interpret", "You retrieve", 'File "')


# Feature: agent-orchestration-response, Property 33: Retries are bounded and idempotent,
# budget exhaustion fails closed, and failures surface one leak-free code
@given(
    failures=st.integers(0, 5),
    idempotent=st.booleans(),
    max_attempts=st.integers(1, 4),
    max_model_calls=st.integers(0, 2),
)
def test_property_33_bounded_retry_fail_closed_one_code(
    failures: int, idempotent: bool, max_attempts: int, max_model_calls: int
) -> None:
    attempts: list[int] = []
    delays: list[float] = []

    async def sleep(d: float) -> None:
        delays.append(d)

    async def op() -> str:
        attempts.append(1)
        if len(attempts) <= failures:
            raise TransientError("transient")
        return "ok"

    policy = RetryPolicy(max_attempts=max_attempts, base_delay_s=0.1, sleep=sleep)
    allowed = max_attempts if idempotent else 1
    if failures < allowed:
        assert asyncio.run(retry_idempotent(op, policy=policy, idempotent=idempotent)) == "ok"
        assert len(attempts) == failures + 1
    else:
        with pytest.raises(TransientError):
            asyncio.run(retry_idempotent(op, policy=policy, idempotent=idempotent))
        assert len(attempts) == allowed
    assert delays == sorted(delays) and len(set(delays)) == len(delays)  # increasing backoff

    # Non-transient errors are never retried.
    calls: list[int] = []

    async def boom() -> None:
        calls.append(1)
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        asyncio.run(retry_idempotent(boom, policy=policy))
    assert calls == [1]

    # Budget exhaustion fails closed with exactly one typed code and no leak.
    tracker = BudgetTracker(TurnBudget(max_model_calls_per_turn=max_model_calls))
    from series76_agent.domain.enums import ModelFunction

    for _ in range(max_model_calls):
        tracker.check_model_call(ModelFunction.INTERPRETATION)
    with pytest.raises(BudgetExceeded) as exc:
        tracker.check_model_call(ModelFunction.TOOL_CALLING)
    assert exc.value.limit is BudgetLimit.MODEL_CALLS
    with pytest.raises(BudgetExceeded):
        tracker.check_tool_call()  # sticky: nothing further may start
    h = make_harness(
        {"show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"])},
        budget=TurnBudget(max_model_calls_per_turn=max_model_calls),
    )
    res = h.run(uuid.uuid4(), uuid.uuid4(), "show 76-100")
    if max_model_calls < 2:
        assert res.state is TurnState.FAILED
        assert res.outcome is OutcomeCode.BUDGET_EXHAUSTED
        assert res.invocations == [] or max_model_calls == 1
        text = visible_text(res)
        assert not any(s in text for s in SECRETS)
        assert res.response.presented == []  # no partial result presented as complete
    assert Decimal(0) <= h.ledger.total_spent
