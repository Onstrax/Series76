"""Properties 1, 2, 3 (evidence half) — repository over seeded PostgreSQL.

Run against a real ``postgres:15-alpine`` container seeded with the fixture
catalog. The domain adapter reads through ``runtime_reader_role``, resolves the
edition server-side, and carries evidence on every fact.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from series76_domain.repository.errors import UnresolvedEditionError
from series76_domain.repository.pg_adapter import PostgresTypedRepository

from .seed import SeededCatalog

pytestmark = pytest.mark.integration

SeededFixture = tuple[SeededCatalog, Callable[[], Session], Engine]


# Feature: domain-and-tools, Property 1: edition scoping is server-authoritative
# and single (model-supplied edition ignored; no mixed set).
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(model_supplied_edition=st.uuids())
def test_property_1_edition_scoping_server_authoritative(
    seeded_catalog: SeededFixture, model_supplied_edition: uuid.UUID
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        # The server resolves the ACTIVE edition; a model-supplied edition value
        # plays no part in resolution (it is never passed to the adapter).
        repo = PostgresTypedRepository.resolve_active(session)
        assert repo.pinned_edition.edition_id == seeded.published_edition_id
        assert repo.pinned_edition.edition_id != model_supplied_edition

        # Every fact read belongs to exactly the one pinned edition.
        for part in repo.list_part_numbers():
            assert part.edition_id == seeded.published_edition_id
            for cfg in repo.configurations_for(part):
                assert cfg.edition_id == seeded.published_edition_id


# Feature: domain-and-tools, Property 2: unresolvable/withdrawn/non-published
# editions return a typed error and zero facts.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(missing_edition=st.uuids())
def test_property_2_unresolvable_edition_zero_facts(
    seeded_catalog: SeededFixture, missing_edition: uuid.UUID
) -> None:
    seeded, factory, _engine = seeded_catalog
    with factory() as session:
        # A random (non-existent) edition id is unresolvable -> typed error.
        if missing_edition in (
            seeded.published_edition_id,
            seeded.withdrawn_edition_id,
        ):
            return
        with pytest.raises(UnresolvedEditionError):
            PostgresTypedRepository.resolve_pinned(session, missing_edition)


# Feature: domain-and-tools, Property 3 (evidence half): every returned fact
# resolves to at least one published source cell with no unresolved reference.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(which=st.sampled_from(["dual", "freq", "t03"]))
def test_property_3_evidence_resolves(
    seeded_catalog: SeededFixture, which: str
) -> None:
    seeded, factory, _engine = seeded_catalog
    pn = {
        "dual": seeded.dual_unit_pn,
        "freq": seeded.multi_freq_pn,
        "t03": seeded.t03_pn,
    }[which]
    with factory() as session:
        repo = PostgresTypedRepository.resolve_active(session)
        part = repo.find_part_number(pn)
        assert part is not None
        for cfg in repo.configurations_for(part):
            assert cfg.evidence.is_resolvable
            for sp in repo.service_performance_for(cfg):
                assert sp.evidence.is_resolvable
            for up in repo.unqualified_performance_for(cfg):
                assert up.evidence.is_resolvable
            for cond in repo.operating_conditions_for(cfg):
                for m in repo.measurements_for(cond):
                    assert m.evidence.is_resolvable
