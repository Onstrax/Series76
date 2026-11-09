"""Shared helpers for the Spec 3 Half B API integration tests.

Register + log in a user (or a seeded developer), build Authorization headers,
and run conversation turns against the live-container FastAPI app. Kept
deliberately small and typed so each property test reads clearly.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient, Response

from series76_api.domain.models import UserRole
from series76_api.seed import seed_account

STRONG_PASSWORD = "Str0ng-Passw0rd!"


def unique_email(prefix: str = "user") -> str:
    """Return a unique canonical email for test isolation."""

    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def auth_header(access_token: str) -> dict[str, str]:
    """Build an Authorization header from an access token."""

    return {"Authorization": f"Bearer {access_token}"}


async def register_and_login(
    client: AsyncClient, email: str | None = None
) -> tuple[str, dict[str, str]]:
    """Register a fresh ``user`` and log in; return (email, auth header)."""

    email = email or unique_email()
    reg = await client.post(
        "/api/auth/register", json={"email": email, "password": STRONG_PASSWORD}
    )
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    )
    assert login.status_code == 200, login.text
    access = login.json()["access_token"]
    return email, auth_header(access)


async def seed_developer_and_login(
    client: AsyncClient, database_url: str, email: str | None = None
) -> tuple[str, dict[str, str]]:
    """Seed a ``developer`` (CLI-only path) and log in; return (email, header)."""

    email = email or unique_email("dev")
    await seed_account(
        database_url, email=email, password=STRONG_PASSWORD, role=UserRole.DEVELOPER
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    )
    assert login.status_code == 200, login.text
    return email, auth_header(login.json()["access_token"])


async def turn(
    client: AsyncClient,
    headers: dict[str, str],
    query: str,
    *,
    session_id: str | None = None,
    client_request_id: str | None = None,
) -> Response:
    """POST a mandatory sync conversation turn."""

    body: dict[str, Any] = {"query": query}
    if session_id is not None:
        body["session_id"] = session_id
    if client_request_id is not None:
        body["client_request_id"] = client_request_id
    return await client.post("/api/conversation", json=body, headers=headers)


__all__ = [
    "STRONG_PASSWORD",
    "unique_email",
    "auth_header",
    "register_and_login",
    "seed_developer_and_login",
    "turn",
]
