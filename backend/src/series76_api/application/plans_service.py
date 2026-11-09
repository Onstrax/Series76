"""Plan revision + confirmation use cases (Spec 3, Req 7).

Plan revisions are strictly increasing per conversation; a correction creates a
greater revision and marks the prior not-current. Confirming the *current*
revision (by the authenticated owner) records exactly one confirmation and
triggers at most one execution; confirming a *non-current* revision is rejected
with ``409 STALE_PLAN`` without executing or changing state; a repeated confirm
of the current revision is idempotent (Properties 28, 29). Unauthenticated
confirmation is ``401`` with no effect (Property 30); a non-owner is an
indistinguishable ``404`` (Property 10); an unknown revision is ``404``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from series76_api.application.authorization import authorize_ownership
from series76_api.application.unit_of_work import UnitOfWork
from series76_api.domain.crypto import AADContext, CryptoPurpose
from series76_api.domain.errors import NotFoundError, StalePlanError
from series76_api.domain.models import AuthenticatedPrincipal
from series76_api.infrastructure.clock import Clock
from series76_api.infrastructure.crypto import Ciphertext, CryptoService


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """The outcome of a confirm: the revision and whether execution was triggered."""

    plan_id: uuid.UUID
    plan_revision: int
    executed: bool


class PlansService:
    """Application service for plan revisions + confirmation."""

    def __init__(self, uow: UnitOfWork, clock: Clock, crypto: CryptoService) -> None:
        self._uow = uow
        self._clock = clock
        self._crypto = crypto

    def _aad(
        self,
        owner_id: uuid.UUID,
        session_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> AADContext:
        return AADContext(
            purpose=CryptoPurpose.PLAN_CONTENT,
            owner_id=owner_id,
            conversation_id=session_id,
            record_id=record_id,
        )

    async def _ensure_dek(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> bytes:
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

    async def _owned_conversation(
        self, principal: AuthenticatedPrincipal, session_id: uuid.UUID
    ) -> None:
        conv = await self._uow.conversations.get(session_id)
        if conv is not None and conv.deleted_at is not None:
            conv = None
        authorize_ownership(principal, conv)

    async def create_revision(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        *,
        plan_text: str,
    ) -> int:
        """Create a new strictly-greater plan revision (encrypted), marking the
        prior not-current. Returns the new revision number (Property 28)."""

        await self._owned_conversation(principal, session_id)
        dek = await self._ensure_dek(
            session_id=session_id, owner_id=principal.user_id
        )
        plan_id = uuid.uuid4()
        plan_ct = self._crypto.encrypt(
            dek,
            plan_text.encode("utf-8"),
            self._aad(principal.user_id, session_id, plan_id),
        ).blob
        plan = await self._uow.plans.add_revision(
            session_id=session_id,
            owner_id=principal.user_id,
            plan_ciphertext=plan_ct,
        )
        await self._uow.commit()
        return plan.plan_revision

    async def confirm(
        self,
        principal: AuthenticatedPrincipal,
        session_id: uuid.UUID,
        revision: int,
    ) -> ConfirmationResult:
        """Confirm a plan revision (owner-only, current-only).

        Confirming a non-current revision raises :class:`StalePlanError` (409)
        with no execution and no state change (Property 28). Confirming the
        current revision records at most one confirmation + triggers at most one
        execution; repeating it is idempotent (Property 29). An unknown revision
        raises :class:`NotFoundError` (404); a non-owner conversation is an
        indistinguishable 404 (Property 10).
        """

        await self._owned_conversation(principal, session_id)
        plan = await self._uow.plans.get_revision(session_id, revision)
        if plan is None:
            # Unknown revision -> 404 (Req 7.8).
            raise NotFoundError("Resource not found.")
        if not plan.is_current:
            # Non-current -> 409 STALE_PLAN, no execution, state unchanged.
            await self._uow.rollback()
            raise StalePlanError("The plan has been superseded by a newer revision.")

        executed = plan.confirmed_at is None  # first confirm triggers execution
        # mark_confirmed_executed is a no-op WHERE confirmed_at IS NULL so a
        # repeated confirm records at most one confirmation (Property 29).
        await self._uow.plans.mark_confirmed_executed(
            plan.plan_id, at=self._clock.now()
        )
        await self._uow.commit()
        return ConfirmationResult(
            plan_id=plan.plan_id,
            plan_revision=plan.plan_revision,
            executed=executed,
        )


__all__ = ["ConfirmationResult", "PlansService"]
