"""SourceInventory filter: register source PDFs with provenance (Spec 1, Task 5).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
SourceInventory.

Registers one or more source PDFs, recording for each a SHA-256 digest, a
unique document id (assigned by the DB), the page count, the declared template,
and the documentary authority role (Req 1.3). Only
``series_76_electric_data.pdf`` is an ``authorized-technical-source``; the
summary PDF is ``context-only`` and may never supply a technical number
(Req 1.1, 1.2). A technical value whose evidence does not trace to an
authorized-technical-source cell is rejected downstream — this module exposes
:func:`is_authorized_technical_source` so later stages can enforce that.

Errors (each halts that document; any prior edition is left unchanged):

* ``INPUT_UNREADABLE`` — the file cannot be read.
* ``TEMPLATE_UNKNOWN`` — the declared template is not in the recognized set.
* ``HASH_MISMATCH`` — a recomputed SHA-256 differs from the recorded digest.

The SHA-256 comparison is factored into pure functions (:func:`compute_sha256`,
:func:`digests_match`) so property tests can drive the halting behaviour without
real PDFs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from series76_data.errors import IngestionErrorCode
from series76_data.models.enums import AuthorityRole
from series76_data.models.orm import SourceDocument
from series76_data.pipeline.diagnostics import fail

# The recognized template set. A declared template outside this set halts the
# document with TEMPLATE_UNKNOWN (Req 9.4). Templates T01-T07 are the seven
# tables of the electric-data PDF; ``summary`` is the narrative summary.
RECOGNIZED_TEMPLATES: frozenset[str] = frozenset(
    {"T01", "T02", "T03", "T04", "T05", "T06", "T07", "summary"}
)

# Declared documentary role per known filename (Req 1.1, 1.2). Only the
# electric-data PDF is an authorized technical source.
AUTHORITY_BY_FILENAME: dict[str, AuthorityRole] = {
    "series_76_electric_data.pdf": AuthorityRole.AUTHORIZED_TECHNICAL_SOURCE,
    "series_76_summary.pdf": AuthorityRole.CONTEXT_ONLY,
}

_HASH_CHUNK = 1 << 20  # 1 MiB streaming read


def compute_sha256(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data`` (pure)."""

    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of the file at ``path``, read in chunks.

    Raises:
        IngestionError: ``INPUT_UNREADABLE`` if the file cannot be opened/read.
    """

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
                digest.update(chunk)
    except OSError as exc:
        fail(
            IngestionErrorCode.INPUT_UNREADABLE,
            affected_unit=f"doc:{path.name}",
            trigger="source file could not be read",
            detail={"filename": path.name, "os_error": exc.strerror},
        )
    return digest.hexdigest()


def digests_match(recorded: str, recomputed: str) -> bool:
    """True iff two hex SHA-256 digests are equal (case-insensitive, pure).

    This is the single comparison the halting behaviour pivots on; property
    tests exercise it directly so they need no real PDF.
    """

    return recorded.strip().lower() == recomputed.strip().lower()


def verify_digest(affected_unit: str, recorded: str, recomputed: str) -> None:
    """Raise ``HASH_MISMATCH`` if ``recorded`` != ``recomputed`` (Req 1.6, 2.3).

    On mismatch the pipeline halts before producing an edition; the caller must
    not proceed. The prior active edition is therefore left unchanged.
    """

    if not digests_match(recorded, recomputed):
        fail(
            IngestionErrorCode.HASH_MISMATCH,
            affected_unit=affected_unit,
            trigger="recomputed sha256 differs from recorded digest",
            detail={
                "recorded_sha256": recorded,
                "recomputed_sha256": recomputed,
            },
        )


def resolve_authority_role(filename: str) -> AuthorityRole:
    """Return the documentary authority role for a known source ``filename``.

    An unknown filename defaults to ``context-only`` — never technical source —
    so no number can be sourced from an unrecognized document (fail safe).
    """

    return AUTHORITY_BY_FILENAME.get(filename, AuthorityRole.CONTEXT_ONLY)


def is_authorized_technical_source(role: AuthorityRole) -> bool:
    """True iff ``role`` permits supplying technical numbers (Req 1.1)."""

    return role is AuthorityRole.AUTHORIZED_TECHNICAL_SOURCE


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    """A request to register one source document."""

    path: Path
    template: str
    recorded_sha256: str | None = None
    """If provided, the recomputed digest is checked against it (HASH_MISMATCH)."""


class SourceInventory:
    """Register source PDFs into ``provenance.source_document``.

    Args:
        session: an open SQLAlchemy :class:`Session`. The caller owns commit/
            rollback — this stage only flushes so ids are assigned.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def register(self, registration: SourceRegistration) -> SourceDocument:
        """Register one document, returning the persisted :class:`SourceDocument`.

        Raises:
            IngestionError: ``INPUT_UNREADABLE`` / ``TEMPLATE_UNKNOWN`` /
                ``HASH_MISMATCH`` per the Error Handling table; each halts this
                document and leaves any prior edition unchanged.
        """

        path = registration.path
        affected_unit = f"doc:{path.name}"

        if registration.template not in RECOGNIZED_TEMPLATES:
            fail(
                IngestionErrorCode.TEMPLATE_UNKNOWN,
                affected_unit=affected_unit,
                trigger="declared template not in the recognized set",
                detail={
                    "filename": path.name,
                    "declared_template": registration.template,
                },
            )

        try:
            byte_size = path.stat().st_size
        except OSError as exc:
            fail(
                IngestionErrorCode.INPUT_UNREADABLE,
                affected_unit=affected_unit,
                trigger="source file metadata could not be read",
                detail={"filename": path.name, "os_error": exc.strerror},
            )

        recomputed = compute_file_sha256(path)
        if registration.recorded_sha256 is not None:
            verify_digest(affected_unit, registration.recorded_sha256, recomputed)

        role = resolve_authority_role(path.name)
        page_count = _probe_page_count(path)

        document = SourceDocument(
            sha256=recomputed,
            filename=path.name,
            byte_size=byte_size,
            page_count=page_count,
            template=registration.template,
            authority_role=role,
        )
        self._session.add(document)
        self._session.flush()
        return document


def _probe_page_count(path: Path) -> int:
    """Best-effort page count for a PDF.

    A full PDF parser is out of scope for this filter (and would pull a heavy
    dependency); we count ``/Type /Page`` markers in the raw bytes as a
    structural probe. Unreadable files are reported as ``INPUT_UNREADABLE``.
    A non-PDF or marker-less file yields ``0`` rather than raising, leaving the
    (recorded) page count to be confirmed by the manual audit.
    """

    try:
        data = path.read_bytes()
    except OSError as exc:
        fail(
            IngestionErrorCode.INPUT_UNREADABLE,
            affected_unit=f"doc:{path.name}",
            trigger="source file could not be read for page count",
            detail={"filename": path.name, "os_error": exc.strerror},
        )
    return data.count(b"/Type /Page") or data.count(b"/Type/Page")
