"""Jobs router: poll + cancel durable turn jobs (Spec 3, Req 5).

* ``GET /api/jobs/{id}`` — owner poll returning exactly one ``Job_State`` and,
  on ``COMPLETED``, the shared ``Response_Envelope``. ``Cache-Control:
  no-store`` is always set; non-terminal states carry a ``Retry-After`` integer
  in ``[1, 60]`` (Properties 18, 20).
* ``POST /api/jobs/{id}/cancel`` — idempotent cancel for cancelable states
  (Property 19). Non-owner GET/cancel is an indistinguishable denial (P10).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response, status

from series76_api.api.dependencies import ClockDep, CryptoDep, SessionDep, SettingsDep
from series76_api.application.authorization import authenticate
from series76_api.application.jobs_service import JobsService
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.errors import ValidationError

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _parse_job_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Malformed job id.") from exc


@router.get("/{job_id}")
async def poll_job(
    job_id: str,
    response: Response,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Poll a job owner-scoped; returns one state + envelope on COMPLETED."""

    jid = _parse_job_id(job_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = JobsService(uow, clock, crypto, settings)
        poll = await service.poll(principal, jid)

    # Cache-Control: no-store is ALWAYS set (Property 20).
    response.headers["Cache-Control"] = "no-store"
    body: dict[str, Any] = {"job_id": str(poll.job_id), "status": poll.state.value}
    if poll.retry_after is not None:
        response.headers["Retry-After"] = str(poll.retry_after)
    if poll.envelope is not None:
        body["response"] = poll.envelope.model_dump(mode="json")
    return body


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    response: Response,
    session: SessionDep,
    clock: ClockDep,
    crypto: CryptoDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Cancel a job idempotently (owner-only, cancelable states)."""

    jid = _parse_job_id(job_id)
    async with UnitOfWork(session) as uow:
        principal = await authenticate(uow, clock, authorization)
        service = JobsService(uow, clock, crypto, settings)
        state = await service.cancel(principal, jid)
    response.status_code = status.HTTP_200_OK
    response.headers["Cache-Control"] = "no-store"
    return {"job_id": str(jid), "status": state.value}


__all__ = ["router"]
