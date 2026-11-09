"""Spec 4 Properties 17-21: transparency, single pass, gates, confirmation."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from _agent_fakes import interp, make_harness, pred
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.composer import ResponseComposer
from series76_agent.domain.enums import (
    CriterionLabel,
    Intent,
    Language,
    PresentationIntent,
    Provenance,
    ReferentKind,
    Strength,
    TurnState,
)
from series76_agent.domain.plan import Criterion, DraftPlan, Referent, UnresolvedItem
from series76_agent.policy import ConfirmationSignal
from series76_agent.tools import TOOL_SET_A, TOOL_SET_B
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, Operator, Predicate
from series76_domain.services.rank_candidates import RankPriority, SortDirection

FORBIDDEN_INTERNALS = (
    *TOOL_SET_A,
    *TOOL_SET_B,
    "filter_ast",
    "catalog_edition_id",
    "edition_id",
    "require_parameters",
    "max_tool_calls",
    "trace_id",
    "system prompt",
    "You interpret",
    "You retrieve",
    *[f.value for f in AllowlistField if "_" in f.value],
)

summary_drafts = st.builds(
    lambda intent, lang, pres, crit_status, strength, declared, pns, prio, unresolved: DraftPlan(
        intent=intent,
        response_language=lang,
        presentation_intent=pres,
        referents=tuple(
            Referent(p, ReferentKind.PART_NUMBER, Provenance.CURRENT_MESSAGE, p) for p in pns
        ),
        criteria=(
            Criterion(
                "torque requirement",
                crit_status,
                strength,
                RequirementGroup.REQUIRED_TORQUE,
                AllowlistField.TORQUE_INLBS,
                declared,
                "in-lbs" if declared else None,
            ),
        ),
        filter_ast=Predicate(AllowlistField.SERVICE, Operator.EQ, "On/Off"),
        proposed_priorities=(RankPriority("torque_inlbs", SortDirection.DESC),) if prio else (),
        unresolved=(UnresolvedItem("FIELD", "ip rating", "x"),) if unresolved else (),
    ),
    st.sampled_from(list(Intent)),
    st.sampled_from(list(Language)),
    st.sampled_from(list(PresentationIntent)),
    st.sampled_from(list(CoverageStatus)),
    st.sampled_from(list(Strength)),
    st.one_of(st.none(), st.integers(1, 500).map(str)),
    st.lists(st.from_regex(r"76-[0-9]{3}", fullmatch=True), max_size=2),
    st.booleans(),
    st.booleans(),
)


# Feature: agent-orchestration-response, Property 17: The Interpretation_Summary is
# always visible, fully labeled, and leaks no internals
@given(draft=summary_drafts)
def test_property_17_summary_visible_labeled_no_internals(draft: DraftPlan) -> None:
    summary = ResponseComposer().summary(draft, draft.response_language)
    assert summary.intent and summary.expected_presentation_format
    for name in ("applied", "proposed", "delegated", "ignored"):
        assert isinstance(getattr(summary, name), tuple)
    items = summary.all_items()
    assert items, "a criterion-bearing plan lists at least one criterion"
    assert all(isinstance(i.label, CriterionLabel) for i in items)
    text = summary.all_text()
    for token in FORBIDDEN_INTERNALS:
        assert token not in text
    # Delivered with the turn itself (no extra action): the turn envelope carries it.
    h = make_harness({"show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"])})
    res = h.run(uuid.uuid4(), uuid.uuid4(), "show 76-100")
    assert res.response.summary is not None


# Feature: agent-orchestration-response, Property 18: Determinate exact or single-filter
# queries execute in one pass
@given(
    pn=st.sampled_from(["76-100", "76-200", "76-300"]),
    tool_set=st.sampled_from(["A", "B"]),
    n=st.integers(50, 250),
)
def test_property_18_single_pass(pn: str, tool_set: str, n: int) -> None:
    allow = TOOL_SET_A if tool_set == "A" else TOOL_SET_B
    table = {
        f"show {pn}": interp("EXACT_LOOKUP", part_numbers=[pn]),
        f"torque at least {n} in-lbs": interp(
            "FILTER_SEARCH", filter_ast=pred("torque_inlbs", "GE", str(n), "in-lbs")
        ),
        "show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"]),
    }
    h = make_harness(table, allow=allow, tool_set=tool_set)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    for message in table:
        res = h.run(sid, oid, message)
        assert res.state is TurnState.COMPLETED
        assert res.response.status == "COMPLETED"
        assert not any(b.kind.value == "plan_review" for b in res.response.blocks)
        assert h.plans.created == []
    # Multi-measurement part: every applicable measurement, labeled, in one pass.
    res = h.run(sid, oid, "show 76-100")
    card = next(b for b in res.response.blocks if b.kind.value == "product_card")
    fla = [f for f in card.figures if f.metric_key == "fla"]
    assert {f.frequency_hz for f in fla} == {"50", "60"}
    torque = [f for f in card.figures if f.metric_key == "torque_inlbs"]
    assert {f.service for f in torque} == {"On/Off", "Modulating"}
    shown = {s.ref for s in res.response.answer.spans if s.kind == "figure"}
    for f in fla + torque:
        assert f.figure_id in shown


GATED: dict[str, Any] = {
    "ambiguous": interp(
        "FILTER_SEARCH", alternative_interpretations=2, filter_ast=pred("torque_inlbs", "GE", "100")
    ),
    "conflict": interp(
        "FILTER_SEARCH", conflicting_statements=True, filter_ast=pred("torque_inlbs", "GE", "100")
    ),
    "boolean": interp(
        "FILTER_SEARCH",
        boolean_precedence_ambiguous=True,
        filter_ast={
            "type": "or",
            "children": [pred("torque_inlbs", "GE", "100"), pred("service", "EQ", "On/Off")],
        },
    ),
    "delegation": interp(
        "RECOMMENDATION",
        delegation_changes_results=True,
        filter_ast=pred("torque_inlbs", "GE", "100"),
        criteria=[{"description": "t", "group": "REQUIRED_TORQUE", "status": "SPECIFIED"}],
    ),
    "proposal": interp(
        "RECOMMENDATION",
        top_one=True,
        filter_ast=pred("torque_inlbs", "GE", "100"),
        criteria=[{"description": "t", "group": "REQUIRED_TORQUE", "status": "SPECIFIED"}],
        proposed_priorities=[{"key": "torque_inlbs", "direction": "DESC"}],
    ),
}


# Feature: agent-orchestration-response, Property 19: Ambiguity, conflict, material
# delegation, or an unaccepted proposal forces clarification or confirmation
@given(kind=st.sampled_from(sorted(GATED)))
def test_property_19_gates_force_clarification_or_confirmation(kind: str) -> None:
    message = f"{kind} request about 100"
    h = make_harness({message: GATED[kind]})
    res = h.run(uuid.uuid4(), uuid.uuid4(), message)
    assert res.state in (TurnState.NEEDS_CLARIFICATION, TurnState.AWAITING_CONFIRMATION)
    assert res.response.status in ("NEEDS_CLARIFICATION", "AWAITING_CONFIRMATION")
    assert res.invocations == [] and h.catalog.repo.reads == [] and h.chat.calls == []


REC = "rank those over 120 in-lbs"
REC_OUT = interp(
    "RECOMMENDATION",
    ranking_requested=True,
    filter_ast=pred("torque_inlbs", "GT", "120", "in-lbs"),
    criteria=[{"description": "t", "group": "REQUIRED_TORQUE", "status": "SPECIFIED"}],
    proposed_priorities=[{"key": "torque_inlbs", "direction": "DESC"}],
)


# Feature: agent-orchestration-response, Property 20: Confirmation materializes only on an
# exact 4-tuple match and corrections invalidate prior approval
@given(corrections=st.integers(0, 3), target=st.integers(0, 3))
def test_property_20_exact_tuple_and_corrections(corrections: int, target: int) -> None:
    h = make_harness({REC: REC_OUT})
    sid, oid = uuid.uuid4(), uuid.uuid4()
    signals: list[ConfirmationSignal] = []
    revisions: list[int] = []
    for _ in range(corrections + 1):
        h.run(sid, oid, REC)
        p = h.states.data[(sid, oid)].pending_plan
        assert p is not None
        revisions.append(p.plan_revision)
        signals.append(ConfirmationSignal(sid, p.plan_id, p.plan_revision, oid, True))
    assert revisions == sorted(set(revisions))  # strictly increasing
    idx = min(target, len(signals) - 1)
    before = h.states.data[(sid, oid)]
    res = h.run(sid, oid, confirmation=signals[idx])
    if idx == len(signals) - 1:
        assert TurnState.EXECUTING in res.history
    else:
        assert res.state is TurnState.STALE_PLAN and res.invocations == []
        assert h.states.data[(sid, oid)] == before  # active state not mutated
        assert str(revisions[-1]) in res.response.answer.text  # current revision shown


# Feature: agent-orchestration-response, Property 21: Confirmed execution occurs only after
# the Spec 3 seam binds the current revision, and is idempotent
@given(bound=st.booleans(), repeats=st.integers(1, 4))
def test_property_21_bound_and_idempotent(bound: bool, repeats: int) -> None:
    h = make_harness({REC: REC_OUT})
    sid, oid = uuid.uuid4(), uuid.uuid4()
    h.run(sid, oid, REC)
    p = h.states.data[(sid, oid)].pending_plan
    assert p is not None
    sig = ConfirmationSignal(sid, p.plan_id, p.plan_revision, oid, bound)
    executions = 0
    for _ in range(repeats):
        res = h.run(sid, oid, confirmation=sig)
        executions += int(TurnState.EXECUTING in res.history)
    assert executions == (1 if bound else 0)
    assert Decimal(0) <= h.ledger.total_spent
