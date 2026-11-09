"""Repository-boundary **guard errors** (design § Error Handling).

These are *not* semantic business outcomes (which are
:class:`~series76_domain.model.enums.SemanticFailureCode` values). They are
exceptions raised at the repository boundary when a hard invariant is violated:

* :class:`DisallowedSqlError` — a model-originated or non-parameterized SQL
  string reached the repository; rejected unexecuted, catalog unchanged
  (Req 1.2).
* :class:`UnresolvedEditionError` — no single resolvable pinned edition, or a
  withdrawn/non-published edition; no facts returned (Req 1.5).
* :class:`EditionMixingError` — a read would combine facts from more than one
  edition; rejected, no mixed value set (Req 1.6).

They never carry secrets, SQL text, or stack traces in their message.
"""

from __future__ import annotations


class RepositoryGuardError(Exception):
    """Base class for all repository-boundary guard violations."""


class DisallowedSqlError(RepositoryGuardError):
    """A model-originated/non-parameterized SQL string was rejected unexecuted."""


class UnresolvedEditionError(RepositoryGuardError):
    """No single resolvable, published edition could be pinned for the read."""


class EditionMixingError(RepositoryGuardError):
    """A read would have combined facts from more than one edition."""
