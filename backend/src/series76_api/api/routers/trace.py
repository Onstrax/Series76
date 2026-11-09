"""Debug-trace router (Spec 3, Req 10).

``GET /api/sessions/{id}/messages/{mid}/trace`` returns a sanitized trace to a
developer-owner, or a byte-for-byte identical ``404`` denial for every other
case (non-developer, non-owner, developer A vs B, nonexistent, deleted). The
denial is emitted as a fixed :class:`JSONResponse` (not through the error
envelope, whose per-request ``request_id`` would vary) so it is identical across
all denied cases (Property 46).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from series76_api.api.dependencies import ClockDep, CryptoDep, SessionDep
from series76_api.application.authorization import authenticate
from series76_api.application.trace_service import TraceService
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.trace import IDENTICAL_DENIAL

router = APIRouter(prefix="/api/sessions", tags=["trace"])


def _denial() -> JSONResponse:
    """The single byte-for-byte identical denial for every unauthorized case."""

    return JSONResponse(status_code=404, content=IDENTICAL_DENIAL)


@router.get("/{session_id}/messages/{message_id}/trace")
async def get_trace(
    session_id: str,
    message_id: str,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Return a sanitized trace to a developer-owner, else an identical denial."""

    # A malformed id is treated as the identical denial, disclosing nothing.
    try:
        sid = uuid.UUID(session_id)
        mid = uuid.UUID(message_id)
    except (ValueError, AttributeError):
        return _denial()

    async with UnitOfWork(session) as uow:
        # An unauthenticated caller is denied identically (authenticate raises;
        # we convert any auth failure into the same denial so existence and
        # auth state are indistinguishable at this endpoint).
        try:
            principal = await authenticate(uow, clock, authorization)
        except Exception:  # noqa: BLE001 — identical denial, no disclosure
            return _denial()
        service = TraceService(uow, crypto)
        sanitized = await service.get_sanitized_trace(principal, sid, mid)

    if sanitized is None:
        return _denial()
    return JSONResponse(status_code=200, content=sanitized)


__all__ = ["router"]
