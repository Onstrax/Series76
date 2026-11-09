"""Stable response/error envelope DTOs (Spec 3).

The ``Error_Envelope`` shape and stable code set are defined fully here. The
``Response_Envelope`` pins the inviolable ``session_id`` + ``answer`` contract
and defines the structural ``content_blocks`` discriminated union. Population of
blocks with verified figures is owned by Spec 2/4; the structural shape and the
unknown-kind -> ``text`` fallback live here (Req 4.8, design: Response_Envelope).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from series76_api.domain.errors import ErrorCode


class ErrorDetail(BaseModel):
    """The ``error`` object: a stable ``code`` and a user-safe ``user_message``."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    user_message: str


class ErrorEnvelope(BaseModel):
    """The single stable error envelope (design: Error_Envelope).

    ``details`` is sanitized only — never SQL, prompts, secrets, stack traces,
    or PII. ``retryable`` is consistent for a given ``code``.
    """

    model_config = ConfigDict(frozen=True)

    error: ErrorDetail
    request_id: str
    retryable: bool
    details: dict[str, str] = Field(default_factory=dict)


# --- content_blocks: a structural discriminated union (design §Response) -----


class BlockKind(str, Enum):
    """The discriminator values for ``content_blocks`` entries.

    An unknown/unsupported kind degrades to :data:`TEXT` (safe fallback).
    """

    TEXT = "text"
    PRODUCT_CARD = "product_card"
    COMPARISON_TABLE = "comparison_table"
    MATCHING_PART_NUMBERS = "matching_part_numbers"
    BAR_CHART = "bar_chart"
    CLARIFICATION = "clarification"
    PLAN_REVIEW = "plan_review"


class _BlockBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1


# --- typed figure fields (populated by Spec 4 from the Spec 2 figure set) ----
#
# Every technical number a client renders is read from one of these typed
# fields — never parsed from ``answer`` prose (Spec 5 Property 1). ``value`` is
# the canonical Decimal string at the stored precision (digit-for-digit), and is
# ``None`` exactly when ``status`` is not ``AVAILABLE`` (N/A / absent are
# explicit states, never zero).


class EvidenceDTO(BaseModel):
    """The published source cells/rows/notes a figure resolves to."""

    model_config = ConfigDict(frozen=True)

    cell_refs: list[int] = Field(default_factory=list)
    row_refs: list[int] = Field(default_factory=list)
    note_refs: list[int] = Field(default_factory=list)


class FigureDTO(BaseModel):
    """One verified figure (or explicit absence) with its full context."""

    model_config = ConfigDict(frozen=True)

    figure_id: str
    metric_key: str
    label: str
    value: str | None = None
    unit: str | None = None
    status: str
    part_number: str
    service: str | None = None
    frequency_hz: str | None = None
    supply: str | None = None
    derived: bool = False
    formula: str | None = None
    precision_decimals: int | None = None
    evidence: EvidenceDTO = Field(default_factory=EvidenceDTO)


class ComparisonRowDTO(BaseModel):
    """One metric compared across parts, with comparability and context."""

    model_config = ConfigDict(frozen=True)

    metric_key: str
    label: str
    cells: list[FigureDTO] = Field(default_factory=list)
    comparable: bool = False
    warning: str | None = None
    winner_part_number: str | None = None
    supply_heterogeneous: bool = False


class BarPointDTO(BaseModel):
    """One bar of a comparable chart; an N/A/absent point carries no value."""

    model_config = ConfigDict(frozen=True)

    label: str
    figure: FigureDTO


class CriterionDTO(BaseModel):
    """One criterion of an interpretation summary with exactly one category."""

    model_config = ConfigDict(frozen=True)

    text: str
    category: Literal["documented-fact", "user-assumption", "proposal", "delegation"]


class InterpretationSummaryDTO(BaseModel):
    """The always-visible interpretation of a turn (no internals leaked)."""

    model_config = ConfigDict(frozen=True)

    intent: str
    applied: list[CriterionDTO] = Field(default_factory=list)
    proposed: list[CriterionDTO] = Field(default_factory=list)
    delegated: list[CriterionDTO] = Field(default_factory=list)
    ignored: list[CriterionDTO] = Field(default_factory=list)
    expected_presentation_format: str


class TextBlock(_BlockBase):
    """Plain conversational text. The universal safe fallback block."""

    kind: Literal[BlockKind.TEXT] = BlockKind.TEXT
    text: str = ""


class ProductCardBlock(_BlockBase):
    """A single product/part summary card. Figures are verified upstream."""

    kind: Literal[BlockKind.PRODUCT_CARD] = BlockKind.PRODUCT_CARD
    part_number: str
    fields: dict[str, str] = Field(default_factory=dict)
    figures: list[FigureDTO] = Field(default_factory=list)
    grade: str | None = None
    catalog_edition_id: str | None = None


