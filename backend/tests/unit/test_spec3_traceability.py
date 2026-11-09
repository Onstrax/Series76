"""Spec 3 traceability + composition-root wiring assertions (Task 18).

Asserts that every Requirement group (1-12) and every Correctness Property
(P1-P49) maps to at least one implementation/test entry, that every Half B
property names both an implementation site and a test, that all routers / use
cases / repositories / the worker entrypoint / the crypto + checkpointer
adapters are registered at the composition root (no orphaned code), and that the
mandatory ``POST /api/conversation`` contract is tracked across all job paths.

DB-free. Named ``spec3`` for selectability.
"""

from __future__ import annotations

import base64
import os

from series76_api.app import create_app
from series76_api.infrastructure.settings import Settings
from series76_api.traceability import (
    HALF_B_PROPERTIES,
    MANDATORY_CONTRACT_PATHS,
    REQUIREMENT_TASKS,
    all_property_numbers,
)


def test_spec3_all_requirements_mapped() -> None:
    """Every requirement group 1-12 maps to at least one task."""

    assert set(REQUIREMENT_TASKS) == set(range(1, 13))
    assert all(len(v) >= 1 for v in REQUIREMENT_TASKS.values())


def test_spec3_all_properties_covered() -> None:
    """Every property P1-P49 is covered (Half A + Half B)."""

    assert all_property_numbers() == set(range(1, 50))


def test_spec3_half_b_properties_have_impl_and_tests() -> None:
    """Each Half B property names at least one implementation site + one test."""

    expected_half_b = set(range(11, 38)) | {45, 46, 47, 48, 49}
    assert {p.number for p in HALF_B_PROPERTIES} == expected_half_b
    for p in HALF_B_PROPERTIES:
        assert p.implementation, f"P{p.number} has no implementation site"
        assert p.tests, f"P{p.number} has no test"


def test_spec3_mandatory_contract_tracked_across_job_paths() -> None:
    """The mandatory POST contract is tracked across sync + async + poll paths."""

    assert len(MANDATORY_CONTRACT_PATHS) == 3
    joined = " ".join(MANDATORY_CONTRACT_PATHS).lower()
    assert "sync post /api/conversation" in joined
    assert "202" in joined and "never substitutes" in joined
    assert "same response_envelope" in joined.lower()


def _build_test_app():  # type: ignore[no-untyped-def]
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        DATABASE_URL="postgresql+psycopg://x:y@localhost:5432/z",
        ENCRYPTION_KEK=base64.b64encode(os.urandom(32)).decode("ascii"),
    )
    return create_app(settings)


def test_spec3_all_routers_registered_at_composition_root() -> None:
    """Every Half B router path is mounted by the app factory (no orphans)."""

    app = _build_test_app()
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    required = {
        "/api/health",
        "/api/ready",
        "/api/auth/register",
        "/api/auth/login",
        "/api/conversation",
        "/api/conversation/jobs",
        "/api/sessions",
        "/api/sessions/{session_id}/messages",
        "/api/sessions/{session_id}",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/cancel",
        "/api/sessions/{session_id}/plans/{revision}/confirm",
        "/api/sessions/{session_id}/messages/{message_id}/trace",
    }
    missing = required - paths
    assert not missing, f"routers not registered: {missing}"


def test_spec3_crypto_and_checkpointer_adapters_wired() -> None:
    """The crypto service, agent seam, and checkpointer are on app.state."""

    from series76_api.application.agent_seam import FakeAgent
    from series76_api.infrastructure.checkpointer import EncryptedCheckpointer
    from series76_api.infrastructure.crypto import CryptoService

    app = _build_test_app()
    assert isinstance(app.state.crypto, CryptoService)
    assert isinstance(app.state.agent, FakeAgent)
    assert isinstance(app.state.checkpointer, EncryptedCheckpointer)
    assert app.state.checkpointer.checkpoint_cipher == "GCM"


def test_spec3_worker_entrypoint_builds() -> None:
    """The worker composition root builds a WorkerService from settings."""

    from series76_api.application.worker_service import WorkerService
    from series76_api.worker import build_worker

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        DATABASE_URL="postgresql+psycopg://x:y@localhost:5432/z",
        ENCRYPTION_KEK=base64.b64encode(os.urandom(32)).decode("ascii"),
    )
    worker, engine = build_worker(settings)
    assert isinstance(worker, WorkerService)
    assert engine is not None


def test_spec3_all_unit_of_work_repositories_wired() -> None:
    """The Unit_Of_Work exposes every Half B repository (no orphaned repo)."""

    from unittest.mock import MagicMock

    from series76_api.application.unit_of_work import UnitOfWork

    uow = UnitOfWork(MagicMock())
    for repo in (
        "conversations",
        "messages",
        "domain_states",
        "plans",
        "turn_jobs",
        "job_attempts",
        "tool_traces",
        "checkpoints",
        "key_metadata",
    ):
        assert hasattr(uow, repo), f"UoW missing repository: {repo}"
