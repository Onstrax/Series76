"""AST validation example tests (Task 5.3, Req 3.8).

Structurally invalid, out-of-allowlist, and unit/operator-incompatible ASTs
reject with ``INVALID_FILTER`` and the offending predicate; a valid AST
validates clean. The reference boolean evaluator oracle used by the search
properties lives in ``test_prop_search_semantics``.
"""

from __future__ import annotations

from decimal import Decimal

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.filter_ast import (
    AllowlistField,
    And,
    Not,
    Operator,
    Or,
    Predicate,
)
from series76_domain.model.filter_validation import validate_filter
from series76_domain.model.units import Unit


def test_valid_nested_ast_validates_clean() -> None:
    node = And(
        children=(
            Predicate(AllowlistField.TORQUE_INLBS, Operator.GE, Decimal(10)),
            Or(
                children=(
                    Predicate(AllowlistField.ENCLOSURE, Operator.EQ, "NEMA 4"),
                    Not(Predicate(AllowlistField.SERVICE, Operator.EQ, "On/Off")),
                )
            ),
        )
    )
    result = validate_filter(node)
    assert result.ok
    assert result.code is None


def test_ordered_operator_on_string_field_is_invalid() -> None:
    node = Predicate(AllowlistField.ENCLOSURE, Operator.LT, "NEMA 4")
    result = validate_filter(node)
    assert not result.ok
    assert result.code is SemanticFailureCode.INVALID_FILTER
    assert result.offending_predicate is node


def test_incompatible_unit_is_invalid() -> None:
    # Torque field with an Ampere unit (wrong dimension) -> INVALID_FILTER.
    node = Predicate(
        AllowlistField.TORQUE_NM, Operator.LE, Decimal(5), unit=Unit.AMPERE
    )
    result = validate_filter(node)
    assert not result.ok
    assert result.code is SemanticFailureCode.INVALID_FILTER


def test_unit_on_non_numeric_field_is_invalid() -> None:
    node = Predicate(AllowlistField.ENCLOSURE, Operator.EQ, "NEMA 4", unit=Unit.NM)
    result = validate_filter(node)
    assert not result.ok


def test_empty_and_is_invalid() -> None:
    result = validate_filter(And(children=()))
    assert not result.ok
    assert result.code is SemanticFailureCode.INVALID_FILTER


def test_in_requires_non_empty_tuple() -> None:
    node = Predicate(AllowlistField.SERVICE, Operator.IN, ())
    result = validate_filter(node)
    assert not result.ok


def test_scalar_operator_rejects_tuple_value() -> None:
    node = Predicate(AllowlistField.TORQUE_NM, Operator.EQ, (Decimal(1), Decimal(2)))
    result = validate_filter(node)
    assert not result.ok


def test_numeric_field_rejects_string_value() -> None:
    node = Predicate(AllowlistField.TORQUE_NM, Operator.EQ, "not-a-number")
    result = validate_filter(node)
    assert not result.ok
