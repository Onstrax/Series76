"""Conversation use cases (Spec 3, Req 4, 8).

Implements the mandatory sync ``POST /api/conversation`` turn and the session
listing / messages / rename reads, all owner-scoped and encrypting sensitive
content *before* persistence via the Half A :class:`CryptoService`. The agent
is reached only through the faked :class:`AgentPort` seam (zero provider spend).

Key invariants realized here:

* The final response always carries a non-empty ``session_id`` + ``answer``
  (Property 11), and the ``202`` job acceptance is never substituted for it.
* Omitting ``session_id`` creates a caller-owned conversation with a stable id
  (Property 12).
* Clarification/confirmation turns carry a ``status`` and no unverified number
  (Property 13).
* A repeated ``Client_Request_Id`` yields exactly one turn effect, enforced by
  ``UNIQUE(owner_id, client_request_id)`` (Property 15).
* An invalid query is rejected with no persistence (Property 16).
* Listing + title search are owner-scoped and decrypt only *after*
  authorization (Property 35); message history is deterministically ordered and
  trace-free (Property 36); rename enforces length + ownership (Property 37).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from series76_api.api.envelopes import (
    ResponseEnvelope,
    parse_content_blocks,
)
from series76_api.application.agent_seam import (
    AgentPort,
    ConfirmationRequest,
    ProviderUnavailable,
    TurnOutcome,
    TurnRequest,
    build_response_envelope,
)
from series76_api.application.authorization import authorize_ownership
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.errors import (
    DomainError,
    ErrorCode,
    GoneError,
    UpstreamUnavailableError,
    ValidationError,
)
from series76_api.domain.models import AuthenticatedPrincipal
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.crypto import Ciphertext, CryptoService
from series76_api.infrastructure.orm import ConversationORM, MessageORM

# Query length bounds (Req 4.9).
QUERY_MIN_LEN = 1
QUERY_MAX_LEN = 4000
# Title length bounds for rename (Req 8.7).
TITLE_MIN_LEN = 1
TITLE_MAX_LEN = 200
# Title-search ciphertext fetch cap (Req 8.5, Property 35).
TITLE_SEARCH_CAP = 1000


def validate_query(query: str | None) -> str:
    """Validate the turn query, or raise :class:`ValidationError` (Property 16).

    Rejects a missing, empty, whitespace-only, or over-4000-character query
    before any persistence. The surviving value is the original (not trimmed)
    query so the agent sees exactly what the caller sent.
    """

    if query is None:
        raise ValidationError("A query is required.")
    if not query.strip():
        raise ValidationError("A query is required.")
    if len(query) > QUERY_MAX_LEN:
        raise ValidationError("The query exceeds the maximum length.")
    return query


def validate_title(title: str) -> str:
    """Validate a rename title (1-200 chars), or raise (Property 37)."""

    if not (TITLE_MIN_LEN <= len(title) <= TITLE_MAX_LEN):
        raise ValidationError("The title must be between 1 and 200 characters.")
    return title


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """A listing entry: id, decrypted title (after authorize), timestamps."""

    session_id: uuid.UUID
    title: str | None
    created_at: str
    updated_at: str
    pending_jobs: int = 0


@dataclass(frozen=True, slots=True)
class MessageView:
    """A decrypted message for the history read (after authorize)."""

    message_id: uuid.UUID
    role: str
    content: str
    blocks: list[dict[str, object]]
    created_at: str


class ConversationService:
    """Application service for conversation turns and reads."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        crypto: CryptoService,
        agent: AgentPort,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._crypto = crypto
        self._agent = agent

    # --- DEK lifecycle ----------------------------------------------------

    async def _ensure_dek(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bytes:
        """Return the conversation DEK, creating + wrapping it on first use.

        The DEK is generated once per conversation, wrapped under the KEK, and
        the wrapped form persisted in ``key_metadata``; the raw DEK and the KEK
        are never stored (Property 40).
        """

        handle = await self._uow.key_metadata.get_for_session(session_id)
        if handle is not None:
            return self._crypto.unwrap_dek(
                handle.wrapped_dek, owner_id=owner_id, conversation_id=session_id
            )
        dek = self._crypto.generate_dek()
        wrapped = self._crypto.wrap_dek(
            dek, owner_id=owner_id, conversation_id=session_id
        )
        self._uow.key_metadata.add(
            session_id=session_id,
            owner_id=owner_id,
            wrapped_dek=wrapped,
            cipher_version=Ciphertext(wrapped).cipher_version,
        )
        return dek

    def _aad(
        self,
        purpose: CryptoPurpose,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> AADContext:
        return AADContext(
            purpose=purpose,
            owner_id=owner_id,
            conversation_id=session_id,
            record_id=record_id,
        )

    # --- conversation resolution -----------------------------------------

    async def _resolve_conversation(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID | None,
    ) -> ConversationORM:
        """Resolve an existing owned conversation or create a caller-owned one.

        When ``session_id`` is omitted a new conversation is created with a
        stable id owned by the caller (Property 12). When supplied, the
        authorization guard enforces ownership — a nonexistent or not-owned id
        is an indistinguishable 404 and nothing is created (Property 10, 4.10).
        A deleted conversation is treated as not-found (its row carries
        ``deleted_at``).
        """

        if session_id is None:
            new_id = uuid.uuid4()
            conv = self._uow.conversations.add(
                session_id=new_id, owner_id=principal.user_id
            )
            await self._uow.flush()
            return conv

        existing = await self._uow.conversations.get(session_id)
        if existing is not None and existing.deleted_at is not None:
            # Deleted conversations are indistinguishable from nonexistent.
            existing = None
        authorize_ownership(principal, existing)
        assert existing is not None  # authorize_ownership raised otherwise
        return existing

    async def _history(
        self, session_id: uuid.UUID, owner_id: uuid.UUID, dek: bytes
    ) -> tuple[tuple[str, str], ...]:
        """Decrypt the owner-scoped prior turns for the resumed conversation."""

        messages = await self._uow.messages.list_for_session(session_id)
        out: list[tuple[str, str]] = []
        for m in messages:
            text = self._crypto.decrypt(
                dek,
                Ciphertext(m.content_ciphertext),
                self._aad(
                    CryptoPurpose.MESSAGE_CONTENT, owner_id, session_id, m.message_id
                ),
            ).decode("utf-8")
            out.append((m.role, text))
        return tuple(out)

    # --- mandatory sync turn ---------------------------------------------

    async def run_sync_turn(
        self,
        principal: AuthenticatedPrincipal,
        *,
        session_id: uuid.UUID | None,
        query: str | None,
        client_request_id: str | None,
    ) -> ResponseEnvelope:
        """Run one mandatory sync turn and return the ``Response_Envelope``.

        Always returns a non-empty ``session_id`` + ``answer`` (Property 11).
        Rejects an invalid query before persisting (Property 16). Enforces
        idempotency on ``Client_Request_Id`` so a retry returns the original
        response and persists exactly one turn effect (Property 15).
        """

        clean_query = validate_query(query)

        # Idempotency: a repeated client_request_id for this owner returns the
        # original turn's response without a second effect (Property 15).
        if client_request_id:
            existing_job = await self._uow.turn_jobs.get_by_client_request_id(
                principal.user_id, client_request_id
            )
            if existing_job is not None:
                env = await self._load_persisted_envelope(principal, existing_job)
                if env is not None:
                    await self._uow.commit()
                    return env

        created = session_id is None
        conv = await self._resolve_conversation(principal, session_id)
        dek = await self._ensure_dek(
            session_id=conv.session_id, owner_id=principal.user_id
        )
        history = await self._history(conv.session_id, principal.user_id, dek)

        # Phase A — persist the user message (encrypted) and COMMIT, so no SQL
        # transaction is open while the agent calls the model (Spec 4 Req 4.3).
        user_msg_id = uuid.uuid4()
        self._persist_message(
            message_id=user_msg_id,
            session_id=conv.session_id,
            owner_id=principal.user_id,
            role="user",
            text=clean_query,
            blocks=None,
            dek=dek,
        )
        await self._uow.commit()

        # Phase B — run the turn outside any transaction. The ownership check
        # already completed, so dispatch is authorized (Property 43).
        try:
            outcome = await self._agent.run_turn(
                TurnRequest(
                    owner_id=principal.user_id,
                    session_id=conv.session_id,
                    query=clean_query,
                    history=history,
                    trace_id=str(user_msg_id),
                )
            )
        except ProviderUnavailable as exc:
            # A provider failure is a 503 UPSTREAM_UNAVAILABLE, never a success;
            # the turn leaves no partial effect behind.
            await self._compensate(principal, conv.session_id, user_msg_id, created)
            raise UpstreamUnavailableError(str(exc)) from exc
        except DomainError:
            await self._compensate(principal, conv.session_id, user_msg_id, created)
            raise

        # Phase C — persist the result in a separate short transaction.
        return await self._persist_outcome(
            principal, conv.session_id, outcome, dek, client_request_id=client_request_id
        )

    async def run_confirmation_turn(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        confirmation: ConfirmationRequest,
    ) -> ResponseEnvelope:
        """Execute a plan revision the plan seam just bound and confirmed.

        Called only after the confirmation committed; the agent runs outside any
        transaction and its result is persisted as an assistant message.
        """

        conv = await self._uow.conversations.get(session_id)
        if conv is not None and conv.deleted_at is not None:
            conv = None
        authorize_ownership(principal, conv)
        dek = await self._ensure_dek(session_id=session_id, owner_id=principal.user_id)
        await self._uow.commit()
        try:
            outcome = await self._agent.run_turn(
                TurnRequest(
                    owner_id=principal.user_id,
                    session_id=session_id,
                    query="",
                    confirmation=confirmation,
                    trace_id=f"confirm:{confirmation.plan_id}:{confirmation.plan_revision}",
                )
            )
        except ProviderUnavailable as exc:
            raise UpstreamUnavailableError(str(exc)) from exc
        return await self._persist_outcome(principal, session_id, outcome, dek)

    async def _persist_outcome(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        outcome: TurnOutcome,
        dek: bytes,
        *,
        client_request_id: str | None = None,
    ) -> ResponseEnvelope:
        """Persist the assistant message, trace, and idempotency record."""

        conv = await self._uow.conversations.get(session_id)
        if conv is None or conv.deleted_at is not None:
            # Deleted while the turn ran: the late result must not resurrect it.
            await self._uow.rollback()
            raise GoneError("Resource not found.")
        envelope, assistant_msg_id = self._build_envelope(session_id, outcome)
        self._persist_message(
            message_id=assistant_msg_id,
            session_id=session_id,
            owner_id=principal.user_id,
            role="assistant",
            text=envelope.answer,
            blocks=[b.model_dump(mode="json") for b in envelope.content_blocks],
            dek=dek,
        )
        if outcome.trace is not None:
            await self._uow.flush()
            self._persist_trace(
                message_id=assistant_msg_id,
                session_id=session_id,
                owner_id=principal.user_id,
                trace=outcome.trace,
                dek=dek,
            )
        if client_request_id:
            await self._record_idempotency_job(
                principal, session_id, client_request_id, envelope, dek
            )
        await self._uow.conversations.touch(session_id, at=self._clock.now())
        await self._uow.commit()
        return envelope

    async def _compensate(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        user_msg_id: uuid.UUID,
        created: bool,
    ) -> None:
        """Undo phase A after a failed turn (no partial effect is left behind)."""

        await self._uow.rollback()
        if created:
            from series76_api.application.deletion_service import DeletionService

            await DeletionService(self._uow, self._clock).delete(principal, session_id)
            return
        await self._uow.messages.delete(user_msg_id)
        await self._uow.commit()

    def _persist_trace(
        self,
        *,
        message_id: uuid.UUID,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        trace: dict[str, object],
        dek: bytes,
    ) -> None:
        """Encrypt (AES-256-GCM, purpose tool.trace) and stage the debug trace."""

        trace_id = uuid.uuid4()
        ciphertext = self._crypto.encrypt(
            dek,
            json.dumps(trace, sort_keys=True, default=str).encode("utf-8"),
            self._aad(CryptoPurpose.TOOL_TRACE, owner_id, session_id, trace_id),
        ).blob
        row = self._uow.tool_traces.add(
            message_id=message_id,
            session_id=session_id,
            owner_id=owner_id,
            trace_ciphertext=ciphertext,
            duration_ms=None,
        )
        row.id = trace_id

    def _persist_message(
        self,
        *,
        message_id: uuid.UUID,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        text: str,
        blocks: list[dict[str, object]] | None,
        dek: bytes,
    ) -> None:
        content_ct = self._crypto.encrypt(
            dek,
            text.encode("utf-8"),
            self._aad(CryptoPurpose.MESSAGE_CONTENT, owner_id, session_id, message_id),
        ).blob
        blocks_ct: bytes | None = None
        if blocks:
            blocks_ct = self._crypto.encrypt(
                dek,
                json.dumps(blocks).encode("utf-8"),
                self._aad(
                    CryptoPurpose.MESSAGE_BLOCKS, owner_id, session_id, message_id
                ),
            ).blob
        self._uow.messages.add(
            message_id=message_id,
            session_id=session_id,
            owner_id=owner_id,
            role=role,
            content_ciphertext=content_ct,
            blocks_ciphertext=blocks_ct,
        )

    def _build_envelope(
        self, session_id: uuid.UUID, outcome: TurnOutcome
    ) -> tuple[ResponseEnvelope, uuid.UUID]:
        """Map a :class:`TurnOutcome` to a ``Response_Envelope`` (non-empty answer)."""

        assistant_msg_id = uuid.uuid4()
        envelope = build_response_envelope(
            session_id, outcome, turn_id=str(assistant_msg_id),
            message_id=str(assistant_msg_id),
        )
        return envelope, assistant_msg_id

    async def _record_idempotency_job(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        client_request_id: str,
        envelope: ResponseEnvelope,
        dek: bytes,
    ) -> None:
        """Record a COMPLETED job row to anchor idempotency + the saved envelope.

        The ``UNIQUE(owner_id, client_request_id)`` constraint guarantees a
        retried request cannot create a second effect; the stored encrypted
        envelope is returned verbatim on a retry (Property 15).
        """

        from series76_api.domain.models import JobState

        seq = await self._uow.turn_jobs.next_accepted_seq(session_id)
        job_id = uuid.uuid4()
        result_ct = self._encrypt_envelope(
            session_id, principal.user_id, job_id, envelope, dek
        )
        job = self._uow.turn_jobs.add(
            job_id=job_id,
            session_id=session_id,
            owner_id=principal.user_id,
            accepted_seq=seq,
            client_request_id=client_request_id,
            job_state=JobState.COMPLETED,
        )
        job.result_ciphertext = result_ct

    def _encrypt_envelope(
        self,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        job_id: uuid.UUID,
        envelope: ResponseEnvelope,
        dek: bytes,
    ) -> bytes:
        return self._crypto.encrypt(
            dek,
            envelope.model_dump_json().encode("utf-8"),
            self._aad(CryptoPurpose.JOB_INPUT, owner_id, session_id, job_id),
        ).blob

    async def _load_persisted_envelope(
        self, principal: AuthenticatedPrincipal, job: object
    ) -> ResponseEnvelope | None:
        """Decrypt a job's stored result envelope for an idempotent replay."""

        from series76_api.infrastructure.orm import TurnJobORM

        assert isinstance(job, TurnJobORM)
        if job.result_ciphertext is None:
            return None
        handle = await self._uow.key_metadata.get_for_session(job.session_id)
        if handle is None:
            return None
        dek = self._crypto.unwrap_dek(
            handle.wrapped_dek,
            owner_id=principal.user_id,
            conversation_id=job.session_id,
        )
        raw = self._crypto.decrypt(
            dek,
            Ciphertext(job.result_ciphertext),
            self._aad(
                CryptoPurpose.JOB_INPUT, principal.user_id, job.session_id, job.job_id
            ),
        )
        return ResponseEnvelope.model_validate_json(raw.decode("utf-8"))

    # --- reads: listing / search / messages / rename --------------------

    async def list_sessions(
        self, principal: AuthenticatedPrincipal, *, title_query: str | None = None
    ) -> list[SessionSummary]:
        """List the caller's conversations, decrypting titles after authorize.

        Fetches at most the caller's own ciphertext titles (owner-scoped WHERE,
        capped at 1000) and decrypts them *after* the ownership scope — never
        an ``ILIKE``/substring over ciphertext, never a message-body search,
        never another owner's data (Property 35). An optional ``title_query``
        is applied as a plaintext substring match on the *decrypted* titles the
        caller already owns.
        """

        rows = await self._uow.conversations.list_for_owner(
            principal.user_id, limit=TITLE_SEARCH_CAP
        )
        summaries: list[SessionSummary] = []
        pending = await self._uow.turn_jobs.pending_counts(principal.user_id)
        needle = title_query.strip().lower() if title_query else None
        for row in rows:
            title = await self._decrypt_title(principal.user_id, row)
            if needle is not None and (title is None or needle not in title.lower()):
                continue
            summaries.append(
                SessionSummary(
                    session_id=row.session_id,
                    title=title,
                    created_at=row.created_at.isoformat(),
                    updated_at=row.updated_at.isoformat(),
                    pending_jobs=pending.get(row.session_id, 0),
                )
            )
        return summaries

    async def _decrypt_title(
        self, owner_id: uuid.UUID, row: ConversationORM
    ) -> str | None:
        """Decrypt a conversation title AFTER the owner scope (Property 35).

        The title ciphertext belongs to the caller (the query that fetched it
        was owner-scoped), so unwrapping the conversation DEK and decrypting the
        title here never touches another owner's data.
        """

        if row.title_ciphertext is None:
            return None
        handle = await self._uow.key_metadata.get_for_session(row.session_id)
        if handle is None:
            return None
        dek = self._crypto.unwrap_dek(
            handle.wrapped_dek, owner_id=owner_id, conversation_id=row.session_id
        )
        return self._crypto.decrypt(
            dek,
            Ciphertext(row.title_ciphertext),
            self._aad(
                CryptoPurpose.CONVERSATION_TITLE,
                owner_id,
                row.session_id,
                row.session_id,
            ),
        ).decode("utf-8")

    async def get_messages(
        self, principal: AuthenticatedPrincipal, session_id: uuid.UUID
    ) -> list[MessageView]:
        """Return the owner's messages + typed blocks in deterministic order.

        Authorizes ownership first (indistinguishable 404 otherwise), then
        decrypts in ``(created_at asc, message_id asc)`` order, excluding debug
        traces entirely (Property 36).
        """

        conv = await self._uow.conversations.get(session_id)
        if conv is not None and conv.deleted_at is not None:
            conv = None
        authorize_ownership(principal, conv)
        assert conv is not None
        dek = await self._ensure_dek(session_id=session_id, owner_id=principal.user_id)
        messages = await self._uow.messages.list_for_session(session_id)
        return [
            self._decrypt_message(principal.user_id, session_id, m, dek)
            for m in messages
        ]

    def _decrypt_message(
        self, owner_id: uuid.UUID, session_id: uuid.UUID, m: MessageORM, dek: bytes
    ) -> MessageView:
        content = self._crypto.decrypt(
            dek,
            Ciphertext(m.content_ciphertext),
            self._aad(
                CryptoPurpose.MESSAGE_CONTENT, owner_id, session_id, m.message_id
            ),
        ).decode("utf-8")
        blocks: list[dict[str, object]] = []
        if m.blocks_ciphertext is not None:
            raw = self._crypto.decrypt(
                dek,
                Ciphertext(m.blocks_ciphertext),
                self._aad(
                    CryptoPurpose.MESSAGE_BLOCKS, owner_id, session_id, m.message_id
                ),
            ).decode("utf-8")
            raw_blocks = json.loads(raw)
            # Re-run through the structural union so an unknown kind degrades.
            blocks = [
                b.model_dump(mode="json") for b in parse_content_blocks(raw_blocks)
            ]
        return MessageView(
            message_id=m.message_id,
            role=m.role,
            content=content,
            blocks=blocks,
            created_at=m.created_at.isoformat(),
        )

    async def rename_session(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        new_title: str,
    ) -> None:
        """Rename a conversation, enforcing length + ownership (Property 37).

        Validates the title BEFORE touching storage so an invalid length leaves
        the existing title unchanged; authorizes ownership so a non-owner is an
        indistinguishable 404 and the title is unchanged. The new title is
        persisted encrypted.
        """

        validate_title(new_title)
        conv = await self._uow.conversations.get(session_id)
        if conv is not None and conv.deleted_at is not None:
            conv = None
        authorize_ownership(principal, conv)
        assert conv is not None
        dek = await self._ensure_dek(session_id=session_id, owner_id=principal.user_id)
        title_ct = self._crypto.encrypt(
            dek,
            new_title.encode("utf-8"),
            self._aad(
                CryptoPurpose.CONVERSATION_TITLE,
                principal.user_id,
                session_id,
                session_id,
            ),
        ).blob
        await self._uow.conversations.set_title(
            session_id, title_ciphertext=title_ct, at=self._clock.now()
        )
        await self._uow.commit()


__all__ = [
    "QUERY_MIN_LEN",
    "QUERY_MAX_LEN",
    "TITLE_MIN_LEN",
    "TITLE_MAX_LEN",
    "TITLE_SEARCH_CAP",
    "validate_query",
    "validate_title",
    "SessionSummary",
    "MessageView",
    "ConversationService",
]


# Avoid an unused-import error for ErrorCode/DomainError referenced in docs.
_ = (ErrorCode, DomainError)
