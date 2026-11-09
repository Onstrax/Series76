"""Seams this layer plugs into (Spec 3) and reads the catalog through (Spec 2).

All are injected; the orchestrator never opens a SQL session, encrypts data,
establishes identity, or owns the job queue itself. Each persistence port call
is expected to run in its **own short transaction** that commits before the
call returns, so no SQL transaction is ever open across a model call.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from series76_agent.domain.conversation import DomainConversationState
from series76_agent.domain.enums import TurnState
from series76_agent.tools import CatalogTool
from series76_domain.tools.context import ToolContext


@dataclass(frozen=True, slots=True)
class EditionInfo:
    """The conversation's pinned catalog edition, resolved server-side."""

    edition_id: uuid.UUID
    withdrawn: bool = False


class EditionPort(Protocol):
    """Resolves (and on first use pins) the conversation's edition (Spec 3)."""

    async def pinned_edition(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> EditionInfo | None:
        """The pinned edition, or ``None`` when no published edition exists."""
        ...


class DomainStatePort(Protocol):
    """Owner-scoped encrypted persistence of the domain conversation state."""

    async def load(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> DomainConversationState | None:
        """Load this conversation's state for this owner (never another's)."""
        ...

    async def save(self, state: DomainConversationState) -> None:
        """Persist the state (short transaction)."""
        ...


class TurnStatePort(Protocol):
    """Records each Turn_State transition in its own committed transaction."""

    async def record(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        turn_id: str,
        state: TurnState,
    ) -> None:
        """Persist ``turn_id``'s state (committed before returning)."""
        ...


class PlanPort(Protocol):
    """The Spec 3 plan-revision surface (monotonic revisions per session)."""

    async def create_revision(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID, payload: str
    ) -> tuple[str, int]:
        """Create a strictly greater revision; return ``(plan_id, revision)``."""
        ...


class CancellationPort(Protocol):
    """Reports whether a turn's conversation was cancelled or deleted."""

    async def is_cancelled(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """True iff no result may be persisted for this conversation any more."""
        ...


class CatalogToolProvider(Protocol):
    """Builds the Spec 2 tools bound to a server-injected context."""

    def tools(self, context: ToolContext) -> Mapping[str, CatalogTool]:
        """Tools whose every invocation runs with ``context`` (never a model value)."""
        ...


class NeverCancelled:
    """A cancellation port for paths without a durable job (always ``False``)."""

    async def is_cancelled(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        return False
