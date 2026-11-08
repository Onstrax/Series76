"""Shared enumerations mirrored by the PostgreSQL schema (Spec 1).

The string values are the canonical DB/wire forms and must match the enum
types created by the Alembic migrations exactly.
"""

from __future__ import annotations

from enum import Enum


class AvailabilityStatus(str, Enum):
    """Status half of every ``(value, status)`` technical metric pair.

    The four states keep *documented zero*, *N/A*, and *absence* distinct
    (Req 5.1-5.3). A documented numeric zero is ``AVAILABLE`` with value ``0``;
    a printed "N/A" is ``NOT_APPLICABLE``; a missing value is ``NOT_DOCUMENTED``;
    a value awaiting manual audit is ``NOT_VERIFIED``.
    """

    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_DOCUMENTED = "NOT_DOCUMENTED"
    NOT_VERIFIED = "NOT_VERIFIED"


class FrequencyState(str, Enum):
    """Frequency context of an operating condition (Req 4.4, 4.5)."""

    EXPLICIT = "EXPLICIT"
    NOT_SPECIFIED = "NOT_SPECIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EditionState(str, Enum):
    """Lifecycle of a :class:`catalog_edition` (Req 8)."""

    CANDIDATE = "candidate"
    PUBLISHED = "published"
    RETIRED = "retired"


class AuthorityRole(str, Enum):
    """Documentary trust role of a source document (Req 1.1, 1.2).

    Only an ``authorized-technical-source`` document may supply technical
    numbers. ``context-only`` (the summary PDF) never can.
    """

    AUTHORIZED_TECHNICAL_SOURCE = "authorized-technical-source"
    CONTEXT_ONLY = "context-only"


class SupplyMode(str, Enum):
    """Admitted AC/DC mode of a supply profile (no synthetic AC/DC split)."""

    AC = "AC"
    DC = "DC"


class IngestionMode(str, Enum):
    """The two ingestion modes (Req 2)."""

    VERIFIED_REPLAY = "verified_replay"
    FRESH_EXTRACTION = "fresh_extraction"


class RunStatus(str, Enum):
    """Terminal status of a completed fresh_extraction run (Req 2.6)."""

    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    VERIFIED_READY = "VERIFIED_READY"
