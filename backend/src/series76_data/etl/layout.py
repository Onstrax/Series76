"""Printed layout of the seven Series 76 electric-data tables (structure only).

This module encodes *structure* read from the table headers of
``series_76_electric_data.pdf`` — table titles, enclosure headings, supply
headings and the ordered printed columns with their units. It contains **no
catalog value**: every number comes from the human-audited sheets (see
``series76_data.etl.sheets``). The structure itself is shown to the auditor in
the audit sheets and confirmed during the manual audit.

Semantic mapping decisions (listed in ``AUDIT_GUIDE.md`` for confirmation):

* In T01/T02/T06/T07 the printed column groups are "On/Off Output Torque, On/Off
  Duty Cycle, Cycles Per Hour" and "Modulating Output Torque, Modulating Duty
  Cycle, Starts Per Hour". Cycles per hour is therefore attributed to the
  ``On/Off`` service record and starts per hour to the ``Modulating`` record;
  the other field of each record is ``NOT_DOCUMENTED`` (never copied across).
* T03 prints no service attribution: it becomes one unqualified-performance
  record with cycles and starts as two separate fields.
* T04 (On/Off, 24V AC/DC) and T05 (Modulating, 24V DC) print no frequency: one
  operating condition with ``NOT_SPECIFIED`` frequency each (no Hz invented).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TableKind(str, Enum):
    """How a table's columns map to typed facts."""

    DUAL_SERVICE = "dual_service"  # On/Off + Modulating, 60/50 Hz blocks
    UNQUALIFIED = "unqualified"  # T03: no service attribution, 60/50 Hz blocks
    ONOFF_24 = "onoff_24"  # T04: On/Off only, no printed frequency
    MODULATING_24 = "modulating_24"  # T05: Modulating only, no printed frequency


@dataclass(frozen=True, slots=True)
class Column:
    """One printed data column.

    Attributes:
        key: stable sheet column name, ``<group>.<field>[@<hz>]``.
        header: the printed header path (verbatim enough to locate it).
        unit: the printed unit text of the column ("" when none is printed).
    """

    key: str
    header: str
    unit: str


@dataclass(frozen=True, slots=True)
class TableLayout:
    """Structure of one printed table."""

    code: str
    page: int
    enclosure: str
    title: str
    voltage_v: str
    phase_state: str | None
    phase_count: int | None
    supply_modes: tuple[str, ...]
    kind: TableKind
    columns: tuple[Column, ...]

    @property
    def column_keys(self) -> tuple[str, ...]:
        return tuple(c.key for c in self.columns)


def _freq_block(prefix: str = "") -> tuple[Column, ...]:
    cols: list[Column] = []
    for label, field, unit in (
        ("Operating Speed (sec)", "operating_speed_sec", "sec"),
        ("Full Load Current (FLA) [A]", "fla_a", "A"),
        ("Locked Rotor Current (LRA) [A]", "lra_a", "A"),
    ):
        for hz in ("60", "50"):
            cols.append(Column(f"{prefix}meas.{field}@{hz}", f"{label} / {hz} Hz", unit))
    return tuple(cols)


_DUAL_COLUMNS: tuple[Column, ...] = (
    Column("onoff.torque_inlbs", "On/Off Output Torque / In-Lbs.", "in-lbs"),
    Column("onoff.torque_nm", "On/Off Output Torque / Nm", "Nm"),
    Column("onoff.duty_s4_pct", "On/Off Duty Cycle / S4%", "%"),
    Column("onoff.cycles_per_hour", "Cycles Per Hour / Cycles", ""),
    Column("mod.torque_inlbs", "Modulating Output Torque / In-Lbs.", "in-lbs"),
    Column("mod.torque_nm", "Modulating Output Torque / Nm", "Nm"),
    Column("mod.duty_s4_pct", "Modulating Duty Cycle / S4%", "%"),
    Column("mod.starts_per_hour", "Starts Per Hour / Starts", ""),
    *_freq_block(),
    Column("config.motor_power_w", "Motor Power / Watts", "W"),
)

