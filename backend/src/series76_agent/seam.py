"""The Spec 4 agent mounted on the Spec 3 ``AgentPort`` seam.

:class:`Series76Agent` adapts one :class:`~series76_agent.orchestrator.TurnResult`
to the Spec 3 :class:`~series76_api.application.agent_seam.TurnOutcome`:

* completed / clarification / confirmation / stale-plan / withdrawn turns
  become a ``Response_Envelope`` (answer + typed blocks + interpretation
  summary + plan reference + warnings + pinned edition);
* provider / catalog / configuration failures raise ``ProviderUnavailable``
  (``503 UPSTREAM_UNAVAILABLE``, retryable, with the request id as correlation
  id) — never a fabricated answer;
* a fail-closed budget stop raises ``BudgetExceededError``;
* a cancelled / deleted conversation raises ``GoneError`` (no resurrection).

The debug trace attached to the outcome is content-light (turn states, tool
names/origins/statuses, typed arguments, counts) and is encrypted by Spec 3 and
served only to the owning developer. No prompt, key, or model name is in it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from series76_agent.agent_graph import ToolAgent
from series76_agent.composer import summary_dto
from series76_agent.domain.budget import TurnBudget
from series76_agent.domain.enums import OutcomeCode, TurnState
from series76_agent.domain.ledger import CostLedger
from series76_agent.interpreter import SemanticInterpreter
from series76_agent.models import CapabilityRegistry, ModelConfig, ModelConfigError, ModelGateway
from series76_agent.orchestrator import AgentOrchestrator, OrchestratorConfig, TurnInput, TurnResult
from series76_agent.policy import ConfirmationSignal
from series76_agent.tools import TOOL_SET_A, TOOL_SET_B
from series76_api.api.envelopes import EnvelopeStatus, PlanRef
from series76_api.application.agent_seam import (
    OutcomeKind,
    ProviderUnavailable,
    TurnOutcome,
    TurnRequest,
)
from series76_api.domain.errors import BudgetExceededError, GoneError

_UNAVAILABLE = {
    OutcomeCode.PROVIDER_UNAVAILABLE,
    OutcomeCode.TOOL_UNAVAILABLE,
    OutcomeCode.PROVIDER_QUOTA_EXCEEDED,
    OutcomeCode.UNSUPPORTED_CAPABILITY,
    OutcomeCode.EDITION_UNAVAILABLE,
    OutcomeCode.COST_CAP_REACHED,
}
_BUDGET = {OutcomeCode.BUDGET_EXHAUSTED, OutcomeCode.LIMIT_REACHED}
_STATUS = {
    "COMPLETED": EnvelopeStatus.COMPLETED,
    "NEEDS_CLARIFICATION": EnvelopeStatus.NEEDS_CLARIFICATION,
    "AWAITING_CONFIRMATION": EnvelopeStatus.AWAITING_CONFIRMATION,
}


def to_outcome(result: TurnResult) -> TurnOutcome:
    """Map a turn result onto the Spec 3 seam (or raise the typed failure)."""

    code = result.outcome
    answer = result.response.answer.text
    if code in _UNAVAILABLE:
        raise ProviderUnavailable(answer)
    if code in _BUDGET:
        raise BudgetExceededError(answer)
    if code is OutcomeCode.CANCELLED or result.state is TurnState.CANCELLED:
        raise GoneError("Resource not found.")

    if result.state is TurnState.STALE_PLAN:
        kind = OutcomeKind.STALE_PLAN
    elif result.state is TurnState.SOURCE_WITHDRAWN:
        kind = OutcomeKind.CATALOG_WITHDRAWN
    elif result.response.status == "NEEDS_CLARIFICATION":
        kind = OutcomeKind.CLARIFICATION
    elif result.response.status == "AWAITING_CONFIRMATION":
        kind = OutcomeKind.CONFIRMATION
    elif code is OutcomeCode.NO_RESULTS:
        kind = OutcomeKind.NO_RESULTS
    else:
        kind = OutcomeKind.OK
    warnings: list[str] = list(result.response.warnings)
    if kind in (OutcomeKind.STALE_PLAN, OutcomeKind.CATALOG_WITHDRAWN):
        warnings.append(kind.value)
    plan = result.response.plan
    return TurnOutcome(
        answer=answer,
        outcome_kind=kind,
        status=_STATUS.get(result.response.status, EnvelopeStatus.COMPLETED),
        content_blocks=tuple(result.response.blocks),
        interpretation_summary=(
            summary_dto(result.response.summary) if result.response.summary else None
        ),
        plan=PlanRef(plan_id=plan.plan_id, revision=plan.revision,
                     confirmation_needed=plan.confirmation_needed) if plan else None,
        warnings=tuple(warnings),
        catalog_edition_id=str(result.edition_id) if result.edition_id else None,
        trace=debug_trace(result),
    )


def debug_trace(result: TurnResult) -> dict[str, Any]:
    """A sanitized, developer-only trace of the turn (encrypted by Spec 3)."""

    return {
        "turn_id": result.turn_id,
        "turn_states": [s.value for s in result.history],
        "outcome": result.outcome.value,
        "model_calls": result.model_calls,
        "tool_calls": [
            {
                "tool": inv.name,
                "origin": inv.origin,
                "status": inv.status.value,
                "arguments": inv.args,
                "ignored_server_arguments": list(inv.ignored_server_keys),
            }
            for inv in result.invocations
        ],
        "figures_presented": len(result.response.presented),
        "figures_withheld": len(result.response.withheld),
        "claims": [
            {"kind": c.claim.kind.value, "verdict": c.verdict.value}
            for c in result.response.claims
        ],
    }


class Series76Agent:
    """The real ``AgentPort`` implementation (Spec 4 orchestrator)."""

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def run_turn(self, request: TurnRequest) -> TurnOutcome:
        confirmation = None
        if request.confirmation is not None:
            c = request.confirmation
            confirmation = ConfirmationSignal(
                session_id=request.session_id,
                plan_id=c.plan_id,
                plan_revision=c.plan_revision,
                user_id=c.user_id,
                bound_to_current=c.bound_to_current,
            )
        result = await self._orchestrator.run_turn(
            TurnInput(
                session_id=request.session_id,
                owner_id=request.owner_id,
                message=request.query or None,
                confirmation=confirmation,
                trace_id=request.trace_id,
            )
        )
        return to_outcome(result)


class UnconfiguredAgent:
    """Answers every turn with a clear 503 when no model runtime is configured."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def run_turn(self, request: TurnRequest) -> TurnOutcome:
        raise ProviderUnavailable(self._reason)


