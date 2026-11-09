"""Multi-turn context resolution against persisted domain state (Req 9.1-9.7).

References ("the second one", "that one", a prior model) are resolved
**exclusively** against the persisted :class:`DomainConversationState` of the
active conversation and owner — never re-derived from prose history. A
reference matching more than one plausible referent, or none, is not guessed:
the turn goes to ``NEEDS_CLARIFICATION``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import Enum

from series76_agent.domain.conversation import DomainConversationState
from series76_agent.domain.enums import Provenance, ReferentKind
from series76_agent.domain.plan import DraftPlan, Referent


class ResolutionStatus(str, Enum):
    """Outcome of resolving every referent of a draft."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"


@dataclass(frozen=True, slots=True)
class Resolution:
    """The resolved draft and, if not resolved, which reference failed."""

    draft: DraftPlan
    status: ResolutionStatus
    failed_reference: str | None = None
    candidates: tuple[str, ...] = ()


class ContextResolver:
    """Resolves references against one conversation's persisted state only."""

    def resolve(
        self,
        draft: DraftPlan,
        state: DomainConversationState | None,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Resolution:
        """Resolve ordinal/anaphoric referents; never guess, never cross owners."""

        # A state that is not this conversation's (or this owner's) is ignored
        # entirely: references then resolve to nothing (Req 9.6).
        scoped = (
            state
            if state is not None and state.belongs_to(session_id=session_id, owner_id=owner_id)
            else None
        )
        resolved: list[Referent] = []
        for ref in draft.referents:
            if ref.kind is ReferentKind.PART_NUMBER:
                resolved.append(ref)
                continue
            outcome = self._resolve_one(ref, scoped)
            if outcome.status is not ResolutionStatus.RESOLVED:
                return Resolution(
                    draft=draft,
                    status=outcome.status,
                    failed_reference=ref.text,
                    candidates=outcome.candidates,
                )
            assert outcome.part_number is not None
            resolved.append(
                replace(ref, part_number=outcome.part_number, provenance=Provenance.PRIOR_TURN)
            )
        return Resolution(
            draft=replace(draft, referents=tuple(resolved)), status=ResolutionStatus.RESOLVED
        )

    def _resolve_one(self, ref: Referent, state: DomainConversationState | None) -> _One:
        if state is None:
            return _One(ResolutionStatus.UNMATCHED)
        if ref.kind is ReferentKind.ORDINAL:
            n = ref.ordinal
            if n is None or n < 1:
                return _One(ResolutionStatus.UNMATCHED)
            pools = [p for p in (state.last_search_results, state.last_comparison_set) if p]
            picks = {p[n - 1] for p in pools if len(p) >= n}
            if not picks:
                return _One(ResolutionStatus.UNMATCHED)
            if len(picks) > 1:
                return _One(ResolutionStatus.AMBIGUOUS, candidates=tuple(sorted(picks)))
            return _One(ResolutionStatus.RESOLVED, part_number=next(iter(picks)))
        # ANAPHORA: the conversation's current focus must name exactly one part.
        focus = tuple(dict.fromkeys(state.focus))
        if not focus:
            return _One(ResolutionStatus.UNMATCHED)
        if len(focus) > 1:
            return _One(ResolutionStatus.AMBIGUOUS, candidates=focus)
        return _One(ResolutionStatus.RESOLVED, part_number=focus[0])


@dataclass(frozen=True, slots=True)
class _One:
    status: ResolutionStatus
    part_number: str | None = None
    candidates: tuple[str, ...] = ()
