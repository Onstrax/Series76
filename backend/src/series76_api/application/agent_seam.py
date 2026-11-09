"""The agent/LLM seam that Spec 4 plugs into (Spec 3, Req 4.1-4.4, 4.8).

Spec 3 owns the trust/transport/durability boundary and the *seam* the Spec 4
agent runtime plugs into. The real agent (LangGraph + an OpenRouter-backed
model) is **not** implemented here and is **faked** in CI so no provider call
and no spend ever happens. This module defines:

* :class:`TurnRequest` / :class:`TurnOutcome` — the DTOs crossing the seam;
* :class:`AgentPort` — the protocol a turn processor implements;
* :class:`FakeAgent` — a deterministic, zero-spend implementation used by the
  sync endpoint, the worker, and the tests.

The outcome carries only a user-safe ``answer`` (no unverified number), an
optional ``status`` (clarification/confirmation), structural ``content_blocks``,
and an optional ``outcome_kind`` distinguishing a zero-match ``NO_RESULTS``
business success from an ``UPSTREAM_UNAVAILABLE`` provider failure (Req 11.2).
No model name, prompt, tool name, or secret ever crosses the seam.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from series76_api.api.envelopes import (
    ContentBlock,
    EnvelopeStatus,
    InterpretationSummaryDTO,
    PlanRef,
    PlanReviewBlock,
    ResponseEnvelope,
    TextBlock,
)


class OutcomeKind(str, Enum):
    """The business classification of a turn outcome.

    ``NO_RESULTS`` is a *successful* business outcome (HTTP 200), kept strictly
    distinct from the ``UPSTREAM_UNAVAILABLE`` provider failure (HTTP 503) so
    the two are never conflated (Property 48).
    """

    OK = "OK"
    NO_RESULTS = "NO_RESULTS"
    CLARIFICATION = "CLARIFICATION"
    CONFIRMATION = "CONFIRMATION"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    STALE_PLAN = "STALE_PLAN"
    CATALOG_WITHDRAWN = "CATALOG_WITHDRAWN"


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    """A confirmation the plan seam has validated and materialized.

    ``bound_to_current`` is set only when the confirmed revision is the
    conversation's current revision for its authenticated owner;
    ``first_confirmation`` is ``True`` only for the confirmation that triggers
    the (single) execution of that revision.
    """

    plan_id: str
    plan_revision: int
    user_id: uuid.UUID
    bound_to_current: bool
    first_confirmation: bool


@dataclass(frozen=True, slots=True)
class TurnRequest:
    """A single turn to process. Carries the validated query + prior history.

    ``history`` is the owner-scoped prior turns (role, text) the resumed
    conversation provides; the seam implementation decides how to use it.
    """

    owner_id: uuid.UUID
    session_id: uuid.UUID
    query: str
    history: tuple[tuple[str, str], ...] = ()
    confirmation: ConfirmationRequest | None = None
    trace_id: str = ""


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    """The result of processing a turn, mapped onto the ``Response_Envelope``.

    ``answer`` is always non-empty and user-safe (Property 11). ``status`` is
    set for clarification/confirmation turns (Property 13). ``plan_summary``
    requests a plan-review block when present.
    """

    answer: str
    outcome_kind: OutcomeKind = OutcomeKind.OK
    status: EnvelopeStatus | None = None
    content_blocks: tuple[ContentBlock, ...] = ()
    plan_summary: str | None = None
    verified_figures: tuple[float, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    interpretation_summary: InterpretationSummaryDTO | None = None
    plan: PlanRef | None = None
    warnings: tuple[str, ...] = ()
    catalog_edition_id: str | None = None
    trace: dict[str, Any] | None = None


class AgentPort(Protocol):
    """The seam a turn processor implements (real agent in Spec 4, fake in CI)."""

    async def run_turn(self, request: TurnRequest) -> TurnOutcome:
        """Process one turn and return a :class:`TurnOutcome` (no provider spend
        in the fake)."""
        ...


class ProviderUnavailable(Exception):
    """Raised by a seam implementation to signal a provider/upstream failure.

    The transport layer maps this to ``UPSTREAM_UNAVAILABLE`` (503), never to a
    ``NO_RESULTS`` success (Property 48).
    """


class FakeAgent:
    """A deterministic, zero-spend agent used by the sync endpoint and worker.

    It never contacts a provider. It inspects the query text for small, stable
    markers so tests can drive each turn outcome deterministically:

    * contains ``[clarify]`` -> a clarification turn (status ``clarification``);
    * contains ``[confirm]`` -> a confirmation turn (status ``confirmation``);
    * contains ``[noresults]`` -> a ``NO_RESULTS`` business success;
    * contains ``[upstream_down]`` -> raises :class:`ProviderUnavailable`;
    * otherwise -> a completed turn echoing a safe acknowledgement.

    The ``answer`` is always a non-empty, user-safe string carrying no
    unverified technical number (Property 11, 13).
    """

    def __init__(self, *, marker_prefix: str = "") -> None:
        self._marker_prefix = marker_prefix

    async def run_turn(self, request: TurnRequest) -> TurnOutcome:
        """Produce a deterministic outcome from the query markers (no spend)."""

        q = request.query.lower()
        if "[upstream_down]" in q:
            raise ProviderUnavailable("The assistant is temporarily unavailable.")
        if "[clarify]" in q:
            return TurnOutcome(
                answer="Could you clarify your request so I can help accurately?",
                outcome_kind=OutcomeKind.CLARIFICATION,
                status=EnvelopeStatus.CLARIFICATION,
            )
        if "[confirm]" in q:
            return TurnOutcome(
                answer="Please confirm before I proceed with this action.",
                outcome_kind=OutcomeKind.CONFIRMATION,
                status=EnvelopeStatus.CONFIRMATION,
                plan_summary="Proposed plan awaiting your confirmation.",
            )
        if "[noresults]" in q:
            return TurnOutcome(
                answer="I could not find any matching results for that request.",
                outcome_kind=OutcomeKind.NO_RESULTS,
                status=EnvelopeStatus.COMPLETED,
            )
        # Default: a completed, user-safe acknowledgement (no unverified number).
        return TurnOutcome(
            answer="Here is what I found for your request.",
            outcome_kind=OutcomeKind.OK,
            status=EnvelopeStatus.COMPLETED,
            content_blocks=(TextBlock(text="Here is what I found for your request."),),
        )


def build_response_envelope(
    session_id: uuid.UUID,
    outcome: TurnOutcome,
    *,
    turn_id: str | None = None,
    message_id: str | None = None,
) -> ResponseEnvelope:
    """Map a :class:`TurnOutcome` onto the inviolable ``Response_Envelope``.

    ``answer`` is never empty; a plan summary from a seam implementation adds a
    plan-review block; an outcome with no block falls back to a text block.
    """

    answer = outcome.answer or "Here is your response."
    blocks = list(outcome.content_blocks)
    if outcome.plan_summary is not None:
        blocks.append(
            PlanReviewBlock(summary=outcome.plan_summary, requires_confirmation=True)
        )
    if not blocks:
        blocks = [TextBlock(text=answer)]
    return ResponseEnvelope(
        session_id=str(session_id),
        answer=answer,
        content_blocks=blocks,
        status=outcome.status or EnvelopeStatus.COMPLETED,
        interpretation_summary=outcome.interpretation_summary,
        plan=outcome.plan,
        warnings=list(outcome.warnings),
        catalog_edition_id=outcome.catalog_edition_id,
        turn_id=turn_id,
        message_id=message_id,
    )


__all__ = [
    "build_response_envelope",
    "OutcomeKind",
    "ConfirmationRequest",
    "TurnRequest",
    "TurnOutcome",
    "AgentPort",
    "ProviderUnavailable",
    "FakeAgent",
]
