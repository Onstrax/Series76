"""Debug-trace access use case (Spec 3, Req 10).

Returns a sanitized trace ONLY when the caller holds role ``developer`` AND
owns the conversation that the message belongs to. Every other case —
non-developer, non-owner, developer A requesting developer B's trace,
nonexistent message/conversation, or a deleted conversation — yields a
byte-for-byte identical denial disclosing nothing (Property 46). The trace
never contains secrets (Property 44); sanitization is applied in the pure
``domain.trace`` policy.
"""

from __future__ import annotations

import json
import uuid

from series76_api.application.authorization import is_developer, resolve_owner_id
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.models import AuthenticatedPrincipal
from series76_api.domain.trace import sanitize_trace
from series76_api.infrastructure.crypto import Ciphertext, CryptoService


class TraceService:
    """Application service for the developer-only debug trace read."""

    def __init__(self, uow: UnitOfWork, crypto: CryptoService) -> None:
        self._uow = uow
        self._crypto = crypto

    async def get_sanitized_trace(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> dict[str, object] | None:
        """Return a sanitized trace, or ``None`` for an identical denial.

        ``None`` is returned for EVERY unauthorized or not-found case so the
        router can emit one byte-for-byte identical denial, confirming nothing
        about existence (Property 46). A sanitized trace is returned only to a
        developer who owns the conversation.
        """

        # Only a developer may ever see a trace; a non-developer is denied
        # identically to a non-owner (no distinction, Property 46).
        if not is_developer(principal):
            return None

        conv = await self._uow.conversations.get(session_id)
        # Nonexistent, not-owned, or deleted conversation -> identical denial.
        if conv is None or conv.owner_id != resolve_owner_id(principal):
            return None
        if conv.deleted_at is not None:
            return None

        message = await self._uow.messages.get(message_id)
        if (
            message is None
            or message.session_id != session_id
            or message.owner_id != resolve_owner_id(principal)
        ):
            return None

        trace = await self._uow.tool_traces.get_for_message(message_id)
        if trace is None or trace.owner_id != resolve_owner_id(principal):
            return None

        # Ownership confirmed before any decryption (Property 42). Unwrap the
        # DEK and decrypt the trace blob, then sanitize (Property 44).
        handle = await self._uow.key_metadata.get_for_session(session_id)
        if handle is None:
            return None
        dek = self._crypto.unwrap_dek(
            handle.wrapped_dek,
            owner_id=resolve_owner_id(principal),
            conversation_id=session_id,
        )
        raw = self._crypto.decrypt(
            dek,
            Ciphertext(trace.trace_ciphertext),
            AADContext(
                purpose=CryptoPurpose.TOOL_TRACE,
                owner_id=resolve_owner_id(principal),
                conversation_id=session_id,
                record_id=trace.id,
            ),
        )
        decoded = json.loads(raw.decode("utf-8"))
        sanitized = sanitize_trace(decoded)
        # The persisted duration (already non-negative per the CHECK) is the
        # authoritative timing; prefer it when present.
        if trace.duration_ms is not None:
            sanitized["duration_ms"] = max(0, int(trace.duration_ms))
        return sanitized


__all__ = ["TraceService"]
