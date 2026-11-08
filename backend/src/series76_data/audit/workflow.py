"""Human manual-audit workflow and correction records (Spec 1, Task 11).

Design reference: data-and-ingestion/design.md § Human Manual-Audit Workflow.

Provides the workflow for writing ``ingestion.verification_record`` rows that
capture, per confirmed or corrected fact: reviewer identity, prior value,
verified value, justification, source cell reference, and source document hash
(Req 3.4). It can mark an edition audit-complete once coverage is reached.

A correction whose referenced source document hash differs from the *current*
source hash is **stale**: the workflow reports ``CORRECTION_STALE``, does NOT
apply the correction, and leaves the edition unchanged (Property 6, Req 3.5).
The staleness check is factored into a pure predicate so property tests drive it
directly.

This module delivers the workflow, the record writes, and the staleness logic
only. Executing the audit against the real PDF is **[EXPERIMENT]** (Task 19) and
is not performed or asserted here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from series76_data.errors import IngestionErrorCode
from series76_data.models.orm import VerificationRecord
from series76_data.pipeline.diagnostics import fail


def is_correction_stale(referenced_hash: str, current_hash: str) -> bool:
    """True iff a correction's referenced document hash is not the current one.

    Pure predicate (Property 6). A stale correction must not be applied.
    """

    return referenced_hash.strip().lower() != current_hash.strip().lower()


@dataclass(frozen=True, slots=True)
class Correction:
    """A reviewer's confirmation or correction of one fact.

    Attributes:
        reviewer: the reviewer's identity (captured verbatim).
        prior_value: the value before the review, if any.
        verified_value: the value the reviewer confirms/corrects to.
        justification: the reviewer's reason, captured verbatim.
        source_cell_id: the backing source cell, if one applies.
        referenced_document_hash: the source document hash the reviewer saw.
    """

    reviewer: str
    prior_value: str | None
    verified_value: str | None
    justification: str
    source_cell_id: int | None
    referenced_document_hash: str


class ManualAuditWorkflow:
    """Record verification results and enforce correction staleness.

    Args:
        session: an open SQLAlchemy :class:`Session`; the caller owns commit.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def apply_correction(
        self,
        correction: Correction,
        current_document_hash: str,
        manifest_id: int | None = None,
    ) -> VerificationRecord:
        """Apply a correction, writing a :class:`VerificationRecord`.

        Raises:
            IngestionError: ``CORRECTION_STALE`` when the correction references a
                document hash other than ``current_document_hash``. The record is
                NOT written and the edition is unchanged (Property 6).
        """

        if is_correction_stale(
            correction.referenced_document_hash, current_document_hash
        ):
            fail(
                IngestionErrorCode.CORRECTION_STALE,
                affected_unit=f"cell:{correction.source_cell_id}",
                trigger="correction references a stale source document hash",
                detail={
                    "referenced_document_hash": correction.referenced_document_hash,
                    "current_document_hash": current_document_hash,
                },
            )

        record = VerificationRecord(
            reviewer=correction.reviewer,
            prior_value=correction.prior_value,
            verified_value=correction.verified_value,
            justification=correction.justification,
            source_cell_id=correction.source_cell_id,
            source_document_hash=correction.referenced_document_hash,
            manifest_id=manifest_id,
            state="verified",
        )
        self._session.add(record)
        self._session.flush()
        return record

    def mark_edition_audit_complete(
        self, reviewer: str, current_document_hash: str
    ) -> VerificationRecord:
        """Write a record marking the edition audit-complete.

        This is a workflow marker only; whether coverage is actually 100% is the
        Verifier gate's decision. Executing the real audit is [EXPERIMENT].
        """

        record = VerificationRecord(
            reviewer=reviewer,
            prior_value=None,
            verified_value=None,
            justification="edition audit marked complete",
            source_cell_id=None,
            source_document_hash=current_document_hash,
            manifest_id=None,
            state="audit_complete",
        )
        self._session.add(record)
        self._session.flush()
        return record
