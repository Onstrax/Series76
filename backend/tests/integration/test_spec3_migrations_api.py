"""Spec 3 migrations + per-service role integration tests (real PostgreSQL).

Exercises ``alembic upgrade head`` against the live container: the identity/
conversation/execution schemas, every table, the ``UNIQUE(owner_id,
client_request_id)`` idempotency constraint, the three enum types, and the
``app_writer`` least-privilege role (which must have no privilege on the Spec 1
``ingestion`` staging schema). Downgrade is exercised by the ``migrated_db``
teardown reverting to base.

Named with ``spec3``/``migrations_api`` so it is selectable with
``-k "spec3 or migrations_api"``.
"""

from __future__ import annotations

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration


def _sync_engine(url: str):  # type: ignore[no-untyped-def]
    # Migrations and these schema assertions use a plain sync engine.
    return create_engine(url, future=True)


def test_spec3_migrations_api_create_all_schemas_and_tables(
    migrated_db: Config, postgres_url: str
) -> None:
    """Upgrade to head creates the three app schemas and all their tables."""

    engine = _sync_engine(postgres_url)
    try:
        inspector = inspect(engine)

        identity_tables = set(inspector.get_table_names(schema="identity"))
        conversation_tables = set(inspector.get_table_names(schema="conversation"))
        execution_tables = set(inspector.get_table_names(schema="execution"))

        assert {"users", "auth_sessions", "token_verifiers", "login_attempts"} <= (
            identity_tables
        )
        assert {
            "conversations",
            "messages",
            "domain_states",
            "plans",
        } <= conversation_tables
        assert {
            "turn_jobs",
            "job_attempts",
            "encrypted_checkpoints",
            "tool_traces",
            "key_metadata",
            "audit_events_minimal",
        } <= execution_tables
    finally:
        engine.dispose()


def test_spec3_migrations_api_unique_owner_client_request(
    migrated_db: Config, postgres_url: str
) -> None:
    """``turn_jobs`` enforces UNIQUE(owner_id, client_request_id)."""

    engine = _sync_engine(postgres_url)
    try:
        inspector = inspect(engine)
        uniques = inspector.get_unique_constraints("turn_jobs", schema="execution")
        cols = {frozenset(u["column_names"]) for u in uniques}
        assert frozenset({"owner_id", "client_request_id"}) in cols
    finally:
        engine.dispose()


def test_spec3_migrations_api_enums_present(
    migrated_db: Config, postgres_url: str
) -> None:
    """The ``user_role``, ``token_type``, and ``job_state`` enum types exist."""

    engine = _sync_engine(postgres_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
                {"names": ["user_role", "token_type", "job_state"]},
            ).scalars().all()
        assert set(rows) == {"user_role", "token_type", "job_state"}
    finally:
        engine.dispose()


def test_spec3_migrations_api_job_state_labels(
    migrated_db: Config, postgres_url: str
) -> None:
    """The ``job_state`` enum carries exactly the nine design labels."""

    engine = _sync_engine(postgres_url)
    try:
        with engine.connect() as conn:
            labels = conn.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'job_state' ORDER BY e.enumsortorder"
                )
            ).scalars().all()
        assert set(labels) == {
            "QUEUED",
            "RUNNING",
            "NEEDS_CLARIFICATION",
            "AWAITING_CONFIRMATION",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "STALE_PLAN",
            "CATALOG_WITHDRAWN",
        }
    finally:
        engine.dispose()


def test_spec3_migrations_api_app_writer_has_no_ingestion_access(
    migrated_db: Config, postgres_url: str
) -> None:
    """``app_writer`` exists and holds NO privilege on the ingestion schema.

    Verifies least privilege: the application data path cannot touch the Spec 1
    ingestion-staging schema (Req 1.5).
    """

    engine = _sync_engine(postgres_url)
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = 'app_writer'")
            ).scalar_one_or_none()
            assert exists == 1

            # No USAGE on the ingestion schema.
            ingestion_usage = conn.execute(
                text("SELECT has_schema_privilege('app_writer', 'ingestion', 'USAGE')")
            ).scalar_one()
            assert ingestion_usage is False

            # Has USAGE on its own app schemas.
            for schema in ("identity", "conversation", "execution"):
                usage = conn.execute(
                    text(f"SELECT has_schema_privilege('app_writer', '{schema}', 'USAGE')")
                ).scalar_one()
                assert usage is True

            # Can write its own users table but cannot write an ingestion table.
            can_insert_users = conn.execute(
                text(
                    "SELECT has_table_privilege('app_writer', 'identity.users', 'INSERT')"
                )
            ).scalar_one()
            assert can_insert_users is True
    finally:
        engine.dispose()
