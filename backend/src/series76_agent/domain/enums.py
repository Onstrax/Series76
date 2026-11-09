"""Closed enumerations of the agent orchestration layer (Spec 4 § Data Models).

These are the agent's own vocabularies. The domain vocabularies they build on
(``DataStatus``, ``CoverageStatus``, ``RequirementGroup``,
``SemanticFailureCode``) are owned by Spec 2 and imported, never redefined.
"""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    """Exactly one intent per interpreted turn (Req 2.1)."""

    EXACT_LOOKUP = "EXACT_LOOKUP"
    FILTER_SEARCH = "FILTER_SEARCH"
    COMPARISON = "COMPARISON"
    RECOMMENDATION = "RECOMMENDATION"
    DERIVED_CALCULATION = "DERIVED_CALCULATION"
    EXPLANATION = "EXPLANATION"
    FOLLOWUP = "FOLLOWUP"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class TurnState(str, Enum):
    """The 12-value per-turn state set (Req 4.1)."""

    ACCEPTED = "ACCEPTED"
    INTERPRETING = "INTERPRETING"
    INTERPRETED = "INTERPRETED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE_PLAN = "STALE_PLAN"
    SOURCE_WITHDRAWN = "SOURCE_WITHDRAWN"


class Provenance(str, Enum):
    """Where a referent originated (Req 2.4)."""

    CURRENT_MESSAGE = "CURRENT_MESSAGE"
    PRIOR_TURN = "PRIOR_TURN"


class ReferentKind(str, Enum):
    """How a referent was expressed by the user."""

    PART_NUMBER = "PART_NUMBER"
    ORDINAL = "ORDINAL"
    ANAPHORA = "ANAPHORA"


class Strength(str, Enum):
    """Whether a criterion is a hard constraint or a preference (Req 2.5)."""

    HARD = "HARD"
    PREFERENCE = "PREFERENCE"


class CriterionLabel(str, Enum):
    """The single category each summarized criterion carries (Req 5.3)."""

    DOCUMENTED_FACT = "documented-fact"
    USER_ASSUMPTION = "user-assumption"
    PROPOSAL = "proposal"
    DELEGATION = "delegation"


class PresentationIntent(str, Enum):
    """Expected presentation format of the answer (design: presentation_intent)."""

    SIMPLE = "SIMPLE"
    LIST = "LIST"
    TOP_ONE = "TOP_ONE"
    TABLE = "TABLE"
    DUAL_COMPARISON = "DUAL_COMPARISON"
    BAR_CHART = "BAR_CHART"


class Language(str, Enum):
    """Supported response languages (Req 9.5)."""

    ES = "es"
    EN = "en"


class RecommendationGrade(str, Enum):
    """Eligibility classification of a recommendation candidate set (Req 7.1)."""

    VERIFIED = "verified"
    PRELIMINARY = "preliminary"


class OutcomeCode(str, Enum):
    """The single typed code a turn outcome carries (Req 10.6).

    Business successes (``OK``, ``NO_RESULTS``, ``N_A``) are kept distinct from
    gating outcomes (clarification/confirmation) and from technical failures.
    """

    OK = "OK"
    NO_RESULTS = "NO_RESULTS"
    N_A = "N_A"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    INVALID_PN = "INVALID_PN"
    PART_NOT_LISTED = "PART_NOT_LISTED"
    INVALID_FILTER = "INVALID_FILTER"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SOURCE_WITHDRAWN = "SOURCE_WITHDRAWN"
    STALE_PLAN = "STALE_PLAN"
    CANCELLED = "CANCELLED"
    ALREADY_EXECUTED = "ALREADY_EXECUTED"
    EDITION_UNAVAILABLE = "EDITION_UNAVAILABLE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    LIMIT_REACHED = "LIMIT_REACHED"
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_QUOTA_EXCEEDED = "PROVIDER_QUOTA_EXCEEDED"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    COST_CAP_REACHED = "COST_CAP_REACHED"

    @property
    def is_business_success(self) -> bool:
        """``NO_RESULTS`` and ``N_A`` are successes, never retried (Req 10.3)."""
        return self in (OutcomeCode.OK, OutcomeCode.NO_RESULTS, OutcomeCode.N_A)


class FallbackCondition(str, Enum):
    """The F2 §10 Fallback_Matrix rows (Req 10.2 a–n)."""

    INVALID_PN_FORMAT = "a_invalid_pn_format"
    PART_NOT_LISTED = "b_part_not_listed"
    PART_LISTED_NA = "c_part_listed_na"
    ZERO_MATCHES = "d_zero_matches"
    INCOMPLETE_RECOMMENDATION = "e_incomplete_recommendation"
    AMBIGUOUS_BOOLEAN = "f_ambiguous_boolean"
    SCOPE_WITHOUT_EVIDENCE = "g_scope_without_evidence"
    OUT_OF_SCOPE = "h_out_of_scope"
    SOURCE_WITHDRAWN = "i_source_withdrawn"
    TOOL_UNAVAILABLE = "j_tool_unavailable"
    PROVIDER_QUOTA = "k_provider_quota"
    PROMPT_INJECTION = "l_prompt_injection"
    STALE_CONFIRMATION = "m_stale_confirmation"
    DELETE_VS_LATE_JOB = "n_delete_vs_late_job"


class ModelFunction(str, Enum):
    """The configurable LLM roles (Req 11.1). Titles/ranking/numbers have none."""

    INTERPRETATION = "INTERPRETATION"
    TOOL_CALLING = "TOOL_CALLING"
    EXPLANATION = "EXPLANATION"


class Capability(str, Enum):
    """Provider-endpoint features a request may require (Req 11.3-11.5)."""

    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_outputs"
