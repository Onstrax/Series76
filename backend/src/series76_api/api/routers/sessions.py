"""Sessions router: list/search, messages, rename, delete (Spec 3, Req 8).

* ``GET /api/sessions`` — the caller's conversations with titles/dates; an
  optional ``q`` applies a title-only search that decrypts after authorization
  (Property 35).
* ``GET /api/sessions/{id}/messages`` — the owner's messages + typed blocks in
  deterministic order, excluding debug traces (Property 36).
* ``PATCH /api/sessions/{id}`` — rename, enforcing length + ownership (Property
  37).
* ``DELETE /api/sessions/{id}`` — tombstone + crypto-shred (Properties 31-34).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status

from series76_api.api.dependencies import ClockDep, CryptoDep, SessionDep
from series76_api.api.dtos import (
    MessageResponse,
    RenameRequest,
    SessionSummaryResponse,
)
from series76_api.application.authorization import authenticate
from series76_api.application.conversation_service import ConversationService
from series76_api.application.deletion_service import DeletionService
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.errors import ValidationError

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _parse_session_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Malformed session id.") from exc


# A conversation service needs an agent seam; reads never dispatch it, so we
# pass the app's faked seam via the request only where a turn is run. Reads
# construct the service with a no-op placeholder agent.
from series76_api.application.agent_seam import FakeAgent  # noqa: E402

_READ_AGENT = FakeAgent()


@router.get("")
async def list_sessions(
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> list[SessionSummaryResponse]:
    """List the caller's conversations (optional owner-scoped title search)."""

    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = ConversationService(uow, clock, crypto, _READ_AGENT)
        summaries = await service.list_sessions(principal, title_query=q)
    return [
        SessionSummaryResponse(
            session_id=str(s.session_id),
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            pending_jobs=s.pending_jobs,
        )
        for s in summaries
    ]


@router.get("/{session_id}/messages")
async def get_messages(
    session_id: str,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    authorization: Annotated[str | None, Header()] = None,
) -> list[MessageResponse]:
    """Return the owner's messages + typed blocks in deterministic order."""

    sid = _parse_session_id(session_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = ConversationService(uow, clock, crypto, _READ_AGENT)
        views = await service.get_messages(principal, sid)
    return [
        MessageResponse(
            message_id=str(v.message_id),
            role=v.role,
            content=v.content,
            blocks=v.blocks,
            created_at=v.created_at,
        )
        for v in views
    ]


@router.patch("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_session(
    session_id: str,
    body: RenameRequest,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Rename a conversation (1-200 chars, owner-only)."""

    sid = _parse_session_id(session_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = ConversationService(uow, clock, crypto, _READ_AGENT)
        await service.rename_session(principal, sid, body.title)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    session: SessionDep,
    clock: ClockDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Delete a conversation: tombstone, purge, crypto-shred (204)."""

    sid = _parse_session_id(session_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = DeletionService(uow, clock)
        await service.delete(principal, sid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
