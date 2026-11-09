"""The verified-figure-set contract types and stable accessor (Task 14.1, 14.2).

A :class:`Figure` is the single shape Spec 4 renders for both the ``answer``
and the structured response blocks. It wraps either a documented
:class:`~series76_domain.model.metric_value.MetricValue` (direct) or a
:class:`~series76_domain.model.derived.DerivedValue` (derived), always with an
:class:`~series76_domain.model.evidence.EvidenceReference`. A figure with no
supporting value and no derivation is an explicit *no-number* state — never a
fabricated value (Property 30).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from series76_domain.model.derived import DerivedValue
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue


@dataclass(frozen=True, slots=True)
class Figure:
    """One number (or explicit absence) in the verified figure set.

    Exactly one of :attr:`direct` / :attr:`derived` is set for a present
    figure; when both are ``None`` the figure is an explicit no-number state
    carrying :attr:`status` (never a fabricated value).
    """

    key: str
    status: DataStatus
    evidence: EvidenceReference
    direct: MetricValue | None = None
    derived: DerivedValue | None = None

    def __post_init__(self) -> None:
        if self.direct is not None and self.derived is not None:
            raise ValueError("a Figure is either direct or derived, never both")

    @property
    def is_derived(self) -> bool:
        """True iff this figure is a labeled deterministic derivation."""
        return self.derived is not None

    @property
    def has_number(self) -> bool:
        """True iff a number (direct or derived) is present."""
        return self.direct is not None or self.derived is not None

    @property
    def magnitude(self) -> Decimal | None:
        """The numeric magnitude if present, else ``None`` (never fabricated)."""
        if self.direct is not None:
            return self.direct.value
        if self.derived is not None:
            return self.derived.value
        return None


@dataclass(frozen=True, slots=True)
class FigureSet:
    """The verified figure set shared by the answer and block paths."""

    figures: tuple[Figure, ...] = ()

    def by_key(self, key: str) -> Figure | None:
        """Return the figure for ``key`` (first match), or ``None``."""
        for figure in self.figures:
            if figure.key == key:
                return figure
        return None


def direct_figure(key: str, metric: MetricValue, evidence: EvidenceReference) -> Figure:
    """Wrap a documented :class:`MetricValue` as a direct :class:`Figure`."""

    return Figure(key=key, status=metric.status, evidence=evidence, direct=metric)


def derived_figure(key: str, derived: DerivedValue) -> Figure:
    """Wrap a :class:`DerivedValue` as a derived :class:`Figure`."""

    return Figure(
        key=key,
        status=DataStatus.AVAILABLE,
        evidence=derived.input_evidence[0],
        derived=derived,
    )


def no_number(key: str, status: DataStatus, evidence: EvidenceReference) -> Figure:
    """Build an explicit no-number figure (N/A / absent) — never fabricated."""

    if status is DataStatus.AVAILABLE:
        raise ValueError("a no-number figure cannot carry AVAILABLE status")
    return Figure(key=key, status=status, evidence=evidence)


def build_figure_set(figures: tuple[Figure, ...]) -> FigureSet:
    """Assemble a :class:`FigureSet` from already-resolved figures.

    The same inputs always build an equal :class:`FigureSet` (figures are
    immutable Decimal-backed values), giving the determinism of Property 31.
    """

    return FigureSet(figures=figures)
