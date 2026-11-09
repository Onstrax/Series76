"""Properties 24, 25 — recommendation completeness primitives (Spec 2)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.services.completeness import GroupInput, evaluate_completeness

_ALL_GROUPS = list(RequirementGroup)


@st.composite
def group_inputs(draw: st.DrawFn) -> tuple[GroupInput, ...]:
    inputs = []
    for group in _ALL_GROUPS:
        status = draw(st.sampled_from(list(CoverageStatus)))
        has_match = draw(st.booleans())
        inputs.append(GroupInput(group=group, status=status, has_catalog_match=has_match))
    return tuple(inputs)


# Feature: domain-and-tools, Property 24: completeness is verified iff all four
# groups are SPECIFIED with a catalog-backed match, else preliminary with the
# exact unmet set; each group is evaluated independently.
@given(inputs=group_inputs())
def test_property_24_verified_iff_all_specified(inputs: tuple[GroupInput, ...]) -> None:
    result = evaluate_completeness(inputs)

    # Exactly one status per group, one per RequirementGroup.
    assert len(result.per_group) == len(_ALL_GROUPS)
    assert {gc.group for gc in result.per_group} == set(_ALL_GROUPS)

    expected_unmet = {
        gi.group
        for gi in inputs
        if not (gi.status is CoverageStatus.SPECIFIED and gi.has_catalog_match)
    }
    all_ok = not expected_unmet

    assert result.is_verified == all_ok
    assert set(result.unmet_groups) == expected_unmet
    if all_ok:
        assert result.classification == "verified"
    else:
        assert result.classification == "preliminary"

    # Independence: each group's reported status mirrors its input.
    by_group = {gi.group: gi for gi in inputs}
    for gc in result.per_group:
        assert gc.status is by_group[gc.group].status


# Feature: domain-and-tools, Property 25: a DELEGATED group never synthesizes a
# physical condition.
@given(delegated_group=st.sampled_from(_ALL_GROUPS))
def test_property_25_delegated_synthesizes_nothing(
    delegated_group: RequirementGroup,
) -> None:
    inputs = tuple(
        GroupInput(
            group=group,
            status=CoverageStatus.DELEGATED
            if group is delegated_group
            else CoverageStatus.SPECIFIED,
            has_catalog_match=group is not delegated_group,
        )
        for group in _ALL_GROUPS
    )
    result = evaluate_completeness(inputs)
    # No physical condition is synthesized for the delegated group.
    assert result.synthesized_conditions == ()
    # A DELEGATED group is treated as unmet (not SPECIFIED), so classification
    # is preliminary and the delegated group is reported.
    assert not result.is_verified
    assert delegated_group in result.unmet_groups
