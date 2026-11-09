"""Spec 3 error-envelope + health/ready integration tests (real PostgreSQL).

Properties 47, 48, 49 run end-to-end against the live engine through the
FastAPI app. The faked agent seam drives a NO_RESULTS success vs an
UPSTREAM_UNAVAILABLE failure deterministically (zero provider spend).

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import pytest
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st

from ._spec3_app import spec3_client
from ._spec3_helpers import register_and_login

pytestmark = pytest.mark.integration

_STABLE_CODES = {
    "VALIDATION_ERROR",
    "AUTH_REQUIRED",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
    "STALE_PLAN",
    "CATALOG_WITHDRAWN",
    "JOB_CANCELLED",
    "UPSTREAM_UNAVAILABLE",
    "BUDGET_EXCEEDED",
}


# Feature: backend-api-auth-jobs-crypto, Property 47: The error envelope is
# stable and status mapping is consistent (code set, localized message,
# unique request_id, consistent retryable).
@given(lang=st.sampled_from(["en", "es"]))
async def test_property_47_error_envelope_stable(
    lang: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """Representative errors carry a stable envelope with consistent mapping."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        hdr = {**headers, "Accept-Language": lang}

        # 422 VALIDATION_ERROR (empty query).
        v = await client.post("/api/conversation", json={"query": ""}, headers=hdr)
        assert v.status_code == 422
        vb = v.json()
        assert vb["error"]["code"] == "VALIDATION_ERROR"
        assert vb["error"]["code"] in _STABLE_CODES
        assert vb["error"]["user_message"]  # localized, non-empty
        assert vb["request_id"]
        assert vb["retryable"] is False  # VALIDATION_ERROR is never retryable

        # 404 NOT_FOUND (a nonexistent conversation for this owner).
        import uuid as _uuid

        nf = await client.get(
            f"/api/sessions/{_uuid.uuid4()}/messages", headers=hdr
        )
        assert nf.status_code == 404
        assert nf.json()["error"]["code"] == "NOT_FOUND"
        assert nf.json()["retryable"] is False

        # Two errors get distinct, unique request_ids.
        v2 = await client.post("/api/conversation", json={"query": ""}, headers=hdr)
        assert v2.json()["request_id"] != vb["request_id"]

        # Localized message differs by language for the same code.
        other_lang = "es" if lang == "en" else "en"
        v_other = await client.post(
            "/api/conversation",
            json={"query": ""},
            headers={**headers, "Accept-Language": other_lang},
        )
        assert v_other.json()["error"]["user_message"] != vb["error"]["user_message"]


# Feature: backend-api-auth-jobs-crypto, Property 48: NO_RESULTS and
# UPSTREAM_UNAVAILABLE are never conflated.
@given(_seed=st.integers(min_value=0, max_value=5))
async def test_property_48_no_results_vs_upstream_unavailable(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A zero-match turn is a 200 success; a provider failure is a 503."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)

        # Zero matches -> 200 success (NO_RESULTS business outcome).
        no_res = await client.post(
            "/api/conversation", json={"query": "find [noresults]"}, headers=headers
        )
        assert no_res.status_code == 200
        assert no_res.json()["answer"]

        # Provider failure -> 503 UPSTREAM_UNAVAILABLE (never a 200).
        down = await client.post(
            "/api/conversation", json={"query": "ask [upstream_down]"}, headers=headers
        )
        assert down.status_code == 503
        assert down.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
        assert down.json()["retryable"] is True
        # The two outcomes are never represented identically.
        assert no_res.status_code != down.status_code


# Feature: backend-api-auth-jobs-crypto, Property 49: Readiness distinguishes
# database from other critical dependencies; health is liveness-only.
@given(_seed=st.integers(min_value=0, max_value=3))
async def test_property_49_ready_distinguishes_dependencies(
    _seed: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """/ready distinguishes DB from key material + provider; /health is liveness."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        ready = await client.get("/api/ready")
        assert ready.status_code == 200
        deps = ready.json()["dependencies"]
        # Three distinct dependency flags are reported separately.
        assert set(deps.keys()) == {"database", "key_material", "provider"}
        assert deps["database"] is True  # live container
        assert deps["key_material"] is True  # test app has a real KEK
        # The provider is a distinct flag (degraded, no outbound call made).
        assert isinstance(deps["provider"], bool)

        health = await client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        # Liveness only; no sensitive info / dependency internals.
        assert body == {"status": "ok"}
