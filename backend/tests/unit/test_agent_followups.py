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
