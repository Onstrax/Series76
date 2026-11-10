"""Deterministic settling of resolved drafts (followups.settle_turn)."""

from __future__ import annotations

from series76_agent.domain.enums import Intent, Language, Provenance, ReferentKind
from series76_agent.domain.plan import DraftPlan, Referent
from series76_agent.followups import asks_undocumented_attribute, settle_turn

PN = "761A00-11300000/A"


def _draft(intent: Intent, *pns: str) -> DraftPlan:
    refs = tuple(Referent(text=p, kind=ReferentKind.PART_NUMBER,
                          provenance=Provenance.CURRENT_MESSAGE, part_number=p) for p in pns)
    return DraftPlan(intent=intent, response_language=Language.EN, referents=refs)


def test_undocumented_attributes_abstain_whatever_the_model_said() -> None:
    for msg in (f"What is the price of {PN}?", "¿Quién fabrica estos actuadores?",
                f"¿Cuánto cuesta el {PN}?", "What warranty do they have?"):
        assert settle_turn(_draft(Intent.EXACT_LOOKUP, PN), msg, ()).intent is Intent.OUT_OF_SCOPE
    for msg in (f"Torque of {PN}", "Corriente a 50 Hz", "Parts with torque over 3,980 in-lbs"):
        assert not asks_undocumented_attribute(msg)


def test_a_resolved_followup_is_a_lookup_of_the_resolved_part() -> None:
    settled = settle_turn(_draft(Intent.FOLLOWUP, PN), "Muéstrame la segunda", ())
    assert settled.intent is Intent.EXACT_LOOKUP and settled.part_numbers == (PN,)


def test_a_frequency_refinement_applies_to_the_single_focus_only() -> None:
    lower = settle_turn(_draft(Intent.FOLLOWUP), "And at the lower frequency?", (PN,))
    assert lower.intent is Intent.EXACT_LOOKUP and lower.frequency_hz == "50"
    assert lower.part_numbers == (PN,)
    assert settle_turn(_draft(Intent.FOLLOWUP), "¿Y a la frecuencia alta?", (PN,)
                       ).frequency_hz == "60"
    two = settle_turn(_draft(Intent.FOLLOWUP), "And at the lower frequency?", (PN, "762A00-1/A"))
    assert two.intent is Intent.FOLLOWUP  # ambiguous focus: never guessed
    assert settle_turn(_draft(Intent.FOLLOWUP), "And the other one?", (PN,)).intent \
        is Intent.FOLLOWUP


def test_a_pure_language_switch_repeats_the_focus_lookup() -> None:
    switched = settle_turn(_draft(Intent.OUT_OF_SCOPE), "responde en español", (PN,))
    assert switched.intent is Intent.EXACT_LOOKUP and switched.part_numbers == (PN,)
    assert settle_turn(_draft(Intent.OUT_OF_SCOPE), "responde en español", ()).intent \
        is Intent.OUT_OF_SCOPE  # nothing in focus: nothing to repeat
    mixed = settle_turn(_draft(Intent.FILTER_SEARCH), "en español, partes On/Off", (PN,))
    assert mixed.intent is Intent.FILTER_SEARCH  # not only a language request


def test_a_named_part_judged_out_of_scope_is_looked_up() -> None:
    settled = settle_turn(_draft(Intent.OUT_OF_SCOPE, PN),
                          f"Torque of {PN} for On/Off and Modulating", ())
    assert settled.intent is Intent.EXACT_LOOKUP
    assert settle_turn(_draft(Intent.OUT_OF_SCOPE, PN), f"Price of {PN}", ()).intent \
        is Intent.OUT_OF_SCOPE


def test_requested_metrics_are_detected_deterministically() -> None:
    from series76_agent.interpreter import requested_metrics

    assert requested_metrics("and how much power does it draw?") == ("motor_power",)
    assert requested_metrics("¿Qué potencia tiene?") == ("motor_power",)
    assert requested_metrics("Torque of 761A00-11300000/A") == ("torque_inlbs", "torque_nm")
    assert requested_metrics("Corriente del 761A00") == ("fla", "lra")
    assert requested_metrics("Show the data for 761A00-11300000/A") == ()


def test_a_metric_question_without_a_part_applies_to_the_single_focus() -> None:
    from dataclasses import replace

    vague = replace(_draft(Intent.FOLLOWUP), requested_metrics=("motor_power",))
    settled = settle_turn(vague, "and how much power does it draw?", (PN,))
    assert settled.intent is Intent.EXACT_LOOKUP and settled.part_numbers == (PN,)
    assert settle_turn(vague, "and how much power does it draw?", (PN, "762A00-1/A")
                       ).intent is Intent.FOLLOWUP  # two parts in focus: never guessed


def test_assessment_followup_answers_the_motor_power_without_repeating_the_part() -> None:
    """The assessment's own example, end to end through the orchestrator."""

    import uuid

    from _agent_fakes import interp, make_harness, make_part
    from _fakes import FakeRepository

    from series76_domain.repository.port import PinnedEdition

    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True, is_withdrawn=False)
    repo = FakeRepository(pinned=edition)
    repo.add(make_part("76-100", edition.edition_id,
                       services={"On/Off": (100, "11.3"), "Modulating": (90, "10.2")},
                       measurements=((50, 18, "1.2", 3), (60, 15, "1.0", "2.5")),
                       motor_power=40))
    table = {
        "What is the torque of 76-100?": interp("EXACT_LOOKUP", part_numbers=["76-100"]),
        "and how much power does it draw?": interp("FOLLOWUP", confident=False),
    }
    h = make_harness(table, repo=repo)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    first = h.run(sid, oid, "What is the torque of 76-100?")
    assert "100 in-lbs" in first.response.answer.text
    second = h.run(sid, oid, "and how much power does it draw?")
    text = second.response.answer.text
    assert "40 W" in text, text
    assert "in-lbs" not in text  # the answer leads with what was asked


def test_how_much_alone_is_not_a_price_question() -> None:
    assert not asks_undocumented_attribute("and how much power does it draw?")
    assert not asks_undocumented_attribute("How much current does it use?")
    assert asks_undocumented_attribute("How much does it cost?")


def test_debug_trace_shows_the_data_each_tool_returned() -> None:
    """Assessment: the Debug screen shows tools, parameters AND the data returned."""

    import uuid

    from _agent_fakes import interp, make_harness

    from series76_agent.seam import debug_trace
    from series76_api.domain.trace import sanitize_trace

    h = make_harness({"show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"])})
    res = h.run(uuid.uuid4(), uuid.uuid4(), "show 76-100")
    trace = sanitize_trace(debug_trace(res))
    (result,) = [r for r in trace["tool_results"] if r["status"] == "OK"]
    facts = result["data"]["facts"]
    assert {"field": "On/Off:torque_inlbs", "value": "100", "unit": "in-lbs",
            "status": "AVAILABLE"} in facts
    assert trace["tool_args"][0]["arguments"]  # parameters are still there
