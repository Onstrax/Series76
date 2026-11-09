"""Pure domain enums and value objects for the Series 76 backend (Spec 3).

These mirror the conceptual data model exactly and are shared by the
application and infrastructure layers. They are pure: no FastAPI, SQLAlchemy,
LangChain, or provider imports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    """Account role. ``developer`` is a Debug capability over the developer's
    OWN resources only — never a superuser (design: Authorization guard)."""

    USER = "user"
    DEVELOPER = "developer"


class TokenType(str, Enum):
    """Opaque-token kind stored in ``identity.token_verifiers``."""

    ACCESS = "access"
    REFRESH = "refresh"


class JobState(str, Enum):
    """Durable ``turn_jobs`` state machine (design: Job_State enum, Req 5.6).

    Each ``turn_job`` carries exactly one. Conversation and plan state are
    modeled separately and are not members of this enum.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE_PLAN = "STALE_PLAN"
    CATALOG_WITHDRAWN = "CATALOG_WITHDRAWN"


# PostgreSQL enum type names (shared with the Alembic migration).
USER_ROLE_ENUM = "user_role"
TOKEN_TYPE_ENUM = "token_type"
JOB_STATE_ENUM = "job_state"


@dataclass(frozen=True, slots=True)
class User:
    """A registered account. ``password_verifier`` is a one-way Argon2id hash,
    never reversible ciphertext (design: Data Models)."""

    id: uuid.UUID
    email: str
    password_verifier: str
    role: UserRole
    email_verified: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """The authoritative identity resolved from a validated session token.

    The authorization guard derives ``Owner_User_Id`` from this principal and
    from nothing in the request body/query/header (Property 10).
    """

    user_id: uuid.UUID
    role: UserRole
    auth_session_id: uuid.UUID


__all__ = [
    "UserRole",
    "TokenType",
    "JobState",
    "USER_ROLE_ENUM",
    "TOKEN_TYPE_ENUM",
    "JOB_STATE_ENUM",
    "User",
    "AuthenticatedPrincipal",
]
