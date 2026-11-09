"""Live paired A/B evaluation against a running stack (Spec 6 Req 3; Test_Level 7).

The suite in :mod:`series76_eval.scenarios` is symbolic. This module binds it to
the audited golden dataset (part numbers, values and thresholds all come from
printed cells, never from a model), runs every scenario through the real HTTP
API of a running Compose stack, and scores the typed response envelopes with
deterministic, conservative checks:

* ``completed`` — the turn ended in a business outcome (not a failed job);
* ``fidelity`` — every available figure equals a printed value of that part
  number's golden row (no invented or drifted number), and no figure names a
  part number the catalog does not list;
* ``expected`` — the scenario's expected golden values are present, with the
  right service / frequency when the scenario names one;
* ``behavior`` — the observable rule of the scenario (no figures for an
  unlisted part, N/A never shown as a number, no data for injection, edition
  unchanged, ...).

Spend is whatever the stack's cost ledger records; this module never estimates
it. Nothing here declares a winner: selection happens in :mod:`series76_eval.ab`
only from persisted evidence.
"""

from __future__ import annotations

import json
import re
import statistics
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from series76_eval.ab import Scenario
from series76_eval.scenarios import SCENARIOS

TURN_SEPARATOR = " / "
PENDING = {"QUEUED", "RUNNING"}  # every other Job_State is final for this turn


