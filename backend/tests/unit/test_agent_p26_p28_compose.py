"""Spec 4 Properties 26-28: number tracing, claim verification, composition rules."""

from __future__ import annotations

import uuid
from decimal import Decimal

from _agent_fakes import interp, lazy, make_harness, make_part, pred
from _fakes import FakeRepository
from hypothesis import given
from hypothesis import strategies as st
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from series76_agent.claim_verifier import ClaimVerifier
from series76_agent.domain.claims import Claim, ClaimKind, Verdict
from series76_agent.domain.enums import CriterionLabel
from series76_agent.domain.figures import VerifiedFigureSet, same_service
from series76_agent.rendering import untraceable_digit_runs
from series76_data.models.enums import SupplyMode
from series76_domain.operations.get_part import get_part
from series76_domain.repository.port import PinnedEdition

decimals = st.one_of(
    st.integers(1, 999).map(str),
    st.tuples(st.integers(0, 99), st.integers(0, 99)).map(lambda t: f"{t[0]}.{t[1]:02d}"),
)
maybe = st.one_of(st.none(), decimals)


def _repo(values: list[tuple[str | None, str | None, int]]) -> FakeRepository:
    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True)
    repo = FakeRepository(pinned=edition)
    for i, (torque, fla, volts) in enumerate(values):
        repo.add(
            make_part(
                f"76-P{i}",
                edition.edition_id,
                services={"On/Off": (torque, None)},
                measurements=((60, "15", fla, "4"),),
                voltage=volts,
                modes=frozenset({SupplyMode.AC}),
            )
        )
    return repo


def _outside_spans(answer: object) -> str:
    text = answer.text  # type: ignore[attr-defined]
    out, cursor = [], 0
    for s in sorted(answer.spans, key=lambda x: x.start):  # type: ignore[attr-defined]
        out.append(text[cursor : s.start])
        cursor = max(cursor, s.end)
    out.append(text[cursor:])
    return "".join(out)


def _chatty(messages: list[BaseMessage], tool_names: list[str]) -> AIMessage:
    """Follows the plan, then 'answers' with invented numbers (must never show)."""

    from _agent_fakes import follow_plan

    if any(isinstance(m, ToolMessage) for m in messages):
        return AIMessage(content="The torque is 98765 in-lbs and FLA 4321 A. DONE")
    return follow_plan(messages, tool_names)


# Feature: agent-orchestration-response, Property 26: Every visible technical figure traces
# to exactly one Spec 2 fact or deterministic derivation
@given(
    values=st.lists(st.tuples(maybe, maybe, st.sampled_from([24, 120])), min_size=2, max_size=3),
    responder=st.sampled_from(["chatty", "lazy"]),
)
def test_property_26_every_visible_figure_traces(
    values: list[tuple[str | None, str | None, int]], responder: str
) -> None:
    repo = _repo(values)
    pns = [f"76-P{i}" for i in range(len(values))]
    table = {
        f"show {pns[0]}": interp("EXACT_LOOKUP", part_numbers=[pns[0]]),
        "compare " + " and ".join(pns): interp(
            "COMPARISON", part_numbers=pns, presentation="BAR_CHART"
        ),
        "torque at least 1 in-lbs": interp(
            "FILTER_SEARCH", filter_ast=pred("torque_inlbs", "GE", "1", "in-lbs")
        ),
    }
    h = make_harness(table, repo=repo, responder=_chatty if responder == "chatty" else lazy)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    for message in table:
        res = h.run(sid, oid, message)
        answer = res.response.answer
        assert untraceable_digit_runs(answer) == []
        outside = _outside_spans(answer)
        assert "98765" not in outside and "4321" not in outside and "999" not in outside
        for s in answer.spans:
            if s.kind == "figure":  # inside a figure slot: only the bound figure's text
                assert answer.text[s.start : s.end].split(" ")[0] in (
                    {bf.value_text for bf in res.response.presented} | {"N/A", "not", "unverified"}
                )
        presented = {bf.figure_id: bf for bf in res.response.presented}
        assert set(answer.figure_ids) <= set(presented)
        for block in res.response.blocks:
            for dto in getattr(block, "figures", []):
                bf = presented[dto.figure_id]
                assert dto.value == bf.value_text and dto.status == bf.status.value
            for row in getattr(block, "metric_rows", []):
                for dto in row.cells:
                    assert presented[dto.figure_id].value_text == dto.value
            for point in getattr(block, "points", []):
                assert presented[point.figure.figure_id].value_text == point.figure.value


claim_kinds = st.sampled_from(list(ClaimKind))


