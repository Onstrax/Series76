"""The verified-figure-set contract surface consumed by Spec 4 (Task 14).

Every number this layer returns is either read directly from the published
catalog (resolving to at least one source cell) or a
:class:`~series76_domain.model.derived.DerivedValue` computed deterministically
from published values (resolving to its derivation-input cells). Each figure
carries a :class:`~series76_domain.model.enums.DataStatus` and an
:class:`~series76_domain.model.evidence.EvidenceReference`; derived figures are
labeled with their formula and fixed precision. Repeated identical queries
return equal figures — exactly for direct values, to the attached precision for
derived (Property 30, Property 31). An unsupported fact yields an explicit
no-number state, never a fabricated value; a new recommendation against a
withdrawn edition yields ``SOURCE_WITHDRAWN`` while pinned historical reads
still succeed (Property 32).
"""

from __future__ import annotations

from series76_domain.figures.contract import (
    Figure,
    FigureSet,
    build_figure_set,
    direct_figure,
    no_number,
)

__all__ = [
    "Figure",
    "FigureSet",
    "build_figure_set",
    "direct_figure",
    "no_number",
]