_T03_COLUMNS: tuple[Column, ...] = (
    Column("unq.torque_inlbs", "Output Torque / In-Lbs.", "in-lbs"),
    Column("unq.torque_nm", "Output Torque / Nm", "Nm"),
    Column("unq.duty_s4_pct", "Duty Cycle / S4%", "%"),
    Column("unq.cycles_per_hour", "Cycles per Hour / Cycles", ""),
    Column("unq.starts_per_hour", "Starts per Hour / Starts", ""),
    *_freq_block(),
    Column("config.motor_power_w", "Motor Power / Watts", "W"),
)


def _single_freq(group: str, rate_field: str, rate_header: str) -> tuple[Column, ...]:
    label = "On/Off" if group == "onoff" else "Modulating"
    return (
        Column(f"{group}.torque_inlbs", f"{label} Output Torque / In-Lbs.", "in-lbs"),
        Column(f"{group}.torque_nm", f"{label} Output Torque / Nm", "Nm"),
        Column(f"{group}.duty_s4_pct", f"{label} Duty Cycle / S4%", "%"),
        Column(f"{group}.{rate_field}", rate_header, ""),
        Column("meas.operating_speed_sec", "Operating Speed / Sec", "sec"),
        Column("meas.fla_a", "Full Load Current (FLA) / Amps", "A"),
        Column("meas.lra_a", "Locked Rotor Current (LRA) / Amps", "A"),
        Column("config.motor_power_w", "Motor Power / Watts", "W"),
    )


WEATHERPROOF = "Weatherproof - CSA, CE, & UKCA"
EXPLOSIONPROOF = "Explosionproof - CSA"

TABLES: tuple[TableLayout, ...] = (
    TableLayout(
        "T01", 1, WEATHERPROOF, "110V - Single Phase Power", "110", "Single Phase", 1,
        ("AC",), TableKind.DUAL_SERVICE, _DUAL_COLUMNS,
    ),
    TableLayout(
        "T02", 1, WEATHERPROOF, "220V - Single Phase Power", "220", "Single Phase", 1,
        ("AC",), TableKind.DUAL_SERVICE, _DUAL_COLUMNS,
    ),
    TableLayout(
        "T03", 2, WEATHERPROOF, "220V - 3 Phase Power", "220", "3 Phase", 3,
        ("AC",), TableKind.UNQUALIFIED, _T03_COLUMNS,
    ),
    TableLayout(
        "T04", 3, EXPLOSIONPROOF, "24V AC/DC Power - On/Off", "24", None, None,
        ("AC", "DC"), TableKind.ONOFF_24,
        _single_freq("onoff", "cycles_per_hour", "Cycles per Hour / Cycles"),
    ),
    TableLayout(
        "T05", 3, EXPLOSIONPROOF, "24V DC Power - Modulating", "24", None, None,
        ("DC",), TableKind.MODULATING_24,
        _single_freq("mod", "starts_per_hour", "Starts per Hour / Starts"),
    ),
    TableLayout(
        "T06", 4, EXPLOSIONPROOF, "110V - Single Phase Power", "110", "Single Phase", 1,
        ("AC",), TableKind.DUAL_SERVICE, _DUAL_COLUMNS,
    ),
    TableLayout(
        "T07", 4, EXPLOSIONPROOF, "220V - Single Phase Power", "220", "Single Phase", 1,
        ("AC",), TableKind.DUAL_SERVICE, _DUAL_COLUMNS,
    ),
)

TABLES_BY_CODE: dict[str, TableLayout] = {t.code: t for t in TABLES}

# Printed service labels (verbatim from the headers).
SERVICE_LABELS: dict[str, str] = {"onoff": "On/Off", "mod": "Modulating"}

# Field name -> normalizer field code / golden unit family.
FIELD_UNITS: dict[str, str] = {
    "torque_inlbs": "in-lbs",
    "torque_nm": "Nm",
    "duty_s4_pct": "%",
    "cycles_per_hour": "",
    "starts_per_hour": "",
    "operating_speed_sec": "sec",
    "fla_a": "A",
    "lra_a": "A",
    "motor_power_w": "W",
}
