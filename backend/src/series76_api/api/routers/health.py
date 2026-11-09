"""Liveness and readiness routes (Spec 3, Req 11.6).

* ``GET /api/health`` — liveness with no sensitive info.
* ``GET /api/ready`` — readiness distinguishing database availability from
  other critical dependencies (e.g. crypto key material). Reflects degraded
  dependencies rather than crashing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from series76_api.api.dependencies import CryptoDep, SessionDep

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a minimal liveness payload (no sensitive information)."""

    return {"status": "ok"}


@router.get("/ready")
async def ready(session: SessionDep, crypto: CryptoDep) -> dict[str, Any]:
    """Return readiness, distinguishing database from other dependencies.

    Never raises on a degraded dependency: a failing probe is reported as a
    ``False`` flag so the process stays up and surfaces the degradation.
    """

    database_ok = False
    try:
        await session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 — report degradation, never crash readiness
        database_ok = False

    # ``has_kek`` is a boolean only; the KEK value itself is never exposed.
    key_material_ok = crypto.has_kek
    ready_overall = database_ok
    return {
        "ready": ready_overall,
        "dependencies": {
            "database": database_ok,
            "key_material": key_material_ok,
        },
    }


__all__ = ["router"]
