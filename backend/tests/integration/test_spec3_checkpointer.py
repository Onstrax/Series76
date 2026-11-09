"""Spec 3 encrypted LangGraph checkpointer integration test (real PostgreSQL).

Property 45: checkpoints (including pending writes) are GCM-serialized, fail
closed on tamper, and round-trip so recovery succeeds. Runs against the live
engine through the :class:`EncryptedCheckpointer`, which persists to
``execution.encrypted_checkpoints``.

Named with ``spec3`` for selectability.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from alembic.config import Config
from hypothesis import given
from hypothesis import strategies as st
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, empty_checkpoint

from series76_api.domain.errors import DecryptionError
from series76_api.infrastructure.checkpointer import EncryptedCheckpointer
from series76_api.infrastructure.crypto import CryptoService

from ._spec3_app import build_settings, create_test_session_factory

pytestmark = pytest.mark.integration


async def _seed_conversation(factory, crypto):  # type: ignore[no-untyped-def]
    owner_id = uuid.uuid4()
    session_id = uuid.uuid4()
    dek = crypto.generate_dek()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO identity.users (id, email, password_verifier, role, "
                "email_verified) VALUES (:id, :email, 'x', 'user', true)"
            ),
            {"id": owner_id, "email": f"{owner_id}@e.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO conversation.conversations (session_id, owner_id) "
                "VALUES (:sid, :oid)"
            ),
            {"sid": session_id, "oid": owner_id},
        )
        await s.commit()
    return owner_id, session_id, dek


# Feature: backend-api-auth-jobs-crypto, Property 45: Checkpoints are
# GCM-serialized, fail-closed, and recoverable (incl. pending writes).
@given(
    channel=st.text(min_size=1, max_size=20),
    value=st.integers(min_value=-1000, max_value=1000),
)
async def test_property_45_checkpoint_gcm_recoverable_fail_closed(
    channel: str, value: int, postgres_url: str, migrated_db_module: Config
) -> None:
    """A checkpoint + pending writes GCM-round-trips; a tampered blob fails."""

    settings = build_settings(postgres_url)
    crypto = CryptoService.from_base64_kek(settings.resolve_kek_base64())
    factory, engine = create_test_session_factory(postgres_url)
    cp = EncryptedCheckpointer(factory, crypto)
    # The GCM path is the one taken (ADR 0003), never EAX.
    assert cp.checkpoint_cipher == "GCM"
    try:
        owner_id, session_id, dek = await _seed_conversation(factory, crypto)
        thread_id = uuid.uuid4().hex

        checkpoint: Checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {channel: value}
        metadata: CheckpointMetadata = {"source": "input", "step": 1, "writes": {}}  # type: ignore[typeddict-item]
        pending = [(channel, "task-1", value)]

        await cp.aput(
            owner_id=owner_id,
            session_id=session_id,
            thread_id=thread_id,
            checkpoint=checkpoint,
            metadata=metadata,
            pending_writes=pending,
            dek=dek,
        )

        bundle = await cp.aget(
            owner_id=owner_id, session_id=session_id, thread_id=thread_id, dek=dek
        )
        assert bundle is not None
        # The checkpoint round-trips (recovery succeeds).
        assert bundle.checkpoint["channel_values"][channel] == value
        # Pending writes are preserved.
        assert bundle.pending_writes == [(channel, "task-1", value)]

        # Fail closed: tamper the stored checkpoint blob -> decryption raises.
        async with factory() as s:
            row = (
                await s.execute(
                    sa.text(
                        "SELECT id, checkpoint_ciphertext FROM "
                        "execution.encrypted_checkpoints WHERE session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).one()
            rec_id, blob = row[0], bytes(row[1])
            tampered = bytearray(blob)
            tampered[-1] ^= 0x01
            await s.execute(
                sa.text(
                    "UPDATE execution.encrypted_checkpoints SET "
                    "checkpoint_ciphertext = :b WHERE id = :id"
                ),
                {"b": bytes(tampered), "id": rec_id},
            )
            await s.commit()

        with pytest.raises(DecryptionError):
            await cp.aget(
                owner_id=owner_id,
                session_id=session_id,
                thread_id=thread_id,
                dek=dek,
            )
    finally:
        await engine.dispose()
