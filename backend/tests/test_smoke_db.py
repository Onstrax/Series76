"""Connectivity smoke test against a real PostgreSQL container (Task 1 demo)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.integration
def test_postgres_select_one(postgres_url: str) -> None:
    engine = create_engine(postgres_url, future=True)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar_one()
        assert result == 1
    finally:
        engine.dispose()
