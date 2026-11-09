"""Deterministic services over already-retrieved facts (Spec 2 § Components).

``rank_candidates``, ``compare_parts``, ``convert_units``, and the
``CompletenessEvaluator`` are **pure** functions: no database, no I/O, no
mutation of their inputs. They are the figure-producing core of the verified
figure set and are deliberately **not** exposed as LLM tools (Req 9.10).
"""

from __future__ import annotations

from series76_domain.services.compare_parts import (
    ComparableMetric,
    ComparisonPair,
    ComparisonResult,
    PartComparisonInput,
    compare_parts,
)
from series76_domain.services.completeness import (
    CompletenessResult,
    GroupCoverage,
    GroupInput,
    evaluate_completeness,
)
from series76_domain.services.convert_units import (
    ConversionError,
    ConversionResult,
    convert_units,
)
from series76_domain.services.rank_candidates import (
    RankCandidate,
    RankingResult,
    RankPriority,
    SortDirection,
    TopOneResult,
    rank_candidates,
    rank_top_one,
)

__all__ = [
    "ComparableMetric",
    "ComparisonPair",
    "ComparisonResult",
    "CompletenessResult",
    "ConversionError",
    "ConversionResult",
    "GroupCoverage",
    "GroupInput",
    "PartComparisonInput",
    "RankCandidate",
    "RankPriority",
    "RankingResult",
    "SortDirection",
    "TopOneResult",
    "compare_parts",
    "convert_units",
    "evaluate_completeness",
    "rank_candidates",
    "rank_top_one",
]
