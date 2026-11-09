"""Spec 4 Properties 10-16: Policy_Engine and the turn state machine."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from _agent_fakes import interp, make_harness, pred
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.domain.conversation import PendingPlan, new_state
from series76_agent.domain.enums import Intent, Language, Strength, TurnState
from series76_agent.domain.plan import Ambiguity, Criterion, DraftPlan
from series76_agent.domain.state_machine import TRANSITIONS, Turn, TurnStateError, coerce_state
from series76_agent.policy import (
    ConfirmationSignal,
    DecisionKind,
    PolicyEngine,
    SessionContext,
)
from series76_agent.recommendation import evaluate_coverage
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, And, Operator, Predicate
from series76_domain.model.units import Unit

SESSION = SessionContext(
    session_id=uuid.uuid4(), owner_id=uuid.uuid4(), catalog_edition_id=uuid.uuid4()
)

invalid_predicates = st.sampled_from(
    [
        Predicate(AllowlistField.SERVICE, Operator.GT, "On/Off"),  # ordered on string
        Predicate(AllowlistField.TORQUE_INLBS, Operator.EQ, Decimal(5), Unit.AMPERE),  # unit
        Predicate(AllowlistField.TORQUE_NM, Operator.IN, ()),  # empty IN
        Predicate(AllowlistField.ENCLOSURE, Operator.EQ, Decimal(4)),  # value kind
        Predicate(AllowlistField.FLA, Operator.LT, "high"),  # numeric needs number
    ]
)


# Feature: agent-orchestration-response, Property 10: AST validation precedes execution
# and invalid filters block the catalog
@given(bad=invalid_predicates, wrap=st.booleans())
def test_property_10_invalid_ast_blocks_catalog(bad: Predicate, wrap: bool) -> None:
    node = And(children=(bad,)) if wrap else bad
    draft = DraftPlan(intent=Intent.FILTER_SEARCH, response_language=Language.EN, filter_ast=node)
    decision = PolicyEngine().decide(draft, SESSION, plan_id="p")
    assert decision.kind is DecisionKind.INVALID_FILTER
    assert decision.validation is not None and not decision.validation.ok
    assert decision.validation.offending_predicate == bad
    # End to end: the orchestrator issues no tool call and no catalog read.
    from series76_agent.domain.serialization import ast_to_json

    raw = ast_to_json(node)
    message = "filter with 5 and 4"
    h = make_harness({message: interp("FILTER_SEARCH", filter_ast=raw)})
    sid, oid = uuid.uuid4(), uuid.uuid4()
    before = new_state(sid, oid).evolve(plan_revision=3, focus=("76-100",))
    h.states.data[(sid, oid)] = before
    res = h.run(sid, oid, message)
    assert res.invocations == [] and h.catalog.repo.reads == []
    assert res.state in (TurnState.NEEDS_CLARIFICATION,)
    after = h.states.data[(sid, oid)]
    assert (after.plan_revision, after.focus, after.criteria, after.last_search_results) == (
        before.plan_revision,
        before.focus,
        before.criteria,
        before.last_search_results,
    )


drafts = st.builds(
    lambda intent, alts, boolean, conflict, top, n: DraftPlan(
        intent=intent,
        response_language=Language.EN,
        filter_ast=Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(n)) if n else None,
        ambiguity=Ambiguity(
            alternative_interpretations=alts,
            boolean_precedence_ambiguous=boolean,
            conflicting_statements=conflict,
        ),
        top_one=top,
        criteria=(
            Criterion(
                "t", CoverageStatus.SPECIFIED, Strength.HARD, RequirementGroup.REQUIRED_TORQUE
            ),
        ),
    ),
    st.sampled_from(list(Intent)),
    st.integers(1, 3),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.integers(0, 300),
)
statuses = st.sampled_from(list(CoverageStatus))


# Feature: agent-orchestration-response, Property 11: Policy and plan decisions are
# deterministic and performed with zero LLM invocations
@given(
    draft=drafts,
    coverage=st.tuples(statuses, statuses, statuses, statuses),
    match=st.booleans(),
    rev=st.integers(0, 4),
    sig_rev=st.integers(0, 4),
)
def test_property_11_deterministic_zero_llm(
    draft: DraftPlan, coverage: tuple[CoverageStatus, ...], match: bool, rev: int, sig_rev: int
) -> None:
    import series76_agent.policy as policy_module

    engine = PolicyEngine()
    a = engine.decide(draft, SESSION, plan_id="p", plan_revision=rev)
    b = engine.decide(draft, SESSION, plan_id="p", plan_revision=rev)
    assert a == b
    groups = list(RequirementGroup)
    criteria = tuple(
        Criterion("c", s, Strength.HARD, g) for s, g in zip(coverage, groups, strict=True)
    )
    c1 = evaluate_coverage(criteria, frozenset(groups), match)
    c2 = evaluate_coverage(criteria, frozenset(groups), match)
    assert c1 == c2
    state = new_state(SESSION.session_id, SESSION.owner_id).evolve(
        plan_revision=rev,
        plan_id="pid",
        pending_plan=PendingPlan("t", "pid", rev, {}) if rev else None,
    )
    sig = ConfirmationSignal(SESSION.session_id, "pid", sig_rev, SESSION.owner_id, True)
    assert engine.verify_revision(state, sig) == engine.verify_revision(state, sig)
    # Structural zero-LLM guarantee: the policy module holds no model seam at all.
    source = Path(policy_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("ModelGateway", "langchain", "openai", "ChatOpenAI", "interpret("):
        assert forbidden not in source


# Feature: agent-orchestration-response, Property 12: A single-filter search does not
# require recommendation coverage
@given(
    field=st.sampled_from(
        [AllowlistField.TORQUE_INLBS, AllowlistField.FLA, AllowlistField.OPERATING_SPEED]
    ),
    n=st.integers(1, 500),
)
def test_property_12_single_filter_no_coverage(field: AllowlistField, n: int) -> None:
    draft = DraftPlan(
        intent=Intent.FILTER_SEARCH,
        response_language=Language.EN,
        filter_ast=Predicate(field, Operator.GE, Decimal(n)),
    )
    engine = PolicyEngine()
    assert not engine.requires_coverage(draft)
    assert engine.decide(draft, SESSION, plan_id="p").kind is DecisionKind.EXECUTE


# Feature: agent-orchestration-response, Property 13: A turn carries exactly one valid
# state and advances only along enumerated transitions
@given(
    src=st.sampled_from(list(TurnState)),
    dst=st.one_of(st.sampled_from(list(TurnState)), st.text(min_size=1, max_size=12)),
)
def test_property_13_state_machine(src: TurnState, dst: object) -> None:
    turn = Turn("t", src)
    try:
        target = coerce_state(dst)
    except TurnStateError:
        with pytest.raises(TurnStateError):
            turn.advance(dst)
        assert turn.state is src
        return
    if (src, target) in TRANSITIONS:
        assert turn.advance(target) is target
        assert turn.state is target
    else:
        with pytest.raises(TurnStateError):
            turn.advance(target)
        assert turn.state is src
    assert isinstance(turn.state, TurnState)


TURNS = {
    "show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"]),
    "parts with torque over 120 in-lbs": interp(
        "FILTER_SEARCH", filter_ast=pred("torque_inlbs", "GT", "120", "in-lbs")
    ),
    "something vague": interp("FOLLOWUP", confident=False, alternative_interpretations=2),
    "what about the weather": interp("OUT_OF_SCOPE"),
    "compare 76-100 and 76-200": interp("COMPARISON", part_numbers=["76-100", "76-200"]),
}


# Feature: agent-orchestration-response, Property 14: No SQL transaction spans a
# model-provider call
@given(messages=st.lists(st.sampled_from(sorted(TURNS)), min_size=1, max_size=4))
def test_property_14_no_transaction_across_model_call(messages: list[str]) -> None:
    h = make_harness(TURNS)  # fakes assert no open txn when a model is called
    sid, oid = uuid.uuid4(), uuid.uuid4()
    for m in messages:
        h.run(sid, oid, m)
    events = h.events
    for i, (kind, _) in enumerate(events):
        if kind == "model":
            # A committed state record immediately precedes and follows each call.
            assert events[i - 1][0] == "record"
            assert i + 1 < len(events) and events[i + 1][0] == "record"


# Feature: agent-orchestration-response, Property 15: Clarification and confirmation
# gates block execution and budget-consuming tools
@given(
    d_session=st.booleans(),
    d_plan=st.booleans(),
    d_rev=st.booleans(),
    d_user=st.booleans(),
    bound=st.booleans(),
)
def test_property_15_gates_block_execution(
    d_session: bool, d_plan: bool, d_rev: bool, d_user: bool, bound: bool
) -> None:
    table = {
        "something vague": interp("FOLLOWUP", confident=False, alternative_interpretations=2),
        "rank those over 120 in-lbs": interp(
            "RECOMMENDATION",
            ranking_requested=True,
            filter_ast=pred("torque_inlbs", "GT", "120", "in-lbs"),
            criteria=[{"description": "t", "group": "REQUIRED_TORQUE", "status": "SPECIFIED"}],
            proposed_priorities=[{"key": "torque_inlbs", "direction": "DESC"}],
        ),
    }
    h = make_harness(table)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    clar = h.run(sid, oid, "something vague")
    assert clar.state is TurnState.NEEDS_CLARIFICATION and clar.invocations == []
    # A confirmation is not a reply to the clarification: nothing executes.
    stray = h.run(sid, oid, confirmation=ConfirmationSignal(sid, "x", 1, oid, True))
    assert stray.invocations == [] and TurnState.EXECUTING not in stray.history
    # Awaiting confirmation: only the exact authenticated 4-tuple executes.
    conf = h.run(sid, oid, "rank those over 120 in-lbs")
    assert conf.state is TurnState.AWAITING_CONFIRMATION and conf.invocations == []
    pending = h.states.data[(sid, oid)].pending_plan
    assert pending is not None
    sig = ConfirmationSignal(
        uuid.uuid4() if d_session else sid,
        "other" if d_plan else pending.plan_id,
        pending.plan_revision + 1 if d_rev else pending.plan_revision,
        uuid.uuid4() if d_user else oid,
        bound,
    )
    reads_before = len(h.catalog.repo.reads)
    model_before = len(h.chat.calls)
    res = h.run(sid, oid, confirmation=sig)
    exact = not (d_session or d_plan or d_rev or d_user) and bound
    if exact:
        assert TurnState.EXECUTING in res.history and res.invocations
    else:
        assert res.invocations == [] and TurnState.EXECUTING not in res.history
        assert len(h.catalog.repo.reads) == reads_before
        assert len(h.chat.calls) == model_before


# Feature: agent-orchestration-response, Property 16: Cancellation and source withdrawal
# terminate without resurrection or new recommendation
@given(cancel=st.booleans(), withdrawn=st.booleans())
def test_property_16_cancel_and_withdrawn(cancel: bool, withdrawn: bool) -> None:
    rec_msg = "recommend actuators with torque over 120 in-lbs"
    table = {
        "show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"]),
        rec_msg: interp(
            "RECOMMENDATION",
            filter_ast=pred("torque_inlbs", "GT", "120", "in-lbs"),
            criteria=[{"description": "t", "group": "REQUIRED_TORQUE", "status": "SPECIFIED"}],
        ),
    }
    h = make_harness(table, withdrawn=withdrawn)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    first = h.run(sid, oid, "show 76-100")  # history: a pinned historical read
    assert first.state is TurnState.COMPLETED
    history_before = h.states.data[(sid, oid)]
    h.cancel.cancelled = cancel
    saves_before = h.states.saves
    res = h.run(sid, oid, rec_msg)
    if withdrawn:
        assert res.state is TurnState.SOURCE_WITHDRAWN
        assert res.invocations == []
        after = h.states.data[(sid, oid)]
        assert (after.focus, after.mentioned, after.last_search_results) == (
            history_before.focus,
            history_before.mentioned,
            history_before.last_search_results,
        )
    elif cancel:
        assert res.state is TurnState.CANCELLED
        assert h.states.saves == saves_before  # no late write resurrects anything
    else:
        assert res.state is TurnState.COMPLETED
