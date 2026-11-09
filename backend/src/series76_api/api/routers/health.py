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

from series76_api.api.dependencies import CryptoDep, SessionDep, SettingsDep

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a minimal liveness payload (no sensitive information)."""

    return {"status": "ok"}


@router.get("/ready")
async def ready(
    session: SessionDep, crypto: CryptoDep, settings: SettingsDep
) -> dict[str, Any]:
    """Return readiness, distinguishing database from other dependencies.

    Distinguishes **database** availability from **other critical
    dependencies** — key material and the LLM **provider** (Property 49). A
    degraded dependency is reported as a ``False`` flag so the process stays up
    and surfaces the degradation rather than crashing. Overall readiness
    requires the database and key material; a degraded *provider* is reported
    but does not, on its own, crash the service (the sync turn surfaces
    ``UPSTREAM_UNAVAILABLE`` honestly).
    """

    database_ok = False
    try:
        await session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 — report degradation, never crash readiness
        database_ok = False

    # ``has_kek`` is a boolean only; the KEK value itself is never exposed.
    key_material_ok = crypto.has_kek
    # Provider readiness is a configuration signal only; we never make an
    # outbound call here (zero spend). An unconfigured provider is reported as
    # a degraded-but-non-fatal dependency, distinct from the database.
    provider_ok = bool(settings.openrouter_api_key or settings.agent_model)

    return {
        "ready": database_ok and key_material_ok,
        "dependencies": {
            "database": database_ok,
            "key_material": key_material_ok,
            "provider": provider_ok,
        },
    }


__all__ = ["router"]
