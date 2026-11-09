"""Pure, in-memory domain model of the domain-and-tools layer (Spec 2).

Re-exports the core value types, enums, evidence/derivation types, the pure
domain aggregate (:class:`Part`), and the ``Filter_AST`` node kinds so callers
import from one stable surface:

    from series76_domain.model import MetricValue, DataStatus, Part

Nothing here touches persistence or transport; every fact carries a
:class:`DataStatus` and an :class:`EvidenceReference`, and all arithmetic is
``Decimal`` (never ``float``).
"""

from __future__ import annotations

from series76_domain.model.derived import DerivedValue, DerivedValueError
from series76_domain.model.enums import (
    CoverageStatus,
    DataStatus,
    RequirementGroup,
    SemanticFailureCode,
)
from series76_domain.model.evidence import EvidenceError, EvidenceReference
from series76_domain.model.filter_ast import (
    AllowlistField,
    And,
    FieldKind,
    Node,
    Not,
    Operator,
    Or,
    Predicate,
    TypedValue,
)
from series76_domain.model.metric_value import (
    MetricValue,
    MetricValueError,
    data_status_from_availability,
)
from series76_domain.model.types import (
    Configuration,
    DomainInvariantError,
    ElectricalMeasurement,
    Note,
    OperatingCondition,
    Part,
    PartNumber,
    ServicePerformance,
    SupplyProfile,
    UnqualifiedPerformance,
)
from series76_domain.model.units import (
    CONVERSION_FACTORS,
    Dimension,
    Unit,
    parse_unit,
)

__all__ = [
    "CONVERSION_FACTORS",
    "AllowlistField",
    "And",
    "Configuration",
    "CoverageStatus",
    "DataStatus",
    "DerivedValue",
    "DerivedValueError",
    "Dimension",
    "DomainInvariantError",
    "ElectricalMeasurement",
    "EvidenceError",
    "EvidenceReference",
    "FieldKind",
    "MetricValue",
    "MetricValueError",
    "Node",
    "Not",
    "Note",
    "OperatingCondition",
    "Operator",
    "Or",
    "Part",
    "PartNumber",
    "Predicate",
    "RequirementGroup",
    "SemanticFailureCode",
    "ServicePerformance",
    "SupplyProfile",
    "TypedValue",
    "UnqualifiedPerformance",
    "Unit",
    "data_status_from_availability",
    "parse_unit",
]
