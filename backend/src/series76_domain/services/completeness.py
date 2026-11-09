"""The ``CompletenessEvaluator`` (Task 10.1, Req 7.*).

Reports exactly one :class:`~series76_domain.model.enums.CoverageStatus` per
each of the four :class:`~series76_domain.model.enums.RequirementGroup`s. The
candidate set is ``verified`` **iff** all four groups are ``SPECIFIED`` with a
non-empty catalog-backed match; otherwise ``preliminary`` with the exact set of
groups whose status is not ``SPECIFIED`` (including any ``CONFLICTING`` group).
Each group is evaluated independently (Property 24). A ``DELEGATED`` group is
treated as a preference input and synthesizes **no** physical condition absent
from the source (Property 25).

Pure, deterministic primitives only — the recommendation *decision* is Spec 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from series76_domain.model.enums import CoverageStatus, RequirementGroup

_ALL_GROUPS = (
    RequirementGroup.ENVIRONMENT_ENCLOSURE,
    RequirementGroup.POWER_SUPPLY,
    RequirementGroup.SERVICE_TYPE,
    RequirementGroup.REQUIRED_TORQUE,
)


@dataclass(frozen=True, slots=True)
class GroupInput:
    """The resolved coverage input for one requirement group.

    Attributes:
        group: the requirement group.
        status: its resolved :class:`CoverageStatus`.
        has_catalog_match: whether a non-empty catalog-backed match exists for
            this group under the pinned edition. Only meaningful when
            ``status`` is ``SPECIFIED``.
    """

    group: RequirementGroup
    status: CoverageStatus
    has_catalog_match: bool = False


@dataclass(frozen=True, slots=True)
class GroupCoverage:
    """The evaluated coverage of one group (exactly one status)."""

    group: RequirementGroup
    status: CoverageStatus


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    """The completeness classification over the four groups.

    Attributes:
        per_group: one :class:`GroupCoverage` per requirement group.
        classification: ``"verified"`` iff all four groups are ``SPECIFIED``
            with a catalog-backed match, else ``"preliminary"``.
        unmet_groups: the groups that are not satisfied (empty iff verified).
        synthesized_conditions: always empty — the evaluator never synthesizes
            a physical condition (Property 25).
    """

    per_group: tuple[GroupCoverage, ...]
    classification: str
    unmet_groups: tuple[RequirementGroup, ...]
    synthesized_conditions: tuple[object, ...] = ()

    @property
    def is_verified(self) -> bool:
        """True iff the classification is ``verified``."""
        return self.classification == "verified"


def evaluate_completeness(inputs: tuple[GroupInput, ...]) -> CompletenessResult:
    """Evaluate completeness over the four requirement groups.

    Args:
        inputs: a :class:`GroupInput` for each group. A group missing from
            ``inputs`` is treated as ``UNSPECIFIED``.

    Returns:
        A :class:`CompletenessResult` with exactly one status per group.
    """

    by_group = {gi.group: gi for gi in inputs}
    per_group: list[GroupCoverage] = []
    unmet: list[RequirementGroup] = []

    for group in _ALL_GROUPS:
        gi = by_group.get(group)
        status = gi.status if gi is not None else CoverageStatus.UNSPECIFIED
        per_group.append(GroupCoverage(group=group, status=status))

        satisfied = (
            status is CoverageStatus.SPECIFIED
            and gi is not None
            and gi.has_catalog_match
        )
        if not satisfied:
            unmet.append(group)

    classification = "verified" if not unmet else "preliminary"
    return CompletenessResult(
        per_group=tuple(per_group),
        classification=classification,
        unmet_groups=tuple(unmet),
        synthesized_conditions=(),
    )
