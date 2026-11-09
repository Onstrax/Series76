"""The per-turn ``Turn_State`` machine and its transition guard (Req 4.1, 4.2).

Exactly the transitions of the design's state diagram are permitted; any other
transition — and any value outside the 12-value set — is rejected. The map onto
the Spec 3 ``Job_State`` is applied at the worker boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from series76_agent.domain.enums import TurnState

S = TurnState

#: The enumerated transitions (design § Turn state machine). Nothing else.
TRANSITIONS: frozenset[tuple[TurnState, TurnState]] = frozenset(
    {
        (S.ACCEPTED, S.INTERPRETING),
        (S.INTERPRETING, S.INTERPRETED),
        (S.INTERPRETED, S.NEEDS_CLARIFICATION),
        (S.INTERPRETED, S.AWAITING_CONFIRMATION),
        (S.INTERPRETED, S.EXECUTING),
        (S.NEEDS_CLARIFICATION, S.INTERPRETING),
        (S.AWAITING_CONFIRMATION, S.EXECUTING),
        (S.AWAITING_CONFIRMATION, S.STALE_PLAN),
        (S.EXECUTING, S.VERIFYING),
        (S.VERIFYING, S.COMPLETED),
        (S.INTERPRETING, S.FAILED),
        (S.EXECUTING, S.FAILED),
        (S.VERIFYING, S.FAILED),
        (S.ACCEPTED, S.CANCELLED),
        (S.INTERPRETING, S.CANCELLED),
        (S.INTERPRETED, S.CANCELLED),
        (S.NEEDS_CLARIFICATION, S.CANCELLED),
        (S.AWAITING_CONFIRMATION, S.CANCELLED),
        (S.EXECUTING, S.CANCELLED),
        (S.INTERPRETED, S.SOURCE_WITHDRAWN),
        (S.EXECUTING, S.SOURCE_WITHDRAWN),
    }
)

#: Terminal states: no outgoing transition exists.
TERMINAL: frozenset[TurnState] = frozenset(
    {S.COMPLETED, S.FAILED, S.CANCELLED, S.STALE_PLAN, S.SOURCE_WITHDRAWN}
)

#: Paused states: the turn waits for a user reply / an authenticated confirmation.
PAUSED: frozenset[TurnState] = frozenset({S.NEEDS_CLARIFICATION, S.AWAITING_CONFIRMATION})


class TurnStateError(ValueError):
    """Raised for an out-of-set value or a non-enumerated transition."""


def is_allowed(source: TurnState, target: TurnState) -> bool:
    """True iff ``source -> target`` is one of the enumerated transitions."""
    return (source, target) in TRANSITIONS


def coerce_state(value: object) -> TurnState:
    """Return ``value`` as a :class:`TurnState` or raise :class:`TurnStateError`."""

    if isinstance(value, TurnState):
        return value
    if isinstance(value, str):
        try:
            return TurnState(value)
        except ValueError as exc:
            raise TurnStateError(f"unknown turn state: {value!r}") from exc
    raise TurnStateError(f"unknown turn state: {value!r}")


@dataclass
class Turn:
    """One turn carrying exactly one :class:`TurnState` at a time.

    ``history`` records every state the turn has held, in order, so a test (or
    the debug trace) can audit that only enumerated transitions occurred.
    """

    turn_id: str
    state: TurnState = TurnState.ACCEPTED
    history: list[TurnState] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.state = coerce_state(self.state)
        if not self.history:
            self.history.append(self.state)

    def advance(self, target: object) -> TurnState:
        """Move to ``target`` if the transition is enumerated, else raise."""

        new_state = coerce_state(target)
        if not is_allowed(self.state, new_state):
            raise TurnStateError(
                f"transition {self.state.value} -> {new_state.value} is not permitted"
            )
        self.state = new_state
        self.history.append(new_state)
        return new_state

    @property
    def is_terminal(self) -> bool:
        """True iff the turn reached a terminal state."""
        return self.state in TERMINAL


#: Turn_State -> Spec 3 Job_State value (design: mapped at the worker boundary).
JOB_STATE_BY_TURN_STATE: dict[TurnState, str] = {
    S.ACCEPTED: "RUNNING",
    S.INTERPRETING: "RUNNING",
    S.INTERPRETED: "RUNNING",
    S.EXECUTING: "RUNNING",
    S.VERIFYING: "RUNNING",
    S.NEEDS_CLARIFICATION: "NEEDS_CLARIFICATION",
    S.AWAITING_CONFIRMATION: "AWAITING_CONFIRMATION",
    S.COMPLETED: "COMPLETED",
    S.FAILED: "FAILED",
    S.CANCELLED: "CANCELLED",
    S.STALE_PLAN: "STALE_PLAN",
    S.SOURCE_WITHDRAWN: "CATALOG_WITHDRAWN",
}


def to_job_state(state: TurnState) -> str:
    """Map a :class:`TurnState` to the Spec 3 ``Job_State`` value."""
    return JOB_STATE_BY_TURN_STATE[coerce_state(state)]
