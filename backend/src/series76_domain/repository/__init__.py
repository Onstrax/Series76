"""Read-only typed repository port and its PostgreSQL adapter (Spec 2 § Repository).

The :class:`~series76_domain.repository.port.TypedRepository` protocol is the
*only* outward port of the domain core. Its PostgreSQL adapter
(:class:`~series76_domain.repository.pg_adapter.PostgresTypedRepository`) binds
to the Spec 1 ``runtime_reader_role``, authors only parameterized typed SQL
(through the Spec 1 ORM ``select`` construct), resolves the pinned edition
**server-side**, and maps rows to the pure domain types with evidence.
"""

from __future__ import annotations

from series76_domain.repository.errors import (
    DisallowedSqlError,
    EditionMixingError,
    RepositoryGuardError,
    UnresolvedEditionError,
)
from series76_domain.repository.pg_adapter import PostgresTypedRepository
from series76_domain.repository.port import PinnedEdition, TypedRepository

__all__ = [
    "DisallowedSqlError",
    "EditionMixingError",
    "PinnedEdition",
    "PostgresTypedRepository",
    "RepositoryGuardError",
    "TypedRepository",
    "UnresolvedEditionError",
]
