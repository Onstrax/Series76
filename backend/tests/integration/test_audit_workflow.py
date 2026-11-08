"""Integration test for the manual-audit workflow DB side (Task 11).

Property 6 (DB side): a stale correction writes no verification_record row and
leaves the edition unchanged. A fresh correction is persisted with full
provenance. Runs against the real PostgreSQL container.
"""

from __future__ import annotations

import pytest
from alembic.config import Config
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from series76_data.audit.workflow import Correction, ManualAuditWorkflow
from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.models.orm import VerificationRecord

pytestmark = pytest.mark.integration


def _engine(url: str) -> Engine:
    return create_engine(url, future=True)


def _correction(referenced_hash: str) -> Correction:
    return Correction(
        reviewer="alice",
        prior_value="10",
        verified_value="11",
        justification="re-read the cell",
        source_cell_id=None,
        referenced_document_hash=referenced_hash,
    )


# Feature: data-and-ingestion, Property 6: Stale corrections are not applied. A
# correction whose referenced document hash differs from the current source hash
# writes no record (the edition is unchanged); a matching hash is persisted.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    referenced=st.text(alphabet="0123456789abcdef", min_size=8, max_size=16),
    current=st.text(alphabet="0123456789abcdef", min_size=8, max_size=16),
)
def test_property_6_stale_correction_not_persisted(
    migrated_db: Config, postgres_url: str, referenced: str, current: str
) -> None:
    eng = _engine(postgres_url)
    try:
        with Session(eng) as s:
            s.execute(VerificationRecord.__table__.delete())
            s.commit()

        with Session(eng) as s:
            workflow = ManualAuditWorkflow(s)
            if referenced.lower() == current.lower():
                record = workflow.apply_correction(_correction(referenced), current)
                s.commit()
                assert record.reviewer == "alice"
                assert record.source_document_hash == referenced
            else:
                with pytest.raises(IngestionError) as exc:
                    workflow.apply_correction(_correction(referenced), current)
                assert exc.value.failure.code is IngestionErrorCode.CORRECTION_STALE
                s.rollback()

        # A stale correction must have persisted no row.
        with Session(eng) as s:
            count = s.execute(
                select(func.count()).select_from(VerificationRecord)
            ).scalar_one()
            if referenced.lower() == current.lower():
                assert count == 1
            else:
                assert count == 0
    finally:
        eng.dispose()
