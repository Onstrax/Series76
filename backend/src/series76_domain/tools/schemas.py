"""Model-visible typed input schemas for the tools (Task 12.1, 12.2).

These Pydantic models are the **only** model-visible surface. They deliberately
**omit** the server-injected inputs (``edition_id``, permissions, limits,
``trace_id``): a model cannot set them here, so there is nothing to override
(Property 27). Every input is validated against its schema **before** any
catalog query (Property 27); a non-conforming input is rejected with a typed
validation failure and no query runs.

A ``filter_ast`` arrives as a typed JSON object shaped like the
``Filter_AST`` node kinds; :func:`parse_filter_ast` turns it into the typed
:class:`~series76_domain.model.filter_ast.Node` tree. A raw-SQL string is not
representable in the schema at all.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from series76_domain.model.filter_ast import (
    AllowlistField,
    And,
    Node,
    Not,
    Operator,
    Or,
    Predicate,
)
from series76_domain.model.units import Unit


class GetPartInput(BaseModel):
    """Model-visible input for a part lookup (Set B ``get_part_details``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    part_number: str = Field(min_length=1, max_length=64)
    service: str | None = Field(default=None, max_length=64)
    frequency_hz: Decimal | None = None
    requested_fields: tuple[str, ...] | None = None


class SearchInput(BaseModel):
    """Model-visible input for a filtered search (Set B ``search_parts``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filter_ast: dict[str, Any]
    requested_fields: tuple[str, ...] | None = None
    sort_hint: str | None = Field(default=None, max_length=64)
    cursor: int | None = Field(default=None, ge=0)


class SourceNotesInput(BaseModel):
    """Model-visible input for source notes (Set B ``get_source_notes``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    part_number: str = Field(min_length=1, max_length=64)
    note_type: str | None = Field(default=None, max_length=64)


class QueryPartsInput(BaseModel):
    """Model-visible input for the Set A generic ``query_parts`` baseline.

    A discriminated ``op`` routes to the same GET / SEARCH paths as Set B.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["GET", "SEARCH"]
    # GET fields
    part_number: str | None = Field(default=None, max_length=64)
    service: str | None = Field(default=None, max_length=64)
    frequency_hz: Decimal | None = None
    # SEARCH fields
    filter_ast: dict[str, Any] | None = None
    sort_hint: str | None = Field(default=None, max_length=64)
    cursor: int | None = Field(default=None, ge=0)
    requested_fields: tuple[str, ...] | None = None

    @field_validator("op")
    @classmethod
    def _known_op(cls, value: str) -> str:
        if value not in ("GET", "SEARCH"):
            raise ValueError("op must be GET or SEARCH")
        return value


class FilterParseError(ValueError):
    """Raised when a model-supplied ``filter_ast`` cannot be typed."""


def parse_filter_ast(payload: dict[str, Any]) -> Node:
    """Parse a typed JSON ``filter_ast`` payload into a :class:`Node` tree.

    The payload is a nested object with a ``"type"`` discriminator in
    ``{"and", "or", "not", "predicate"}``. A raw-SQL string is not a
    representable node, so no SQL can enter through this surface.

    Raises:
        FilterParseError: if the payload is structurally malformed or
            references an unknown field/operator/unit. The caller maps this to
            ``INVALID_FILTER`` (never executes the search).
    """

    if not isinstance(payload, dict):
        raise FilterParseError("filter_ast must be an object")
    kind = payload.get("type")
    if kind == "and":
        return And(children=tuple(parse_filter_ast(c) for c in _children(payload)))
    if kind == "or":
        return Or(children=tuple(parse_filter_ast(c) for c in _children(payload)))
    if kind == "not":
        child = payload.get("child")
        if not isinstance(child, dict):
            raise FilterParseError("not requires a single child object")
        return Not(child=parse_filter_ast(child))
    if kind == "predicate":
        return _parse_predicate(payload)
    raise FilterParseError(f"unknown filter node type: {kind!r}")


def _children(payload: dict[str, Any]) -> list[dict[str, Any]]:
    children = payload.get("children")
    if not isinstance(children, list) or not children:
        raise FilterParseError("and/or require a non-empty children list")
    for child in children:
        if not isinstance(child, dict):
            raise FilterParseError("each child must be an object")
    return children


def _parse_predicate(payload: dict[str, Any]) -> Predicate:
    try:
        field = AllowlistField(payload["field"])
        operator = Operator(payload["operator"])
    except (KeyError, ValueError) as exc:
        raise FilterParseError(f"invalid predicate field/operator: {exc}") from exc
    unit_raw = payload.get("unit")
    unit = None
    if unit_raw is not None:
        try:
            unit = Unit(unit_raw)
        except ValueError as exc:
            raise FilterParseError(f"unknown unit: {unit_raw!r}") from exc
    if "value" not in payload:
        raise FilterParseError("predicate requires a value")
    value = _coerce_value(payload["value"])
    return Predicate(field=field, operator=operator, value=value, unit=unit)


def _coerce_value(raw: Any) -> Any:
    """Coerce a JSON scalar/list into a typed predicate value (Decimal/str/bool)."""

    if isinstance(raw, list):
        return tuple(_coerce_scalar(item) for item in raw)
    return _coerce_scalar(raw)


def _coerce_scalar(raw: Any) -> Decimal | str | bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        # Never accept float silently; require a string for decimals.
        raise FilterParseError("numeric values must be integers or decimal strings")
    if isinstance(raw, str):
        # Try Decimal first for numeric-looking strings, else keep as string.
        try:
            return Decimal(raw)
        except InvalidOperation:
            return raw
    raise FilterParseError(f"unsupported value type: {type(raw).__name__}")
