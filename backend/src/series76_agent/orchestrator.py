"""The ``Agent_Orchestrator``: one conversation turn end to end (Req 1-12).

Pipeline: **Interpret** (LLM, structured) → **Policy validate** (deterministic)
→ **Branch** (clarify / confirm / execute) → **Execute** (LangChain agent over
allow-listed Spec 2 tools, bounded) → **Verify** (deterministic claims and
figure binding) → **Compose** (deterministic answer + typed blocks from one
verified figure set).

Transaction discipline (Req 4.3): the turn state is recorded through
:class:`~series76_agent.ports.TurnStatePort` — each call its own committed
transaction — immediately **before** and immediately **after** every model
call. The orchestrator itself never holds a SQL session.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from series76_agent.agent_graph import RequiredCall, ToolAgent, call_args, invocation_satisfies
from series76_agent.composer import (
    ComposedResponse,
    PlanRefData,
    ResponseComposer,
    _Ctx,
    edition_label,
)
from series76_agent.context import ContextResolver, ResolutionStatus
from series76_agent.domain.budget import BudgetExceeded, BudgetLimit, BudgetTracker, TurnBudget
from series76_agent.domain.conversation import (
    DomainConversationState,
    PendingClarification,
    PendingPlan,
    new_state,
)
from series76_agent.domain.enums import Intent, Language, OutcomeCode, TurnState
from series76_agent.domain.figures import BoundFigure, VerifiedFigureSet, default_evidence_resolver
from series76_agent.domain.ledger import CostCapReached
from series76_agent.domain.plan import Ambiguity, DraftPlan, InterpretedPlan
from series76_agent.domain.serialization import ast_to_json, draft_from_json, draft_to_json
from series76_agent.domain.state_machine import Turn
from series76_agent.fallback import RetryPolicy
from series76_agent.followups import settle_turn
from series76_agent.interpreter import InterpreterInput, SemanticInterpreter
from series76_agent.language import resolve_language
from series76_agent.models import (
    ProviderQuotaExceeded,
    ProviderUnavailableError,
    UnsupportedCapability,
)
from series76_agent.policy import (
    ClarifyReason,
    ConfirmationSignal,
    DecisionKind,
    PolicyDecision,
    PolicyEngine,
    RevisionCheck,
    SessionContext,
    groups_with_predicates,
)
from series76_agent.ports import (
    CancellationPort,
    CatalogToolProvider,
    DomainStatePort,
    EditionInfo,
    EditionPort,
    NeverCancelled,
    PlanPort,
    TurnStatePort,
)
from series76_agent.recommendation import RecommendationCoordinator, RecommendationInput
from series76_agent.rendering import Ident, Lit, Pn, UserEcho, join
from series76_agent.tools import TOOL_SET_B, AllowListToolAdapter, InvocationStatus, ToolInvocation
from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.units import Unit
from series76_domain.operations.results import GetPartResult, SearchResult, SourceNotesResult
from series76_domain.services.convert_units import convert_units
from series76_domain.tools.context import ToolContext

_CLARIFY_KEYS: dict[ClarifyReason, str] = {
    ClarifyReason.AMBIGUOUS: "clarify_ambiguous",
    ClarifyReason.CONFLICT: "clarify_conflict",
    ClarifyReason.FOLLOWUP: "clarify_followup",
    ClarifyReason.MISSING_PN: "clarify_missing_pn",
    ClarifyReason.COMPARE_ARITY: "clarify_compare_arity",
    ClarifyReason.MISSING_FILTER: "clarify_missing_filter",
    ClarifyReason.TARGET_UNIT: "clarify_target_unit",
    ClarifyReason.NEEDS_PRIORITY: "clarify_priority",
}
_CONFIRM_DETAIL: dict[ClarifyReason, str] = {
    ClarifyReason.BOOLEAN_PRECEDENCE: "confirm_boolean",
    ClarifyReason.UNACCEPTED_PRIORITY: "confirm_priority",
    ClarifyReason.MATERIAL_DELEGATION: "confirm_delegation",
}


@dataclass(frozen=True, slots=True)
class TurnInput:
    """One unit of work handed over by the Spec 3 worker / sync endpoint."""

    session_id: uuid.UUID
    owner_id: uuid.UUID
    message: str | None = None
    confirmation: ConfirmationSignal | None = None
    trace_id: str = ""


@dataclass
class TurnResult:
    """The typed result of one turn."""

    turn_id: str
    state: TurnState
    response: ComposedResponse
    outcome: OutcomeCode
    history: list[TurnState] = field(default_factory=list)
    invocations: list[ToolInvocation] = field(default_factory=list)
    model_calls: int = 0
    edition_id: uuid.UUID | None = None


@dataclass
class OrchestratorConfig:
    """Static wiring choices (all from environment in the shipped path)."""

    tool_allow_list: frozenset[str] = TOOL_SET_B
    page_size: int = 50
    budget: TurnBudget = field(default_factory=TurnBudget)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    transient_tool_errors: tuple[type[BaseException], ...] = ()


class AgentOrchestrator:
    """Drives one turn through the 12-state machine (see module docstring)."""

    def __init__(
        self,
        *,
        interpreter: SemanticInterpreter,
        tool_agent: ToolAgent,
        catalog: CatalogToolProvider,
        editions: EditionPort,
        states: DomainStatePort,
        turn_states: TurnStatePort,
        plans: PlanPort,
        cancellation: CancellationPort | None = None,
        config: OrchestratorConfig | None = None,
        composer: ResponseComposer | None = None,
        policy: PolicyEngine | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interpreter = interpreter
        self._agent = tool_agent
        self._catalog = catalog
        self._editions = editions
        self._states = states
        self._turn_states = turn_states
        self._plans = plans
        self._cancellation = cancellation or NeverCancelled()
        self._config = config or OrchestratorConfig()
        self._composer = composer or ResponseComposer(evidence_resolver=default_evidence_resolver)
        self._policy = policy or PolicyEngine()
        self._resolver = ContextResolver()
        self._recommender = RecommendationCoordinator()
        self._clock = clock

    # ================================================================== entry

    async def run_turn(self, data: TurnInput) -> TurnResult:
        """Run one turn (a user message or an authenticated confirmation)."""

        budget = BudgetTracker(self._config.budget, clock=self._clock)
        edition = await self._editions.pinned_edition(
            session_id=data.session_id, owner_id=data.owner_id
        )
        loaded = await self._states.load(session_id=data.session_id, owner_id=data.owner_id)
        state = (
            loaded
            if loaded is not None
            and loaded.belongs_to(session_id=data.session_id, owner_id=data.owner_id)
            else new_state(data.session_id, data.owner_id)
        )
        if data.confirmation is not None:
            return await self._confirm(data, data.confirmation, state, edition, budget)
        return await self._message_turn(data, state, edition, budget)

    # ================================================================ message

    async def _message_turn(
        self,
        data: TurnInput,
        state: DomainConversationState,
        edition: EditionInfo | None,
        budget: BudgetTracker,
    ) -> TurnResult:
        message = (data.message or "").strip()
        lang = resolve_language(message, state.language)

        # A pending plan is superseded by any new user message (a correction):
        # its paused turn is cancelled and its revision can no longer execute.
        if state.pending_plan is not None:
            old = Turn(state.pending_plan.turn_id, TurnState.AWAITING_CONFIRMATION)
            old.advance(TurnState.CANCELLED)
            await self._record(data, old)
            state = state.with_turn_state(old.turn_id, old.state).evolve(pending_plan=None)

        interp_message = message
        if state.pending_clarification is not None:
            pending = state.pending_clarification
            turn = Turn(pending.turn_id, TurnState.NEEDS_CLARIFICATION)
            interp_message = f"{pending.original_message}\n{message}"
            state = state.evolve(pending_clarification=None)
        else:
            turn = Turn(uuid.uuid4().hex)
            await self._record(data, turn)

        if edition is None or (
            state.catalog_edition_id is not None and state.catalog_edition_id != edition.edition_id
        ):
            # Req 2.8: no edition from the validated session -> no plan at all.
            turn.advance(TurnState.INTERPRETING)
            turn.advance(TurnState.FAILED)
            await self._record(data, turn)
            ctx = self._ctx(state, lang, None)
            resp = self._composer.simple(
                ctx, "edition_unavailable", OutcomeCode.EDITION_UNAVAILABLE
            )
            return self._result(turn, resp, budget, None)

        state = state.evolve(catalog_edition_id=edition.edition_id)
        session = SessionContext(
            session_id=data.session_id,
            owner_id=data.owner_id,
            catalog_edition_id=edition.edition_id,
            edition_withdrawn=edition.withdrawn,
        )

        # ---- Interpret (LLM): committed state before and after the call ----
        turn.advance(TurnState.INTERPRETING)
        await self._record(data, turn)
        try:
            draft, _raw = await self._interpreter.interpret(
                InterpreterInput(
                    message=interp_message,
                    catalog_edition_id=edition.edition_id,
                    previous_language=state.language,
                    has_prior_results=bool(state.last_search_results or state.last_comparison_set),
                ),
                budget,
            )
        except Exception as exc:  # typed provider/budget failures
            turn.advance(TurnState.FAILED)
            await self._record(data, turn)
            return self._failure(turn, exc, state, lang, edition, budget, data)
        # The response language follows the *latest* user turn (Req 9.5).
        draft = replace(draft, response_language=resolve_language(message, state.language))
        lang = draft.response_language
        turn.advance(TurnState.INTERPRETED)
        await self._record(data, turn)

        # ---- Context resolution against persisted state only ----
        resolution = self._resolver.resolve(
            draft, state, session_id=data.session_id, owner_id=data.owner_id
        )
        ctx = self._ctx(state, lang, edition)
        if resolution.status is not ResolutionStatus.RESOLVED:
            ref = resolution.failed_reference or "?"
            if resolution.status is ResolutionStatus.AMBIGUOUS:
                ctx.catalog_pns.update(resolution.candidates)
                resp = self._composer.clarification(
                    ctx,
                    draft,
                    "clarify_ref_ambiguous",
                    slots={
                        "ref": UserEcho(ref),
                        "pns": join([[Pn(p)] for p in resolution.candidates], ", "),
                    },
                    options=list(resolution.candidates),
                )
            else:
                resp = self._composer.clarification(
                    ctx, draft, "clarify_ref_unmatched", slots={"ref": UserEcho(ref)}
                )
            return await self._pause_for_clarification(
                data, turn, state, interp_message, "reference", resp, budget, edition, lang
            )
        draft = settle_turn(resolution.draft, message, state.focus)

        # ---- Policy (deterministic, zero LLM) ----
        decision = self._policy.decide(draft, session, plan_id=f"turn:{turn.turn_id}")
        return await self._branch(
            data, turn, state, decision, draft, ctx, budget, edition, interp_message
        )

    async def _branch(
        self,
        data: TurnInput,
        turn: Turn,
        state: DomainConversationState,
        decision: PolicyDecision,
        draft: DraftPlan,
        ctx: _Ctx,
        budget: BudgetTracker,
        edition: EditionInfo,
        interp_message: str,
    ) -> TurnResult:
        lang = ctx.lang
        kind = decision.kind
        if kind is DecisionKind.REJECTED:
            turn.advance(TurnState.CANCELLED)
            await self._record(data, turn)
            resp = self._composer.simple(
                ctx, "edition_unavailable", OutcomeCode.EDITION_UNAVAILABLE, draft=draft
            )
            return self._result(turn, resp, budget, edition)
        if kind is DecisionKind.SOURCE_WITHDRAWN:
            turn.advance(TurnState.SOURCE_WITHDRAWN)
            await self._record(data, turn)
            await self._save(state.with_turn_state(turn.turn_id, turn.state).evolve(language=lang))
            resp = self._composer.simple(
                ctx,
                "withdrawn",
                OutcomeCode.SOURCE_WITHDRAWN,
                draft=draft,
                slots={"edition": ctx.edition()},
            )
            return self._result(turn, resp, budget, edition)
        if kind in (DecisionKind.CLARIFY, DecisionKind.INVALID_FILTER):
            resp = self._clarification_response(ctx, draft, decision)
            return await self._pause_for_clarification(
                data,
                turn,
                state,
                interp_message,
                decision.reason.value if decision.reason else "clarify",
                resp,
                budget,
                edition,
                lang,
            )
        if kind is DecisionKind.CONFIRM:
            assert decision.reason is not None
            plan_id, revision = await self._plans.create_revision(
                session_id=data.session_id,
                owner_id=data.owner_id,
                payload=json.dumps(draft_to_json(draft), sort_keys=True),
            )
            turn.advance(TurnState.AWAITING_CONFIRMATION)
            await self._record(data, turn)
            new = state.with_turn_state(turn.turn_id, turn.state).evolve(
                pending_plan=PendingPlan(turn.turn_id, plan_id, revision, draft_to_json(draft)),
                plan_id=plan_id,
                plan_revision=revision,
                language=lang,
            )
            await self._save(new)
            resp = self._composer.confirmation(
                ctx,
                draft,
                plan_id=plan_id,
                revision=revision,
                detail_keys=[_CONFIRM_DETAIL[decision.reason]],
            )
            return self._result(turn, resp, budget, edition)
        assert decision.plan is not None
        return await self._execute(data, turn, state, decision.plan, ctx, budget, edition)

    def _clarification_response(
        self, ctx: _Ctx, draft: DraftPlan, decision: PolicyDecision
    ) -> ComposedResponse:
        if decision.kind is DecisionKind.INVALID_FILTER:
            offending = decision.validation.offending_predicate if decision.validation else None
            if offending is not None:
                from series76_agent.i18n import FIELD_LABELS, label

                return self._composer.clarification(
                    ctx,
                    draft,
                    "clarify_invalid_filter",
                    slots={"field": Lit(label(FIELD_LABELS, offending.field.value, ctx.lang))},
                    outcome=OutcomeCode.INVALID_FILTER,
                )
            return self._composer.clarification(
                ctx, draft, "clarify_invalid_filter_generic", outcome=OutcomeCode.INVALID_FILTER
            )
        if decision.reason is ClarifyReason.INVALID_PN:
            pns = decision.offending or ("?",)
            return self._composer.clarification(
                ctx,
                draft,
                "invalid_pn",
                slots={"pn": join([[UserEcho(p)] for p in pns], ", ")},
                outcome=OutcomeCode.INVALID_PN,
            )
        key = _CLARIFY_KEYS.get(decision.reason or ClarifyReason.FOLLOWUP, "clarify_followup")
        options: list[str] = []
        if decision.reason is ClarifyReason.NEEDS_PRIORITY:
            from series76_agent.i18n import metric_label

            options = [
                metric_label(k, ctx.lang) for k in ("torque_inlbs", "operating_speed", "fla")
            ]
        return self._composer.clarification(ctx, draft, key, options=options)

    async def _pause_for_clarification(
        self,
        data: TurnInput,
        turn: Turn,
        state: DomainConversationState,
        interp_message: str,
        reason: str,
        resp: ComposedResponse,
        budget: BudgetTracker,
        edition: EditionInfo,
        lang: Language,
    ) -> TurnResult:
        turn.advance(TurnState.NEEDS_CLARIFICATION)
        await self._record(data, turn)
        new = state.with_turn_state(turn.turn_id, turn.state).evolve(
            pending_clarification=PendingClarification(
                turn.turn_id, interp_message[-2000:], reason
            ),
            language=lang,
        )
        await self._save(new)
        return self._result(turn, resp, budget, edition)

    # =========================================================== confirmation

    async def _confirm(
        self,
        data: TurnInput,
        signal: ConfirmationSignal,
        state: DomainConversationState,
        edition: EditionInfo | None,
        budget: BudgetTracker,
    ) -> TurnResult:
        lang = state.language or Language.EN
        ctx = self._ctx(state, lang, edition)
        check = self._policy.verify_revision(state, signal)
        pending = state.pending_plan
        if check is RevisionCheck.DUPLICATE:
            turn = Turn(f"confirm-{signal.plan_revision}", TurnState.COMPLETED)
            resp = self._composer.simple(ctx, "already_executed", OutcomeCode.ALREADY_EXECUTED)
            return self._result(turn, resp, budget, edition)
        if check is not RevisionCheck.MATCH or pending is None or edition is None:
            # Stale / mismatched / unbound: nothing executes and the active
            # state (incl. a still-pending current revision) is untouched; the
            # confirmation's own turn ends in STALE_PLAN.
            turn = Turn(
                f"confirm-{signal.plan_revision}-{uuid.uuid4().hex[:8]}",
                TurnState.AWAITING_CONFIRMATION,
            )
            turn.advance(TurnState.STALE_PLAN)
            await self._record(data, turn)
            current = state.plan_revision
            resp = self._composer.simple(
                ctx,
                "stale",
                OutcomeCode.STALE_PLAN,
                slots={"rev": Lit("—") if current == 0 else _ident(current)},
                plan=PlanRefData(state.plan_id, current, pending is not None)
                if state.plan_id is not None
                else None,
            )
            return self._result(turn, resp, budget, edition)

        turn = Turn(pending.turn_id, TurnState.AWAITING_CONFIRMATION)
        draft = draft_from_json(pending.draft)
        # Confirming a reviewed revision accepts exactly what it showed: its
        # proposed priority and its explicit grouping (never a new LLM input).
        draft = replace(
            draft,
            accepted_priorities=draft.accepted_priorities or draft.proposed_priorities,
            ambiguity=Ambiguity(),
        )
        state = state.evolve(
            pending_plan=None,
            executed_revisions=(*state.executed_revisions, signal.plan_revision),
        )
        plan = InterpretedPlan(
            draft=draft,
            catalog_edition_id=edition.edition_id,
            plan_id=pending.plan_id,
            plan_revision=pending.plan_revision,
        )
        ctx = self._ctx(state, draft.response_language, edition)
        if draft.intent is Intent.RECOMMENDATION and edition.withdrawn:
            turn.advance(TurnState.EXECUTING)
            turn.advance(TurnState.SOURCE_WITHDRAWN)
            await self._record(data, turn)
            await self._save(state.with_turn_state(turn.turn_id, turn.state))
            resp = self._composer.simple(
                ctx,
                "withdrawn",
                OutcomeCode.SOURCE_WITHDRAWN,
                draft=draft,
                slots={"edition": ctx.edition()},
            )
            return self._result(turn, resp, budget, edition)
        return await self._execute(data, turn, state, plan, ctx, budget, edition)

    # ================================================================ execute

    async def _execute(
        self,
        data: TurnInput,
        turn: Turn,
        state: DomainConversationState,
        plan: InterpretedPlan,
        ctx: _Ctx,
        budget: BudgetTracker,
        edition: EditionInfo,
    ) -> TurnResult:
        draft = plan.draft
        turn.advance(TurnState.EXECUTING)
        await self._record(data, turn)

        if draft.intent is Intent.OUT_OF_SCOPE:
            return await self._complete(
                data, turn, state, self._composer.abstain(ctx, draft), budget, edition, draft, ()
            )

        tool_ctx = ToolContext(
            edition_id=plan.catalog_edition_id,
            permissions=plan.permissions,
            max_results=self._config.page_size,
            trace_id=data.trace_id,
            allow_new_recommendation=not edition.withdrawn,
        )
        adapter = AllowListToolAdapter(
            tools=self._catalog.tools(tool_ctx),
            allow_list=self._config.tool_allow_list,
            budget=budget,
            retry=self._config.retry,
            transient_errors=self._config.transient_tool_errors,
        )
        required = required_calls(draft)
        try:
            await self._agent.run(
                plan_brief=plan_brief(draft), required=required, adapter=adapter, budget=budget
            )
        except BudgetExceeded as exc:
            await self._record(data, turn)
            return await self._fail(
                data, turn, ctx, budget, edition, draft, budget_limit=exc.limit.value
            )
        except Exception as exc:  # typed provider failures
            await self._record(data, turn)
            turn.advance(TurnState.FAILED)
            await self._record(data, turn)
            return self._failure(turn, exc, state, ctx.lang, edition, budget, data, adapter.log)
        # Committed state after the model call (Req 4.3).
        await self._record(data, turn)

        # Deterministic completion of any plan-required read the model skipped,
        # through the same allow-listed adapter (never another path).
        outcomes = await self._ensure_required(adapter, required)
        failure = _first_failure(outcomes)
        if failure is not None:
            if failure.status is InvocationStatus.LIMIT_REACHED:
                return await self._fail(
                    data,
                    turn,
                    ctx,
                    budget,
                    edition,
                    draft,
                    budget_limit=failure.limit or "max_tool_calls_per_turn",
                )
            turn.advance(TurnState.FAILED)
            await self._record(data, turn)
            resp = self._composer.simple(
                ctx,
                "tool_unavailable",
                OutcomeCode.TOOL_UNAVAILABLE,
                draft=draft,
                slots={"ref": _ident_text(data.trace_id)},
            )
            return self._result(turn, resp, budget, edition, adapter.log)

        if await self._cancelled(data):
            turn.advance(TurnState.CANCELLED)
            await self._record(data, turn)
            resp = self._composer.simple(ctx, "cancelled", OutcomeCode.CANCELLED, draft=draft)
            return self._result(turn, resp, budget, edition, adapter.log)

        try:
            response, focus = await self._verify_and_compose(ctx, draft, outcomes, adapter, budget)
        except BudgetExceeded as exc:
            return await self._fail(
                data, turn, ctx, budget, edition, draft, budget_limit=exc.limit.value
            )
        turn.advance(TurnState.VERIFYING)
        await self._record(data, turn)
        return await self._complete(
            data, turn, state, response, budget, edition, draft, focus, adapter.log
        )

    async def _ensure_required(
        self, adapter: AllowListToolAdapter, required: Sequence[RequiredCall]
    ) -> list[tuple[RequiredCall, ToolInvocation]]:
        out: list[tuple[RequiredCall, ToolInvocation]] = []
        for req in required:
            done = next((i for i in adapter.log if invocation_satisfies(i, req)), None)
            if done is None:
                name, args = call_args(req, adapter.allow_list)
                done = await adapter.invoke(name, args, origin="coordinator")
            out.append((req, done))
        return out

    async def _verify_and_compose(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        outcomes: list[tuple[RequiredCall, ToolInvocation]],
        adapter: AllowListToolAdapter,
        budget: BudgetTracker,
    ) -> tuple[ComposedResponse, tuple[str, ...]]:
        figset = ctx.figset
        found: list[str] = []
        not_listed: list[str] = []
        invalid: list[str] = []
        for req, inv in outcomes:
            payload = inv.result.payload if inv.result is not None else None
            if req.operation == "GET" and isinstance(payload, GetPartResult):
                if payload.view is not None:
                    figset.add_part_view(payload.view)
                    found.append(payload.view.part.part_number.canonical_pn)
                elif payload.failure is SemanticFailureCode.INVALID_PN:
                    invalid.append(req.part_number or "")
                else:
                    not_listed.append(req.part_number or "")

        intent = draft.intent
        if invalid:
            return self._composer.clarification(
                ctx,
                draft,
                "invalid_pn",
                slots={"pn": join([[UserEcho(p)] for p in invalid])},
                outcome=OutcomeCode.INVALID_PN,
            ), ()
        if intent in (Intent.EXACT_LOOKUP,) or (
            intent is Intent.COMPARISON and (not_listed or len(found) < 2)
        ):
            return self._composer.lookup(ctx, draft, found, not_listed), tuple(found)
        if intent is Intent.COMPARISON:
            return self._composer.comparison(ctx, draft, found), tuple(found)
        if intent is Intent.DERIVED_CALCULATION:
            if not found:
                return self._composer.lookup(ctx, draft, found, not_listed), ()
            pn = found[0]
            pairs = _conversions(figset, pn, draft.target_unit)
            return self._composer.derived(ctx, draft, pn, pairs), (pn,)
        if intent is Intent.EXPLANATION:
            notes = next(
                (
                    inv.result.payload
                    for req, inv in outcomes
                    if req.operation == "NOTES"
                    and inv.result is not None
                    and isinstance(inv.result.payload, SourceNotesResult)
                ),
                None,
            )
            pn = draft.part_numbers[0]
            if notes is None or notes.failure is not None:
                return self._composer.lookup(ctx, draft, [], [pn]), ()
            figset.listed_parts.append(normalize(pn))
            return self._composer.notes(ctx, draft, normalize(pn), notes), (normalize(pn),)

        search = next(
            (
                inv.result.payload
                for req, inv in outcomes
                if req.operation == "SEARCH"
                and inv.result is not None
                and isinstance(inv.result.payload, SearchResult)
            ),
            None,
        )
        assert search is not None, "a search plan always yields a typed search result"
        verified = tuple(p.canonical_pn for p in search.verified)
        preliminary = tuple(p.canonical_pn for p in search.preliminary)
        page = tuple(c.part_number.canonical_pn for c in search.page)
        if intent is Intent.FILTER_SEARCH:
            return self._composer.search(
                ctx,
                draft,
                total=search.total_matches,
                verified=verified,
                preliminary=preliminary,
                page=page,
                complete=search.next_cursor is None,
            ), page

        # RECOMMENDATION
        wants_rank = draft.top_one or draft.ranking_requested
        rank_limited = False
        if wants_rank and draft.accepted_priorities and verified:
            if len(verified) > budget.remaining_tool_calls():
                rank_limited = True
            else:
                for pn in verified:
                    name, args = call_args(RequiredCall("GET", pn), adapter.allow_list)
                    inv = await adapter.invoke(name, args, origin="coordinator")
                    if inv.status is InvocationStatus.LIMIT_REACHED:
                        raise BudgetExceeded(_limit(inv))
                    payload = inv.result.payload if inv.result is not None else None
                    if isinstance(payload, GetPartResult) and payload.view is not None:
                        figset.add_part_view(payload.view)
        data = RecommendationInput(
            criteria=draft.criteria,
            groups_with_predicates=groups_with_predicates(draft.filter_ast),
            verified_matches=verified,
            preliminary_matches=preliminary,
            accepted_priorities=() if rank_limited else draft.accepted_priorities,
            top_one=draft.top_one,
            ranking_requested=draft.ranking_requested,
            service=draft.service,
        )
        rec = self._recommender.decide(data, figset)
        response = self._composer.recommendation(
            ctx,
            draft,
            rec,
            verified=verified,
            preliminary=preliminary,
            total=search.total_matches,
            rank_limited=rank_limited,
        )
        visible = (rec.winner,) if draft.top_one and rec.winner else (rec.ranked or page)
        return response, tuple(p for p in visible if p)

    # =============================================================== complete

    async def _complete(
        self,
        data: TurnInput,
        turn: Turn,
        state: DomainConversationState,
        response: ComposedResponse,
        budget: BudgetTracker,
        edition: EditionInfo,
        draft: DraftPlan,
        focus: Sequence[str],
        invocations: Sequence[ToolInvocation] = (),
    ) -> TurnResult:
        if turn.state is TurnState.EXECUTING:
            if await self._cancelled(data):
                # Cancelled / deleted: no state is persisted (no resurrection).
                turn.advance(TurnState.CANCELLED)
                await self._record(data, turn)
                ctx = self._ctx(state, draft.response_language, edition)
                resp = self._composer.simple(ctx, "cancelled", OutcomeCode.CANCELLED, draft=draft)
                return self._result(turn, resp, budget, edition, invocations)
            turn.advance(TurnState.VERIFYING)
            await self._record(data, turn)
        turn.advance(TurnState.COMPLETED)
        await self._record(data, turn)
        new = state.with_turn_state(turn.turn_id, turn.state).evolve(
            language=draft.response_language,
            mentioned=tuple(dict.fromkeys((*state.mentioned, *draft.part_numbers, *focus)))[-50:],
        )
        if focus:
            new = new.evolve(focus=tuple(focus))
        if draft.intent is Intent.COMPARISON and focus:
            new = new.evolve(last_comparison_set=tuple(focus))
        elif draft.intent in (Intent.FILTER_SEARCH, Intent.RECOMMENDATION) and focus:
            new = new.evolve(last_search_results=tuple(focus))
        if draft.intent is Intent.RECOMMENDATION:
            new = new.evolve(criteria=draft.criteria)
            if draft.accepted_priorities:
                new = new.evolve(accepted_priorities=draft.accepted_priorities)
        await self._save(new)
        return self._result(turn, response, budget, edition, invocations)

    # ================================================================ failures

    async def _fail(
        self,
        data: TurnInput,
        turn: Turn,
        ctx: _Ctx,
        budget: BudgetTracker,
        edition: EditionInfo,
        draft: DraftPlan,
        *,
        budget_limit: str,
    ) -> TurnResult:
        if turn.state is not TurnState.FAILED:
            turn.advance(TurnState.FAILED)
            await self._record(data, turn)
        resp = self._composer.budget_failure(ctx, budget_limit, draft)
        return self._result(turn, resp, budget, edition)

    def _failure(
        self,
        turn: Turn,
        exc: Exception,
        state: DomainConversationState,
        lang: Language,
        edition: EditionInfo | None,
        budget: BudgetTracker,
        data: TurnInput,
        invocations: Sequence[ToolInvocation] = (),
    ) -> TurnResult:
        ctx = self._ctx(state, lang, edition)
        if isinstance(exc, BudgetExceeded):
            resp = self._composer.budget_failure(ctx, exc.limit.value, None)
        elif isinstance(exc, ProviderQuotaExceeded):
            resp = self._composer.simple(ctx, "provider_quota", OutcomeCode.PROVIDER_QUOTA_EXCEEDED)
        elif isinstance(exc, UnsupportedCapability):
            resp = self._composer.simple(
                ctx, "unsupported_capability", OutcomeCode.UNSUPPORTED_CAPABILITY
            )
        elif isinstance(exc, CostCapReached):
            resp = self._composer.simple(ctx, "cost_cap", OutcomeCode.COST_CAP_REACHED)
        elif isinstance(exc, ProviderUnavailableError):
            resp = self._composer.simple(
                ctx, "provider_unavailable", OutcomeCode.PROVIDER_UNAVAILABLE
            )
        else:
            raise exc
        return self._result(turn, resp, budget, edition, invocations)

    # ================================================================ helpers

    def _ctx(
        self, state: DomainConversationState, lang: Language, edition: EditionInfo | None
    ) -> _Ctx:
        edition_id = edition.edition_id if edition is not None else uuid.UUID(int=0)
        figset = VerifiedFigureSet(edition_id=edition_id)
        label_text = edition_label(edition_id) if edition is not None else "—"
        return self._composer.context(figset, lang, label_text)

    async def _record(self, data: TurnInput, turn: Turn) -> None:
        await self._turn_states.record(
            session_id=data.session_id,
            owner_id=data.owner_id,
            turn_id=turn.turn_id,
            state=turn.state,
        )

    async def _save(self, state: DomainConversationState) -> None:
        await self._states.save(state.evolve(version=state.version + 1))

    async def _cancelled(self, data: TurnInput) -> bool:
        return await self._cancellation.is_cancelled(
            session_id=data.session_id, owner_id=data.owner_id
        )

    def _result(
        self,
        turn: Turn,
        response: ComposedResponse,
        budget: BudgetTracker,
        edition: EditionInfo | None,
        invocations: Sequence[ToolInvocation] = (),
    ) -> TurnResult:
        return TurnResult(
            turn_id=turn.turn_id,
            state=turn.state,
            response=response,
            outcome=response.outcome,
            history=list(turn.history),
            invocations=list(invocations),
            model_calls=budget.model_calls,
            edition_id=edition.edition_id if edition is not None else None,
        )


# ====================================================================== plan io


def required_calls(draft: DraftPlan) -> list[RequiredCall]:
    """The catalog reads a validated plan needs (tool-set neutral)."""

    pns = draft.part_numbers
    intent = draft.intent
    if intent in (Intent.EXACT_LOOKUP, Intent.COMPARISON, Intent.DERIVED_CALCULATION):
        return [RequiredCall("GET", pn) for pn in pns[:3]]
    if intent is Intent.EXPLANATION:
        return [RequiredCall("NOTES", pns[0])] if pns else []
    if intent in (Intent.FILTER_SEARCH, Intent.RECOMMENDATION) and draft.filter_ast is not None:
        return [RequiredCall("SEARCH", filter_ast=ast_to_json(draft.filter_ast))]
    return []


def plan_brief(draft: DraftPlan) -> dict[str, object]:
    """The validated plan as shown to the tool-selecting model (no raw message)."""

    return {
        "intent": draft.intent.value,
        "part_numbers": list(draft.part_numbers),
        "filter_ast": ast_to_json(draft.filter_ast) if draft.filter_ast is not None else None,
        "needs": [r.operation for r in required_calls(draft)],
    }


def normalize(pn: str) -> str:
    """Canonical PN form used across results."""
    return pn.strip().upper()


def _conversions(
    figset: VerifiedFigureSet, pn: str, target_unit: str | None
) -> list[tuple[BoundFigure, BoundFigure | None]]:
    if target_unit is None:
        return []
    try:
        target = Unit(target_unit)
    except ValueError:
        return []
    pairs: list[tuple[BoundFigure, BoundFigure | None]] = []
    for bf in figset.for_part(pn):
        direct = bf.figure.direct
        unit = bf.unit
        if unit is None or bf.figure.derived is not None:
            continue
        try:
            source_unit = Unit(unit)
        except ValueError:
            continue
        if source_unit is target or not source_unit.is_convertible_to(target):
            continue
        if direct is None:
            pairs.append((bf, None))
            continue
        result = convert_units(direct, target, evidence=bf.figure.evidence)
        pairs.append((bf, figset.add_derived(bf, result.derived) if result.derived else None))
    return pairs


def _first_failure(
    outcomes: Sequence[tuple[RequiredCall, ToolInvocation]],
) -> ToolInvocation | None:
    for _req, inv in outcomes:
        if inv.status is not InvocationStatus.OK:
            return inv
    return None


def _limit(inv: ToolInvocation) -> BudgetLimit:
    try:
        return BudgetLimit(inv.limit or "max_tool_calls_per_turn")
    except ValueError:
        return BudgetLimit.TOOL_CALLS


def _ident(value: int) -> Ident:
    return Ident(str(value))


def _ident_text(value: str) -> Ident:
    return Ident(value or "-")
