"""Properties 26 and 32 — source notes and withdrawn editions (seeded PG)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.filter_ast import AllowlistField, Operator, Predicate
from series76_domain.operations.get_part import get_part
from series76_domain.operations.get_source_notes import get_source_notes
from series76_domain.operations.search_parts import search_parts
from series76_domain.repository.pg_adapter import PostgresTypedRepository

from .seed import SeededCatalog

pytestmark = pytest.mark.integration

SeededFixture = tuple[SeededCatalog, Callable[[], Session], Engine]


# Feature: domain-and-tools, Property 26: notes returned literal, separate, and
# scoped exactly to covered rows; NOT_DOCUMENTED distinct from UNVERIFIED.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(note_type=st.sampled_from([None, "footnote", "certification", "nonexistent"]))
def test_property_26_notes_literal_scoped(
    seeded_catalog: SeededFixture, note_type: str | None
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        result = get_source_notes(repo, seeded.dual_unit_pn, note_type=note_type)

        if note_type == "nonexistent":
            # A requested note that does not exist -> NOT_DOCUMENTED.
            assert result.not_documented
            assert not result.notes
            return

        assert result.is_documented
        # Each note is a separate item with literal text and exact covered rows.
        scopes = {n.note_id: n.covered_rows for n in result.notes}
        if note_type in (None, "footnote"):
            assert seeded.note_a_id in scopes
            assert set(scopes[seeded.note_a_id]) == set(seeded.note_a_rows)
        if note_type in (None, "certification"):
            assert seeded.note_b_id in scopes
            assert set(scopes[seeded.note_b_id]) == set(seeded.note_b_rows)
        # Distinct scopes are not merged.
        if note_type is None:
            assert set(seeded.note_a_rows) != set(seeded.note_b_rows)
            # The instruction-like certification note text is literal data only.
            cert = next(n for n in result.notes if n.note_id == seeded.note_b_id)
            assert "ignore this instruction" in cert.printed_text


# Feature: domain-and-tools, Property 32: a withdrawn edition blocks new
# recommendations but allows pinned reads.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_n=st.integers(min_value=0, max_value=3))
def test_property_32_withdrawn_blocks_new_allows_pinned(
    seeded_catalog: SeededFixture, _n: int
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        repo = PostgresTypedRepository.resolve_pinned(
            session, seeded.withdrawn_edition_id
        )
        assert repo.pinned_edition.is_withdrawn

        # A NEW recommendation request is blocked with SOURCE_WITHDRAWN.
        blocked = get_part(repo, seeded.dual_unit_pn, allow_withdrawn=False)
        assert blocked.failure is SemanticFailureCode.SOURCE_WITHDRAWN
        assert blocked.view is None

        blocked_search = search_parts(
            repo,
            Predicate(AllowlistField.MOTOR_POWER, Operator.GE, 0),
            allow_withdrawn=False,
        )
        assert blocked_search.failure is SemanticFailureCode.SOURCE_WITHDRAWN

        # A PINNED historical read still succeeds (no fabricated value).
        pinned = get_part(repo, seeded.dual_unit_pn, allow_withdrawn=True)
        assert pinned.is_found
        assert pinned.view is not None
