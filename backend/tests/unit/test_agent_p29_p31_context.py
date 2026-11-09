"""Spec 4 Properties 29-31: multi-turn context, edition/language, abstention."""

from __future__ import annotations

import uuid

from _agent_fakes import interp, make_harness, visible_text
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.context import ContextResolver, ResolutionStatus
from series76_agent.domain.conversation import new_state
from series76_agent.domain.enums import Intent, Language, Provenance, ReferentKind, TurnState
from series76_agent.domain.plan import DraftPlan, Referent
from series76_agent.language import resolve_language
from series76_agent.ports import EditionInfo

pn_lists = st.lists(
    st.sampled_from(["76-100", "76-200", "76-300", "76-T03"]), max_size=4, unique=True
)


# Feature: agent-orchestration-response, Property 29: Follow-up references resolve only
# against persisted owner-scoped state or else request clarification
@given(
    search=pn_lists,
    comparison=pn_lists,
    focus=pn_lists,
    n=st.integers(1, 5),
    anaphora=st.booleans(),
    foreign=st.booleans(),
)
def test_property_29_references_resolve_only_from_owner_state(
    search: list[str],
    comparison: list[str],
    focus: list[str],
    n: int,
    anaphora: bool,
    foreign: bool,
) -> None:
    sid, oid = uuid.uuid4(), uuid.uuid4()
    state = new_state(uuid.uuid4() if foreign else sid, oid).evolve(
        last_search_results=tuple(search),
        last_comparison_set=tuple(comparison),
        focus=tuple(focus),
    )
    ref = (
        Referent("that one", ReferentKind.ANAPHORA, Provenance.PRIOR_TURN)
        if anaphora
        else Referent(f"#{n}", ReferentKind.ORDINAL, Provenance.PRIOR_TURN, ordinal=n)
    )
    draft = DraftPlan(intent=Intent.EXACT_LOOKUP, response_language=Language.EN, referents=(ref,))
    res = ContextResolver().resolve(draft, state, session_id=sid, owner_id=oid)
    if foreign:
        assert res.status is ResolutionStatus.UNMATCHED  # never another conversation's state
        return
    if anaphora:
        expected = {1: ResolutionStatus.RESOLVED, 0: ResolutionStatus.UNMATCHED}.get(
            len(focus), ResolutionStatus.AMBIGUOUS
        )
        assert res.status is expected
        if expected is ResolutionStatus.RESOLVED:
            assert res.draft.part_numbers == (focus[0],)
        return
    picks = {pool[n - 1] for pool in (search, comparison) if pool and len(pool) >= n}
    if not picks:
        assert res.status is ResolutionStatus.UNMATCHED
    elif len(picks) > 1:
        assert res.status is ResolutionStatus.AMBIGUOUS and set(res.candidates) == picks
    else:
        assert res.status is ResolutionStatus.RESOLVED
        assert res.draft.part_numbers == (next(iter(picks)),)
    # End to end + restart: a fresh orchestrator over the same store resolves
    # identically; an unresolved reference pauses in NEEDS_CLARIFICATION.
    table = {"show the one": interp("EXACT_LOOKUP", ordinal_references=[n])}
    h = make_harness(table)
    h.states.data[(sid, oid)] = state
    out = h.run(sid, oid, "show the one")
    if res.status is ResolutionStatus.RESOLVED:
        assert out.state is TurnState.COMPLETED or out.outcome.value == "PART_NOT_LISTED"
    else:
        assert out.state is TurnState.NEEDS_CLARIFICATION and out.invocations == []


messages = st.lists(
    st.sampled_from(
        [
            ("muestra los datos de 76-100", Language.ES),
            ("show me the data for 76-100", Language.EN),
            ("76-100", None),
            ("2", None),
            ("¿cuál es el par de 76-100?", Language.ES),
            ("answer in english please, muestra 76-100", Language.EN),
        ]
    ),
    min_size=1,
    max_size=6,
)


# Feature: agent-orchestration-response, Property 30: A conversation is pinned to one
# edition and the response language follows the resolution rule
@given(seq=messages, change_edition=st.booleans())
def test_property_30_edition_pinned_and_language_rule(
    seq: list[tuple[str, Language | None]], change_edition: bool
) -> None:
    table = {m: interp("EXACT_LOOKUP", part_numbers=["76-100"]) for m, _ in seq}
    h = make_harness(table)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    previous: Language | None = None
    editions = set()
    for message, expected in seq:
        res = h.run(sid, oid, message)
        lang = resolve_language(message, previous)
        if expected is not None:
            assert lang is expected
        else:
            assert lang is (previous or Language.EN)  # no natural language: keep prior
        assert h.states.data[(sid, oid)].language is lang
        previous = lang
        editions.add(h.states.data[(sid, oid)].catalog_edition_id)
        assert res.edition_id == h.edition.edition_id
    assert len(editions) == 1
    if change_edition:
        # Another edition can never replace the pinned one mid-conversation.
        h.editions.edition = EditionInfo(uuid.uuid4())
        res = h.run(sid, oid, seq[0][0])
        assert res.state is TurnState.FAILED and res.invocations == []
        assert h.states.data[(sid, oid)].catalog_edition_id in editions


# Feature: agent-orchestration-response, Property 31: Out-of-scope requests abstain naming
# the pinned edition with no untraceable fact, and well-formed absent PNs report not-listed
@given(
    question=st.sampled_from(
        [
            "what is the price of a 76-100",
            "who invented actuators",
            "cuál es el clima hoy",
            "give me the IP67 certificate list",
        ]
    ),
    absent=st.from_regex(r"ZZ-[0-9]{4}", fullmatch=True),
)
def test_property_31_abstain_and_not_listed(question: str, absent: str) -> None:
    table = {
        question: interp("OUT_OF_SCOPE"),
        f"show {absent}": interp("EXACT_LOOKUP", part_numbers=[absent]),
    }
    h = make_harness(table)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    res = h.run(sid, oid, question)
    assert res.outcome.value == "OUT_OF_SCOPE" and res.invocations == []
    assert str(h.edition.edition_id)[:8] in res.response.answer.text
    assert res.response.presented == [] and res.response.blocks == []
    nl = h.run(sid, oid, f"show {absent}")
    assert nl.outcome.value == "PART_NOT_LISTED"
    text = visible_text(nl)
    assert "not listed" in text
    for other in ("76-100", "76-200", "76-300", "76-T03"):
        assert other not in text  # no substitution
    for claim in ("does not exist", "doesn't exist", "discontinued", "no existe"):
        assert claim not in text.lower()
