"""Backend support for the Android client (Spec 5), on real PostgreSQL.

* ``GET /api/sessions`` reports ``pending_jobs`` (QUEUED/RUNNING) per
  conversation, so the app shows a pending indicator iff a job is outstanding.
* A turn processed by the worker (async job path) persists the user and the
  assistant message, encrypted, in the same fenced transaction as the result,
  so the conversation history the app reloads includes asynchronous turns.
"""

from __future__ import annotations

import pytest
from alembic.config import Config

from ._spec3_app import build_settings, spec3_client
from ._spec3_helpers import register_and_login
from .test_spec3_jobs_api import _drain, _enqueue

pytestmark = pytest.mark.integration


async def test_pending_jobs_and_async_history(postgres_url: str, migrated_db: Config) -> None:
    settings = build_settings(postgres_url)
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        accepted = await _enqueue(client, headers, "first question")
        assert accepted.status_code == 202
        sid = accepted.json()["session_id"]

        listing = (await client.get("/api/sessions", headers=headers)).json()
        assert [s["pending_jobs"] for s in listing if s["session_id"] == sid] == [1]

        await _drain(settings)

        listing = (await client.get("/api/sessions", headers=headers)).json()
        assert [s["pending_jobs"] for s in listing if s["session_id"] == sid] == [0]
        messages = (await client.get(f"/api/sessions/{sid}/messages", headers=headers)).json()
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "first question"
        job = (await client.get(f"/api/jobs/{accepted.json()['job_id']}", headers=headers)).json()
        assert job["response"]["message_id"] == messages[1]["message_id"]


async def test_async_turns_keep_question_before_answer(
    postgres_url: str, migrated_db: Config
) -> None:
    """Same-transaction user/assistant rows keep insertion order (regression)."""

    settings = build_settings(postgres_url)
    async with spec3_client(postgres_url) as (client, _app, _clock):
        _email, headers = await register_and_login(client)
        sid = None
        for i in range(5):
            accepted = await _enqueue(client, headers, f"question {i}", session_id=sid)
            sid = accepted.json()["session_id"]
            await _drain(settings)
        messages = (await client.get(f"/api/sessions/{sid}/messages", headers=headers)).json()
        assert [m["role"] for m in messages] == ["user", "assistant"] * 5
        assert [m["content"] for m in messages[::2]] == [f"question {i}" for i in range(5)]
