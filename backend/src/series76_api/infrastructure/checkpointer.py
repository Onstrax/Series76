"""AES-256-GCM encrypted LangGraph checkpointer (Spec 3, Req 9.8).

A ``BaseCheckpointSaver``-compatible saver that serializes a LangGraph
checkpoint — *including its pending writes* — and encrypts the serialized blob
with AES-256-GCM via the Half A :class:`CryptoService` before it reaches
PostgreSQL. It fails closed on tag-verification failure and round-trips so
recovery succeeds (Property 45). Owner/thread scoping is derived
*post-authorization* (the caller passes the authorized owner + session).

**GCM vs EAX decision (ADR 0003).** We evaluated whether GCM is viable for the
serialized checkpoint blob. It is: LangGraph's ``SerializerProtocol`` turns a
checkpoint and its pending writes into opaque ``bytes``, which GCM encrypts as a
single AEAD unit with contextual AAD exactly like every other sensitive field.
There is no framework constraint (no streaming/random-access requirement, no
fixed-size nonce reuse) that makes GCM infeasible here, so we take the **GCM
path** and do NOT use the EAX fallback. The EAX fallback remains documented in
``docs/adr/0003-checkpoint-eax-fallback.md`` as the pre-authorized escape hatch
*should* a future framework change make GCM infeasible for this blob only; it
is never used for titles/messages/domain-state/plans/traces.

This adapter persists through a repository inside a short-lived async session
so it composes with the Unit_Of_Work transaction discipline; the sync
``BaseCheckpointSaver`` methods are not used (we expose explicit async methods
the worker/agent call), keeping the encryption boundary inside our async stack.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy.ext.asyncio import async_sessionmaker

from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.infrastructure.crypto import Ciphertext, CryptoService
from series76_api.infrastructure.engine import AsyncSession


@dataclass(frozen=True, slots=True)
class CheckpointBundle:
    """A checkpoint plus its pending writes, as recovered from storage."""

    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    pending_writes: list[tuple[str, str, Any]]


class EncryptedCheckpointer:
    """Encrypts LangGraph checkpoints with AES-256-GCM (GCM path, fail-closed).

    Not a drop-in sync ``BaseCheckpointSaver``; it exposes async ``aput`` /
    ``aget`` methods that the async worker/agent call, because the encryption
    and persistence are async. The serialized blob format is GCM everywhere.
    """

    # The cipher this checkpointer uses for the checkpoint blob. "GCM" is the
    # primary (and, per ADR 0003, the path actually taken); "EAX" is reserved.
    checkpoint_cipher: str = "GCM"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        crypto: CryptoService,
    ) -> None:
        self._session_factory = session_factory
        self._crypto = crypto
        self._serde = JsonPlusSerializer()

    def _aad(
        self,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> AADContext:
        return AADContext(
            purpose=CryptoPurpose.CHECKPOINT,
            owner_id=owner_id,
            conversation_id=session_id,
            record_id=record_id,
        )

    def _encrypt_blob(
        self,
        dek: bytes,
        payload: bytes,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> bytes:
        return self._crypto.encrypt(
            dek, payload, self._aad(owner_id, session_id, record_id)
        ).blob

    def _decrypt_blob(
        self,
        dek: bytes,
        blob: bytes,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> bytes:
        # Fails closed on a tag mismatch (raises DecryptionError) — Property 45.
        return self._crypto.decrypt(
            dek, Ciphertext(blob), self._aad(owner_id, session_id, record_id)
        )

    async def aput(
        self,
        *,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        thread_id: str,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        pending_writes: list[tuple[str, str, Any]] | None,
        dek: bytes,
    ) -> uuid.UUID:
        """Serialize + GCM-encrypt a checkpoint (incl. pending writes); persist.

        The checkpoint and metadata are serialized together and the pending
        writes separately; both blobs are GCM-encrypted under the conversation
        DEK with distinct record ids so recovery restores both (Property 45).
        Returns the new checkpoint row id.
        """

        record_id = uuid.uuid4()
        payload = {
            "checkpoint": self._serde.dumps_typed(checkpoint),
            "metadata": self._serde.dumps_typed(dict(metadata)),
        }
        checkpoint_blob = self._encrypt_blob(
            dek, self._serde.dumps(payload), owner_id, session_id, record_id
        )
        pending_blob: bytes | None = None
        if pending_writes:
            pending_blob = self._encrypt_blob(
                dek,
                self._serde.dumps(
                    [
                        (ch, task, self._serde.dumps_typed(val))
                        for ch, task, val in pending_writes
                    ]
                ),
                owner_id,
                session_id,
                record_id,
            )
        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            uow.checkpoints.add(
                record_id=record_id,
                session_id=session_id,
                owner_id=owner_id,
                thread_id=thread_id,
                checkpoint_ciphertext=checkpoint_blob,
                pending_writes_ciphertext=pending_blob,
                cipher_version=Ciphertext(checkpoint_blob).cipher_version,
            )
            await uow.commit()
        return record_id

    async def aget(
        self,
        *,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        thread_id: str,
        dek: bytes,
    ) -> CheckpointBundle | None:
        """Recover + decrypt the latest checkpoint for a (session, thread).

        Returns ``None`` when no checkpoint exists. Decryption fails closed on
        a tag mismatch, so a tampered blob raises rather than returning data
        (Property 45). The checkpoint and pending writes are both restored.
        """

        async with self._session_factory() as session:
            uow = UnitOfWork(session)
            row = await uow.checkpoints.latest_for_thread(session_id, thread_id)
            if row is None:
                await uow.rollback()
                return None
            # Capture the columns while the session is still open (the ORM row
            # detaches on session close, so late attribute access would raise).
            record_id = row.id
            checkpoint_blob = bytes(row.checkpoint_ciphertext)
            pending_blob = (
                bytes(row.pending_writes_ciphertext)
                if row.pending_writes_ciphertext is not None
                else None
            )
            await uow.rollback()

        plain = self._decrypt_blob(
            dek, checkpoint_blob, owner_id, session_id, record_id
        )
        payload = self._serde.loads(plain)
        checkpoint: Checkpoint = self._serde.loads_typed(payload["checkpoint"])
        metadata_dict = self._serde.loads_typed(payload["metadata"])
        metadata: CheckpointMetadata = metadata_dict  # structurally a TypedDict

        pending: list[tuple[str, str, Any]] = []
        if pending_blob is not None:
            plain_pending = self._decrypt_blob(
                dek, pending_blob, owner_id, session_id, record_id
            )
            for ch, task, typed_val in self._serde.loads(plain_pending):
                pending.append((ch, task, self._serde.loads_typed(typed_val)))

        return CheckpointBundle(
            checkpoint=checkpoint, metadata=metadata, pending_writes=pending
        )


__all__ = ["CheckpointBundle", "EncryptedCheckpointer"]
