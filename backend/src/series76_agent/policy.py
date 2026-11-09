"""The deterministic ``Policy_Engine`` (Req 3.1-3.7, 5.4-5.5, 7.3).

Every decision here is a pure function of its inputs and performs **zero**
language-model invocations: AST validation (before any tool execution),
requirement-group coverage and grade, the clarification / confirmation
decision, permission and edition resolution from the validated session, and
plan-revision verification against the conversation's active state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import Enum

from series76_agent.domain.conversation import DomainConversationState
from series76_agent.domain.enums import FallbackCondition, Intent
from series76_agent.domain.plan import DraftPlan, InterpretedPlan
from series76_agent.recommendation import group_statuses
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, And, Node, Not, Or, Predicate
from series76_domain.model.filter_validation import FilterValidationResult, validate_filter
from series76_domain.operations.pn import is_well_formed_pn

#: Which requirement group a filter field belongs to (F2 §4 / Spec 2 Req 7).
FIELD_GROUP: dict[AllowlistField, RequirementGroup] = {
    AllowlistField.ENCLOSURE: RequirementGroup.ENVIRONMENT_ENCLOSURE,
    AllowlistField.NOMINAL_VOLTAGE: RequirementGroup.POWER_SUPPLY,
    AllowlistField.CURRENT_MODE: RequirementGroup.POWER_SUPPLY,
    AllowlistField.PHASE: RequirementGroup.POWER_SUPPLY,
    AllowlistField.SERVICE: RequirementGroup.SERVICE_TYPE,
    AllowlistField.TORQUE_INLBS: RequirementGroup.REQUIRED_TORQUE,
    AllowlistField.TORQUE_NM: RequirementGroup.REQUIRED_TORQUE,
}


class DecisionKind(str, Enum):
    """The single decision the policy engine returns for a plan."""

    EXECUTE = "EXECUTE"
    CLARIFY = "CLARIFY"
    CONFIRM = "CONFIRM"
    ABSTAIN = "ABSTAIN"
    INVALID_FILTER = "INVALID_FILTER"
    SOURCE_WITHDRAWN = "SOURCE_WITHDRAWN"
    REJECTED = "REJECTED"


class ClarifyReason(str, Enum):
    """Why a clarification / confirmation is required."""

    INVALID_PN = "invalid_pn"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    FOLLOWUP = "followup"
    MISSING_PN = "missing_pn"
    COMPARE_ARITY = "compare_arity"
    MISSING_FILTER = "missing_filter"
    TARGET_UNIT = "target_unit"
    NEEDS_PRIORITY = "needs_priority"
    BOOLEAN_PRECEDENCE = "boolean_precedence"
    UNACCEPTED_PRIORITY = "unaccepted_priority"
    MATERIAL_DELEGATION = "material_delegation"
    INVALID_FILTER = "invalid_filter"


class ValueOrigin(str, Enum):
    """Where a server-controlled value came from."""

    SESSION = "SESSION"
    MODEL = "MODEL"


@dataclass(frozen=True, slots=True)
class SessionContext:
    """The validated, server-injected context of a turn (from Spec 3)."""

    session_id: uuid.UUID
    owner_id: uuid.UUID
    catalog_edition_id: uuid.UUID | None
    edition_withdrawn: bool = False
    permissions: str = "runtime_reader"
    edition_origin: ValueOrigin = ValueOrigin.SESSION
    permissions_origin: ValueOrigin = ValueOrigin.SESSION


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The policy outcome: exactly one kind, plus what justified it."""

    kind: DecisionKind
    plan: InterpretedPlan | None = None
    reason: ClarifyReason | None = None
    fallback: FallbackCondition | None = None
    validation: FilterValidationResult | None = None
    offending: tuple[str, ...] = ()

    @property
    def blocks_execution(self) -> bool:
        """True iff no tool may run for this decision."""
        return self.kind is not DecisionKind.EXECUTE


class RevisionCheck(str, Enum):
    """Result of verifying a confirmation against the active plan state."""

    MATCH = "MATCH"
    STALE = "STALE"
    MISMATCH = "MISMATCH"
    DUPLICATE = "DUPLICATE"
    NOT_BOUND = "NOT_BOUND"


@dataclass(frozen=True, slots=True)
class ConfirmationSignal:
    """An authenticated confirmation materialized by the Spec 3 plan seam."""

    session_id: uuid.UUID
    plan_id: str
    plan_revision: int
    user_id: uuid.UUID
    bound_to_current: bool


