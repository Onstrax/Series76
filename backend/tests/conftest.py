"""Shared pytest fixtures for the Series 76 backend test suite.

The ``postgres_url`` fixture starts a *real* PostgreSQL container (Req 7.1,
7.3, 8.2 are exercised against the actual engine, never a mock). It is
session-scoped so the container is reused across the suite and torn down once.

If Docker is unavailable, integration tests are skipped with a clear reason
rather than failing spuriously — the pure-logic unit and property tests still
run without a container.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


def _docker_available() -> bool:
    try:
        import docker  # noqa: F401  (import side-effect probe)

        client = __import__("docker").from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Yield a SQLAlchemy URL for a live PostgreSQL container.

    Honors ``SERIES76_TEST_DATABASE_URL`` if set (so CI can point at an
    already-running PostgreSQL), otherwise spins up a Testcontainers instance.
    """

    override = os.environ.get("SERIES76_TEST_DATABASE_URL")
    if override:
        yield override
        return

    if not _docker_available():
        pytest.skip("Docker not available; skipping real-PostgreSQL integration test")

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()


# --- Hypothesis profile: enforce >= 100 examples per property (Spec 2 Task 1.1) ---
from hypothesis import HealthCheck, settings  # noqa: E402

settings.register_profile(
    "series76",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile("series76")
