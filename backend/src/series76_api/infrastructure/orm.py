"""SQLAlchemy 2.0 ORM models mirroring the Spec 3 migration (infrastructure).

These are the single concrete access layer (no separate DAO). They mirror the
tables created by migration ``0006_api_schemas`` exactly; the migration — not
this ORM — is the schema source of truth (same convention as Spec 1). DTOs in
the api layer are kept distinct from these ORM models.

Half A maps the identity tables, the ``conversations`` table, and
``key_metadata`` (the crypto key handle). Messages/plans/jobs tables exist in
the migration and get ORM models in Half B; leaving them unmapped here keeps
the surface small without blocking those seams.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from series76_api.domain.models import JobState, TokenType, UserRole

_user_role_enum: PgEnum = PgEnum(
    UserRole,
    name="user_role",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_token_type_enum: PgEnum = PgEnum(
    TokenType,
    name="token_type",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_job_state_enum: PgEnum = PgEnum(
    JobState,
    name="job_state",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Base(DeclarativeBase):
    """Declarative base for the Spec 3 ORM models."""


class UserORM(Base):
    """``identity.users`` — ``password_verifier`` is a one-way Argon2id hash."""

    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_verifier: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _user_role_enum, nullable=False, server_default="user"
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class AuthSessionORM(Base):
    """``identity.auth_sessions`` — session metadata, no secrets."""

    __tablename__ = "auth_sessions"
    __table_args__ = {"schema": "identity"}

    auth_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class TokenVerifierORM(Base):
    """``identity.token_verifiers`` — stores only ``SHA-256(secret)`` verifiers."""

    __tablename__ = "token_verifiers"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    public_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_type: Mapped[TokenType] = mapped_column(_token_type_enum, nullable=False)
    verifier: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_family_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    prev_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    auth_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.auth_sessions.auth_session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class LoginAttemptORM(Base):
    """``identity.login_attempts`` — content-free ledger for login lockout."""

    __tablename__ = "login_attempts"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class ConversationORM(Base):
    """``conversation.conversations`` — ``title_ciphertext`` is encrypted."""

    __tablename__ = "conversations"
    __table_args__ = {"schema": "conversation"}

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    catalog_edition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    title_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    tombstone_fence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class KeyMetadataORM(Base):
    """``execution.key_metadata`` — the DEK stored ONLY wrapped by the KEK."""

    __tablename__ = "key_metadata"
    __table_args__ = {"schema": "execution"}

    key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cipher_version: Mapped[int] = mapped_column(Integer, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
        unique=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    shredded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MessageORM(Base):
    """``conversation.messages`` — content + typed blocks are encrypted."""

    __tablename__ = "messages"
    __table_args__ = {"schema": "conversation"}

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    blocks_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    #: Insertion order (identity); breaks same-transaction ``created_at`` ties.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)


class DomainStateORM(Base):
    """``conversation.domain_states`` — per-conversation state ciphertext."""

    __tablename__ = "domain_states"
    __table_args__ = {"schema": "conversation"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    state_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class PlanORM(Base):
    """``conversation.plans`` — revisioned, encrypted plan content."""

    __tablename__ = "plans"
    __table_args__ = {"schema": "conversation"}

    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    plan_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class TurnJobORM(Base):
    """``execution.turn_jobs`` — the durable per-session turn queue."""

    __tablename__ = "turn_jobs"
    __table_args__ = {"schema": "execution"}

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    job_state: Mapped[JobState] = mapped_column(
        _job_state_enum, nullable=False, server_default="QUEUED"
    )
    accepted_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    input_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    result_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    fencing_token: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class JobAttemptORM(Base):
    """``execution.job_attempts`` — one row per worker attempt of a job."""

    __tablename__ = "job_attempts"
    __table_args__ = {"schema": "execution"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution.turn_jobs.job_id"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detail_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class EncryptedCheckpointORM(Base):
    """``execution.encrypted_checkpoints`` — GCM-encrypted LangGraph state."""

    __tablename__ = "encrypted_checkpoints"
    __table_args__ = {"schema": "execution"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    checkpoint_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pending_writes_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    cipher_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class ToolTraceORM(Base):
    """``execution.tool_traces`` — encrypted sanitized trace + timing."""

    __tablename__ = "tool_traces"
    __table_args__ = {"schema": "execution"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.messages.message_id"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.conversations.session_id"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    trace_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class AuditEventORM(Base):
    """``execution.audit_events_minimal`` — content-free audit ledger."""

    __tablename__ = "audit_events_minimal"
    __table_args__ = {"schema": "execution"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True
    )


__all__ = [
    "Base",
    "UserORM",
    "AuthSessionORM",
    "TokenVerifierORM",
    "LoginAttemptORM",
    "ConversationORM",
    "KeyMetadataORM",
    "MessageORM",
    "DomainStateORM",
    "PlanORM",
    "TurnJobORM",
    "JobAttemptORM",
    "EncryptedCheckpointORM",
    "ToolTraceORM",
    "AuditEventORM",
]
