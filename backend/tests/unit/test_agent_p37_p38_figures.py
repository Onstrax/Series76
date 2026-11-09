"""Spec 4 Properties 37-38: status/evidence carried, derived labeled, determinism."""

from __future__ import annotations

import uuid

from _agent_fakes import interp, make_harness, make_part
from _fakes import FakeRepository
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.rendering import untraceable_digit_runs
from series76_data.models.enums import SupplyMode
from series76_domain.repository.port import PinnedEdition

maybe = st.one_of(st.none(), st.integers(1, 500).map(str))


def _repo(torque: str | None, nm: str | None, resolvable: bool) -> FakeRepository:
    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True)
    repo = FakeRepository(pinned=edition)
    repo.add(
        make_part(
            "76-E1",
            edition.edition_id,
            services={"On/Off": (torque, nm)},
            measurements=((60, "15", "1.5", "3"),),
            modes=frozenset({SupplyMode.AC}),
            evidence_id=None if resolvable else 0,
        )
    )
    return repo


# Feature: agent-orchestration-response, Property 37: Presented figures carry resolvable
# status and evidence, derived values are labeled, and gaps are explicit
@given(torque=maybe, nm=maybe, resolvable=st.booleans())
def test_property_37_status_evidence_derived_gaps(
    torque: str | None, nm: str | None, resolvable: bool
) -> None:
    repo = _repo(torque, nm, resolvable)
    table = {
        "show 76-E1": interp("EXACT_LOOKUP", part_numbers=["76-E1"]),
        "convert 76-E1 torque to Nm": interp(
            "DERIVED_CALCULATION", part_numbers=["76-E1"], target_unit="Nm"
        ),
    }
    h = make_harness(table, repo=repo)
    sid, oid = uuid.uuid4(), uuid.uuid4()
    for message in table:
        res = h.run(sid, oid, message)
        resp = res.response
        presented = {bf.figure_id: bf for bf in resp.presented}
        if not resolvable:
            # Unresolvable evidence: every figure withheld, an unavailable state shown.
            assert presented == {}
            assert resp.withheld and "unavailable" in resp.answer.text
            assert untraceable_digit_runs(resp.answer) == []
            continue
        for block in resp.blocks:
            for dto in getattr(block, "figures", []):
                bf = presented[dto.figure_id]
                assert dto.status == bf.status.value
                ev = bf.figure.evidence
                assert (dto.evidence.cell_refs, dto.evidence.row_refs) == (
                    list(ev.cell_refs),
                    list(ev.row_refs),
                )
                assert dto.evidence.cell_refs or dto.evidence.row_refs
                if dto.status != "AVAILABLE":
                    assert dto.value is None  # explicit gap, never a number
                if bf.figure.derived is not None:
                    assert dto.derived and dto.formula and dto.precision_decimals is not None
        for bf in presented.values():
            if bf.figure.derived is not None:
                # Derived values are labeled as derived, with formula and precision.
                assert "derived" in resp.answer.text
                assert bf.figure.derived.formula in resp.answer.text
        if message.startswith("convert") and torque is None:
            assert not any(bf.figure.derived for bf in presented.values())


# Feature: agent-orchestration-response, Property 38: Repeated identical queries return
# digit-for-digit equal figures
@given(
    torque=maybe,
    fla=st.integers(1, 99).map(lambda n: f"{n}.{n % 10}"),
    message=st.sampled_from(["show 76-E1", "compare 76-E1 and 76-E2"]),
)
def test_property_38_repeated_queries_identical(torque: str | None, fla: str, message: str) -> None:
    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True)
    repo = FakeRepository(pinned=edition)
    repo.add(
        make_part(
            "76-E1",
            edition.edition_id,
            services={"On/Off": (torque, None)},
            measurements=((60, "15", fla, "3"),),
        )
    )
    repo.add(
        make_part(
            "76-E2",
            edition.edition_id,
            services={"On/Off": ("120", None)},
            measurements=((60, "12", "2.0", "3"),),
        )
    )
    table = {
        "show 76-E1": interp("EXACT_LOOKUP", part_numbers=["76-E1"]),
        "compare 76-E1 and 76-E2": interp("COMPARISON", part_numbers=["76-E1", "76-E2"]),
    }
    outputs = []
    for _ in range(2):  # two separate orchestrators (a restart) over the same edition
        h = make_harness(table, repo=repo)
        sid, oid = uuid.uuid4(), uuid.uuid4()
        a = h.run(sid, oid, message)
        b = h.run(sid, oid, message)
        assert a.response.answer.text == b.response.answer.text
        outputs.append(
            (a.response.answer.text, [blk.model_dump_json() for blk in a.response.blocks])
        )
    assert outputs[0] == outputs[1]
