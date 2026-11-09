"""Add ``execution.turn_jobs.result_ciphertext`` for the shared result envelope.

Revision ID: 0008_turn_job_result
Revises: 0007_app_writer
Create Date: Spec 3 — Task 9/10 (Half B)

The sync and async turn paths share the same durable job and the same
``Response_Envelope``. The worker persists the completed turn's envelope as an
encrypted blob on the job row so a later poll (``GET /api/jobs/{id}`` on
``COMPLETED``) returns the identical envelope. The column is encrypted
(``bytea`` ciphertext) like every other sensitive field.

Requirements: 5.3, 5.6, 6.6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_turn_job_result"
down_revision: str | None = "0007_app_writer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXECUTION = "execution"


def upgrade() -> None:
    op.add_column(
        "turn_jobs",
        sa.Column("result_ciphertext", sa.LargeBinary(), nullable=True),
        schema=EXECUTION,
    )


def downgrade() -> None:
    op.drop_column("turn_jobs", "result_ciphertext", schema=EXECUTION)
