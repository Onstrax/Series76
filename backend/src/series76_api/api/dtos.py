"""Pydantic v2 request/response DTOs for the auth endpoints (Spec 3).

DTOs are deliberately distinct from the ORM models. The register DTO does not
even declare a ``role`` field, so a client-supplied role is dropped at the
transport edge (``extra="ignore"``) and can never influence the server-assigned
``user`` role (Property 3).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from series76_api.domain.models import UserRole


class RegisterRequest(BaseModel):
    """Registration payload: email + password only.

    ``extra="ignore"`` drops any unexpected field (including an injected
    ``role``/privilege field) so it never reaches the use case.
    """

    model_config = ConfigDict(extra="ignore")

    email: str
    password: str


class LoginRequest(BaseModel):
    """Login payload: email + password."""

    model_config = ConfigDict(extra="ignore")

    email: str
    password: str


class RefreshRequest(BaseModel):
    """Refresh payload carrying the presented refresh token string.

    The token may also be presented via the ``Authorization`` header; the body
    form is accepted for non-browser clients.
    """

    model_config = ConfigDict(extra="ignore")

    refresh_token: str


class TokenPairResponse(BaseModel):
    """The issued access+refresh token pair returned to the client once."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Registration result and ``/me`` body: identity + role only.

    Contains NO password hash, token secret, or verifier (Property 9).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    role: UserRole
    email_verified: bool


class MeResponse(BaseModel):
    """``GET /api/auth/me`` body — identity and role, never secret material."""

    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    role: UserRole


class ConversationTurnRequest(BaseModel):
    """``POST /api/conversation`` body: optional session id + required query.

    ``client_request_id`` is the idempotency key (Property 15). ``extra`` is
    ignored so a client cannot smuggle an ``owner_id`` (Property 10).
    """

    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None
    query: str
    client_request_id: str | None = None


class JobAcceptedResponse(BaseModel):
    """``POST /api/conversation/jobs`` 202 body: job id + session + QUEUED."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    session_id: str
    status: str


class RenameRequest(BaseModel):
    """``PATCH /api/sessions/{id}`` body: a new title (validated in the service)."""

    model_config = ConfigDict(extra="ignore")

    title: str


class SessionSummaryResponse(BaseModel):
    """A ``GET /api/sessions`` listing entry (title decrypted after authorize)."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    title: str | None
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    """A ``GET /api/sessions/{id}/messages`` entry (decrypted, trace-free)."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    role: str
    content: str
    blocks: list[dict[str, object]]
    created_at: str


__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "RefreshRequest",
    "TokenPairResponse",
    "UserResponse",
    "MeResponse",
    "ConversationTurnRequest",
    "JobAcceptedResponse",
    "RenameRequest",
    "SessionSummaryResponse",
    "MessageResponse",
]
