"""Spec 4 Properties 5-9: the bilingual Semantic_Interpreter.

The LLM is a recorded model (zero spend); what is under test is the
deterministic interpretation contract wrapped around it.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import pytest
from _agent_fakes import TEST_INTERPRETER_MODEL, RecordedInterpreter, interp, make_harness, pred
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.domain.budget import BudgetTracker, TurnBudget
from series76_agent.domain.enums import Capability, Intent, Language, Provenance, ReferentKind
from series76_agent.domain.ledger import CostLedger
from series76_agent.domain.serialization import predicates_of
from series76_agent.interpreter import (
    EditionUnavailableError,
    InterpretationOutput,
    InterpreterInput,
    SemanticInterpreter,
)
from series76_agent.models import CapabilityRegistry, ModelConfig, ModelGateway
from series76_domain.model.filter_ast import AllowlistField, And, Node, Not, Or, Predicate

EDITION = uuid.uuid4()


def _interpreter(
    out: InterpretationOutput | Any,
) -> tuple[SemanticInterpreter, RecordedInterpreter]:
    rec = RecordedInterpreter(lambda _m: out)
    config = ModelConfig(agent_model="test/a", interpreter_model=TEST_INTERPRETER_MODEL)
    registry = CapabilityRegistry(
        {
            "test/a": frozenset({Capability.TOOLS}),
            TEST_INTERPRETER_MODEL: frozenset({Capability.STRUCTURED_OUTPUT}),
        }
    )
    return SemanticInterpreter(rec, ModelGateway(config, registry, CostLedger())), rec


def _run(si: SemanticInterpreter, message: str, edition: uuid.UUID | None = EDITION):
    return asyncio.run(
        si.interpret(
            InterpreterInput(message=message, catalog_edition_id=edition),
            BudgetTracker(TurnBudget()),
        )
    )


def _numbers(node: Node | None) -> list[Decimal]:
    out: list[Decimal] = []
    for p in predicates_of(node):
        vals = p.value if isinstance(p.value, tuple) else (p.value,)
        out.extend(v for v in vals if isinstance(v, Decimal))
    return out


intents = st.one_of(st.sampled_from([i.value for i in Intent]), st.text(min_size=1, max_size=10))
numbers = st.integers(1, 999)


# Feature: agent-orchestration-response, Property 5: Interpretation yields exactly one
# intent and invents no number or rule
@given(
    intent=intents,
    confident=st.booleans(),
    stated=numbers,
    invented=numbers,
    alternatives=st.integers(1, 3),
)
def test_property_5_one_intent_no_invented_number(
    intent: str, confident: bool, stated: int, invented: int, alternatives: int
) -> None:
    message = f"parts with torque over {stated} in-lbs"
    out = interp(
        intent,
        confident=confident,
        alternative_interpretations=alternatives,
        filter_ast={
            "type": "and",
            "children": [
                pred("torque_inlbs", "GT", str(stated), "in-lbs"),
                pred("fla", "LT", str(invented)),
            ],
        },
        criteria=[
            {
                "description": f"torque {invented}",
                "group": "REQUIRED_TORQUE",
                "status": "SPECIFIED",
                "declared_value": str(invented),
            }
        ],
    )
    si, rec = _interpreter(out)
    draft, _ = _run(si, message)
    assert isinstance(draft.intent, Intent)
    if not confident or intent not in {i.value for i in Intent}:
        assert draft.intent in (Intent.FOLLOWUP, Intent.OUT_OF_SCOPE)
    else:
        assert draft.intent is Intent(intent)
    stated_numbers = {Decimal(stated)}
    assert set(_numbers(draft.filter_ast)) <= stated_numbers
    for c in draft.criteria:
        assert c.declared_value is None or Decimal(c.declared_value) in stated_numbers
    # The plan type has no catalog-figure field at all.
    assert not any(name in draft.__dataclass_fields__ for name in ("figures", "facts", "values"))
    assert len(rec.calls) == 1


def _equivalent_outputs(pn: str, n: int, unit: str, es: bool) -> InterpretationOutput:
    return interp(
        "FILTER_SEARCH",
        part_numbers=[pn],
        filter_ast=pred("torque_inlbs", "GE", str(n), unit),
        criteria=[
            {
                "description": "par mínimo" if es else "minimum torque",
                "group": "REQUIRED_TORQUE",
                "status": "SPECIFIED",
                "strength": "HARD",
                "field": "torque_inlbs",
                "declared_value": str(n),
                "declared_unit": unit,
            }
        ],
    )


# Feature: agent-orchestration-response, Property 6: Bilingual interpretation is
# equivalent with identifier identity preserved
@given(
    pn=st.from_regex(r"76-[0-9]{3}[A-Z]?", fullmatch=True),
    n=numbers,
    unit=st.sampled_from(["in-lbs", "Nm"]),
)
def test_property_6_bilingual_equivalence(pn: str, n: int, unit: str) -> None:
    es_msg = f"busca partes como {pn} con par de al menos {n} {unit}"
    en_msg = f"find parts like {pn} with torque of at least {n} {unit}"
    es_draft, _ = _run(_interpreter(_equivalent_outputs(pn, n, unit, True))[0], es_msg)
    en_draft, _ = _run(_interpreter(_equivalent_outputs(pn, n, unit, False))[0], en_msg)
    assert es_draft.intent is en_draft.intent

    def crit_key(d: Any) -> set[tuple[Any, ...]]:
        return {
            (c.group, c.status, c.strength, c.field, c.declared_value, c.declared_unit)
            for c in d.criteria
        }

    assert crit_key(es_draft) == crit_key(en_draft)
    assert [(r.kind, r.part_number, r.ordinal) for r in es_draft.referents] == [
        (r.kind, r.part_number, r.ordinal) for r in en_draft.referents
    ]
    assert es_draft.filter_ast == en_draft.filter_ast
    assert es_draft.part_numbers == en_draft.part_numbers == (pn.upper(),)
    assert es_draft.response_language is Language.ES
    assert en_draft.response_language is Language.EN


def _ast_strategy() -> st.SearchStrategy[dict[str, Any]]:
    fields = st.one_of(
        st.sampled_from([f.value for f in AllowlistField]),
        st.sampled_from(["ip_rating", "price", "DROP TABLE x", "1=1"]),
    )
    leaf = st.builds(
        lambda f, op, v: pred(f, op, v),
        fields,
        st.sampled_from(["EQ", "NE", "LT", "LE", "GT", "GE", "LIKE"]),
        st.one_of(st.sampled_from(["5", "60", "On/Off"]), st.just("'; DELETE FROM t; --")),
    )
    return st.recursive(
        leaf,
        lambda kids: st.one_of(
            st.builds(
                lambda c: {"type": "and", "children": c}, st.lists(kids, min_size=1, max_size=3)
            ),
            st.builds(
                lambda c: {"type": "or", "children": c}, st.lists(kids, min_size=1, max_size=3)
            ),
            st.builds(lambda c: {"type": "not", "child": c}, kids),
        ),
        max_leaves=6,
    )


def _only_allowed_nodes(node: Node | None) -> bool:
    if node is None:
        return True
    if isinstance(node, Predicate):
        return isinstance(node.field, AllowlistField)
    if isinstance(node, And | Or):
        return all(_only_allowed_nodes(c) for c in node.children)
    if isinstance(node, Not):
        return _only_allowed_nodes(node.child)
    return False


# Feature: agent-orchestration-response, Property 7: Logical filtering produces an
# allow-listed AST and never raw SQL
@given(ast=_ast_strategy())
def test_property_7_allow_listed_ast_never_sql(ast: dict[str, Any]) -> None:
    si, _ = _interpreter(interp("FILTER_SEARCH", filter_ast=ast))
    draft, _ = _run(si, "filter parts with 5 and 60 values, On/Off service")
    assert draft.filter_ast is None or isinstance(draft.filter_ast, Node)
    assert _only_allowed_nodes(draft.filter_ast)
    assert not isinstance(draft.filter_ast, str)


# Feature: agent-orchestration-response, Property 8: Referents and criteria are recorded
# with provenance and classification
@given(
    pns=st.lists(
        st.from_regex(r"76-[0-9]{3}", fullmatch=True), min_size=0, max_size=3, unique=True
    ),
    ordinals=st.lists(st.integers(1, 5), max_size=2),
    group=st.sampled_from(
        ["ENVIRONMENT_ENCLOSURE", "POWER_SUPPLY", "SERVICE_TYPE", "REQUIRED_TORQUE"]
    ),
    status=st.sampled_from(
        ["SPECIFIED", "NO_PREFERENCE", "UNKNOWN", "DELEGATED", "UNSPECIFIED", "CONFLICTING"]
    ),
    strength=st.sampled_from(["HARD", "PREFERENCE"]),
)
def test_property_8_provenance_and_classification(
    pns: list[str], ordinals: list[int], group: str, status: str, strength: str
) -> None:
    message = "compare " + " ".join(pns) + " and the second one"
    si, _ = _interpreter(
        interp(
            "COMPARISON",
            part_numbers=pns,
            ordinal_references=ordinals,
            criteria=[
                {"description": "criterion", "group": group, "status": status, "strength": strength}
            ],
        )
    )
    draft, _ = _run(si, message)
    pn_refs = [r for r in draft.referents if r.kind is ReferentKind.PART_NUMBER]
    ord_refs = [r for r in draft.referents if r.kind is ReferentKind.ORDINAL]
    assert [r.part_number for r in pn_refs] == [p.upper() for p in pns]
    assert all(r.provenance is Provenance.CURRENT_MESSAGE for r in pn_refs)
    assert [r.ordinal for r in ord_refs] == ordinals
    assert all(r.provenance is Provenance.PRIOR_TURN for r in ord_refs)
    (crit,) = draft.criteria
    assert (crit.group.value, crit.status.value, crit.strength.value) == (group, status, strength)


# Feature: agent-orchestration-response, Property 9: Missing session edition yields no
# plan, and unresolved items are excluded and recorded
@given(
    has_edition=st.booleans(),
    ghost_pn=st.from_regex(r"99-[0-9]{3}", fullmatch=True),
    bad_field=st.sampled_from(["ip_rating", "price", "colour"]),
)
def test_property_9_no_edition_no_plan_and_unresolved(
    has_edition: bool, ghost_pn: str, bad_field: str
) -> None:
    out = interp(
        "FILTER_SEARCH",
        part_numbers=["76-100", ghost_pn],
        filter_ast={
            "type": "and",
            "children": [pred(bad_field, "EQ", "x"), pred("service", "EQ", "On/Off")],
        },
    )
    si, rec = _interpreter(out)
    message = "look at 76-100 with On/Off service"
    if not has_edition:
        with pytest.raises(EditionUnavailableError):
            _run(si, message, edition=None)
        assert rec.calls == []  # no model call, no plan
        # Orchestrator level: nothing persisted for the conversation.
        h = make_harness({message: out}, no_edition=True)
        sid, oid = uuid.uuid4(), uuid.uuid4()
        res = h.run(sid, oid, message)
        assert res.outcome.value == "EDITION_UNAVAILABLE"
        assert h.states.saves == 0 and h.plans.created == [] and h.interp.calls == []
        return
    draft, _ = _run(si, message)
    assert ghost_pn.upper() not in draft.part_numbers
    unresolved = {(u.kind, u.text) for u in draft.unresolved}
    assert ("PART_NUMBER", ghost_pn) in unresolved
    assert ("FIELD", bad_field) in unresolved
    assert all(p.field.value != bad_field for p in predicates_of(draft.filter_ast))


def test_categorical_filter_values_are_mapped_to_documented_values() -> None:
    from series76_agent.interpreter import canonical_value
    from series76_domain.model.filter_ast import AllowlistField

    assert canonical_value(AllowlistField.SERVICE, "modulante") == "Modulating"
    assert canonical_value(AllowlistField.SERVICE, " On-Off ") == "On/Off"
    modes = canonical_value(AllowlistField.CURRENT_MODE, ["corriente continua", "AC"])
    assert modes == ["DC", "AC"]
    assert canonical_value(AllowlistField.SERVICE, "Modulating") == "Modulating"
    assert canonical_value(AllowlistField.SERVICE, "weird") == "weird"  # never invented
    assert canonical_value(AllowlistField.ENCLOSURE, "modulante") == "modulante"