class ComparisonTableBlock(_BlockBase):
    """A comparison table across parts/attributes (verified figures only)."""

    kind: Literal[BlockKind.COMPARISON_TABLE] = BlockKind.COMPARISON_TABLE
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    part_numbers: list[str] = Field(default_factory=list)
    metric_rows: list[ComparisonRowDTO] = Field(default_factory=list)


class MatchingPartNumbersBlock(_BlockBase):
    """Matching part numbers with a total and a (paginated) list."""

    kind: Literal[BlockKind.MATCHING_PART_NUMBERS] = BlockKind.MATCHING_PART_NUMBERS
    total: int = 0
    part_numbers: list[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = 0
    verified: list[str] = Field(default_factory=list)
    preliminary: list[str] = Field(default_factory=list)
    is_complete: bool = True
    top_one: bool = False
    winner_part_number: str | None = None


class BarChartBlock(_BlockBase):
    """A bar chart of labeled numeric series (verified figures only)."""

    kind: Literal[BlockKind.BAR_CHART] = BlockKind.BAR_CHART
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    unit: str = ""
    metric_key: str = ""
    comparable: bool = False
    points: list[BarPointDTO] = Field(default_factory=list)


class ClarificationBlock(_BlockBase):
    """A clarification prompt (carries a question, no unverified numbers)."""

    kind: Literal[BlockKind.CLARIFICATION] = BlockKind.CLARIFICATION
    question: str = ""
    options: list[str] = Field(default_factory=list)


class PlanReviewBlock(_BlockBase):
    """A plan-review block surfacing a plan revision for confirmation."""

    kind: Literal[BlockKind.PLAN_REVIEW] = BlockKind.PLAN_REVIEW
    plan_revision: int = 1
    summary: str = ""
    requires_confirmation: bool = True
    plan_id: str | None = None
    criteria: list[CriterionDTO] = Field(default_factory=list)


ContentBlock = Annotated[
    TextBlock
    | ProductCardBlock
    | ComparisonTableBlock
    | MatchingPartNumbersBlock
    | BarChartBlock
    | ClarificationBlock
    | PlanReviewBlock,
    Field(discriminator="kind"),
]

_BLOCK_ADAPTER: TypeAdapter[ContentBlock] = TypeAdapter(ContentBlock)
_KNOWN_KINDS = {k.value for k in BlockKind}


def parse_content_block(raw: dict[str, Any]) -> ContentBlock:
    """Parse one raw block dict into a typed block, degrading on unknown kind.

    An unknown/unsupported ``kind`` (or a block that fails to validate against
    its declared kind) degrades to a safe :class:`TextBlock` carrying any
    ``text`` present, so a future/garbled block never breaks the envelope
    (design: unknown kind -> text fallback).
    """

    kind = raw.get("kind")
    if kind not in _KNOWN_KINDS:
        return TextBlock(text=str(raw.get("text", "")))
    try:
        return _BLOCK_ADAPTER.validate_python(raw)
    except Exception:  # noqa: BLE001 — degrade to text, never raise on a block
        return TextBlock(text=str(raw.get("text", "")))


def parse_content_blocks(raw_blocks: list[dict[str, Any]]) -> list[ContentBlock]:
    """Parse a list of raw block dicts, applying the unknown-kind fallback."""

    return [parse_content_block(b) for b in raw_blocks]


class EnvelopeStatus(str, Enum):
    """Optional turn ``status`` for a ``Response_Envelope``.

    Mirrors the design: completion plus clarification/confirmation states.
    """

    COMPLETED = "COMPLETED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"


class PlanRef(BaseModel):
    """A plan reference carried by the envelope when a plan is in play."""

    model_config = ConfigDict(frozen=True)

    plan_id: str
    revision: int
    confirmation_needed: bool


class ResponseEnvelope(BaseModel):
    """The mandatory response envelope (design: Response_Envelope).

    The inviolable contract is a non-empty ``session_id`` and a non-empty
    ``answer``. All other fields are optional and typed. ``content_blocks`` is
    the structural discriminated union above. The envelope never carries a
    ``model`` name, tool name, prompt, or any secret.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    status: EnvelopeStatus | None = None
    interpretation_summary: InterpretationSummaryDTO | None = None
    plan: PlanRef | None = None
    warnings: list[str] = Field(default_factory=list)
    request_id: str | None = None
    catalog_edition_id: str | None = None
    turn_id: str | None = None
    message_id: str | None = None


__all__ = [
    "ErrorDetail",
    "ErrorEnvelope",
    "BlockKind",
    "EvidenceDTO",
    "FigureDTO",
    "ComparisonRowDTO",
    "BarPointDTO",
    "CriterionDTO",
    "InterpretationSummaryDTO",
    "TextBlock",
    "ProductCardBlock",
    "ComparisonTableBlock",
    "MatchingPartNumbersBlock",
    "BarChartBlock",
    "ClarificationBlock",
    "PlanReviewBlock",
    "ContentBlock",
    "parse_content_block",
    "parse_content_blocks",
    "EnvelopeStatus",
    "PlanRef",
    "ResponseEnvelope",
]
