"""``DomainConversationState`` — the single authority for multi-turn context.

Referents, criteria, accepted priorities, the plan revision, the response
language, and the pinned edition live here (F2 §2, Req 9.1-9.4). The prose
message history is never the authority. Spec 3 persists this structure
encrypted (AES-256-GCM, purpose ``domain.state``) and scoped to its owner and
conversation; this module only defines the shape and its JSON encoding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Any

from series76_agent.domain.enums import Language, TurnState
from series76_agent.domain.plan import Criterion
from series76_agent.domain.serialization import (
    criterion_from_json,
    criterion_to_json,
    priority_from_json,
    priority_to_json,
)
from series76_domain.services.rank_candidates import RankPriority

#: How many recent turn states are kept (the debug/audit window).
MAX_TRACKED_TURNS = 20


@dataclass(frozen=True, slots=True)
class PendingClarification:
    """A paused turn waiting for the user's reply to a clarification."""

    turn_id: str
    original_message: str
    reason: str


@dataclass(frozen=True, slots=True)
class PendingPlan:
    """A paused turn waiting for an authenticated confirmation of a revision."""

    turn_id: str
    plan_id: str
    plan_revision: int
    draft: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DomainConversationState:
    """Persisted, owner-scoped conversation state (immutable; use ``evolve``)."""

    session_id: uuid.UUID
    owner_id: uuid.UUID
    catalog_edition_id: uuid.UUID | None = None
    language: Language | None = None
    last_search_results: tuple[str, ...] = ()
    last_comparison_set: tuple[str, ...] = ()
    focus: tuple[str, ...] = ()
    mentioned: tuple[str, ...] = ()
    criteria: tuple[Criterion, ...] = ()
    accepted_priorities: tuple[RankPriority, ...] = ()
    plan_id: str | None = None
    plan_revision: int = 0
    pending_clarification: PendingClarification | None = None
    pending_plan: PendingPlan | None = None
    executed_revisions: tuple[int, ...] = ()
    turn_states: tuple[tuple[str, TurnState], ...] = ()
    version: int = 0

    def evolve(self, **changes: Any) -> DomainConversationState:
        """Return a copy with ``changes`` applied (state is immutable)."""
        return replace(self, **changes)

    def with_turn_state(self, turn_id: str, state: TurnState) -> DomainConversationState:
        """Record ``turn_id``'s current state (bounded window, newest last)."""

        kept = [(t, s) for t, s in self.turn_states if t != turn_id]
        kept.append((turn_id, state))
        return self.evolve(turn_states=tuple(kept[-MAX_TRACKED_TURNS:]))

    def turn_state(self, turn_id: str) -> TurnState | None:
        """The last recorded state of ``turn_id``, if tracked."""
        for t, s in self.turn_states:
            if t == turn_id:
                return s
        return None

    def belongs_to(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """True iff this state is the given conversation's, for its owner."""
        return self.session_id == session_id and self.owner_id == owner_id

    # --- JSON ----------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        """Encode for encrypted persistence by Spec 3."""

        return {
            "session_id": str(self.session_id),
            "owner_id": str(self.owner_id),
            "catalog_edition_id": str(self.catalog_edition_id) if self.catalog_edition_id else None,
            "language": self.language.value if self.language else None,
            "last_search_results": list(self.last_search_results),
            "last_comparison_set": list(self.last_comparison_set),
            "focus": list(self.focus),
            "mentioned": list(self.mentioned),
            "criteria": [criterion_to_json(c) for c in self.criteria],
            "accepted_priorities": [priority_to_json(p) for p in self.accepted_priorities],
            "plan_id": self.plan_id,
            "plan_revision": self.plan_revision,
            "pending_clarification": (
                {
                    "turn_id": self.pending_clarification.turn_id,
                    "original_message": self.pending_clarification.original_message,
                    "reason": self.pending_clarification.reason,
                }
                if self.pending_clarification
                else None
            ),
            "pending_plan": (
                {
                    "turn_id": self.pending_plan.turn_id,
                    "plan_id": self.pending_plan.plan_id,
                    "plan_revision": self.pending_plan.plan_revision,
                    "draft": self.pending_plan.draft,
                }
                if self.pending_plan
                else None
            ),
            "executed_revisions": list(self.executed_revisions),
            "turn_states": [[t, s.value] for t, s in self.turn_states],
            "version": self.version,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> DomainConversationState:
        """Decode a persisted state."""

        pc = raw.get("pending_clarification")
        pp = raw.get("pending_plan")
        edition = raw.get("catalog_edition_id")
        language = raw.get("language")
        return cls(
            session_id=uuid.UUID(raw["session_id"]),
            owner_id=uuid.UUID(raw["owner_id"]),
            catalog_edition_id=uuid.UUID(edition) if edition else None,
            language=Language(language) if language else None,
            last_search_results=tuple(raw.get("last_search_results", [])),
            last_comparison_set=tuple(raw.get("last_comparison_set", [])),
            focus=tuple(raw.get("focus", [])),
            mentioned=tuple(raw.get("mentioned", [])),
            criteria=tuple(criterion_from_json(c) for c in raw.get("criteria", [])),
            accepted_priorities=tuple(
                priority_from_json(p) for p in raw.get("accepted_priorities", [])
            ),
            plan_id=raw.get("plan_id"),
            plan_revision=int(raw.get("plan_revision", 0)),
            pending_clarification=PendingClarification(
                turn_id=pc["turn_id"],
                original_message=pc["original_message"],
                reason=pc["reason"],
            )
            if pc
            else None,
            pending_plan=PendingPlan(
                turn_id=pp["turn_id"],
                plan_id=pp["plan_id"],
                plan_revision=int(pp["plan_revision"]),
                draft=pp["draft"],
            )
            if pp
            else None,
            executed_revisions=tuple(int(r) for r in raw.get("executed_revisions", [])),
            turn_states=tuple((str(t), TurnState(s)) for t, s in raw.get("turn_states", [])),
            version=int(raw.get("version", 0)),
        )


def new_state(session_id: uuid.UUID, owner_id: uuid.UUID) -> DomainConversationState:
    """A fresh state for a conversation with no persisted context yet."""
    return DomainConversationState(session_id=session_id, owner_id=owner_id)


__all__ = [
    "DomainConversationState",
    "PendingClarification",
    "PendingPlan",
    "new_state",
]
