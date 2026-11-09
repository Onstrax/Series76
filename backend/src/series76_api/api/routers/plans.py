"""Plans router: confirm a plan revision (Spec 3, Req 7).

* ``POST /api/sessions/{id}/plans/{rev}/confirm`` — confirm the current plan
  revision (owner-only). A non-current revision -> ``409 STALE_PLAN``; an
  unknown revision -> ``404``; unauthenticated -> ``401`` with no effect;
  non-owner -> indistinguishable ``404`` (Properties 28, 29, 30, 10).

Plan *creation/revision* is driven by the agent turn (Spec 4) through the
service; the HTTP surface here is the confirmation contract.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header

from series76_api.api.dependencies import AgentDep, ClockDep, CryptoDep, SessionDep
from series76_api.application.agent_seam import ConfirmationRequest
from series76_api.application.authorization import authenticate
from series76_api.application.conversation_service import ConversationService
from series76_api.application.plans_service import PlansService
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.errors import ValidationError

router = APIRouter(prefix="/api/sessions", tags=["plans"])


def _parse_uuid(raw: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"Malformed {what}.") from exc


@router.post("/{session_id}/plans/{revision}/confirm")
async def confirm_plan(
    session_id: str,
    revision: int,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    agent: AgentDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Confirm the current plan revision; idempotent, owner-only.

    The first confirmation of the current revision triggers its single
    execution through the agent seam (after the confirmation committed); a
    repeated confirmation executes nothing (Property 29, Spec 4 Req 6.5).
    """

    sid = _parse_uuid(session_id, "session id")
    async with UnitOfWork(session) as uow:
        # Authentication precedes any effect: unauthenticated -> 401, nothing
        # is confirmed or executed (Property 30).
        principal = await authenticate(uow, clock, authorization)
        service = PlansService(uow, clock, crypto)
        result = await service.confirm(principal, sid, revision)
        envelope = None
        if result.executed:
            envelope = await ConversationService(
                uow, clock, crypto, agent
            ).run_confirmation_turn(
                principal,
                sid,
                ConfirmationRequest(
                    plan_id=str(result.plan_id),
                    plan_revision=result.plan_revision,
                    user_id=principal.user_id,
                    bound_to_current=True,
                    first_confirmation=True,
                ),
            )
    return {
        "plan_id": str(result.plan_id),
        "plan_revision": result.plan_revision,
        "status": "confirmed",
        "result": envelope.model_dump(mode="json") if envelope is not None else None,
    }


__all__ = ["router"]
