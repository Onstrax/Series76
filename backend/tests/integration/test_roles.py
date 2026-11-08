"""Integration tests for the three DB roles and least-privilege grants (Task 3.1).

Run against a real ``postgres:15-alpine`` container. The container connects as a
superuser; we exercise each role by ``SET ROLE`` within a transaction and assert
the grant boundary holds:

  * ``runtime_reader_role`` is denied UPDATE/DELETE on a catalog table and denied
    SELECT on an ingestion table.
  * a non-publisher role writing ``publication.catalog_current`` is rejected and
    the pointer is unchanged.

Property 18 (min 100 iterations) asserts that for *any* non-publisher role,
activating an edition (writing ``catalog_current``) is rejected and the pointer
is unchanged.

Requirements: 7.3, 7.5
Properties: 18
"""

from __future__ import annotations

import uuid

import pytest
from alembic.config import Config
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.integration

ROLES = ("ingest_editor_role", "publisher_role", "runtime_reader_role")
NON_PUBLISHER_ROLES = ("ingest_editor_role", "runtime_reader_role")


def _engine(url: str) -> Engine:
    return create_engine(url, future=True)


def _seed_edition_and_pointer(conn, edition_id: uuid.UUID) -> None:
    """Create an edition and an initial active pointer as superuser."""

    conn.execute(
        text(
            "INSERT INTO catalog.catalog_edition (edition_id, manifest_digest, state) "
            "VALUES (:eid, :digest, 'published')"
        ),
        {"eid": str(edition_id), "digest": f"digest-{edition_id}"},
    )
    conn.execute(
        text(
            "INSERT INTO publication.catalog_current (pin, edition_id) "
            "VALUES (TRUE, :eid) "
            "ON CONFLICT (pin) DO UPDATE SET edition_id = EXCLUDED.edition_id"
        ),
        {"eid": str(edition_id)},
    )


def test_three_roles_exist(migrated_db: Config, postgres_url: str) -> None:
    eng = _engine(postgres_url)
    try:
        with eng.connect() as conn:
            got = (
                conn.execute(
                    text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"),
                    {"names": list(ROLES)},
                )
                .scalars()
                .all()
            )
        assert set(got) == set(ROLES)
    finally:
        eng.dispose()


def test_runtime_reader_denied_update_on_catalog(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        edition_id = uuid.uuid4()
        with eng.begin() as conn:
            _seed_edition_and_pointer(conn, edition_id)
        with pytest.raises(ProgrammingError) as exc, eng.begin() as conn:
            conn.execute(text("SET ROLE runtime_reader_role"))
            conn.execute(text("UPDATE catalog.catalog_edition SET state = 'retired'"))
        assert "permission denied" in str(exc.value).lower()
    finally:
        eng.dispose()


def test_runtime_reader_denied_delete_on_catalog(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        edition_id = uuid.uuid4()
        with eng.begin() as conn:
            _seed_edition_and_pointer(conn, edition_id)
        with pytest.raises(ProgrammingError) as exc, eng.begin() as conn:
            conn.execute(text("SET ROLE runtime_reader_role"))
            conn.execute(text("DELETE FROM catalog.part_number"))
        assert "permission denied" in str(exc.value).lower()
    finally:
        eng.dispose()


def test_runtime_reader_denied_select_on_ingestion(
    migrated_db: Config, postgres_url: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with pytest.raises(ProgrammingError) as exc, eng.begin() as conn:
            conn.execute(text("SET ROLE runtime_reader_role"))
            conn.execute(text("SELECT * FROM ingestion.ingestion_run"))
        assert "permission denied" in str(exc.value).lower()
    finally:
        eng.dispose()


def test_runtime_reader_can_select_catalog(
    migrated_db: Config, postgres_url: str
) -> None:
    """Positive control: the reader *can* SELECT the published surface."""

    eng = _engine(postgres_url)
    try:
        edition_id = uuid.uuid4()
        with eng.begin() as conn:
            _seed_edition_and_pointer(conn, edition_id)
        with eng.begin() as conn:
            conn.execute(text("SET ROLE runtime_reader_role"))
            count = conn.execute(
                text("SELECT count(*) FROM catalog.catalog_edition")
            ).scalar_one()
        assert count == 1
    finally:
        eng.dispose()


def test_publisher_can_write_catalog_current(
    migrated_db: Config, postgres_url: str
) -> None:
    """Positive control: the publisher *can* flip the active pointer."""

    eng = _engine(postgres_url)
    try:
        edition_id = uuid.uuid4()
        other_id = uuid.uuid4()
        with eng.begin() as conn:
            _seed_edition_and_pointer(conn, edition_id)
            conn.execute(
                text(
                    "INSERT INTO catalog.catalog_edition (edition_id, manifest_digest, state) "
                    "VALUES (:eid, :digest, 'published')"
                ),
                {"eid": str(other_id), "digest": f"digest-{other_id}"},
            )
        with eng.begin() as conn:
            conn.execute(text("SET ROLE publisher_role"))
            conn.execute(
                text("UPDATE publication.catalog_current SET edition_id = :eid"),
                {"eid": str(other_id)},
            )
        with eng.connect() as conn:
            active = conn.execute(
                text("SELECT edition_id FROM publication.catalog_current")
            ).scalar_one()
        assert str(active) == str(other_id)
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 18: Only the Publisher role activates an
# edition. For any non-publisher role, writing publication.catalog_current is
# rejected and the active-edition pointer is left unchanged.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    role=st.sampled_from(NON_PUBLISHER_ROLES),
    use_update=st.booleans(),
)
def test_property_18_only_publisher_activates(
    migrated_db: Config, postgres_url: str, role: str, use_update: bool
) -> None:
    eng = _engine(postgres_url)
    try:
        active_id = uuid.uuid4()
        target_id = uuid.uuid4()
        # Reset state for this example: one active pointer, one alternative edition.
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM publication.catalog_current"))
            conn.execute(text("DELETE FROM catalog.catalog_edition"))
            _seed_edition_and_pointer(conn, active_id)
            conn.execute(
                text(
                    "INSERT INTO catalog.catalog_edition (edition_id, manifest_digest, state) "
                    "VALUES (:eid, :digest, 'published')"
                ),
                {"eid": str(target_id), "digest": f"digest-{target_id}"},
            )

        # The non-publisher attempt must be rejected with a permission error.
        with pytest.raises(ProgrammingError) as exc, eng.begin() as conn:
            conn.execute(text(f"SET ROLE {role}"))
            if use_update:
                conn.execute(
                    text("UPDATE publication.catalog_current SET edition_id = :eid"),
                    {"eid": str(target_id)},
                )
            else:
                conn.execute(
                    text(
                        "INSERT INTO publication.catalog_current (pin, edition_id) "
                        "VALUES (TRUE, :eid) "
                        "ON CONFLICT (pin) DO UPDATE SET edition_id = EXCLUDED.edition_id"
                    ),
                    {"eid": str(target_id)},
                )
        assert "permission denied" in str(exc.value).lower()

        # The pointer is unchanged: still the original active edition.
        with eng.connect() as conn:
            still_active = conn.execute(
                text("SELECT edition_id FROM publication.catalog_current")
            ).scalar_one()
        assert str(still_active) == str(active_id)
    finally:
        eng.dispose()
