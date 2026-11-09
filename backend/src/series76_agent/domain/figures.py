"""The turn's ``Verified_Figure_Set`` — Spec 2 figures bound to their context.

Every figure here wraps a Spec 2 :class:`~series76_domain.figures.contract.Figure`
(a documented ``MetricValue``, a labeled ``DerivedValue``, or an explicit
no-number state) and is bound to the exact part, service, frequency, and supply
context it was documented under. Both ``answer`` and ``content_blocks`` are
rendered from **one** instance of this set (Req 8.1), so the figures they show
are equal digit-for-digit (Req 12.5).

Figures enter this set **only** from typed Spec 2 operation results returned
by allow-listed tools (:meth:`VerifiedFigureSet.add_part_view`) or from the
Spec 2 ``convert_units`` derivation (:meth:`VerifiedFigureSet.add_derived`).
There is no API that accepts a free number.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from series76_domain.figures.contract import (
    Figure,
    derived_figure,
    direct_figure,
    no_number,
)
from series76_domain.model.derived import DerivedValue
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.types import Configuration, OperatingCondition
from series76_domain.operations.results import PartView


class UnboundFigureError(KeyError):
    """A placeholder referenced a figure that is not in the verified set."""


#: Metric keys produced from Spec 2 facts (and their unit dimension family).
METRIC_KEYS: tuple[str, ...] = (
    "torque_inlbs",
    "torque_nm",
    "duty_s4",
    "cycles_per_hour",
    "starts_per_hour",
    "operating_speed",
    "fla",
    "lra",
    "motor_power",
    "nominal_voltage",
)


def format_decimal(value: Decimal) -> str:
    """Render a Decimal at its stored precision, never in exponent notation."""
    return format(value, "f")


def default_evidence_resolver(evidence: EvidenceReference) -> bool:
    """True iff the reference names at least one real (positive-id) cell/row.

    Published ``cell_id`` / ``row_id`` values are positive identities; a
    placeholder id (``0`` or negative) does not resolve to a source cell.
    """

    return any(c > 0 for c in evidence.cell_refs) or any(r > 0 for r in evidence.row_refs)


@dataclass(frozen=True, slots=True)
class BoundFigure:
    """A Spec 2 figure bound to the context it was documented under."""

    figure_id: str
    part_number: str
    metric_key: str
    figure: Figure
    service: str | None = None
    frequency_hz: Decimal | None = None
    supply: str | None = None
    configuration_id: int | None = None
    unqualified: bool = False
    source_figure_id: str | None = None
    documented_unit: str | None = None

    @property
    def unit(self) -> str | None:
        """The unit label of the figure (direct, derived, or the absent unit).

        An N/A / absent figure keeps the unit of its documented field so it
        stays in the same comparison context (it is excluded from comparison
        by its status, never by a mismatched context).
        """
        if self.figure.derived is not None:
            return self.figure.derived.unit.value
        if self.figure.direct is not None and self.figure.direct.unit is not None:
            return self.figure.direct.unit.value
        return self.documented_unit

    @property
    def status(self) -> DataStatus:
        """The figure's Data_Status."""
        return self.figure.status

    @property
    def value_text(self) -> str | None:
        """The canonical magnitude string, or ``None`` for a no-number figure."""
        magnitude = self.figure.magnitude
        return None if magnitude is None else format_decimal(magnitude)

    @property
    def context_key(self) -> tuple[str, str | None, str | None, Decimal | None, str | None]:
        """(metric, unit, service, frequency, supply) — the comparability key."""
        return (self.metric_key, self.unit, self.service, self.frequency_hz, self.supply)