def build_series76_agent(
    *,
    session_factory: Any,
    crypto: Any,
    database_url: str,
    catalog_database_url: str = "",
    api_key: str = "",
    env: Mapping[str, str] | None = None,
) -> Any:
    """Compose the production agent from the environment (no hardcoded model).

    Returns :class:`UnconfiguredAgent` when the model runtime is not configured
    (no ``OPENROUTER_API_KEY`` or ``AGENT_MODEL``), so the service still starts
    and reports a clear, retryable 503 instead of inventing answers.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError

    from series76_agent.integration.spec3 import (
        CatalogUnavailable,
        PgCancellationPort,
        PgCatalogToolProvider,
        PgDomainStateStore,
        PgEditionPort,
        PgPlanPort,
        PgTurnStateRecorder,
    )
    from series76_agent.llm import (
        OpenRouterChatFactory,
        OpenRouterInterpreterModel,
        usage_from_message,
    )

    source = os.environ if env is None else env
    try:
        config = ModelConfig.from_env(source)
    except ModelConfigError:
        return UnconfiguredAgent("The assistant's language model is not configured.")
    if not api_key:
        return UnconfiguredAgent("The assistant's language model is not configured.")
    registry = CapabilityRegistry.from_env(source)
    ledger_path = source.get("COST_LEDGER_PATH")
    ledger = CostLedger(path=Path(ledger_path) if ledger_path else None)
    gateway = ModelGateway(config, registry, ledger)
    tool_set = source.get("AGENT_TOOL_SET", "B").upper()
    url = catalog_database_url or database_url
    engine = create_engine(url, pool_pre_ping=True)
    orchestrator = AgentOrchestrator(
        interpreter=SemanticInterpreter(OpenRouterInterpreterModel(config), gateway),
        tool_agent=ToolAgent(gateway, OpenRouterChatFactory(config), usage_from_message),
        catalog=PgCatalogToolProvider(engine, tool_set),
        editions=PgEditionPort(session_factory),
        states=PgDomainStateStore(session_factory, crypto),
        turn_states=PgTurnStateRecorder(session_factory),
        plans=PgPlanPort(session_factory, crypto),
        cancellation=PgCancellationPort(session_factory),
        config=OrchestratorConfig(
            tool_allow_list=TOOL_SET_A if tool_set == "A" else TOOL_SET_B,
            budget=TurnBudget.from_env(source),
            transient_tool_errors=(OperationalError, CatalogUnavailable),
        ),
    )
    return Series76Agent(orchestrator)