# Feature: agent-orchestration-response, Property 27: Claims are verified
# deterministically under compatible context before display
@given(
    a=st.tuples(maybe, st.sampled_from(["On/Off", "Modulating"]), st.sampled_from([24, 120])),
    b=st.tuples(maybe, st.sampled_from(["On/Off", "Modulating"]), st.sampled_from([24, 120])),
    kind=claim_kinds,
    claim_service=st.sampled_from([None, "On/Off", "Modulating", "Floating"]),
    unit=st.sampled_from([None, "in-lbs", "Nm"]),
    required=st.booleans(),
)
def test_property_27_claims_verified_deterministically(
    a, b, kind, claim_service, unit, required
) -> None:
    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True)
    repo = FakeRepository(pinned=edition)
    for pn, (torque, service, volts) in (("76-CA", a), ("76-CB", b)):
        repo.add(
            make_part(
                pn,
                edition.edition_id,
                services={service: (torque, None)},
                measurements=((60, torque, "1", "2"),),
                voltage=volts,
                modes=frozenset({SupplyMode.AC}),
            )
        )
    figset = VerifiedFigureSet(edition_id=edition.edition_id)
    for pn in ("76-CA", "76-CB"):
        view = get_part(repo, pn).view
        assert view is not None
        figset.add_part_view(view)
    claim = Claim(
        kind,
        "76-CA",
        "76-CB",
        service=claim_service,
        unit=unit,
        value_text=claim_service,
        required=required,
    )
    verifier = ClaimVerifier()
    result = verifier.verify(claim, figset)
    assert verifier.verify(claim, figset) == result  # deterministic
    # Independent oracle for the numeric torque claim.
    if kind is ClaimKind.HAS_MORE_TORQUE:
        key = {"in-lbs": "torque_inlbs", "Nm": "torque_nm"}.get(unit or "")
        left = figset.select("76-CA", key, service=claim_service) if key else []
        right = figset.select("76-CB", key, service=claim_service) if key else []
        ok = (
            key is not None
            and len(left) == len(right) == 1
            and left[0].context_key == right[0].context_key
            and left[0].figure.direct is not None
            and right[0].figure.direct is not None
        )
        if not ok:
            assert result.verdict is Verdict.UNVERIFIABLE
        else:
            holds = left[0].figure.direct.value > right[0].figure.direct.value
            assert result.verdict is (Verdict.VERIFIED if holds else Verdict.REFUTED)
    if kind is ClaimKind.SUPPORTS_SERVICE and claim_service is not None:
        expected = any(same_service(s, claim_service) for s in figset.services["76-CA"])
        assert result.verdict is (Verdict.VERIFIED if expected else Verdict.REFUTED)
    if kind is ClaimKind.LOWER_ENERGY_CONSUMPTION:
        assert result.verdict is Verdict.UNVERIFIABLE  # never stated as fact
    assert result.visible == (result.verdict is Verdict.VERIFIED)
    report = verifier.verify_all([claim], figset)
    assert report.insufficient_information == (required and not result.visible)
    assert all(r.verdict is Verdict.VERIFIED for r in report.visible)


# Feature: agent-orchestration-response, Property 28: User figures are labeled
# Declared_Requirement, charts come from backend facts, and N/A is never zero
@given(n=st.integers(1, 300), t0=maybe, t1=maybe, hetero=st.booleans())
def test_property_28_declared_charts_na(
    n: int, t0: str | None, t1: str | None, hetero: bool
) -> None:
    repo = _repo([(t0, "1.5", 24), (t1, "2.5", 120 if hetero else 24)])
    search_msg = f"torque at least {n} in-lbs"
    table = {
        search_msg: interp(
            "FILTER_SEARCH",
            filter_ast=pred("torque_inlbs", "GE", str(n), "in-lbs"),
            criteria=[
                {
                    "description": "minimum torque",
                    "group": "REQUIRED_TORQUE",
                    "status": "SPECIFIED",
                    "declared_value": str(n),
                    "declared_unit": "in-lbs",
                }
            ],
        ),
        "compare 76-P0 and 76-P1": interp(
            "COMPARISON", part_numbers=["76-P0", "76-P1"], presentation="BAR_CHART"
        ),
    }
    h = make_harness(table, repo=repo)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    res = h.run(sid, oid, search_msg)
    answer = res.response.answer
    # The user's figure appears only inside a user-echo span, never as a catalog spec.
    for s in answer.spans:
        if str(n) in answer.text[s.start : s.end] and s.kind not in ("count", "identifier"):
            assert s.kind == "user"
    summary = res.response.summary
    assert summary is not None
    declared = [i for i in summary.all_items() if str(n) in i.text]
    assert declared and all(i.label is CriterionLabel.USER_ASSUMPTION for i in declared)

    cmp = h.run(sid, oid, "compare 76-P0 and 76-P1")
    for block in cmp.response.blocks:
        if block.kind.value == "bar_chart":
            available = [p for p in block.points if p.figure.value is not None]
            assert block.labels == [p.label for p in available]
            assert block.values == [float(Decimal(p.figure.value)) for p in available]
            for p in block.points:
                if p.figure.value is None:
                    assert p.label not in block.labels  # N/A never a (zero) bar
        if block.kind.value == "comparison_table":
            for row in block.metric_rows:
                if any(c.value is None for c in row.cells):
                    assert row.winner_part_number is None
    text = cmp.response.answer.text
    fla_mixed = hetero
    assert ("do not indicate" in text or "does not indicate" in text) == fla_mixed
    assert not any(
        c.claim.kind is ClaimKind.LOWER_ENERGY_CONSUMPTION and c.visible
        for c in cmp.response.claims
    )
