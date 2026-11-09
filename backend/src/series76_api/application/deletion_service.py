"""Conversation deletion: tombstone, crypto-shred, no resurrection (Req 8, 9.7).

Deleting a conversation (by its owner) performs, in a single transaction:

1. cancel its pending/active jobs;
2. write a tombstone recording a fencing token strictly greater than every
   token ever issued for the conversation (the write-guard);
3. purge messages, domain state, checkpoints, and sensitive traces from active
   storage, and null out sensitive job input/result/attempt ciphertext;
4. crypto-shred the DEK (delete the wrapped key) so the ciphertext becomes
   permanently unrecoverable from active storage.

It returns ``204`` for a successful delete; a not-owned or nonexistent
conversation is an indistinguishable ``404`` and a previously deleted one a
``410`` — both carry no resource attributes (Properties 31-34). A later worker
write whose fencing token is ``<=`` the tombstone token is blocked by the
worker (Property 32); the tombstone token recorded here is the guard it checks.
"""

from __future__ import annotations

import uuid
from enum import Enum

from series76_api.application.authorization import resolve_owner_id
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.errors import GoneError, NotFoundError
from series76_api.domain.models import AuthenticatedPrincipal
from series76_api.infrastructure.clock import Clock


class DeletionResult(str, Enum):
    """The observable result of a delete request (maps to 204/404/410)."""

    DELETED = "DELETED"


class DeletionService:
    """Application service for conversation deletion + crypto-shred."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def delete(
        self, principal: AuthenticatedPrincipal, session_id: uuid.UUID
    ) -> DeletionResult:
        """Delete a conversation the caller owns, or raise an indistinguishable error.

        Raises :class:`NotFoundError` (404) for a nonexistent or not-owned
        conversation and :class:`GoneError` (410) for a previously deleted one —
        both with no resource attributes so existence is never confirmed
        (Property 34). On success performs the tombstone + purge + crypto-shred
        and returns :data:`DeletionResult.DELETED` (Property 31).
        """

        conv = await self._uow.conversations.get(session_id)
        # Not-owned or nonexistent -> indistinguishable 404 (Property 33, 34).
        if conv is None or conv.owner_id != resolve_owner_id(principal):
            raise NotFoundError("Resource not found.")
        # Previously deleted -> 410, no attributes (Property 34).
        if conv.deleted_at is not None:
            raise GoneError("Resource not found.")

        now = self._clock.now()

        # 1) Cancel pending/active jobs for the conversation.
        await self._uow.turn_jobs.cancel_active_for_session(session_id, at=now)

        # 2) Tombstone with a fence strictly greater than any issued token so
        #    any in-flight worker write (fence <= tombstone) is blocked
        #    (Property 32). Jobs issue positive fences; the tombstone sits above.
        max_fence = await self._uow.turn_jobs.max_fencing_token(session_id)
        tombstone_fence = max_fence + 1
        await self._uow.conversations.tombstone(
            session_id, fence=tombstone_fence, at=now
        )

        # 3) Purge sensitive content from active storage (Property 31).
        await self._uow.messages.delete_for_session(session_id)
        await self._uow.domain_states.delete_for_session(session_id)
        await self._uow.checkpoints.delete_for_session(session_id)
        await self._uow.tool_traces.delete_for_session(session_id)
        job_ids = await self._uow.turn_jobs.list_ids_for_session(session_id)
        await self._uow.job_attempts.clear_detail_for_session_jobs(job_ids)
        await self._uow.turn_jobs.clear_sensitive_for_session(session_id)

        # 4) Crypto-shred the DEK: ciphertext is now permanently unrecoverable.
        await self._uow.key_metadata.shred(session_id, at=now)

        await self._uow.commit()
        return DeletionResult.DELETED


__all__ = ["DeletionResult", "DeletionService"]
