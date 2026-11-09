"""Integration smoke tests for the domain-and-tools layer (Spec 2).

* ``runtime_reader_role`` is denied UPDATE/DELETE on catalog and SELECT on
  ``ingestion.*`` when the domain adapter's role is active (Req 1.3, 1.8).
* at least one custom tool is registered and routes a request through the
  repository to a typed fact result (Req 9.1).
* ``search_parts`` pagination enumerates the full matched set (Req 3.5).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from series76_domain.repository.pg_adapter import PostgresTypedRepository
from series76_domain.tools import ToolContext, build_set_a, build_set_b

from .seed import SeededCatalog

pytestmark = pytest.mark.integration

SeededFixture = tuple[SeededCatalog, Callable[[], Session], Engine]


def test_runtime_reader_role_denied_write_and_ingestion(
    seeded_catalog: SeededFixture,
) -> None:
    _seeded, factory, _engine = seeded_catalog
    # Build the adapter (activates runtime_reader_role on the session), then
    # confirm the role boundary holds on that same session.
    with factory() as session:
        PostgresTypedRepository.resolve_active(session)
        with pytest.raises(ProgrammingError):
            session.execute(
                text("UPDATE catalog.catalog_edition SET state = 'retired'")
            )
        session.rollback()
    with factory() as session:
        session.execute(text("SET ROLE runtime_reader_role"))
        with pytest.raises(ProgrammingError):
            session.execute(text("DELETE FROM catalog.part_number"))
        session.rollback()
    with factory() as session:
        session.execute(text("SET ROLE runtime_reader_role"))
        with pytest.raises(ProgrammingError):
            session.execute(text("SELECT * FROM ingestion.ingestion_run"))
        session.rollback()


def test_tool_registered_routes_through_repository(
    seeded_catalog: SeededFixture,
) -> None:
    seeded, factory, _engine = seeded_catalog

    with factory() as session:

        def repo_factory(_ctx: ToolContext) -> PostgresTypedRepository:
            # Reuse the single test-scoped session (closed by the with-block),
            # so no connection leaks to block the schema teardown.
            return PostgresTypedRepository.resolve_pinned(session, _ctx.edition_id)

        ctx = ToolContext(edition_id=seeded.published_edition_id, trace_id="smoke")
        tools_b = build_set_b(lambda: ctx, repo_factory)
        tools_a = build_set_a(lambda: ctx, repo_factory)

        assert "get_part_details" in tools_b
        assert "query_parts" in tools_a

        # Invoke the underlying function directly (no LLM): it routes through
        # the real repository to a typed fact result.
        result = tools_b["get_part_details"].func(part_number=seeded.dual_unit_pn)
        assert result.ok
        assert result.facts
        assert result.trace_id == "smoke"
        session.rollback()


def test_search_pagination_enumerates_full_set(
    seeded_catalog: SeededFixture,
) -> None:
    from series76_domain.model.filter_ast import AllowlistField, Operator, Predicate
    from series76_domain.operations.search_parts import search_parts

    _seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        node = Predicate(AllowlistField.MOTOR_POWER, Operator.GE, Decimal(0))
        all_pns: list[str] = []
        cursor: int | None = None
        first = search_parts(repo, node, cursor=None, page_size=2)
        assert not first.is_no_results
        total = first.total_matches
        while True:
            result = search_parts(repo, node, cursor=cursor, page_size=2)
            all_pns.extend(c.part_number.canonical_pn for c in result.page)
            if result.next_cursor is None:
                break
            cursor = result.next_cursor
        assert len(all_pns) == total
        assert len(set(all_pns)) == total
