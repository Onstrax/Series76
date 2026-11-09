"""Conversation router: the mandatory sync turn + async enqueue (Spec 3, Req 4, 5).

* ``POST /api/conversation`` — the mandatory sync endpoint; always returns a
  ``Response_Envelope`` with a non-empty ``session_id`` + ``answer`` (Property
  11). The ``202`` async acceptance is never substituted for this response.
* ``POST /api/conversation/jobs`` — accepts an async turn job, returning ``202``
  with ``job_id``, ``session_id``, and ``status=QUEUED`` (Property 17).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, status

from series76_api.api.dependencies import (
    AgentDep,
    ClockDep,
    CryptoDep,
    SessionDep,
    SettingsDep,
)
from series76_api.api.dtos import ConversationTurnRequest, JobAcceptedResponse
from series76_api.api.envelopes import ResponseEnvelope
from series76_api.application.authorization import authenticate
from series76_api.application.conversation_service import ConversationService
from series76_api.application.jobs_service import JobsService
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.errors import ValidationError

router = APIRouter(prefix="/api/conversation", tags=["conversation"])


def _parse_session_id(raw: str | None) -> uuid.UUID | None:
    """Parse an optional session id, raising ``VALIDATION_ERROR`` if malformed.

    A malformed session id is a client error, not an enumeration surface; it is
    rejected before any persistence.
    """

    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Malformed session id.") from exc


@router.post("")
async def create_turn(
    body: ConversationTurnRequest,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    agent: AgentDep,
    authorization: Annotated[str | None, Header()] = None,
) -> ResponseEnvelope:
    """Run a mandatory sync turn; always returns a non-empty envelope."""

    session_id = _parse_session_id(body.session_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = ConversationService(uow, clock, crypto, agent)
        return await service.run_sync_turn(
            principal,
            session_id=session_id,
            query=body.query,
            client_request_id=body.client_request_id,
        )


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_turn(
    body: ConversationTurnRequest,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> JobAcceptedResponse:
    """Accept an async turn job (``202``/``QUEUED``); never substitutes sync."""

    session_id = _parse_session_id(body.session_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = JobsService(uow, clock, crypto, settings)
        accepted = await service.accept(
            principal,
            session_id=session_id,
            query=body.query,
            client_request_id=body.client_request_id,
        )
    return JobAcceptedResponse(
        job_id=str(accepted.job_id),
        session_id=str(accepted.session_id),
        status=accepted.status.value,
    )


__all__ = ["router"]
