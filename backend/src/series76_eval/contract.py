"""Versioned backend contract snapshot (Spec 6 Test_Level 5, Req 1.4).

The OpenAPI document of the Spec 3 app is committed at
``docs/contract/openapi.json``; the contract level fails when the live schema
drifts from it, so any contract change is an explicit, reviewed snapshot update
(``python -m series76_eval contract-snapshot --write``).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

SNAPSHOT = Path(__file__).resolve().parents[3] / "docs" / "contract" / "openapi.json"

#: Endpoints the delivery must expose (assessment brief + Spec 3).
MANDATORY: tuple[tuple[str, str], ...] = (
    ("post", "/api/conversation"),
    ("post", "/api/conversation/jobs"),
    ("get", "/api/jobs/{job_id}"),
    ("post", "/api/auth/register"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/refresh"),
    ("post", "/api/auth/logout"),
    ("get", "/api/auth/me"),
    ("get", "/api/sessions"),
)


def current_openapi() -> dict[str, Any]:
    """The live OpenAPI schema (no database connection is opened)."""

    from series76_api.app import create_app
    from series76_api.infrastructure.settings import Settings

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        DATABASE_URL="postgresql://contract:contract@localhost:5432/contract",
        ENCRYPTION_KEK=base64.b64encode(b"contract-snapshot-placeholder-k!").decode("ascii"),
        AGENT_RUNTIME="fake",
    )
    schema: dict[str, Any] = create_app(settings).openapi()
    return schema


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_snapshot() -> Path:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(render(current_openapi()), encoding="utf-8")
    return SNAPSHOT