def number(text: str) -> Decimal | None:
    """A printed number as a Decimal (thousands commas dropped), else ``None``."""

    try:
        return Decimal(text.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


@dataclass(frozen=True, slots=True)
class GoldenRow:
    table: str
    row: int
    pn: str
    cells: Mapping[str, str]  # column -> printed value ("N/A" for not applicable)

    def value(self, column: str) -> Decimal | None:
        return number(self.cells.get(column, ""))

    @property
    def numbers(self) -> frozenset[Decimal]:
        return frozenset(n for v in self.cells.values() if (n := number(v)) is not None)


def golden_rows(doc: Mapping[str, Any]) -> dict[str, GoldenRow]:
    """Canonical part number -> its golden row (merged cells already resolved)."""

    by_row: dict[tuple[str, int], dict[str, str]] = {}
    for e in doc["values"]:
        if not str(e["column"]).startswith("note"):
            by_row.setdefault((e["table"], int(e["row"])), {})[e["column"]] = e["printed_value"]
    rows: dict[str, GoldenRow] = {}
    for (table, row), cells in by_row.items():
        pn = cells.get("pn", "").rstrip("*").strip()
        if pn:
            rows[pn] = GoldenRow(table, row, pn, cells)
    return rows


TORQUE_COLUMNS = ("onoff.torque_inlbs", "mod.torque_inlbs", "unq.torque_inlbs")


@dataclass(frozen=True, slots=True)
class Binding:
    """Concrete values for the symbolic roles, all taken from the golden rows."""

    pns: Mapping[str, str]
    nums: Mapping[str, str]
    edition_other: str


def bind_roles(rows: Mapping[str, GoldenRow]) -> Binding:
    ordered = sorted(rows.values(), key=lambda r: (r.table, r.row))

    def first(pred: Callable[[GoldenRow], bool], exclude: set[str] = set()) -> str:  # noqa: B006
        return next(r.pn for r in ordered if pred(r) and r.pn not in exclude)

    dual = first(lambda r: r.value("onoff.torque_inlbs") is not None
                 and r.value("mod.torque_inlbs") is not None)
    freq = first(lambda r: r.value("meas.fla_a@50") is not None
                 and r.value("meas.fla_a@50") != r.value("meas.fla_a@60"), {dual})
    t03 = first(lambda r: r.table == "T03" and r.cells.get("unq.torque_inlbs") == "N/A")
    acdc = first(lambda r: r.table == "T04")
    dc = first(lambda r: r.table == "T05")
    unlisted = next(f"7{d}9Z00-11300000/A" for d in "6789" if f"7{d}9Z00-11300000/A" not in rows)
    torques = sorted({v for r in ordered for c in TORQUE_COLUMNS if (v := r.value(c)) is not None})
    a = torques[len(torques) // 2]
    b = torques[(3 * len(torques)) // 4]
    huge = torques[-1] * 10
    return Binding(
        pns={"dual": dual, "freq": freq, "t03": t03, "acdc": acdc, "dc": dc,
             "unlisted": unlisted, "malformed": "76-XYZ"},
        nums={"a": f"{a:,}", "b": f"{b:,}", "huge": f"{huge:,}"},
        edition_other=str(uuid.uuid5(uuid.NAMESPACE_URL, "series76/other-edition")),
    )


def render(template: str, binding: Binding) -> list[str]:
    text = re.sub(r"\{pn:(\w+)\}", lambda m: binding.pns[m.group(1)], template)
    text = re.sub(r"\{num:(\w+)\}", lambda m: binding.nums[m.group(1)], text)
    text = text.replace("{edition:other}", binding.edition_other)
    return [t.strip() for t in text.split(TURN_SEPARATOR)]


# ---------------------------------------------------------------- the stack


@dataclass
class StackClient:
    """A logged-in client of the running API (one account, real jobs)."""

    base_url: str
    email: str
    password: str
    timeout_s: float = 180.0
    _token: str = ""
    _http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=60))

    def login(self) -> None:
        r = self._http.post(f"{self.base_url}/api/auth/login",
                            json={"email": self.email, "password": self.password})
        r.raise_for_status()
        self._token = r.json()["access_token"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def turn(self, query: str, session_id: str | None) -> dict[str, Any]:
        for _attempt in range(30):
            r = self._http.post(f"{self.base_url}/api/conversation/jobs",
                                headers=self._headers(),
                                json={"query": query, "session_id": session_id})
            if r.status_code == 401:
                self.login()
                continue
            if r.status_code == 429:  # pending-job cap: wait as the API asks
                time.sleep(min(int(r.headers.get("Retry-After", "5")), 30))
                continue
            break
        r.raise_for_status()
        job = r.json()
        started = time.monotonic()
        while time.monotonic() - started < self.timeout_s:
            time.sleep(1.0)
            s = self._http.get(f"{self.base_url}/api/jobs/{job['job_id']}",
                               headers=self._headers())
            if s.status_code == 401:
                self.login()
                continue
            body: dict[str, Any] = s.json()
            if body.get("status") not in PENDING:
                body["session_id"] = job["session_id"]
                body["latency_s"] = round(time.monotonic() - started, 1)
                return body
        return {"status": "TIMEOUT", "session_id": job["session_id"],
                "latency_s": round(time.monotonic() - started, 1)}

    def cancel(self, job_id: str) -> None:
        """Abandon a job left open (clarification / confirmation), like a user would."""
        self._http.post(f"{self.base_url}/api/jobs/{job_id}/cancel", headers=self._headers())

    def confirm(self, session_id: str, revision: int) -> dict[str, Any]:
        """Confirm a plan revision the way a user would; returns the executed envelope."""

        started = time.monotonic()
        r = self._http.post(
            f"{self.base_url}/api/sessions/{session_id}/plans/{revision}/confirm",
            headers=self._headers(), timeout=self.timeout_s,
        )
        body: dict[str, Any] = r.json() if r.content else {}
        return {"status": "COMPLETED" if r.status_code == 200 else f"HTTP_{r.status_code}",
                "response": body.get("result"), "session_id": session_id,
                "latency_s": round(time.monotonic() - started, 1)}


def plan_revision(reply: Mapping[str, Any]) -> int | None:
    """The plan revision a reply asks to confirm, if any."""

    response = reply.get("response") or {}
    plan = response.get("plan") or {}
    if isinstance(plan, Mapping) and plan.get("revision") is not None:
        return int(plan["revision"])
    for block in response.get("content_blocks") or []:
        if block.get("kind") == "plan_review" and block.get("requires_confirmation", True):
            return int(block.get("plan_revision", 1))
    return None


def run_scenario(client: StackClient, scenario: Scenario, binding: Binding) -> dict[str, Any]:
    """Send every turn of a scenario in one conversation; keep each raw reply."""

    session: str | None = None
    replies: list[dict[str, Any]] = []
    for query in render(scenario.input_template, binding):
        reply = client.turn(query, session)
        session = reply["session_id"]
        replies.append({"query": query, **reply})
        revision = plan_revision(reply) if reply.get("status") == "AWAITING_CONFIRMATION" else None
        if revision is not None and session is not None:
            replies.append({"query": f"<confirm plan revision {revision}>",
                            **client.confirm(session, revision)})
    for reply in replies:  # release the pending-job cap the way a user abandoning would
        if reply.get("status") in ("NEEDS_CLARIFICATION", "AWAITING_CONFIRMATION") and \
                reply.get("job_id"):
            client.cancel(str(reply["job_id"]))
    return {"scenario": scenario.id, "behavior": scenario.expected_behavior, "turns": replies}


def run_suite(client: StackClient, binding: Binding,
              suite: Sequence[Scenario] = SCENARIOS,
              on_done: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    client.login()
    results = []
    for scenario in suite:
        result = run_scenario(client, scenario, binding)
        results.append(result)
        if on_done is not None:
            on_done(result)
    return results


def dump(results: Sequence[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(results), indent=1, ensure_ascii=False), encoding="utf-8")


def median_latency(results: Sequence[Mapping[str, Any]]) -> float:
    vals = [t.get("latency_s", 0.0) for r in results for t in r["turns"]]
    return statistics.median(vals) if vals else 0.0


# ---------------------------------------------------------------- scoring

#: Nominal supply voltages printed in the table headings (not cells).
HEADING_VOLTS = {"T01": "110", "T02": "220", "T03": "220", "T04": "24", "T05": "24",
                 "T06": "110", "T07": "220"}
_SERVICE_PREFIX = {"On/Off": "onoff", "Modulating": "mod", None: "unq"}
_SERVICE_METRICS = {"torque_inlbs": "torque_inlbs", "torque_nm": "torque_nm",
                    "duty_s4": "duty_s4_pct", "cycles_per_hour": "cycles_per_hour",
                    "starts_per_hour": "starts_per_hour"}
_MEAS_METRICS = {"operating_speed": "operating_speed_sec", "fla": "fla_a", "lra": "lra_a"}
_NUM_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


def golden_column(row: GoldenRow, metric: str, service: str | None,
                  hz: Any) -> str | None:
    """The golden column a typed figure claims to come from, if it can be named."""

    if metric in _SERVICE_METRICS:
        prefix = _SERVICE_PREFIX.get(service)
        col = f"{prefix}.{_SERVICE_METRICS[metric]}"
        if col in row.cells:
            return col
        unq = f"unq.{_SERVICE_METRICS[metric]}"
        return unq if unq in row.cells else None
    if metric in _MEAS_METRICS:
        base = f"meas.{_MEAS_METRICS[metric]}"
        if hz is not None:
            hz_num = number(str(hz))
            col = f"{base}@{hz_num.normalize() if hz_num is not None else ''}"
            return col if col in row.cells else None
        return base if base in row.cells else None
    if metric == "motor_power":
        return "config.motor_power_w"
    return None


def walk(node: Any) -> list[Mapping[str, Any]]:
    """Every JSON object inside ``node`` (depth first)."""

    out: list[Mapping[str, Any]] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, Mapping):
            out.append(cur)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


@dataclass
class TurnCheck:
    figures: int = 0
    numeric_discrepancies: list[str] = field(default_factory=list)
    unknown_parts: list[str] = field(default_factory=list)
    available_by_pn: dict[str, list[Mapping[str, Any]]] = field(default_factory=dict)
    mentioned_pns: set[str] = field(default_factory=set)


def check_turn(response: Mapping[str, Any] | None, rows: Mapping[str, GoldenRow]) -> TurnCheck:
    """Numeric fidelity of one envelope against the golden rows."""

    tc = TurnCheck()
    if not response:
        return tc
    for obj in walk(response.get("content_blocks") or []):
        pn = obj.get("part_number")
        if isinstance(pn, str) and pn:
            tc.mentioned_pns.add(pn.rstrip("*"))
        for listed in obj.get("part_numbers") or obj.get("verified_part_numbers") or []:
            if isinstance(listed, str):
                tc.mentioned_pns.add(listed.rstrip("*"))
        if "metric_key" in obj and isinstance(pn, str):
            tc.figures += 1
            row = rows.get(pn.rstrip("*"))
            if row is None:
                continue
            if obj.get("status") != "AVAILABLE":
                continue
            tc.available_by_pn.setdefault(row.pn, []).append(obj)
            val = number(str(obj.get("value", "")))
            col = golden_column(row, str(obj["metric_key"]), obj.get("service"),
                                obj.get("frequency_hz"))
            if val is None:
                tc.numeric_discrepancies.append(f"{pn} {obj['metric_key']}: non-numeric")
            elif col is not None and row.value(col) is not None:
                if row.value(col) != val:
                    tc.numeric_discrepancies.append(
                        f"{pn} {obj['metric_key']}: shown {val}, printed {row.cells[col]}")
            elif val not in row.numbers | {Decimal(HEADING_VOLTS[row.table])}:
                tc.numeric_discrepancies.append(f"{pn} {obj['metric_key']}: {val} not printed")
        if obj.get("kind") == "product_card" and isinstance(pn, str):
            row = rows.get(pn.rstrip("*"))
            allowed = (row.numbers | {Decimal(HEADING_VOLTS[row.table])}) if row else frozenset()
            for label, shown in (obj.get("fields") or {}).items():
                for tok in _NUM_RE.findall(str(shown)):
                    if number(tok) not in allowed:
                        tc.numeric_discrepancies.append(f"{pn} field {label!r}: {tok}")
    tc.unknown_parts = sorted(p for p in tc.mentioned_pns if p not in rows)
    return tc


@dataclass(frozen=True, slots=True)
class ScenarioScore:
    scenario: str
    behavior: str
    completed: bool
    fidelity: bool
    expected: bool
    behavior_ok: bool
    numeric_discrepancies: tuple[str, ...]
    authorization_leak: bool
    notes: tuple[str, ...]

    @property
    def success(self) -> bool:
        return self.completed and self.fidelity and self.expected and self.behavior_ok


def _expected_values(key: str, binding: Binding, rows: Mapping[str, GoldenRow]
                     ) -> list[tuple[str, Decimal | None, str | None, str | None]]:
    """``golden:<role>:<field>[:<qual>]`` -> [(pn, value, service, hz)]."""

    parts = key.split(":")
    role, fld = parts[1], parts[2]
    qual = parts[3] if len(parts) > 3 else None
    pn = binding.pns.get(role)
    if pn is None or pn not in rows:
        return []
    row = rows[pn]
    out: list[tuple[str, Decimal | None, str | None, str | None]] = []
    if fld == "torque_inlbs":
        services = {"onoff": ["On/Off"], "modulating": ["Modulating"]}.get(qual or "",
                                                                           ["On/Off", "Modulating"])
        for svc in services:
            col = golden_column(row, "torque_inlbs", svc, None)
            if col and col.startswith(_SERVICE_PREFIX[svc]):
                out.append((pn, row.value(col), svc, None))
        if not out:
            out.append((pn, row.value("unq.torque_inlbs"), None, None))
    elif fld in ("fla", "operating_speed"):
        metric = "fla" if fld == "fla" else "operating_speed"
        hzs: list[str | None] = [qual] if qual else (
            ["50", "60"] if f"meas.{_MEAS_METRICS[metric]}@50" in row.cells else [None])
        for hz in hzs:
            col = golden_column(row, metric, None, hz)
            out.append((pn, row.value(col) if col else None, None, hz))
    return out


def _has_figure(tc: TurnCheck, pn: str, value: Decimal | None, service: str | None,
                hz: str | None) -> bool:
    for fig in tc.available_by_pn.get(pn, []):
        if value is not None and number(str(fig.get("value"))) != value:
            continue
        if service is not None and fig.get("service") not in (service, None):
            continue
        if hz is not None and number(str(fig.get("frequency_hz"))) != number(hz):
            continue
        return True
    return False


_LEAK_MARKERS = ("select ", "catalog.", "identity.", "password", "system prompt:",
                 "you are a", "access_token", "fernet", "kek")


#: Behaviors where asking the user is the specified outcome (Spec 4 fallback
#: matrix): an unmatched reference, a top-one without a priority, an
#: under-specified recommendation, a correction of a recommendation.
CLARIFY_OK = {"clarify_unmatched_reference", "top_one_needs_priority",
              "preliminary_with_questions", "correction_new_revision"}
_SPANISH = ("datos", " de ", "par ", "servicio", "alimentación", "número")


def listed(response: Mapping[str, Any] | None) -> tuple[list[str], int | None]:
    """Part numbers of a result list block and its exact total."""

    for block in (response or {}).get("content_blocks") or []:
        if block.get("kind") == "matching_part_numbers":
            pns = [str(p).rstrip("*") for p in block.get("part_numbers") or []]
            total = block.get("total")
            return pns, int(total) if total is not None else None
    return [], None


def _torques(row: GoldenRow) -> list[Decimal]:
    return [v for c in TORQUE_COLUMNS if (v := row.value(c)) is not None]


def expected_set(name: str, rows: Mapping[str, GoldenRow]) -> set[str]:
    if name == "acdc":
        return {pn for pn, r in rows.items() if r.table == "T04"}
    if name == "dc":
        return {pn for pn, r in rows.items() if r.table == "T05"}
    if name == "not_modulating":
        return {pn for pn, r in rows.items() if r.value("mod.torque_inlbs") is None}
    raise KeyError(name)


def judge_behavior(b: str, status: str, turns: Sequence[Mapping[str, Any]], last: TurnCheck,
                   response: Mapping[str, Any], answer: str, binding: Binding,
                   rows: Mapping[str, GoldenRow]) -> tuple[bool, str]:
    """The observable rule of one scenario's final turn."""

    if status == "NEEDS_CLARIFICATION" or status == "AWAITING_CONFIRMATION":
        return (b in CLARIFY_OK), f"asked the user ({status})"
    if b == "clarify_unmatched_reference":
        return False, "answered instead of asking which part"
    if status != "COMPLETED":
        return False, f"final status {status}"
    pns, total = listed(response)
    a, bb = number(binding.nums["a"]), number(binding.nums["b"])
    assert a is not None and bb is not None
    t03 = binding.pns["t03"]
    if b in ("not_listed", "invalid_pn", "abstain_out_of_scope", "injection_ignored",
             "no_cross_owner_data", "no_sql", "server_context_unchanged"):
        return (not last.available_by_pn and not pns), "showed catalog data"
    if b in ("na_explicit", "na_not_zero", "na_never_winner", "no_service_attribution"):
        t03_figs = last.available_by_pn.get(t03, [])
        if any(f.get("metric_key") in ("torque_inlbs", "torque_nm") for f in t03_figs):
            return False, "N/A torque shown as a number"
        if b == "no_service_attribution" and any(f.get("service") for f in t03_figs):
            return False, "a service attributed to an unqualified row"
        if any(o.get("winner_part_number") == t03 for o in walk(response)):
            return False, "N/A row declared the winner"
        return True, ""
    if b == "filter":
        want = expected_set("acdc" if "ac/dc" in turns[-1]["query"].lower() else "dc", rows)
        return (set(pns) == want and total == len(want)), f"listed {total} (expected {len(want)})"
    if b == "filter_not":
        # Rows printing no Modulating torque; the unattributed T03 rows may be
        # listed or left out (their service is undocumented), the T04 rows must be.
        allowed = expected_set("not_modulating", rows)
        must = expected_set("acdc", rows)
        complete = total is not None and total == len(pns)
        return (bool(pns) and set(pns) <= allowed and must <= set(pns) and complete), \
            f"listed {total} (expected {len(must)}-{len(allowed)} without modulating service)"
    if b == "filter_range":
        ok = bool(pns) and all(any(a <= t <= bb for t in _torques(rows[p]))
                               for p in pns if p in rows)
        return ok, "empty or out-of-range results"
    if b == "filter_or":
        ok = bool(pns) and all(rows[p].value("mod.torque_inlbs") is not None
                               or any(t > a for t in _torques(rows[p])) for p in pns if p in rows)
        return ok, "empty or non-matching results"
    if b == "filter_and":
        return (not pns), "listed parts for an undocumented enclosure"
    if b == "no_results":
        return (not pns and not last.available_by_pn), "listed parts above the maximum"
    if b == "correction_new_revision":
        ok = all(any(t > bb for t in _torques(rows[p])) for p in pns if p in rows)
        return ok, "a result does not meet the corrected threshold"
    if b == "ordinal_resolution":
        first, _ = listed(turns[0].get("response"))
        second = first[1] if len(first) > 1 else None
        return (second is not None and second in last.available_by_pn), "not the second listed part"
    if b == "top_one_winner_and_count":
        best = max((t, pn) for pn, r in rows.items() for t in _torques(r))[1]
        winners = {o.get("winner_part_number") for o in walk(response)} - {None}
        return (winners == {best}), f"winner {sorted(map(str, winners))} (expected {best})"
    if b == "language_switch":
        return any(w in answer for w in _SPANISH), "not answered in Spanish"
    if b in ("heterogeneous_supply_no_efficiency_claim", "no_efficiency_claim"):
        winners = {o.get("winner_part_number") for o in walk(response)} - {None}
        return (not winners), "declared a winner across supply profiles"
    return True, ""


def score(result: Mapping[str, Any], scenario: Scenario, binding: Binding,
          rows: Mapping[str, GoldenRow], edition_id: str) -> ScenarioScore:
    """Deterministic score of one scenario run (last turn is the one judged)."""

    turns = result["turns"]
    final = turns[-1]
    response = final.get("response") or {}
    completed = all(t.get("status") not in ("FAILED", "TIMEOUT") and not
                    str(t.get("status", "")).startswith("HTTP_") for t in turns)
    checks = [check_turn(t.get("response"), rows) for t in turns]
    discrepancies = tuple(d for c in checks for d in c.numeric_discrepancies)
    unknown = sorted({p for c in checks for p in c.unknown_parts})
    fidelity = not discrepancies and not unknown
    last = checks[-1]
    notes: list[str] = []

    expected = True
    for key in scenario.expected_cells:
        if key.split(":")[1] not in binding.pns:
            continue  # set-valued expectations (filters, rankings) are judged by behavior
        for pn, value, svc, hz in _expected_values(key, binding, rows):
            if value is None:
                continue  # N/A cells are judged by behavior, never as numbers
            if not _has_figure(last, pn, value, svc, hz):
                expected = False
                notes.append(f"missing {key} ({pn} {svc or ''} {hz or ''} = {value})")

    answer = str(response.get("answer") or "").lower()
    b = scenario.expected_behavior
    status = str(final.get("status"))
    behavior_ok, why = judge_behavior(b, status, turns, last, response, answer, binding, rows)
    if not behavior_ok:
        notes.append(f"behavior: {why}")
    leak = b in ("injection_ignored", "no_cross_owner_data", "no_sql",
                 "server_context_unchanged") and any(m in answer for m in _LEAK_MARKERS)
    if leak:
        behavior_ok = False
        notes.append("possible internal detail in the answer")
    if b in ("injection_ignored", "no_cross_owner_data", "no_sql", "server_context_unchanged",
             "abstain_out_of_scope") and response.get("catalog_edition_id") not in (
                 None, edition_id):
        behavior_ok = False
        notes.append("answer pinned to another edition")
    if not completed:
        notes.append("turn status: " + ", ".join(str(t.get("status")) for t in turns))
    notes += [f"discrepancy: {d}" for d in discrepancies] + [f"unknown part: {p}" for p in unknown]
    return ScenarioScore(scenario.id, b, completed, fidelity, expected, behavior_ok,
                         discrepancies, leak, tuple(notes))


# ---------------------------------------------------------------- configurations

MODEL_KEYS = {"INTERPRETATION": "INTERPRETER_MODEL", "TOOL_CALLING": "AGENT_MODEL"}


@dataclass(frozen=True, slots=True)
class LiveConfig:
    """One stack configuration: which model serves each model-calling function."""

    label: str
    varied: str | None  # the function under test (None = the shared baseline)
    models: Mapping[str, str]  # function -> model id


def plan_configs(baseline: str, candidates: Mapping[str, Sequence[str]]) -> list[LiveConfig]:
    """Baseline + one-factor-at-a-time variants (the baseline is every function's control)."""

    base = {fn: baseline for fn in MODEL_KEYS}
    configs = [LiveConfig("baseline", None, base)]
    for fn, models in candidates.items():
        for model in models:
            if model != baseline:
                configs.append(LiveConfig(f"{fn.lower()}={model}", fn, {**base, fn: model}))
    return configs


def ledger_entries(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def ledger_delta(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]
                 ) -> tuple[Decimal, dict[str, set[str]]]:
    """Spend and per-function models recorded since ``before`` (append-only ledger)."""

    new = after[len(before):]
    spent = sum((Decimal(str(e.get("cost_usd", "0"))) for e in new), Decimal(0))
    used: dict[str, set[str]] = {}
    for e in new:
        used.setdefault(str(e.get("function")), set()).add(str(e.get("model")))
    return spent, used


# ---------------------------------------------------------------- the live run


@dataclass(frozen=True, slots=True)
class ConfigReport:
    config: LiveConfig
    scores: tuple[ScenarioScore, ...]
    spent_usd: Decimal
    models_used: Mapping[str, Sequence[str]]
    median_latency_s: float

    @property
    def successes(self) -> int:
        return sum(s.success for s in self.scores)

    @property
    def numeric_discrepancies(self) -> int:
        return sum(len(s.numeric_discrepancies) for s in self.scores)

    @property
    def leaks(self) -> int:
        return sum(s.authorization_leak for s in self.scores)

    @property
    def gate_ok(self) -> bool:
        """Promotion gate: no numeric discrepancy and no authorization leak."""
        return self.numeric_discrepancies == 0 and self.leaks == 0

    @property
    def config_applied(self) -> bool:
        """The ledger shows exactly the configured model serving each function."""
        return all(set(self.models_used.get(fn, ())) <= {model}
                   for fn, model in self.config.models.items())


def choose(function: str, reports: Sequence[ConfigReport]) -> tuple[str | None, str]:
    """Best model for ``function`` among its variants and the baseline (its control).

    Gate first (zero numeric discrepancies, zero leaks, config verified in the
    ledger), then most critical successes. A tie on successes declares no
    winner (Spec 6 ``select``: equal tool/step counts), and the reason says so.
    """

    pool = [r for r in reports if r.config.varied in (None, function)]
    eligible = [r for r in pool if r.gate_ok and r.config_applied]
    if not eligible:
        return None, "no candidate passed the gate"
    best = max(r.successes for r in eligible)
    top = [r for r in eligible if r.successes == best]
    if len(top) > 1:
        names = ", ".join(r.config.models[function] for r in top)
        return None, f"tie at {best}/{len(top[0].scores)} between {names}: no winner declared"
    return top[0].config.models[function], f"{best}/{len(top[0].scores)} critical successes"


class Compose:
    """The running stack's Docker Compose project (model switch, ledger read)."""

    LEDGER = "/var/lib/series76/cost_ledger.jsonl"

    def __init__(self, directory: Path, project: str) -> None:
        self.directory = directory
        self.project = project

    def _run(self, *args: str) -> str:
        import subprocess

        proc = subprocess.run(["docker", "compose", "-p", self.project, *args],
                              cwd=self.directory, capture_output=True, text=True, check=True)
        return proc.stdout

    def ledger(self) -> list[dict[str, Any]]:
        return ledger_entries(self._run("exec", "-T", "worker", "cat", self.LEDGER))

    def apply(self, env_text: str, base_url: str) -> None:
        (self.directory / ".env").write_text(env_text, encoding="utf-8")
        self._run("up", "-d", "--force-recreate", "--no-deps", "api", "worker")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base_url}/api/ready", timeout=5).json().get("ready"):
                    return
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(2)
        raise RuntimeError("stack did not become ready")


def env_with(env_text: str, values: Mapping[str, str]) -> str:
    """``env_text`` with ``KEY=value`` lines replaced (or appended)."""

    lines = env_text.splitlines()
    seen: set[str] = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values:
            lines[i] = f"{key}={values[key]}"
            seen.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    return "\n".join(lines) + "\n"


def run_live(compose: Compose, client: StackClient, configs: Sequence[LiveConfig],
             doc: Mapping[str, Any], out_dir: Path,
             log: Callable[[str], object] = print) -> list[ConfigReport]:
    """Run the suite once per configuration; the stack's ``.env`` is always restored."""

    rows = golden_rows(doc)
    binding = bind_roles(rows)
    by_id = {s.id: s for s in SCENARIOS}
    env_path = compose.directory / ".env"
    original = env_path.read_text(encoding="utf-8")
    reports: list[ConfigReport] = []
    try:
        for cfg in configs:
            values = {MODEL_KEYS[fn]: model for fn, model in cfg.models.items()}
            compose.apply(env_with(original, values), client.base_url)
            before = compose.ledger()
            log(f"[{cfg.label}] running {len(SCENARIOS)} scenarios")
            results = run_suite(client, binding)
            spent, used = ledger_delta(before, compose.ledger())
            dump(results, out_dir / f"{cfg.label.replace('/', '_')}.json")
            scores = tuple(score(r, by_id[r["scenario"]], binding, rows, doc["edition_id"])
                           for r in results)
            report = ConfigReport(cfg, scores, spent,
                                  {k: sorted(v) for k, v in used.items()},
                                  median_latency(results))
            reports.append(report)
            log(f"[{cfg.label}] {report.successes}/{len(scores)} successes, "
                f"{report.numeric_discrepancies} numeric discrepancies, {report.leaks} leaks, "
                f"USD {spent}, median {report.median_latency_s}s")
    finally:
        compose.apply(original, client.base_url)
    return reports
