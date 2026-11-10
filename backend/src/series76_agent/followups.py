"""Deterministic settling of a resolved draft before policy (zero LLM).

The interpreter is a model and can label a clear turn as a vague follow-up or
miss that a question asks for something the source never documents. These
rules run after context resolution, on the draft plus the persisted focus, and
never invent a part number, a value or a scope:

* **Undocumented attribute** (price, manufacturer, warranty, ...): the turn is
  out of scope and abstains, whatever else was interpreted (Spec 4 fallback h).
* **Named part judged out of scope**: a message naming a part number and asking
  nothing undocumented is a lookup of that part.
* **Resolved follow-up**: a ``FOLLOWUP`` whose references already resolved to
  part numbers ("show me the second one") is a lookup of exactly those parts.
* **Metric about the focus**: a question naming a documented metric but no part
  ("and how much power does it draw?") is a lookup of the single part in focus.
* **Refinement of the focus**: a ``FOLLOWUP`` naming only a documented
  frequency ("and at the lower frequency?") applies to the single part in focus.
* **Language switch**: a message that only asks for another language repeats
  the lookup of the single part in focus in that language.
"""

from __future__ import annotations

import re
from dataclasses import replace

from series76_agent.domain.enums import Intent, Provenance, ReferentKind
from series76_agent.domain.plan import DraftPlan, Referent
from series76_agent.language import explicit_switch

#: Attributes the source PDF never documents (EN/ES stems).
_UNDOCUMENTED = re.compile(
    r"\b(price|prices|pricing|cost|costs|precio|precios|cu[aá]nto cuesta|costo|"
    r"coste|manufactur\w*|maker|fabric\w*|brand|marca|warranty|garant[ií]a|weight|peso|"
    r"lead time|stock|availability|disponibilidad|plazo de entrega|delivery)\b",
    re.IGNORECASE,
)
#: The catalog documents exactly two frequencies (column headings "60 Hz", "50 Hz").
_DOCUMENTED_HZ = ("50", "60")
_LOWER = re.compile(r"\b(lower|lowest|low|baja|menor|m[ií]nima)\b", re.IGNORECASE)
_HIGHER = re.compile(r"\b(higher|highest|high|alta|mayor|m[aá]xima)\b", re.IGNORECASE)
_FREQUENCY = re.compile(r"\b(frequency|frecuencia|hz)\b", re.IGNORECASE)
_EXPLICIT_HZ = re.compile(r"\b(50|60)\s*hz\b", re.IGNORECASE)
#: A message that is only a language request ("responde en español", "in English please").
_ONLY_LANGUAGE = re.compile(
    r"^\s*(?:please\s+|por favor\s+)?(?:answer|reply|respond|responde|contesta|resp[oó]ndeme|"
    r"dímelo|dimelo|tell me)?\s*(?:it\s+|lo\s+)?(?:in|en)\s+(?:english|ingl[eé]s|spanish|"
    r"espa[nñ]ol|castellano)(?:\s*,?\s*(?:please|por favor))?\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def asks_undocumented_attribute(message: str) -> bool:
    """True iff the message asks for an attribute the source never documents."""
    return bool(_UNDOCUMENTED.search(message))


def _frequency_qualifier(message: str) -> str | None:
    explicit = _EXPLICIT_HZ.search(message)
    if explicit:
        return explicit.group(1)
    if not _FREQUENCY.search(message):
        return None
    if _LOWER.search(message):
        return min(_DOCUMENTED_HZ, key=int)
    if _HIGHER.search(message):
        return max(_DOCUMENTED_HZ, key=int)
    return None


def _focus_referent(pn: str) -> Referent:
    return Referent(text=pn, kind=ReferentKind.PART_NUMBER, provenance=Provenance.PRIOR_TURN,
                    part_number=pn)


def settle_turn(draft: DraftPlan, message: str, focus: tuple[str, ...]) -> DraftPlan:
    """Apply the deterministic settling rules (see module docstring)."""

    if asks_undocumented_attribute(message):
        return replace(draft, intent=Intent.OUT_OF_SCOPE)
    if draft.intent is Intent.OUT_OF_SCOPE and any(
        r.provenance is Provenance.CURRENT_MESSAGE for r in draft.referents
        if r.part_number is not None
    ):
        # The message names a part and asks nothing undocumented: showing its
        # documented data is in scope (a lookup can only show printed facts).
        return replace(draft, intent=Intent.EXACT_LOOKUP)
    single_focus = focus[0] if len(set(focus)) == 1 else None
    if _ONLY_LANGUAGE.match(message) and explicit_switch(message) is not None:
        if single_focus is not None:
            return replace(draft, intent=Intent.EXACT_LOOKUP,
                           referents=(_focus_referent(single_focus),))
        return draft
    if (draft.requested_metrics and not draft.part_numbers and single_focus is not None
            and draft.intent in (Intent.FOLLOWUP, Intent.EXACT_LOOKUP, Intent.OUT_OF_SCOPE)
            and draft.filter_ast is None):
        # "and how much power does it draw?": a documented metric about the single
        # part in focus, without repeating its part number.
        return replace(draft, intent=Intent.EXACT_LOOKUP,
                       frequency_hz=_frequency_qualifier(message) or draft.frequency_hz,
                       referents=(_focus_referent(single_focus),))
    if draft.intent is not Intent.FOLLOWUP:
        return draft
    if draft.part_numbers:
        return replace(draft, intent=Intent.EXACT_LOOKUP)
    hz = _frequency_qualifier(message)
    if hz is not None and single_focus is not None:
        return replace(draft, intent=Intent.EXACT_LOOKUP, frequency_hz=hz,
                       referents=(_focus_referent(single_focus),))
    return draft
