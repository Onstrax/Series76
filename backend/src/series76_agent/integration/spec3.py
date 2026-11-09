"""Adapters binding the Spec 4 ports to the Spec 3 persistence (PostgreSQL).

Every adapter call opens its **own short transaction** and commits before it
returns, so the orchestrator never holds a SQL transaction across a model call
(Spec 4 Req 4.3). Sensitive state is encrypted with the conversation DEK under
AES-256-GCM with the five-field AAD (purposes ``domain.state`` / ``plan.content``),
exactly like every other Spec 3 record. Writes for a deleted / tombstoned
conversation are skipped so a late turn never resurrects it.

Catalog reads go through the Spec 2 PostgreSQL adapter (``runtime_reader_role``,
typed parameterized queries only), one short read-only session per tool call.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from series76_agent.domain.conversation import DomainConversationState
from series76_agent.domain.enums import TurnState
from series76_agent.ports import EditionInfo
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.errors import CryptoError
from series76_api.infrastructure.crypto import Ciphertext, CryptoService
from series76_api.infrastructure.orm import (
    AuditEventORM,
    ConversationORM,
    DomainStateORM,
)
from series76_api.infrastructure.repositories import KeyMetadataRepository, PlanRepository
from series76_data.models.enums import EditionState
from series76_data.models.orm import CatalogCurrent, CatalogEdition
from series76_domain.repository.errors import UnresolvedEditionError
from series76_domain.repository.pg_adapter import PostgresTypedRepository
from series76_domain.tools import build_set_a, build_set_b
from series76_domain.tools.context import ToolContext

SessionFactory = async_sessionmaker[AsyncSession]


class CatalogUnavailable(Exception):
    """The catalog could not be read for this call (treated as transient)."""


async def _owned_live_conversation(
    session: AsyncSession, session_id: uuid.UUID, owner_id: uuid.UUID
) -> ConversationORM | None:
    conv = await session.get(ConversationORM, session_id)
    if conv is None or conv.owner_id != owner_id or conv.deleted_at is not None:
        return None
    if conv.tombstone_fence is not None:
        return None
    return conv


async def _dek(
    session: AsyncSession, crypto: CryptoService, session_id: uuid.UUID, owner_id: uuid.UUID
) -> bytes | None:
    handle = await KeyMetadataRepository(session).get_for_session(session_id)
    if handle is None:
        return None
    try:
        return crypto.unwrap_dek(handle.wrapped_dek, owner_id=owner_id, conversation_id=session_id)
    except CryptoError:
        return None  # shredded / unavailable key: fail closed, return nothing


class PgEditionPort:
    """Pins the conversation to the active published edition on first use."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    async def pinned_edition(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> EditionInfo | None:
        async with self._sf() as session, session.begin():
            conv = await _owned_live_conversation(session, session_id, owner_id)
            if conv is None:
                return None
            edition_id = conv.catalog_edition_id
            if edition_id is None:
                current = (
                    await session.execute(select(CatalogCurrent.edition_id))
                ).scalar_one_or_none()
                if current is None:
                    return None
                conv.catalog_edition_id = current  # pinned for the conversation's life
                edition_id = current
            state = (
                await session.execute(
                    select(CatalogEdition.state).where(CatalogEdition.edition_id == edition_id)
                )
            ).scalar_one_or_none()
            if state is None or state is EditionState.CANDIDATE:
                return None
            return EditionInfo(edition_id=edition_id, withdrawn=state is EditionState.RETIRED)


