"""``DraftPlan`` / ``InterpretedPlan`` and the ``Interpretation_Summary`` model.

The interpreter (an LLM) authors a :class:`DraftPlan`; the deterministic
Policy_Engine stamps the server-validated ``catalog_edition_id`` and plan
identity to produce an :class:`InterpretedPlan` (design § Data Models).

Structural guarantees enforced at construction:

* exactly one :class:`~series76_agent.domain.enums.Intent` (a tuple/list or a
  string is rejected — Req 2.1);
* the filter is a Spec 2 ``Filter_AST`` :class:`~series76_domain.model.Node` or
  ``None`` — a raw string (e.g. SQL) is not representable (Req 2.3);
* there is **no field** through which a catalog figure can enter: the only
  numbers a plan carries are the user's *declared* requirements (predicate
  values / criterion ``declared_value``), each of which the interpreter has
  checked appears verbatim in the user's message (Req 2.6, 8.6).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from series76_agent.domain.enums import (
    CriterionLabel,
    Intent,
    Language,
    PresentationIntent,
    Provenance,
    ReferentKind,
    Strength,
)
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, Node
from series76_domain.services.rank_candidates import RankPriority


class PlanError(ValueError):
    """Raised when a plan violates a structural invariant."""


@dataclass(frozen=True, slots=True)
class Referent:
    """A part number or a reference to a prior product, with provenance.

    Attributes:
        text: the user's literal expression (a PN, "the second one", ...).
        kind: how the referent was expressed.
        provenance: current message or a prior turn (Req 2.4).
        part_number: the canonical PN once resolved, else ``None``.
        ordinal: the 1-based ordinal for an ordinal referent.
    """

    text: str
    kind: ReferentKind
    provenance: Provenance
    part_number: str | None = None
    ordinal: int | None = None

    @property
    def is_resolved(self) -> bool:
        """True iff the referent maps to a concrete part number."""
        return self.part_number is not None


@dataclass(frozen=True, slots=True)
class Criterion:
    """A recommendation/filter criterion with group, status, and strength.

    ``declared_value`` / ``declared_unit`` carry a figure the *user* stated; it
    is always presented as a Declared_Requirement, never a catalog spec.
    """

    description: str
    status: CoverageStatus
    strength: Strength
    group: RequirementGroup | None = None
    field: AllowlistField | None = None
    declared_value: str | None = None
    declared_unit: str | None = None


@dataclass(frozen=True, slots=True)
class UnresolvedItem:
    """A field, PN, referent, or number that could not be resolved (Req 2.10)."""

    kind: str
    text: str
    reason: str


@dataclass(frozen=True, slots=True)
class Ambiguity:
    """Interpretation-level ambiguity signals the policy engine decides on."""

    alternative_interpretations: int = 1
    boolean_precedence_ambiguous: bool = False
    conflicting_statements: bool = False
    delegation_changes_results: bool = False

    @property
    def any(self) -> bool:
        """True iff any signal requires a clarification/confirmation."""
        return (
            self.alternative_interpretations > 1
            or self.boolean_precedence_ambiguous
            or self.conflicting_statements
            or self.delegation_changes_results
        )


@dataclass(frozen=True, slots=True)
class DraftPlan:
    """The interpreter's structured output, before policy validation.

    It deliberately has **no** ``catalog_edition_id``: the edition is stamped
    from the validated session only (Req 2.7).
    """

    intent: Intent
    response_language: Language
    filter_ast: Node | None = None
    referents: tuple[Referent, ...] = ()
    criteria: tuple[Criterion, ...] = ()
    unresolved: tuple[UnresolvedItem, ...] = ()
    presentation_intent: PresentationIntent = PresentationIntent.SIMPLE
    top_one: bool = False
    ranking_requested: bool = False
    accepted_priorities: tuple[RankPriority, ...] = ()
    proposed_priorities: tuple[RankPriority, ...] = ()
    ambiguity: Ambiguity = field(default_factory=Ambiguity)
    service: str | None = None
    frequency_hz: str | None = None
    target_unit: str | None = None
    injection_detected: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.intent, Intent):
            raise PlanError("a plan carries exactly one Intent value")
        if not isinstance(self.response_language, Language):
            raise PlanError("response_language must be a Language")
        if self.filter_ast is not None and not isinstance(self.filter_ast, Node):
            raise PlanError("filter_ast must be a typed Filter_AST node, never raw text/SQL")
        if not isinstance(self.presentation_intent, PresentationIntent):
            raise PlanError("presentation_intent must be a PresentationIntent")

    @property
    def part_numbers(self) -> tuple[str, ...]:
        """Resolved PNs of the referents, in order, de-duplicated."""
        seen: list[str] = []
        for ref in self.referents:
            if ref.part_number is not None and ref.part_number not in seen:
                seen.append(ref.part_number)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class InterpretedPlan:
    """A policy-validated plan bound to the server-pinned edition.

    Attributes:
        draft: the interpreter's draft (possibly with context-resolved
            referents and policy-stripped predicates).
        catalog_edition_id: from the validated session — never a model value.
        plan_id / plan_revision: from the Spec 3 plan surface when a plan is
            persisted for confirmation, else a turn-local id and revision 0.
        permissions: the server permission context the turn runs under.
    """

    draft: DraftPlan
    catalog_edition_id: uuid.UUID
    plan_id: str
    plan_revision: int = 0
    permissions: str = "runtime_reader"

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_edition_id, uuid.UUID):
            raise PlanError("catalog_edition_id must be a server-resolved UUID")
        if self.plan_revision < 0:
            raise PlanError("plan_revision must be non-negative")

    @property
    def intent(self) -> Intent:
        """The plan's single intent."""
        return self.draft.intent


@dataclass(frozen=True, slots=True)
class SummaryItem:
    """One criterion line in the summary, labeled with exactly one category."""

    text: str
    label: CriterionLabel


@dataclass(frozen=True, slots=True)
class InterpretationSummary:
    """The always-visible interpretation (Req 5.1-5.3).

    Distinct labeled elements: intent, applied, proposed, delegated, ignored,
    expected presentation format. It never contains tool names, prompt text, or
    internal parameter names.
    """

    intent: str
    applied: tuple[SummaryItem, ...]
    proposed: tuple[SummaryItem, ...]
    delegated: tuple[SummaryItem, ...]
    ignored: tuple[SummaryItem, ...]
    expected_presentation_format: str

    def all_items(self) -> tuple[SummaryItem, ...]:
        """Every listed criterion across the four lists."""
        return self.applied + self.proposed + self.delegated + self.ignored

    def all_text(self) -> str:
        """The concatenated user-visible text (for leak scanning)."""
        parts = [self.intent, self.expected_presentation_format]
        parts.extend(item.text for item in self.all_items())
        return "\n".join(parts)
