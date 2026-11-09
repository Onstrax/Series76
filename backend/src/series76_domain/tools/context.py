"""Server-injected tool context and sanitized tool output (Task 12.2, Req 9.*).

The **server-injected** inputs — authorized ``edition_id``, permission context,
result limits, and ``trace_id`` — enter only through :class:`ToolContext`,
merged server-side. A model-supplied value for any of them is **ignored**
(Property 27). Tool output is a :class:`SanitizedFact` carrying only typed data
with :class:`~series76_domain.model.enums.DataStatus` and
:class:`~series76_domain.model.evidence.EvidenceReference`; any instruction-like
string in a fact passes through **inert as data** — nothing is executed or
followed as an instruction (Property 28).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from series76_domain.model.enums import DataStatus, SemanticFailureCode
from series76_domain.model.evidence import EvidenceReference
from series76_domain.repository.port import TypedRepository

# A factory that yields the edition-pinned repository for a resolved context.
RepositoryFactory = Callable[["ToolContext"], TypedRepository]


@dataclass(frozen=True, slots=True)
class ToolContext:
    """The server-injected, non-model inputs merged into every tool call.

    Attributes:
        edition_id: the authorized edition. A model-supplied edition is ignored
            in favor of this value (Property 27, Property 1).
        permissions: an opaque permission-context token set by the server.
        max_results: a server-set result-limit bound.
        trace_id: a server-set correlation id.
        allow_new_recommendation: whether a *new* recommendation is permitted
            against the pinned edition (``False`` blocks a withdrawn edition
            with ``SOURCE_WITHDRAWN`` while pinned reads still succeed).
    """

    edition_id: uuid.UUID
    permissions: str = "runtime_reader"
    max_results: int = 50
    trace_id: str = ""
    allow_new_recommendation: bool = True


@dataclass(frozen=True, slots=True)
class SanitizedFact:
    """One sanitized, typed fact in a tool result.

    Attributes:
        key: a stable field name (e.g. ``"torque_inlbs"``).
        value: the documented magnitude as a string (``None`` when not
            ``AVAILABLE``) — a string so an instruction-like text is inert data.
        unit: the documented unit label, if any.
        status: the :class:`DataStatus` of the fact.
        evidence: the fact's resolvable evidence reference.
        is_derived: ``True`` iff the value is a :class:`DerivedValue`, never an
            official documented figure.
    """

    key: str
    value: str | None
    unit: str | None
    status: DataStatus
    evidence: EvidenceReference
    is_derived: bool = False


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A tool's typed output: sanitized facts or exactly one failure code.

    Attributes:
        facts: the sanitized typed facts (empty on failure).
        failure: exactly one :class:`SemanticFailureCode` for a defined
            non-success outcome, else ``None`` (Property 29).
        not_documented: ``True`` for a ``get_source_notes`` miss (a
            ``DataStatus.NOT_DOCUMENTED`` outcome, distinct from a failure code).
        total_matches: for search, the exact match total.
        verified_pns / preliminary_pns: for search, the partitioned sets.
        next_cursor: for search pagination.
        trace_id: echoed server trace id (never a model value).
        offending_input: a secret-free reference to the offending input, if any.
    """

    facts: tuple[SanitizedFact, ...] = ()
    failure: SemanticFailureCode | None = None
    not_documented: bool = False
    total_matches: int | None = None
    verified_pns: tuple[str, ...] = ()
    preliminary_pns: tuple[str, ...] = ()
    next_cursor: int | None = None
    trace_id: str = ""
    offending_input: str | None = None
    extra_pns: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        """True iff no semantic failure code is set."""
        return self.failure is None


def fact_value_str(value: Decimal | None) -> str | None:
    """Render a Decimal magnitude as a canonical string (never a float)."""

    return None if value is None else str(value)
