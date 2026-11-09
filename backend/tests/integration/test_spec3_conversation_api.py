"""Spec 3 conversation API integration + property tests (real PostgreSQL).

Covers the mandatory sync ``POST /api/conversation`` and the listing/messages/
rename reads. Properties 11-16 and 35-37 run end-to-end against the live engine
through the FastAPI app with the faked agent seam (zero provider spend).

Each property is one Hypothesis test (>=100 iterations via the shared profile);
because every example touches the database, examples use unique users/queries
to stay isolated on a per-test migrated schema.

Named with ``spec3`` for selectability (``-k spec3``).
"""

from __future__ import annotations

import uuid

import pytest
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st

from ._spec3_app import spec3_client
from ._spec3_helpers import register_and_login, turn, unique_email

pytestmark = pytest.mark.integration


# ----------------------------------------------------------------------------
# Property 11: the mandatory POST contract is inviolable.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 11: The mandatory POST
# contract is inviolable (non-empty session_id + answer across all outcomes).
@given(
    marker=st.sampled_from(["", "[clarify]", "[confirm]", "[noresults]"]),
    omit_session=st.booleans(),
)
async def test_property_11_mandatory_contract_inviolable(
    marker: str, omit_session: bool, postgres_url: str, migrated_db_module: Config
) -> None:
    """Every sync outcome returns a non-empty session_id + answer; never a 202."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        session_id: str | None = None
        if not omit_session:
            first = await turn(client, headers, "hello")
            assert first.status_code == 200
            session_id = first.json()["session_id"]

        resp = await turn(client, headers, f"question {marker}", session_id=session_id)
        # The mandatory endpoint is 200 (never a 202 substitution).
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"]  # non-empty
        assert body["answer"]  # non-empty
        # A clarification/confirmation turn still carries an answer (P13 overlap).
        if marker in ("[clarify]", "[confirm]"):
            assert body["status"] in ("clarification", "confirmation")


# ----------------------------------------------------------------------------
# Property 12: omitting session_id creates a caller-owned conversation.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 12: Omitting session_id
# creates a caller-owned conversation with a stable id.
@given(query=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
async def test_property_12_omit_session_creates_stable_owned_conversation(
    query: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """A no-session turn mints a stable id that resolves on subsequent access."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        first = await turn(client, headers, query)
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        assert session_id

        # The id is stable: a second turn on it resolves the same conversation,
        # and the message history now contains both turns' messages.
        second = await turn(client, headers, "follow up", session_id=session_id)
        assert second.status_code == 200
        assert second.json()["session_id"] == session_id

        msgs = await client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        assert msgs.status_code == 200
        # 2 user + 2 assistant messages persisted and resolvable.
        assert len(msgs.json()) == 4


