"""JSON round-trip of plans and Filter_ASTs (for persisted domain state / plans).

The encoding of a ``Filter_AST`` is exactly the typed JSON shape the Spec 2
tool schema accepts (``{"type": "and" | "or" | "not" | "predicate", ...}``), so
a persisted plan re-enters the system only through the Spec 2 parser — there is
no path by which a raw string becomes a filter.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from series76_agent.domain.enums import (
    Intent,
    Language,
    PresentationIntent,
    Provenance,
    ReferentKind,
    Strength,
)
from series76_agent.domain.plan import Ambiguity, Criterion, DraftPlan, Referent, UnresolvedItem
from series76_domain.model.enums import CoverageStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, And, Node, Not, Or, Predicate
from series76_domain.services.rank_candidates import RankPriority, SortDirection
from series76_domain.tools.schemas import parse_filter_ast


def ast_to_json(node: Node) -> dict[str, Any]:
    """Encode a typed AST as the Spec 2 tool-schema JSON shape."""

    if isinstance(node, Predicate):
        out: dict[str, Any] = {
            "type": "predicate",
            "field": node.field.value,
            "operator": node.operator.value,
            "value": _encode_value(node.value),
        }
        if node.unit is not None:
            out["unit"] = node.unit.value
        return out
    if isinstance(node, And):
        return {"type": "and", "children": [ast_to_json(c) for c in node.children]}
    if isinstance(node, Or):
        return {"type": "or", "children": [ast_to_json(c) for c in node.children]}
    if isinstance(node, Not):
        return {"type": "not", "child": ast_to_json(node.child)}
    raise TypeError(f"unknown AST node: {type(node).__name__}")


def _encode_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_encode_scalar(v) for v in value]
    return _encode_scalar(value)


def _encode_scalar(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal | int):
        return str(value)
    return value


def predicates_of(node: Node | None) -> list[Predicate]:
    """Every predicate leaf of an AST, depth-first."""

    if node is None:
        return []
    if isinstance(node, Predicate):
        return [node]
    if isinstance(node, And | Or):
        out: list[Predicate] = []
        for child in node.children:
            out.extend(predicates_of(child))
        return out
    if isinstance(node, Not):
        return predicates_of(node.child)
    return []


def draft_to_json(draft: DraftPlan) -> dict[str, Any]:
    """Encode a :class:`DraftPlan` for encrypted persistence."""

    return {
        "intent": draft.intent.value,
        "response_language": draft.response_language.value,
        "filter_ast": ast_to_json(draft.filter_ast) if draft.filter_ast is not None else None,
        "referents": [
            {
                "text": r.text,
                "kind": r.kind.value,
                "provenance": r.provenance.value,
                "part_number": r.part_number,
                "ordinal": r.ordinal,
            }
            for r in draft.referents
        ],
        "criteria": [criterion_to_json(c) for c in draft.criteria],
        "unresolved": [
            {"kind": u.kind, "text": u.text, "reason": u.reason} for u in draft.unresolved
        ],
        "presentation_intent": draft.presentation_intent.value,
        "top_one": draft.top_one,
        "ranking_requested": draft.ranking_requested,
        "accepted_priorities": [priority_to_json(p) for p in draft.accepted_priorities],
        "proposed_priorities": [priority_to_json(p) for p in draft.proposed_priorities],
        "ambiguity": {
            "alternative_interpretations": draft.ambiguity.alternative_interpretations,
            "boolean_precedence_ambiguous": draft.ambiguity.boolean_precedence_ambiguous,
            "conflicting_statements": draft.ambiguity.conflicting_statements,
            "delegation_changes_results": draft.ambiguity.delegation_changes_results,
        },
        "service": draft.service,
        "frequency_hz": draft.frequency_hz,
        "target_unit": draft.target_unit,
        "injection_detected": draft.injection_detected,
    }


def draft_from_json(raw: dict[str, Any]) -> DraftPlan:
    """Decode a persisted :class:`DraftPlan` (AST re-parsed by Spec 2)."""

    ast_raw = raw.get("filter_ast")
    amb = raw.get("ambiguity") or {}
    return DraftPlan(
        intent=Intent(raw["intent"]),
        response_language=Language(raw["response_language"]),
        filter_ast=parse_filter_ast(ast_raw) if ast_raw else None,
        referents=tuple(
            Referent(
                text=r["text"],
                kind=ReferentKind(r["kind"]),
                provenance=Provenance(r["provenance"]),
                part_number=r.get("part_number"),
                ordinal=r.get("ordinal"),
            )
            for r in raw.get("referents", [])
        ),
        criteria=tuple(criterion_from_json(c) for c in raw.get("criteria", [])),
        unresolved=tuple(
            UnresolvedItem(kind=u["kind"], text=u["text"], reason=u["reason"])
            for u in raw.get("unresolved", [])
        ),
        presentation_intent=PresentationIntent(raw.get("presentation_intent", "SIMPLE")),
        top_one=bool(raw.get("top_one", False)),
        ranking_requested=bool(raw.get("ranking_requested", False)),
        accepted_priorities=tuple(
            priority_from_json(p) for p in raw.get("accepted_priorities", [])
        ),
        proposed_priorities=tuple(
            priority_from_json(p) for p in raw.get("proposed_priorities", [])
        ),
        ambiguity=Ambiguity(
            alternative_interpretations=int(amb.get("alternative_interpretations", 1)),
            boolean_precedence_ambiguous=bool(amb.get("boolean_precedence_ambiguous", False)),
            conflicting_statements=bool(amb.get("conflicting_statements", False)),
            delegation_changes_results=bool(amb.get("delegation_changes_results", False)),
        ),
        service=raw.get("service"),
        frequency_hz=raw.get("frequency_hz"),
        target_unit=raw.get("target_unit"),
        injection_detected=bool(raw.get("injection_detected", False)),
    )


def criterion_to_json(c: Criterion) -> dict[str, Any]:
    """Encode a :class:`Criterion`."""
    return {
        "description": c.description,
        "status": c.status.value,
        "strength": c.strength.value,
        "group": c.group.value if c.group is not None else None,
        "field": c.field.value if c.field is not None else None,
        "declared_value": c.declared_value,
        "declared_unit": c.declared_unit,
    }


def criterion_from_json(raw: dict[str, Any]) -> Criterion:
    """Decode a :class:`Criterion`."""
    return Criterion(
        description=raw["description"],
        status=CoverageStatus(raw["status"]),
        strength=Strength(raw["strength"]),
        group=RequirementGroup(raw["group"]) if raw.get("group") else None,
        field=AllowlistField(raw["field"]) if raw.get("field") else None,
        declared_value=raw.get("declared_value"),
        declared_unit=raw.get("declared_unit"),
    )


def priority_to_json(p: RankPriority) -> dict[str, str]:
    """Encode a ranking priority."""
    return {"key": p.key, "direction": p.direction.value}


def priority_from_json(raw: dict[str, Any]) -> RankPriority:
    """Decode a ranking priority."""
    return RankPriority(key=str(raw["key"]), direction=SortDirection(str(raw["direction"])))
