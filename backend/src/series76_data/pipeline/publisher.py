"""Publisher: atomic promotion, retirement, idempotent re-run (Task 12).

Design reference: data-and-ingestion/design.md § Atomic Publication /
Active-Edition-Pointer Promotion and § Components and Interfaces / Publisher.

The Publisher runs the Verifier gate **inside a transaction**; only on gate PASS
does the single-row ``publication.catalog_current`` pointer atomically flip to
the new edition (Req 8.2). On any failure it emits ``PUBLICATION_FAILED``, rolls
back, and leaves the prior edition and pointer intact (Property 21, Req 8.3).
Activation is restricted to ``Publisher_Role`` — enforced in the DB by grants;
this module performs the privileged write and relies on that boundary.

It also implements:

* **Edition immutability** (Property 20): published facts are never mutated in
  place; a correction requires a NEW edition. The Publisher only ever inserts a
  new edition and flips the pointer — it never updates published facts.
* **Retirement** (Property 22): a retired edition is marked ``retired`` so new
  recommendations are blocked, while its facts and event history are retained
  and readable.
* **Idempotent re-run** (Property 2): a re-run whose manifest digest matches an
  existing edition records the run (an event) but creates NO duplicate edition
  and leaves the pointer unchanged.

The gate and the flip share one transaction, so a reader observes exactly the
prior edition or exactly the new one — never a partial state (Property 19).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.models.enums import EditionState
from series76_data.models.orm import (
    CatalogCurrent,
    CatalogEdition,
    CatalogPublicationEvent,
)
from series76_data.pipeline.diagnostics import classify
from series76_data.pipeline.verifier import AuditedEdition, OracleCounts, Verifier


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC)


class Publisher:
    """Publish, retire, and idempotently re-run editions over a real session.

    Args:
        session: an open SQLAlchemy :class:`Session`. The Publisher manages the
            transaction boundary of each operation (commit on success, rollback
            on failure) so atomicity is exercised by the real engine.
    """

    def __init__(self, session: Session, verifier: Verifier | None = None) -> None:
        self._session = session
        self._verifier = verifier or Verifier()

    # --- publication ------------------------------------------------------

    def publish(
        self,
        edition_id: uuid.UUID,
        manifest_digest: str,
        audited: AuditedEdition,
        actor: str,
        oracle: OracleCounts | None = None,
    ) -> CatalogEdition:
        """Verify and atomically activate an edition.

        If an edition with ``manifest_digest`` already exists, this is an
        idempotent re-run: it records an event and returns the existing edition
        without creating a duplicate or moving the pointer (Property 2).

        Otherwise the gate runs inside the transaction; on PASS the edition is
        inserted, the pointer flips atomically, and a publication event is
        logged. On gate failure the transaction rolls back and
        ``PUBLICATION_FAILED`` is raised with the prior edition intact
        (Property 19, 21).

        Raises:
            IngestionError: ``PUBLICATION_FAILED`` on gate failure or any error
                during activation; ``DUPLICATE_IDENTITY`` propagates from the
                gate (also rolled back).
        """

        existing = self._find_edition_by_digest(manifest_digest)
        if existing is not None:
            return self._record_idempotent_rerun(existing, actor, manifest_digest)

        prev_edition_id = self._active_edition_id()
        try:
            report = self._verifier.verify(audited, oracle)
            if not report.passed:
                raise IngestionError(
                    classify(
                        IngestionErrorCode.PUBLICATION_FAILED,
                        affected_unit=f"edition:{edition_id}",
                        trigger="verification gate did not pass; activation aborted",
                        detail={"gate_failures": report.diagnostics.as_log_records()},
                    ).failure
                )

            edition = CatalogEdition(
                edition_id=edition_id,
                manifest_digest=manifest_digest,
                state=EditionState.PUBLISHED,
                created_at=_utcnow(),
                prev_edition_id=prev_edition_id,
            )
            self._session.add(edition)
            self._session.flush()

            self._flip_pointer(edition_id)
            self._log_event(
                prev_edition_id=prev_edition_id,
                new_edition_id=edition_id,
                actor=actor,
                reason="publish",
                result="activated",
                manifest_digest=manifest_digest,
            )
            self._session.commit()
            return edition
        except IngestionError:
            self._session.rollback()
            raise
        except Exception as exc:  # pragma: no cover - defensive rollback path
            self._session.rollback()
            raise IngestionError(
                classify(
                    IngestionErrorCode.PUBLICATION_FAILED,
                    affected_unit=f"edition:{edition_id}",
                    trigger="activation failed; prior edition and pointer intact",
                    detail={"error_type": type(exc).__name__},
                ).failure
            ) from exc

    # --- retirement -------------------------------------------------------

    def retire(self, edition_id: uuid.UUID, actor: str, reason: str) -> CatalogEdition:
        """Retire an edition: block new recommendations, retain history.

        The edition's state becomes ``retired`` and a retirement event is
        logged. Its facts and events remain readable (Property 22). Retiring the
        active edition does not delete the pointer; callers that generate
        recommendations must honor the ``retired`` state.
        """

        edition = self._session.get(CatalogEdition, edition_id)
        if edition is None:
            raise IngestionError(
                classify(
                    IngestionErrorCode.PUBLICATION_FAILED,
                    affected_unit=f"edition:{edition_id}",
                    trigger="cannot retire unknown edition",
                ).failure
            )
        edition.state = EditionState.RETIRED
        self._session.flush()
        self._log_event(
            prev_edition_id=edition_id,
            new_edition_id=None,
            actor=actor,
            reason=reason,
            result="retired",
            manifest_digest=edition.manifest_digest,
        )
        self._session.commit()
        return edition

    # --- internals --------------------------------------------------------

    def _find_edition_by_digest(self, manifest_digest: str) -> CatalogEdition | None:
        stmt = select(CatalogEdition).where(
            CatalogEdition.manifest_digest == manifest_digest
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def _record_idempotent_rerun(
        self, existing: CatalogEdition, actor: str, manifest_digest: str
    ) -> CatalogEdition:
        self._log_event(
            prev_edition_id=existing.edition_id,
            new_edition_id=existing.edition_id,
            actor=actor,
            reason="idempotent_rerun",
            result="no_duplicate_edition",
            manifest_digest=manifest_digest,
        )
        self._session.commit()
        return existing

    def _active_edition_id(self) -> uuid.UUID | None:
        stmt = select(CatalogCurrent.edition_id).where(CatalogCurrent.pin.is_(True))
        return self._session.execute(stmt).scalar_one_or_none()

    def _flip_pointer(self, edition_id: uuid.UUID) -> None:
        """Atomically set the single-row pointer to ``edition_id``."""

        current = self._session.get(CatalogCurrent, True)
        now = _utcnow()
        if current is None:
            self._session.add(
                CatalogCurrent(pin=True, edition_id=edition_id, activated_at=now)
            )
        else:
            current.edition_id = edition_id
            current.activated_at = now
        self._session.flush()

    def _log_event(
        self,
        *,
        prev_edition_id: uuid.UUID | None,
        new_edition_id: uuid.UUID | None,
        actor: str,
        reason: str,
        result: str,
        manifest_digest: str | None,
    ) -> None:
        self._session.add(
            CatalogPublicationEvent(
                prev_edition_id=prev_edition_id,
                new_edition_id=new_edition_id,
                actor=actor,
                occurred_at=_utcnow(),
                reason=reason,
                result=result,
                manifest_digest=manifest_digest,
            )
        )
        self._session.flush()