@dataclass
class VerifiedFigureSet:
    """All facts the turn may present, keyed by stable figure id.

    Figure ids are deterministic functions of (part, metric, context, source
    configuration/measurement), so repeated identical queries produce equal
    sets (Req 12.5).
    """

    edition_id: uuid.UUID
    figures: dict[str, BoundFigure] = field(default_factory=dict)
    listed_parts: list[str] = field(default_factory=list)
    services: dict[str, set[str]] = field(default_factory=dict)
    enclosures: dict[str, set[str]] = field(default_factory=dict)
    frequencies: dict[str, set[Decimal]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    searched: bool = False

    # --- intake (typed Spec 2 results only) --------------------------------

    def add_part_view(self, view: PartView) -> list[BoundFigure]:
        """Bind every documented fact of a found part (with its context)."""

        pn = view.part.part_number.canonical_pn
        if view.part.edition_id != self.edition_id:
            raise ValueError("a part view from another edition cannot enter this set")
        if pn not in self.listed_parts:
            self.listed_parts.append(pn)
        added: list[BoundFigure] = []
        configs = {c.configuration_id: c for c in view.configurations}
        supply_by_config = {cid: _supply_label(c) for cid, c in configs.items()}

        for cfg in view.configurations:
            if cfg.enclosure:
                self.enclosures.setdefault(pn, set()).add(cfg.enclosure)
            added.append(
                self._bind(
                    pn,
                    "motor_power",
                    cfg.motor_power,
                    cfg.evidence,
                    supply=supply_by_config.get(cfg.configuration_id),
                    configuration_id=cfg.configuration_id,
                    discriminator=f"cfg{cfg.configuration_id}",
                )
            )
            if cfg.supply_profile is not None:
                added.append(
                    self._bind(
                        pn,
                        "nominal_voltage",
                        cfg.supply_profile.voltage_v,
                        cfg.evidence,
                        supply=supply_by_config.get(cfg.configuration_id),
                        configuration_id=cfg.configuration_id,
                        discriminator=f"cfg{cfg.configuration_id}",
                    )
                )

        for sp in view.service_performance:
            self.services.setdefault(pn, set()).add(sp.service_type)
            for key, metric in (
                ("torque_inlbs", sp.torque_inlbs),
                ("torque_nm", sp.torque_nm),
                ("duty_s4", sp.duty_s4),
                ("cycles_per_hour", sp.cycles_per_hour),
                ("starts_per_hour", sp.starts_per_hour),
            ):
                added.append(
                    self._bind(
                        pn,
                        key,
                        metric,
                        sp.evidence,
                        service=sp.service_type,
                        supply=supply_by_config.get(sp.configuration_id),
                        configuration_id=sp.configuration_id,
                        discriminator=f"cfg{sp.configuration_id}",
                    )
                )

        for up in view.unqualified_performance:
            for key, metric in (
                ("torque_inlbs", up.torque_inlbs),
                ("torque_nm", up.torque_nm),
                ("duty_s4", up.duty_s4),
                ("cycles_per_hour", up.cycles_per_hour),
                ("starts_per_hour", up.starts_per_hour),
            ):
                added.append(
                    self._bind(
                        pn,
                        key,
                        metric,
                        up.evidence,
                        supply=supply_by_config.get(up.configuration_id),
                        configuration_id=up.configuration_id,
                        unqualified=True,
                        discriminator=f"cfg{up.configuration_id}:unq",
                    )
                )

        conditions: dict[int, OperatingCondition] = {
            c.condition_id: c for c in view.operating_conditions
        }
        for m in view.measurements:
            cond = conditions.get(m.condition_id)
            cfg_id = cond.configuration_id if cond is not None else None
            freq = m.frequency_hz.value if m.frequency_hz.is_available else None
            if freq is not None:
                self.frequencies.setdefault(pn, set()).add(freq)
            for key, metric in (
                ("operating_speed", m.operating_speed),
                ("fla", m.fla),
                ("lra", m.lra),
            ):
                added.append(
                    self._bind(
                        pn,
                        key,
                        metric,
                        m.evidence,
                        frequency_hz=freq,
                        supply=supply_by_config.get(cfg_id) if cfg_id is not None else None,
                        configuration_id=cfg_id,
                        discriminator=f"m{m.measurement_id}",
                    )
                )
        return added

    def add_derived(self, source: BoundFigure, derived: DerivedValue) -> BoundFigure:
        """Bind a Spec 2 ``convert_units`` derivation of a set figure."""

        if source.figure_id not in self.figures:
            raise UnboundFigureError(source.figure_id)
        key = f"{source.metric_key}->{derived.unit.value}"
        figure_id = f"{source.figure_id}=>{derived.unit.value}"
        bound = BoundFigure(
            figure_id=figure_id,
            part_number=source.part_number,
            metric_key=key,
            figure=derived_figure(key, derived),
            service=source.service,
            frequency_hz=source.frequency_hz,
            supply=source.supply,
            configuration_id=source.configuration_id,
            unqualified=source.unqualified,
            source_figure_id=source.figure_id,
        )
        self.figures[figure_id] = bound
        return bound

    def record_count(self, name: str, value: int) -> None:
        """Record an integer count produced by a Spec 2 operation result."""
        if value < 0:
            raise ValueError("counts are non-negative")
        self.counts[name] = value

    def _bind(
        self,
        pn: str,
        key: str,
        metric: MetricValue,
        evidence: EvidenceReference,
        *,
        discriminator: str,
        service: str | None = None,
        frequency_hz: Decimal | None = None,
        supply: str | None = None,
        configuration_id: int | None = None,
        unqualified: bool = False,
    ) -> BoundFigure:
        figure = (
            direct_figure(key, metric, evidence)
            if metric.is_available
            else no_number(key, metric.status, evidence)
        )
        figure_id = "|".join(
            (
                pn,
                key,
                service or "-",
                format_decimal(frequency_hz) if frequency_hz is not None else "-",
                discriminator,
            )
        )
        bound = BoundFigure(
            figure_id=figure_id,
            part_number=pn,
            metric_key=key,
            figure=figure,
            service=service,
            frequency_hz=frequency_hz,
            supply=supply,
            configuration_id=configuration_id,
            unqualified=unqualified,
            documented_unit=metric.unit.value if metric.unit is not None else None,
        )
        self.figures[figure_id] = bound
        return bound

    # --- lookups -------------------------------------------------------------

    def get(self, figure_id: str) -> BoundFigure:
        """Return a bound figure or raise :class:`UnboundFigureError`."""
        try:
            return self.figures[figure_id]
        except KeyError as exc:
            raise UnboundFigureError(figure_id) from exc

    def contains(self, figure: BoundFigure) -> bool:
        """True iff exactly this bound figure is a member of the set."""
        return self.figures.get(figure.figure_id) == figure

    def for_part(self, pn: str, metric_key: str | None = None) -> list[BoundFigure]:
        """Figures of one part (optionally one metric), in stable id order."""
        return [
            f
            for fid, f in sorted(self.figures.items())
            if f.part_number == pn and (metric_key is None or f.metric_key == metric_key)
        ]

    def select(
        self,
        pn: str,
        metric_key: str,
        *,
        service: str | None = None,
        frequency_hz: Decimal | None = None,
        supply: str | None = None,
    ) -> list[BoundFigure]:
        """Figures of a part/metric matching every *given* context filter."""

        out = []
        for f in self.for_part(pn, metric_key):
            if service is not None and not same_service(f.service, service):
                continue
            if frequency_hz is not None and f.frequency_hz != frequency_hz:
                continue
            if supply is not None and f.supply != supply:
                continue
            out.append(f)
        return out

    def presentable(
        self, figures: Iterable[BoundFigure], resolver: Callable[[EvidenceReference], bool]
    ) -> tuple[list[BoundFigure], list[BoundFigure]]:
        """Split figures into (presentable, withheld) by evidence resolvability.

        A figure is presentable only if it is a member of this set and its
        evidence resolves to a published source cell/row (Req 12.8).
        """

        shown: list[BoundFigure] = []
        withheld: list[BoundFigure] = []
        for f in figures:
            if self.contains(f) and f.figure.evidence.is_resolvable and resolver(f.figure.evidence):
                shown.append(f)
            else:
                withheld.append(f)
        return shown, withheld


def same_service(a: str | None, b: str | None) -> bool:
    """Compare printed service labels ignoring case/separators ("On/Off" ~ "on-off")."""
    if a is None or b is None:
        return a is b
    return _norm(a) == _norm(b)


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _supply_label(cfg: Configuration) -> str | None:
    """A deterministic supply-condition label built from the typed profile.

    The voltage magnitude comes from the documented ``MetricValue`` of the
    configuration (a Spec 2 fact); modes/phase are printed labels.
    """

    profile = cfg.supply_profile
    if profile is None:
        return None
    parts: list[str] = []
    if profile.voltage_v.is_available and profile.voltage_v.value is not None:
        unit = profile.voltage_v.unit.value if profile.voltage_v.unit is not None else "V"
        parts.append(f"{format_decimal(profile.voltage_v.value)} {unit}")
    if profile.modes:
        parts.append("/".join(sorted(m.value for m in profile.modes)))
    if profile.phase_state:
        parts.append(profile.phase_state)
    return " ".join(parts) if parts else None