# ----------------------------------------------------------------------------
# Property 13: clarification/confirmation carries status + only verified numbers.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 13: Clarification/confirmation
# carries status and only verified numbers.
@given(marker=st.sampled_from(["[clarify]", "[confirm]"]))
async def test_property_13_clarification_confirmation_status(
    marker: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """A clarify/confirm turn carries a non-empty answer + status, no number."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        resp = await turn(client, headers, f"please {marker}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"]
        assert body["status"] in ("clarification", "confirmation")
        # The faked clarification/confirmation answer carries no digit (no
        # unverified number leaks into a non-final turn).
        assert not any(ch.isdigit() for ch in body["answer"])


# ----------------------------------------------------------------------------
# Property 14: multi-turn history persists across restart, owner-scoped.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 14: Multi-turn history
# persists across restart, owner-scoped.
@given(n_turns=st.integers(min_value=1, max_value=4))
async def test_property_14_history_persists_across_restart_owner_scoped(
    n_turns: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Resuming after an app restart returns only the owner's persisted turns."""

    # First app instance: create a conversation with n_turns turns.
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        first = await turn(client, headers, "turn-0")
        session_id = first.json()["session_id"]
        for i in range(1, n_turns):
            await turn(client, headers, f"turn-{i}", session_id=session_id)
        # Another owner must never see this conversation's history.
        _other_email, other_headers = await register_and_login(client)

    # Second app instance ("restart"): the owner resumes their history; a
    # different owner is denied with an indistinguishable 404.
    async with spec3_client(postgres_url) as (client, _app, _clock):
        # Re-login the original owner (tokens from the prior instance persisted).
        login = await client.post(
            "/api/auth/login", json={"email": _email, "password": "Str0ng-Passw0rd!"}
        )
        owner_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        msgs = await client.get(
            f"/api/sessions/{session_id}/messages", headers=owner_headers
        )
        assert msgs.status_code == 200
        assert len(msgs.json()) == n_turns * 2  # user + assistant per turn

        other_login = await client.post(
            "/api/auth/login",
            json={"email": _other_email, "password": "Str0ng-Passw0rd!"},
        )
        oh = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
        denied = await client.get(f"/api/sessions/{session_id}/messages", headers=oh)
        assert denied.status_code == 404


# ----------------------------------------------------------------------------
# Property 15: a repeated client request id yields exactly one turn effect.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 15: A repeated client request
# id yields exactly one turn effect (UNIQUE(owner_id, client_request_id)).
@given(crid=st.uuids().map(str))
async def test_property_15_idempotent_client_request_id(
    crid: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """Two POSTs with the same client_request_id persist one turn + same reply."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        first = await turn(client, headers, "idempotent query", client_request_id=crid)
        assert first.status_code == 200
        session_id = first.json()["session_id"]

        # Retry with the SAME client_request_id and same session.
        second = await turn(
            client,
            headers,
            "idempotent query",
            session_id=session_id,
            client_request_id=crid,
        )
        assert second.status_code == 200
        # The original response is returned (same answer + session).
        assert second.json()["session_id"] == first.json()["session_id"]
        assert second.json()["answer"] == first.json()["answer"]

        # Exactly ONE turn effect: the first POST created a user+assistant pair;
        # the idempotent retry adds nothing.
        msgs = await client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        assert len(msgs.json()) == 2


# ----------------------------------------------------------------------------
# Property 16: invalid query is rejected with no persistence effect.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 16: Invalid query is rejected
# with no persistence effect.
@given(
    bad=st.sampled_from(["", "   ", "\t\n", "x" * 4001]),
)
async def test_property_16_invalid_query_rejected_no_persistence(
    bad: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """A missing/empty/whitespace/oversized query -> 422 and no conversation."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        resp = await turn(client, headers, bad)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

        # No conversation was created for the caller.
        listing = await client.get("/api/sessions", headers=headers)
        assert listing.status_code == 200
        assert listing.json() == []


# ----------------------------------------------------------------------------
# Property 35: listing + title search owner-scoped, decrypt-after-authorize.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 35: Session listing and title
# search are owner-scoped and decrypt-after-authorize.
@given(title=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()))
async def test_property_35_listing_title_search_owner_scoped(
    title: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """Listing returns only the caller's rows; title search matches own titles."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await turn(client, headers, "hello")
        session_id = created.json()["session_id"]
        # Rename to a known decrypted title (persisted as ciphertext).
        r = await client.patch(
            f"/api/sessions/{session_id}", json={"title": title}, headers=headers
        )
        assert r.status_code == 204

        # A different owner's listing never shows this conversation.
        _other, other_headers = await register_and_login(client)
        others = await client.get("/api/sessions", headers=other_headers)
        assert all(s["session_id"] != session_id for s in others.json())

        # The owner's listing shows the decrypted title.
        mine = await client.get("/api/sessions", headers=headers)
        titles = {s["session_id"]: s["title"] for s in mine.json()}
        assert titles.get(session_id) == title

        # A title-only search over the owner's own titles matches on a substring
        # of the DECRYPTED title (never a ciphertext substring).
        needle = title.strip()[:3]
        searched = await client.get(
            "/api/sessions", params={"q": needle}, headers=headers
        )
        assert any(s["session_id"] == session_id for s in searched.json())


# ----------------------------------------------------------------------------
# Property 36: message history deterministic total order, excludes traces.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 36: Message history has a
# deterministic total order and excludes traces.
@given(n=st.integers(min_value=1, max_value=5))
async def test_property_36_message_history_total_order(
    n: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """Messages return in (created_at asc, message_id asc) order, trace-free."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        first = await turn(client, headers, "turn-0")
        session_id = first.json()["session_id"]
        for i in range(1, n):
            await turn(client, headers, f"turn-{i}", session_id=session_id)

        msgs = await client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        rows = msgs.json()
        assert len(rows) == n * 2
        # Deterministic total order: sorting by (created_at, message_id) is a
        # no-op (already ordered), and the result contains only message fields
        # (no trace content).
        keyed = [(r["created_at"], r["message_id"]) for r in rows]
        assert keyed == sorted(keyed)
        for r in rows:
            assert set(r.keys()) == {
                "message_id",
                "role",
                "content",
                "blocks",
                "created_at",
            }


# ----------------------------------------------------------------------------
# Property 37: rename enforces length + ownership and persists ciphertext.
# ----------------------------------------------------------------------------
# Feature: backend-api-auth-jobs-crypto, Property 37: Rename enforces length and
# ownership and persists ciphertext.
@given(
    good=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    bad=st.sampled_from(["", "x" * 201]),
)
async def test_property_37_rename_length_ownership_ciphertext(
    good: str, bad: str, postgres_url: str, migrated_db_module: Config
) -> None:
    """A valid rename persists; an invalid length is rejected; non-owner denied."""

    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        created = await turn(client, headers, "hello")
        session_id = created.json()["session_id"]

        # Valid rename persists (204) and shows up decrypted in the listing.
        ok = await client.patch(
            f"/api/sessions/{session_id}", json={"title": good}, headers=headers
        )
        assert ok.status_code == 204
        listing = await client.get("/api/sessions", headers=headers)
        assert {s["session_id"]: s["title"] for s in listing.json()}[session_id] == good

        # Invalid length rejected; the existing title is unchanged.
        rej = await client.patch(
            f"/api/sessions/{session_id}", json={"title": bad}, headers=headers
        )
        assert rej.status_code == 422
        listing2 = await client.get("/api/sessions", headers=headers)
        assert {s["session_id"]: s["title"] for s in listing2.json()}[
            session_id
        ] == good

        # Non-owner rename is an indistinguishable 404; title unchanged.
        _other, other_headers = await register_and_login(client)
        denied = await client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "intruder"},
            headers=other_headers,
        )
        assert denied.status_code == 404
        listing3 = await client.get("/api/sessions", headers=headers)
        assert {s["session_id"]: s["title"] for s in listing3.json()}[
            session_id
        ] == good


_ = (uuid, unique_email)
