"""Core Spec 2 enumerations (design § Data Models → Core enums).

These are the *domain* enums of the domain-and-tools layer. They are distinct
from the Spec 1 persistence enums in :mod:`series76_data.models.enums`.

``DataStatus`` deliberately differs from Spec 1's ``AvailabilityStatus``: it
*adds* ``NOT_LISTED`` (a whole part/entity absent from the edition) and renames
``NOT_VERIFIED`` to ``UNVERIFIED``. The mapping from the Spec 1 status to this
Spec 2 status is performed at the repository boundary
(:func:`series76_domain.model.metric_value.data_status_from_availability`).
"""

from __future__ import annotations

from enum import Enum


class DataStatus(str, Enum):
    """The documented state of a single technical fact (Req 1.7).

    The five states are pairwise distinguishable by direct inspection:

    * ``AVAILABLE`` — a documented value is present (including a documented 0).
    * ``NOT_APPLICABLE`` — the source printed "N/A" for this field.
    * ``NOT_DOCUMENTED`` — the source printed no value (an absence).
    * ``NOT_LISTED`` — a whole part/entity is absent from the edition.
    * ``UNVERIFIED`` — a fact is present but not audit-confirmed.

    ``NOT_DOCUMENTED`` is never collapsed into ``NOT_APPLICABLE`` (Property 3).
    """

    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_DOCUMENTED = "NOT_DOCUMENTED"
    NOT_LISTED = "NOT_LISTED"
    UNVERIFIED = "UNVERIFIED"


class CoverageStatus(str, Enum):
    """Per-group recommendation-completeness state (Req 7.1)."""

    SPECIFIED = "SPECIFIED"
    NO_PREFERENCE = "NO_PREFERENCE"
    UNKNOWN = "UNKNOWN"
    DELEGATED = "DELEGATED"
    UNSPECIFIED = "UNSPECIFIED"
    CONFLICTING = "CONFLICTING"


class RequirementGroup(str, Enum):
    """The four physical requirement groups of a recommendation (Req 7.1)."""

    ENVIRONMENT_ENCLOSURE = "ENVIRONMENT_ENCLOSURE"
    POWER_SUPPLY = "POWER_SUPPLY"
    SERVICE_TYPE = "SERVICE_TYPE"
    REQUIRED_TORQUE = "REQUIRED_TORQUE"


class SemanticFailureCode(str, Enum):
    """Typed, non-exception business outcomes (Req 9.9).

    Every defined non-success business outcome returns exactly one of these
    codes — never a bare exception (that is reserved for repository-boundary
    guard violations). ``NO_RESULTS`` is the one code that is a *success*
    signal.
    """

    INVALID_PN = "INVALID_PN"
    PART_NOT_LISTED = "PART_NOT_LISTED"
    N_A = "N_A"
    NO_RESULTS = "NO_RESULTS"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    SOURCE_WITHDRAWN = "SOURCE_WITHDRAWN"
    INVALID_FILTER = "INVALID_FILTER"
