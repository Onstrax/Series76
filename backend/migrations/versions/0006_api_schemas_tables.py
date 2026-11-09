"""Create the Spec 3 ``identity``, ``conversation``, and ``execution`` schemas.

Revision ID: 0006_api_schemas
Revises: 0005_roles_grants
Create Date: Spec 3 — Task 2.1

Creates the application schemas and every table from the design Data Models
table, plus the ``user_role``, ``token_type``, and ``job_state`` ENUM types.
Sensitive fields are ``bytea`` ciphertext columns (titles, message content,
typed blocks, domain state, plans, sensitive traces, checkpoints, job input);
cleartext is limited to owner_id/edition/timestamps/states/accepted_seq/
lease/fence/attempt and ``key_metadata`` (key_id, cipher_version, wrapped_dek).

Invariants enforced here:
  * ``users.email`` UNIQUE (canonical).
  * ``turn_jobs`` UNIQUE(owner_id, client_request_id) idempotency.
  * ``plans`` UNIQUE(session_id, plan_revision) — strictly increasing per
    conversation — plus a single current-revision partial unique index.
  * Every owned aggregate carries an authoritative ``owner_id`` FK.
  * ``catalog_edition_id`` references the Spec 1 ``catalog.catalog_edition``.

Requirements: 1.5, 12.2 (schema versioning via Alembic).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision: str = "0006_api_schemas"
down_revision: str | None = "0005_roles_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTITY = "identity"
CONVERSATION = "conversation"
EXECUTION = "execution"
SCHEMAS = (IDENTITY, CONVERSATION, EXECUTION)

# ENUM name -> ordered labels (mirror series76_api.domain.models).
USER_ROLE_LABELS = ("user", "developer")
TOKEN_TYPE_LABELS = ("access", "refresh")
JOB_STATE_LABELS = (
    "QUEUED",
    "RUNNING",
    "NEEDS_CLARIFICATION",
    "AWAITING_CONFIRMATION",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "STALE_PLAN",
    "CATALOG_WITHDRAWN",
)


def _quote(labels: tuple[str, ...]) -> str:
    return ", ".join("'" + x.replace("'", "''") + "'" for x in labels)


def _enum(name: str) -> pg.ENUM:
    """Reference an already-created enum type (never re-create)."""

    return pg.ENUM(name=name, create_type=False)


def upgrade() -> None:
    # --- schemas ----------------------------------------------------------
    for schema in SCHEMAS:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # --- enum types (in public so every schema can use them) --------------
    op.execute(sa.text(f"CREATE TYPE user_role AS ENUM ({_quote(USER_ROLE_LABELS)})"))
    op.execute(sa.text(f"CREATE TYPE token_type AS ENUM ({_quote(TOKEN_TYPE_LABELS)})"))
    op.execute(sa.text(f"CREATE TYPE job_state AS ENUM ({_quote(JOB_STATE_LABELS)})"))

    # ================== identity schema ==================================
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_verifier", sa.Text(), nullable=False),
        sa.Column("role", _enum("user_role"), nullable=False, server_default="user"),
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        schema=IDENTITY,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("auth_session_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("device_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_auth_sessions_owner"
        ),
        schema=IDENTITY,
    )
    op.create_index(
        "ix_auth_sessions_owner", "auth_sessions", ["owner_id"], schema=IDENTITY
    )

    op.create_table(
        "token_verifiers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        # Non-secret lookup handle presented as the public_id part of the token.
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("token_type", _enum("token_type"), nullable=False),
        # verifier = SHA-256(secret) hex; the raw secret is never stored.
        sa.Column("verifier", sa.Text(), nullable=False),
        sa.Column("refresh_family_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("prev_token_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("auth_session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("rotated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["auth_session_id"],
            [f"{IDENTITY}.auth_sessions.auth_session_id"],
            name="fk_token_verifiers_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_token_verifiers_owner"
        ),
        sa.UniqueConstraint("public_id", name="uq_token_verifiers_public_id"),
        schema=IDENTITY,
    )
    op.create_index(
        "ix_token_verifiers_family",
        "token_verifiers",
        ["refresh_family_id"],
        schema=IDENTITY,
    )
    op.create_index(
        "ix_token_verifiers_owner", "token_verifiers", ["owner_id"], schema=IDENTITY
    )

    # Login failure ledger for the 5/15min lockout (Property 5). Content-free.
    op.create_table(
        "login_attempts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        # Canonical email the attempt targeted (the throttle subject).
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column(
            "at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=IDENTITY,
    )
    op.create_index(
        "ix_login_attempts_email_at",
        "login_attempts",
        ["email", "at"],
        schema=IDENTITY,
    )

    # ================== conversation schema ==============================
    op.create_table(
        "conversations",
        sa.Column("session_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_edition_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("title_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tombstone_fence", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_conversations_owner"
        ),
        sa.ForeignKeyConstraint(
            ["catalog_edition_id"],
            ["catalog.catalog_edition.edition_id"],
            name="fk_conversations_edition",
        ),
        schema=CONVERSATION,
    )
    op.create_index(
        "ix_conversations_owner", "conversations", ["owner_id"], schema=CONVERSATION
    )

    op.create_table(
        "messages",
        sa.Column("message_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("blocks_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_messages_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_messages_owner"
        ),
        schema=CONVERSATION,
    )
    op.create_index(
        "ix_messages_session_order",
        "messages",
        ["session_id", "created_at", "message_id"],
        schema=CONVERSATION,
    )

    op.create_table(
        "domain_states",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("state_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_domain_states_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_domain_states_owner"
        ),
        sa.UniqueConstraint(
            "session_id", "revision", name="uq_domain_states_session_revision"
        ),
        schema=CONVERSATION,
    )

    op.create_table(
        "plans",
        sa.Column("plan_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column(
            "is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("plan_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_plans_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_plans_owner"
        ),
        sa.CheckConstraint("plan_revision >= 1", name="ck_plans_revision_positive"),
        sa.UniqueConstraint(
            "session_id", "plan_revision", name="uq_plans_session_revision"
        ),
        schema=CONVERSATION,
    )
    # At most one current plan revision per conversation.
    op.create_index(
        "uq_plans_one_current",
        "plans",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
        schema=CONVERSATION,
    )

    # ================== execution schema =================================
    op.create_table(
        "turn_jobs",
        sa.Column("job_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("job_state", _enum("job_state"), nullable=False, server_default="QUEUED"),
        sa.Column("accepted_seq", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column("input_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "fencing_token", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("next_retry_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_turn_jobs_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_turn_jobs_owner"
        ),
        sa.UniqueConstraint(
            "owner_id", "client_request_id", name="uq_turn_jobs_owner_request"
        ),
        sa.UniqueConstraint(
            "session_id", "accepted_seq", name="uq_turn_jobs_session_seq"
        ),
        schema=EXECUTION,
    )
    op.create_index(
        "ix_turn_jobs_state", "turn_jobs", ["job_state"], schema=EXECUTION
    )

    op.create_table(
        "job_attempts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("detail_ciphertext", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"], [f"{EXECUTION}.turn_jobs.job_id"], name="fk_job_attempts_job"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_job_attempts_owner"
        ),
        schema=EXECUTION,
    )

    op.create_table(
        "encrypted_checkpoints",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("pending_writes_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("cipher_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_checkpoints_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_checkpoints_owner"
        ),
        schema=EXECUTION,
    )

    op.create_table(
        "tool_traces",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            [f"{CONVERSATION}.messages.message_id"],
            name="fk_tool_traces_message",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_tool_traces_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_tool_traces_owner"
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_tool_traces_duration"
        ),
        schema=EXECUTION,
    )

    op.create_table(
        "key_metadata",
        sa.Column("key_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("cipher_version", sa.Integer(), nullable=False),
        # The DEK stored ONLY wrapped by the KEK; the KEK is never stored here.
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("shredded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{CONVERSATION}.conversations.session_id"],
            name="fk_key_metadata_session",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_key_metadata_owner"
        ),
        sa.UniqueConstraint("session_id", name="uq_key_metadata_session"),
        schema=EXECUTION,
    )

    op.create_table(
        "audit_events_minimal",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], [f"{IDENTITY}.users.id"], name="fk_audit_events_owner"
        ),
        schema=EXECUTION,
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order, then enums, then schemas.
    op.drop_table("audit_events_minimal", schema=EXECUTION)
    op.drop_table("key_metadata", schema=EXECUTION)
    op.drop_table("tool_traces", schema=EXECUTION)
    op.drop_table("encrypted_checkpoints", schema=EXECUTION)
    op.drop_table("job_attempts", schema=EXECUTION)
    op.drop_index("ix_turn_jobs_state", table_name="turn_jobs", schema=EXECUTION)
    op.drop_table("turn_jobs", schema=EXECUTION)

    op.drop_index("uq_plans_one_current", table_name="plans", schema=CONVERSATION)
    op.drop_table("plans", schema=CONVERSATION)
    op.drop_table("domain_states", schema=CONVERSATION)
    op.drop_index("ix_messages_session_order", table_name="messages", schema=CONVERSATION)
    op.drop_table("messages", schema=CONVERSATION)
    op.drop_index(
        "ix_conversations_owner", table_name="conversations", schema=CONVERSATION
    )
    op.drop_table("conversations", schema=CONVERSATION)

    op.drop_index(
        "ix_login_attempts_email_at", table_name="login_attempts", schema=IDENTITY
    )
    op.drop_table("login_attempts", schema=IDENTITY)
    op.drop_index(
        "ix_token_verifiers_owner", table_name="token_verifiers", schema=IDENTITY
    )
    op.drop_index(
        "ix_token_verifiers_family", table_name="token_verifiers", schema=IDENTITY
    )
    op.drop_table("token_verifiers", schema=IDENTITY)
    op.drop_index("ix_auth_sessions_owner", table_name="auth_sessions", schema=IDENTITY)
    op.drop_table("auth_sessions", schema=IDENTITY)
    op.drop_table("users", schema=IDENTITY)

    op.execute(sa.text("DROP TYPE IF EXISTS job_state"))
    op.execute(sa.text("DROP TYPE IF EXISTS token_type"))
    op.execute(sa.text("DROP TYPE IF EXISTS user_role"))

    for schema in SCHEMAS:
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