class PgDomainStateStore:
    """Owner-scoped, AES-256-GCM encrypted domain conversation state."""

    def __init__(self, session_factory: SessionFactory, crypto: CryptoService) -> None:
        self._sf = session_factory
        self._crypto = crypto

    def _aad(self, owner_id: uuid.UUID, session_id: uuid.UUID, row_id: uuid.UUID) -> AADContext:
        return AADContext(
            purpose=CryptoPurpose.DOMAIN_STATE,
            owner_id=owner_id,
            conversation_id=session_id,
            record_id=row_id,
        )

    async def _latest(self, session: AsyncSession, session_id: uuid.UUID) -> DomainStateORM | None:
        stmt = (
            select(DomainStateORM)
            .where(DomainStateORM.session_id == session_id)
            .order_by(DomainStateORM.revision.desc(), DomainStateORM.updated_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def load(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> DomainConversationState | None:
        async with self._sf() as session, session.begin():
            if await _owned_live_conversation(session, session_id, owner_id) is None:
                return None
            row = await self._latest(session, session_id)
            if row is None or row.owner_id != owner_id:
                return None
            dek = await _dek(session, self._crypto, session_id, owner_id)
            if dek is None:
                return None
            plaintext = self._crypto.decrypt(
                dek, Ciphertext(row.state_ciphertext), self._aad(owner_id, session_id, row.id)
            )
            state = DomainConversationState.from_json(json.loads(plaintext.decode("utf-8")))
            if not state.belongs_to(session_id=session_id, owner_id=owner_id):
                return None
            return state

    async def save(self, state: DomainConversationState) -> None:
        async with self._sf() as session, session.begin():
            sid, oid = state.session_id, state.owner_id
            if await _owned_live_conversation(session, sid, oid) is None:
                return  # deleted / tombstoned: never resurrect
            dek = await _dek(session, self._crypto, sid, oid)
            if dek is None:
                return
            payload = json.dumps(state.to_json(), sort_keys=True).encode("utf-8")
            row = await self._latest(session, sid)
            if row is None:
                row_id = uuid.uuid4()
                session.add(
                    DomainStateORM(
                        id=row_id,
                        session_id=sid,
                        owner_id=oid,
                        state_ciphertext=self._crypto.encrypt(
                            dek, payload, self._aad(oid, sid, row_id)
                        ).blob,
                        revision=state.version,
                    )
                )
                return
            row.state_ciphertext = self._crypto.encrypt(
                dek, payload, self._aad(oid, sid, row.id)
            ).blob
            row.revision = state.version


class PgTurnStateRecorder:
    """Records each Turn_State transition as a content-free audit event."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    async def record(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID, turn_id: str, state: TurnState
    ) -> None:
        async with self._sf() as session, session.begin():
            session.add(
                AuditEventORM(
                    id=uuid.uuid4(),
                    event_type=f"turn_state:{state.value}",
                    request_id=turn_id,
                    owner_id=owner_id,
                )
            )


class PgPlanPort:
    """Creates strictly increasing, encrypted plan revisions (Spec 3 plans)."""

    def __init__(self, session_factory: SessionFactory, crypto: CryptoService) -> None:
        self._sf = session_factory
        self._crypto = crypto

    async def create_revision(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID, payload: str
    ) -> tuple[str, int]:
        async with self._sf() as session, session.begin():
            if await _owned_live_conversation(session, session_id, owner_id) is None:
                raise CatalogUnavailable("conversation is not available")
            dek = await _dek(session, self._crypto, session_id, owner_id)
            if dek is None:
                raise CatalogUnavailable("conversation key is not available")
            plan = await PlanRepository(session).add_revision(
                session_id=session_id, owner_id=owner_id, plan_ciphertext=b"\x00"
            )
            # Bind the ciphertext to the persisted plan id (AAD record id).
            plan.plan_ciphertext = self._crypto.encrypt(
                dek,
                payload.encode("utf-8"),
                AADContext(
                    purpose=CryptoPurpose.PLAN_CONTENT,
                    owner_id=owner_id,
                    conversation_id=session_id,
                    record_id=plan.plan_id,
                ),
            ).blob
            return str(plan.plan_id), plan.plan_revision


class PgCancellationPort:
    """A conversation that was deleted / tombstoned accepts no late result."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    async def is_cancelled(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        async with self._sf() as session, session.begin():
            return await _owned_live_conversation(session, session_id, owner_id) is None


class _PerCallTool:
    """A Spec 2 tool whose every invocation uses one short read-only session."""

    def __init__(self, engine: Engine, name: str, context: ToolContext, tool_set: str) -> None:
        self.name = name
        self._engine = engine
        self._context = context
        self._tool_set = tool_set

    def invoke(self, input: dict[str, Any]) -> Any:  # noqa: A002 - LangChain signature
        with Session(self._engine) as session:
            try:
                repo = PostgresTypedRepository.resolve_pinned(session, self._context.edition_id)
            except UnresolvedEditionError as exc:
                raise CatalogUnavailable("pinned edition is not readable") from exc
            try:
                builder = build_set_a if self._tool_set == "A" else build_set_b
                tools = builder(lambda: self._context, lambda _ctx: repo)
                return tools[self.name].invoke(input)
            finally:
                session.rollback()


class PgCatalogToolProvider:
    """Spec 2 tools over PostgreSQL, bound to the server-injected context."""

    def __init__(self, engine: Engine, tool_set: str = "B") -> None:
        self._engine = engine
        self._tool_set = tool_set

    def tools(self, context: ToolContext) -> Mapping[str, Any]:
        names = ("query_parts",) if self._tool_set == "A" else (
            "get_part_details", "search_parts", "get_source_notes"
        )
        return {n: _PerCallTool(self._engine, n, context, self._tool_set) for n in names}