class PolicyRejection(Exception):
    """A server-controlled value did not originate from the validated session."""


class PolicyEngine:
    """Deterministic validation and decisions — never calls a language model."""

    # --- server context --------------------------------------------------------

    def resolve_server_context(self, session: SessionContext) -> tuple[uuid.UUID, str]:
        """Return (edition, permissions) only if both came from the session."""

        if (
            session.edition_origin is not ValueOrigin.SESSION
            or session.permissions_origin is not ValueOrigin.SESSION
        ):
            raise PolicyRejection("edition/permissions must come from the validated session")
        if session.catalog_edition_id is None:
            raise PolicyRejection("no catalog edition resolved for the session")
        return session.catalog_edition_id, session.permissions

    # --- decisions -------------------------------------------------------------

    def decide(
        self,
        draft: DraftPlan,
        session: SessionContext,
        *,
        plan_id: str,
        plan_revision: int = 0,
        unresolved_reference: bool = False,
    ) -> PolicyDecision:
        """Validate a draft plan and decide exactly one next step.

        The order of checks is fixed, so identical inputs always yield the
        identical decision (Req 3.3).
        """

        try:
            edition, permissions = self.resolve_server_context(session)
        except PolicyRejection:
            return PolicyDecision(kind=DecisionKind.REJECTED)

        draft = self._strip_unbacked_predicates(draft)
        plan = InterpretedPlan(
            draft=draft,
            catalog_edition_id=edition,
            plan_id=plan_id,
            plan_revision=plan_revision,
            permissions=permissions,
        )
        intent = draft.intent

        if intent is Intent.RECOMMENDATION and session.edition_withdrawn:
            return PolicyDecision(
                kind=DecisionKind.SOURCE_WITHDRAWN,
                plan=plan,
                fallback=FallbackCondition.SOURCE_WITHDRAWN,
            )
        if intent is Intent.OUT_OF_SCOPE:
            return PolicyDecision(
                kind=DecisionKind.ABSTAIN, plan=plan, fallback=FallbackCondition.OUT_OF_SCOPE
            )
        if intent is Intent.FOLLOWUP or unresolved_reference:
            return self._clarify(plan, ClarifyReason.FOLLOWUP)

        malformed = tuple(
            r.text
            for r in draft.referents
            if r.part_number is not None and not is_well_formed_pn(r.part_number)
        ) + tuple(u.text for u in draft.unresolved if u.kind == "MALFORMED_PN")
        if malformed:
            return PolicyDecision(
                kind=DecisionKind.CLARIFY,
                plan=plan,
                reason=ClarifyReason.INVALID_PN,
                fallback=FallbackCondition.INVALID_PN_FORMAT,
                offending=malformed,
            )

        if draft.filter_ast is not None:
            validation = validate_filter(draft.filter_ast)
            if not validation.ok:
                return PolicyDecision(
                    kind=DecisionKind.INVALID_FILTER,
                    plan=plan,
                    reason=ClarifyReason.INVALID_FILTER,
                    validation=validation,
                )

        if draft.ambiguity.conflicting_statements or (
            intent is Intent.RECOMMENDATION
            and CoverageStatus.CONFLICTING in group_statuses(draft.criteria).values()
        ):
            return self._clarify(plan, ClarifyReason.CONFLICT)
        if draft.ambiguity.alternative_interpretations > 1:
            return self._clarify(plan, ClarifyReason.AMBIGUOUS)
        if draft.ambiguity.boolean_precedence_ambiguous:
            return PolicyDecision(
                kind=DecisionKind.CONFIRM,
                plan=plan,
                reason=ClarifyReason.BOOLEAN_PRECEDENCE,
                fallback=FallbackCondition.AMBIGUOUS_BOOLEAN,
            )
        if draft.ambiguity.delegation_changes_results:
            return PolicyDecision(
                kind=DecisionKind.CONFIRM, plan=plan, reason=ClarifyReason.MATERIAL_DELEGATION
            )

        missing = self._missing_inputs(draft)
        if missing is not None:
            return self._clarify(plan, missing)

        if intent is Intent.RECOMMENDATION and (draft.top_one or draft.ranking_requested):
            unaccepted = tuple(
                p for p in draft.proposed_priorities if p not in draft.accepted_priorities
            )
            if not draft.accepted_priorities and unaccepted:
                return PolicyDecision(
                    kind=DecisionKind.CONFIRM,
                    plan=plan,
                    reason=ClarifyReason.UNACCEPTED_PRIORITY,
                )
            if not draft.accepted_priorities:
                return self._clarify(plan, ClarifyReason.NEEDS_PRIORITY)

        return PolicyDecision(kind=DecisionKind.EXECUTE, plan=plan)

    def requires_coverage(self, draft: DraftPlan) -> bool:
        """Only a recommendation requires the four-group coverage (Req 3.4)."""
        return draft.intent is Intent.RECOMMENDATION

    # --- revision verification ---------------------------------------------------

    def verify_revision(
        self, state: DomainConversationState, signal: ConfirmationSignal
    ) -> RevisionCheck:
        """Compare a confirmation's 4-tuple with the active state (Req 6.1)."""

        if not signal.bound_to_current:
            return RevisionCheck.NOT_BOUND
        if signal.session_id != state.session_id or signal.user_id != state.owner_id:
            return RevisionCheck.MISMATCH
        if signal.plan_revision in state.executed_revisions:
            return RevisionCheck.DUPLICATE
        if signal.plan_revision != state.plan_revision:
            return RevisionCheck.STALE
        pending = state.pending_plan
        if pending is None or pending.plan_id != signal.plan_id:
            return RevisionCheck.MISMATCH if pending is not None else RevisionCheck.STALE
        if pending.plan_revision != signal.plan_revision:
            return RevisionCheck.STALE
        return RevisionCheck.MATCH

    # --- helpers -------------------------------------------------------------------

    def _clarify(self, plan: InterpretedPlan, reason: ClarifyReason) -> PolicyDecision:
        return PolicyDecision(kind=DecisionKind.CLARIFY, plan=plan, reason=reason)

    def _missing_inputs(self, draft: DraftPlan) -> ClarifyReason | None:
        pns = draft.part_numbers
        intent = draft.intent
        if intent is Intent.EXACT_LOOKUP and not pns:
            return ClarifyReason.MISSING_PN
        if intent is Intent.COMPARISON and not 2 <= len(pns) <= 3:
            return ClarifyReason.COMPARE_ARITY
        if intent is Intent.FILTER_SEARCH and draft.filter_ast is None:
            return ClarifyReason.MISSING_FILTER
        if intent is Intent.DERIVED_CALCULATION and (not pns or draft.target_unit is None):
            return ClarifyReason.TARGET_UNIT
        if intent is Intent.EXPLANATION and not pns:
            return ClarifyReason.MISSING_PN
        if intent is Intent.RECOMMENDATION and draft.filter_ast is None:
            # Nothing specified that the catalog can be searched by.
            return ClarifyReason.MISSING_FILTER
        return None

    def _strip_unbacked_predicates(self, draft: DraftPlan) -> DraftPlan:
        """For a recommendation, keep hard predicates only of SPECIFIED groups.

        A predicate on a field of a DELEGATED / NO_PREFERENCE / UNKNOWN /
        UNSPECIFIED group would be a synthesized physical condition (Req 7.3),
        so it is removed before validation and execution.
        """

        if draft.intent is not Intent.RECOMMENDATION or draft.filter_ast is None:
            return draft
        statuses = group_statuses(draft.criteria)
        allowed = {g for g, s in statuses.items() if s is CoverageStatus.SPECIFIED}
        pruned = _prune(draft.filter_ast, allowed)
        return replace(draft, filter_ast=pruned)


def groups_with_predicates(node: Node | None) -> frozenset[RequirementGroup]:
    """The requirement groups that contribute at least one predicate."""

    from series76_agent.domain.serialization import predicates_of

    return frozenset(FIELD_GROUP[p.field] for p in predicates_of(node) if p.field in FIELD_GROUP)


def _prune(node: Node, allowed: set[RequirementGroup]) -> Node | None:
    if isinstance(node, Predicate):
        group = FIELD_GROUP.get(node.field)
        if group is not None and group not in allowed:
            return None
        return node
    if isinstance(node, And | Or):
        kept = tuple(c for c in (_prune(ch, allowed) for ch in node.children) if c is not None)
        if not kept:
            return None
        return And(children=kept) if isinstance(node, And) else Or(children=kept)
    if isinstance(node, Not):
        child = _prune(node.child, allowed)
        return Not(child=child) if child is not None else None
    return node
