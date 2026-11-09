"""Add ``conversation.messages.seq`` so history keeps insertion order.

Revision ID: 0009_message_seq
Revises: 0008_turn_job_result
Create Date: Spec 6 — final integration

The worker persists a turn's user and assistant messages in ONE fenced
transaction, so both rows get the same ``created_at`` (``now()`` is the
transaction start). Ordering ties by the random ``message_id`` could then show
the answer before the question. ``seq`` is an identity column assigned in
insertion order; history is ordered by ``(created_at, seq)``. Identity columns
need no sequence privilege, so ``app_writer`` grants are unchanged.

Requirements: Spec 3 Req 9 (history order), Spec 6 Req 6.9 (flow 9)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_message_seq"
down_revision: str | None = "0008_turn_job_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        schema="conversation",
    )


def downgrade() -> None:
    op.drop_column("messages", "seq", schema="conversation")
