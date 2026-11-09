"""``Filter_AST`` validation yielding ``INVALID_FILTER`` (Task 5.2, Req 3.8).

A :class:`~series76_domain.model.filter_ast.Node` is validated for:

* **structural well-formedness** — ``And``/``Or`` carry at least one child, no
  node is of an unknown kind (a raw-SQL node is not representable at all);
* **field membership** — every :class:`~series76_domain.model.filter_ast.Predicate`
  references a field in the :class:`~series76_domain.model.filter_ast.AllowlistField`
  set (guaranteed by the enum, re-checked defensively);
* **operator/value/unit compatibility** — the operator suits the field kind
  (ordered comparisons only on numeric fields), the value shape matches the
  operator (``IN`` takes a non-empty tuple; scalar operators take a scalar),
  and any unit shares the field's physical dimension.

An invalid AST is reported through :class:`FilterValidationResult` with the
offending predicate and a reason; it is **never executed** (Property 14). The
result carries the :class:`~series76_domain.model.enums.SemanticFailureCode`
``INVALID_FILTER`` so callers return exactly one typed failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.filter_ast import (
    AllowlistField,
    And,
    FieldKind,
    Node,
    Not,
    Operator,
    Or,
    Predicate,
)

_NUMERIC_SCALARS = (Decimal, int)
# bool is a subclass of int; keep it only for boolean fields.


@dataclass(frozen=True, slots=True)
class FilterValidationResult:
    """The outcome of validating a ``Filter_AST``.

    Attributes:
        ok: ``True`` iff the AST is structurally valid and executable.
        code: the :class:`SemanticFailureCode` when invalid (always
            ``INVALID_FILTER``), else ``None``.
        offending_predicate: the predicate that failed validation, if any.
        reason: a short, secret-free description of the failure, if any.
    """

    ok: bool
    code: SemanticFailureCode | None = None
    offending_predicate: Predicate | None = None
    reason: str | None = None

    @classmethod
    def valid(cls) -> FilterValidationResult:
        """A clean, executable result."""
        return cls(ok=True)

    @classmethod
    def invalid(
        cls, reason: str, predicate: Predicate | None = None
    ) -> FilterValidationResult:
        """A rejected result carrying ``INVALID_FILTER`` and the offender."""
        return cls(
            ok=False,
            code=SemanticFailureCode.INVALID_FILTER,
            offending_predicate=predicate,
            reason=reason,
        )


def validate_filter(node: Node) -> FilterValidationResult:
    """Validate an AST; return a :class:`FilterValidationResult`.

    Walks the tree depth-first and returns the first failure encountered. A
    valid AST returns :meth:`FilterValidationResult.valid`.
    """

    if isinstance(node, Predicate):
        return _validate_predicate(node)
    if isinstance(node, And | Or):
        if not node.children:
            kind = type(node).__name__
            return FilterValidationResult.invalid(f"{kind} must have at least one child")
        for child in node.children:
            result = validate_filter(child)
            if not result.ok:
                return result
        return FilterValidationResult.valid()
    if isinstance(node, Not):
        return validate_filter(node.child)
    # An unknown node kind is structurally invalid (no SQL node is representable).
    return FilterValidationResult.invalid(f"unknown node kind: {type(node).__name__!r}")


def _validate_predicate(predicate: Predicate) -> FilterValidationResult:
    field = predicate.field
    operator = predicate.operator
    value = predicate.value

    if not isinstance(field, AllowlistField):
        return FilterValidationResult.invalid("field is not in the allowlist", predicate)

    # Ordered comparisons apply to numeric fields only.
    if operator.is_ordered and field.kind is not FieldKind.NUMERIC:
        return FilterValidationResult.invalid(
            f"operator {operator.value} is only valid on a numeric field", predicate
        )

    # Value-shape checks per operator.
    if operator is Operator.IN:
        if not isinstance(value, tuple) or len(value) == 0:
            return FilterValidationResult.invalid(
                "IN requires a non-empty tuple of candidates", predicate
            )
        for item in value:
            member = _validate_scalar_for_field(field, item)
            if member is not None:
                return FilterValidationResult.invalid(member, predicate)
    else:
        if isinstance(value, tuple):
            return FilterValidationResult.invalid(
                f"operator {operator.value} requires a scalar value, got a tuple",
                predicate,
            )
        member = _validate_scalar_for_field(field, value)
        if member is not None:
            return FilterValidationResult.invalid(member, predicate)

    # Unit compatibility: a unit may only accompany a numeric field and must
    # share that field's physical dimension.
    if predicate.unit is not None:
        if field.kind is not FieldKind.NUMERIC or field.dimension is None:
            return FilterValidationResult.invalid(
                f"field {field.value} does not accept a unit", predicate
            )
        if predicate.unit.dimension is not field.dimension:
            return FilterValidationResult.invalid(
                f"unit {predicate.unit.value} is incompatible with field {field.value}",
                predicate,
            )

    return FilterValidationResult.valid()


def _validate_scalar_for_field(field: AllowlistField, value: object) -> str | None:
    """Return an error string if ``value`` is wrong for ``field``, else ``None``."""

    kind = field.kind
    if kind is FieldKind.NUMERIC:
        # bool is an int subclass but is not a numeric magnitude here.
        if isinstance(value, bool) or not isinstance(value, _NUMERIC_SCALARS):
            return f"field {field.value} requires a numeric value"
        return None
    if kind is FieldKind.BOOLEAN:
        if not isinstance(value, bool):
            return f"field {field.value} requires a boolean value"
        return None
    # STRING / ENUM both carry string labels.
    if not isinstance(value, str):
        return f"field {field.value} requires a string value"
    return None
