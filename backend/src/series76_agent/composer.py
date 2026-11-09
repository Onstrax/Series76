"""The deterministic ``Response_Composer`` (Req 5.1-5.3, 8.1-8.10, 12.1-12.8).

``answer`` and every typed ``content_block`` are produced from **one**
:class:`~series76_agent.domain.figures.VerifiedFigureSet` instance:

* every technical number / part number enters the text only through a typed
  placeholder (:mod:`series76_agent.rendering`); template text cannot carry a
  digit, so no model-sourced number can reach the user;
* every block figure is a :class:`FigureDTO` built from the same bound figure
  (value string at stored precision, unit, status, context, evidence);
* N/A / absent fields keep their explicit state — never zero, never a
  zero-height bar, never a winner;
* user-supplied figures are echoed only as the user's *declared requirement*;
* heterogeneous-supply FLA is shown with its supply condition and no
  efficiency claim; derived values are labeled with formula and precision;
* a figure whose evidence does not resolve to a published source cell is
  withheld and an unavailable state is surfaced;
* claims appear only after deterministic verification.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from series76_agent.claim_verifier import ClaimVerifier
from series76_agent.domain.claims import Claim, ClaimKind, ClaimResult
from series76_agent.domain.enums import (
    CriterionLabel,
    Language,
    OutcomeCode,
    PresentationIntent,
    Strength,
)
from series76_agent.domain.figures import (
    BoundFigure,
    VerifiedFigureSet,
    default_evidence_resolver,
    format_decimal,
    same_service,
)
from series76_agent.domain.plan import DraftPlan, InterpretationSummary, SummaryItem
from series76_agent.domain.serialization import predicates_of
from series76_agent.i18n import (
    BUDGET_LIMIT_LABELS,
    CONTEXT_WORDS,
    FIELD_LABELS,
    GROUP_LABELS,
    INTENT_LABELS,
    OPERATOR_LABELS,
    PRESENTATION_LABELS,
    STATUS_LABELS,
    label,
    metric_label,
    msg,
)
from series76_agent.recommendation import RecommendationResult
from series76_agent.rendering import (
    Count,
    Fig,
    Ident,
    Lit,
    Note,
    Pn,
    RenderedText,
    RenderError,
    Segment,
    SlotResolver,
    UserEcho,
    join,
    parse_template,
    render,
)
from series76_api.api.envelopes import (
    BarChartBlock,
    BarPointDTO,
    ClarificationBlock,
    ComparisonRowDTO,
    ComparisonTableBlock,
    ContentBlock,
    CriterionDTO,
    EvidenceDTO,
    FigureDTO,
    InterpretationSummaryDTO,
    MatchingPartNumbersBlock,
    PlanReviewBlock,
    ProductCardBlock,
)
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.filter_ast import And, Node, Not, Or, Predicate
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.units import Unit
from series76_domain.operations.results import SourceNotesResult
from series76_domain.services.compare_parts import (
    ComparableMetric,
    PartComparisonInput,
    compare_parts,
)

#: Metrics shown in the answer text of a lookup (the card carries all).
_ANSWER_SERVICE_METRICS = ("torque_inlbs", "torque_nm")
_ANSWER_MEASUREMENT_METRICS = ("operating_speed", "fla")
#: Metrics charted when comparable (bars only for comparable metrics).
_CHART_METRICS = ("torque_inlbs", "torque_nm")
_CARD_ORDER = (
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


@dataclass(frozen=True, slots=True)
class PlanRefData:
    """The plan reference surfaced in the envelope."""

    plan_id: str
    revision: int
    confirmation_needed: bool


@dataclass
class ComposedResponse:
    """The composed turn output (handed to the Spec 3 seam)."""

    answer: RenderedText
    blocks: list[ContentBlock]
    status: str
    outcome: OutcomeCode
    summary: InterpretationSummary | None = None
    warnings: list[str] = field(default_factory=list)
    presented: list[BoundFigure] = field(default_factory=list)
    withheld: list[BoundFigure] = field(default_factory=list)
    plan: PlanRefData | None = None
    claims: tuple[ClaimResult, ...] = ()


@dataclass
class _Ctx:
    figset: VerifiedFigureSet
    lang: Language
    edition_label: str
    resolver: Callable[[EvidenceReference], bool]
    catalog_pns: set[str] = field(default_factory=set)
    notes: dict[str, str] = field(default_factory=dict)
    presented: dict[str, BoundFigure] = field(default_factory=dict)
    withheld: dict[str, BoundFigure] = field(default_factory=dict)

    def word(self, key: str) -> str:
        return CONTEXT_WORDS[key][self.lang]

    def edition(self) -> Ident:
        return Ident(self.edition_label)


class ResponseComposer:
    """Assembles answer + blocks from one verified figure set (zero LLM)."""

    def __init__(
        self,
        *,
        evidence_resolver: Callable[[EvidenceReference], bool] = default_evidence_resolver,
        verifier: ClaimVerifier | None = None,
    ) -> None:
        self._resolver = evidence_resolver
        self._verifier = verifier or ClaimVerifier()

    # ------------------------------------------------------------------ context

    def context(self, figset: VerifiedFigureSet, lang: Language, edition_label: str) -> _Ctx:
        """A per-turn composition context over one figure set."""
        return _Ctx(figset=figset, lang=lang, edition_label=edition_label, resolver=self._resolver)

    # ------------------------------------------------------------------ figures

    def render_figure(self, ctx: _Ctx, bf: BoundFigure, with_context: bool = True) -> str:
        """Render a bound figure: value + unit (or explicit state) + context."""

        lang = ctx.lang
        if bf.figure.has_number:
            value = bf.value_text or ""
            # "count" is the unit of cycles/starts per hour: the label already says it.
            text = f"{value} {bf.unit}" if bf.unit and bf.unit != "count" else value
        else:
            text = STATUS_LABELS[bf.status][lang]
        if bf.figure.derived is not None:
            d = bf.figure.derived
            text += (
                f" ({ctx.word('derived')}: {d.formula}; {d.precision_decimals} "
                f"{ctx.word('decimals')})"
            )
        if with_context:
            parts: list[str] = []
            if bf.unqualified:
                parts.append(ctx.word("no_service"))
            elif bf.service:
                parts.append(f"{ctx.word('service')}: {bf.service}")
            if bf.frequency_hz is not None:
                parts.append(f"{format_decimal(bf.frequency_hz)} Hz")
            if bf.supply:
                parts.append(f"{ctx.word('supply')}: {bf.supply}")
            if parts:
                text += f" ({'; '.join(parts)})"
        return text

    def _slots(self, ctx: _Ctx) -> SlotResolver:
        def figure(fid: str, with_context: bool) -> str:
            bf = ctx.figset.get(fid)
            return self.render_figure(ctx, bf, with_context)

        def part_number(pn: str) -> str:
            if pn not in ctx.figset.listed_parts and pn not in ctx.catalog_pns:
                raise RenderError("part number is not in a typed result")
            return pn

        def count(name: str) -> str:
            return str(ctx.figset.counts[name])

        def note(key: str) -> str:
            return f"“{ctx.notes[key]}”"

        return SlotResolver(figure=figure, part_number=part_number, count=count, note=note)

    def _fig(self, ctx: _Ctx, bf: BoundFigure, with_context: bool = True) -> list[Segment]:
        """A figure placeholder, or an explicit unavailable state if withheld."""

        shown, _ = ctx.figset.presentable([bf], ctx.resolver)
        if shown:
            ctx.presented[bf.figure_id] = bf
            return [Fig(bf.figure_id, with_context)]
        ctx.withheld[bf.figure_id] = bf
        unavailable = "unavailable" if ctx.lang is Language.EN else "no disponible"
        return [Lit(unavailable)]

    def figure_dto(self, ctx: _Ctx, bf: BoundFigure) -> FigureDTO | None:
        """The typed block field of a figure, or ``None`` if it must be withheld."""

        shown, _ = ctx.figset.presentable([bf], ctx.resolver)
        if not shown:
            ctx.withheld[bf.figure_id] = bf
            return None
        ctx.presented[bf.figure_id] = bf
        derived = bf.figure.derived
        ev = bf.figure.evidence
        return FigureDTO(
            figure_id=bf.figure_id,
            metric_key=bf.metric_key,
            label=metric_label(bf.metric_key, ctx.lang),
            value=bf.value_text,
            unit=bf.unit,
            status=bf.status.value,
            part_number=bf.part_number,
            service=None if bf.unqualified else bf.service,
            frequency_hz=format_decimal(bf.frequency_hz) if bf.frequency_hz is not None else None,
            supply=bf.supply,
            derived=derived is not None,
            formula=derived.formula if derived is not None else None,
            precision_decimals=derived.precision_decimals if derived is not None else None,
            evidence=EvidenceDTO(
                cell_refs=list(ev.cell_refs),
                row_refs=list(ev.row_refs),
                note_refs=list(ev.note_refs),
            ),
        )

    def product_card(self, ctx: _Ctx, pn: str, *, grade: str | None = None) -> ProductCardBlock:
        """A product card with every bound figure of ``pn`` as typed fields."""

        figures = sorted(
            ctx.figset.for_part(pn),
            key=lambda f: (
                _CARD_ORDER.index(f.metric_key.split("->")[0])
                if f.metric_key.split("->")[0] in _CARD_ORDER
                else len(_CARD_ORDER),
                f.figure_id,
            ),
        )
        dtos: list[FigureDTO] = []
        fields: dict[str, str] = {}
        for bf in figures:
            dto = self.figure_dto(ctx, bf)
            name = f"{metric_label(bf.metric_key, ctx.lang)} [{_context_tag(bf, ctx)}]"
            if dto is None:
                fields[name] = "unavailable" if ctx.lang is Language.EN else "no disponible"
                continue
            dtos.append(dto)
            fields[name] = self.render_figure(ctx, bf, with_context=False)
        return ProductCardBlock(
            part_number=pn,
            fields=fields,
            figures=dtos,
            grade=grade,
            catalog_edition_id=str(ctx.figset.edition_id),
        )

    # ------------------------------------------------------------------ summary

    def summary(self, draft: DraftPlan, lang: Language) -> InterpretationSummary:
        """The always-visible interpretation (no tool/prompt/parameter names)."""

        applied: list[SummaryItem] = []
        proposed: list[SummaryItem] = []
        delegated: list[SummaryItem] = []
        ignored: list[SummaryItem] = []
        for pn in draft.part_numbers:
            word = "part number" if lang is Language.EN else "número de parte"
            applied.append(SummaryItem(f"{word} {pn}", CriterionLabel.DOCUMENTED_FACT))
        covered_fields = set()
        for c in draft.criteria:
            text = _criterion_text(c.description, c.declared_value, c.declared_unit, lang)
            if c.field is not None:
                covered_fields.add(c.field)
            if c.status.value == "DELEGATED":
                delegated.append(SummaryItem(text, CriterionLabel.DELEGATION))
            elif c.status.value == "SPECIFIED":
                lab = (
                    CriterionLabel.USER_ASSUMPTION
                    if c.declared_value is not None or c.strength is Strength.PREFERENCE
                    else CriterionLabel.DOCUMENTED_FACT
                )
                applied.append(SummaryItem(text, lab))
            else:
                ignored.append(SummaryItem(text, CriterionLabel.USER_ASSUMPTION))
        for p in predicates_of(draft.filter_ast):
            if p.field in covered_fields:
                continue
            text = _predicate_text(p, lang)
            lab = (
                CriterionLabel.USER_ASSUMPTION
                if isinstance(p.value, Decimal | int) and not isinstance(p.value, bool)
                else CriterionLabel.DOCUMENTED_FACT
            )
            applied.append(SummaryItem(text, lab))
        for prio in draft.accepted_priorities:
            applied.append(
                SummaryItem(
                    _priority_text(prio.key, prio.direction.value, lang),
                    CriterionLabel.USER_ASSUMPTION,
                )
            )
        for prio in draft.proposed_priorities:
            if prio in draft.accepted_priorities:
                continue
            proposed.append(
                SummaryItem(
                    _priority_text(prio.key, prio.direction.value, lang), CriterionLabel.PROPOSAL
                )
            )
        for u in draft.unresolved:
            ignored.append(
                SummaryItem(_unresolved_text(u.kind, u.text, lang), CriterionLabel.USER_ASSUMPTION)
            )
        return InterpretationSummary(
            intent=INTENT_LABELS[draft.intent][lang],
            applied=tuple(applied),
            proposed=tuple(proposed),
            delegated=tuple(delegated),
            ignored=tuple(ignored),
            expected_presentation_format=PRESENTATION_LABELS[draft.presentation_intent][lang],
        )

    # ------------------------------------------------------------------ outputs

    def finish(
        self,
        ctx: _Ctx,
        segments: Sequence[Segment],
        blocks: list[ContentBlock],
        *,
        status: str,
        outcome: OutcomeCode,
        draft: DraftPlan | None,
        warnings: Iterable[str] = (),
        plan: PlanRefData | None = None,
        claims: tuple[ClaimResult, ...] = (),
    ) -> ComposedResponse:
        """Render the answer and attach the summary, warnings, and audit sets."""

        segs = list(segments)
        warn = list(warnings)
        if draft is not None and draft.injection_detected:
            segs.extend(parse_template(msg("injection_note", ctx.lang), {}))
        if ctx.withheld:
            segs.extend(parse_template(msg("withheld", ctx.lang), {}))
            warn.append("withheld_unresolved_evidence")
        answer = render(segs, self._slots(ctx))
        if not answer.text.strip():
            answer = render([Lit("—")], self._slots(ctx))
        return ComposedResponse(
            answer=answer,
            blocks=blocks,
            status=status,
            outcome=outcome,
            summary=self.summary(draft, ctx.lang) if draft is not None else None,
            warnings=warn,
            presented=list(ctx.presented.values()),
            withheld=list(ctx.withheld.values()),
            plan=plan,
            claims=claims,
        )

    # --- lookup ---------------------------------------------------------------

    def lookup(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        found: Sequence[str],
        not_listed: Sequence[str],
    ) -> ComposedResponse:
        """Exact lookup: every applicable measurement labeled (Req 5.6)."""

        segs: list[Segment] = []
        blocks: list[ContentBlock] = []
        outcome = OutcomeCode.OK
        frequency = _decimal_or_none(draft.frequency_hz)
        for pn in found:
            segs.extend(
                parse_template(
                    msg("lookup_intro", ctx.lang), {"pn": Pn(pn), "edition": ctx.edition()}
                )
            )
            lines, scope_missing, any_na, all_torque_na = self._lookup_lines(
                ctx, pn, draft.service, frequency
            )
            # One value per line: the answer is read on a phone, next to the card.
            for line in lines:
                segs.append(Lit("\n• "))
                segs.extend(line)
            if lines:
                segs.append(Lit("\n"))
            if len(lines) > 1:
                segs.extend(parse_template(msg("multi_measure", ctx.lang), {}))
            if scope_missing is not None:
                item = scope_missing
                segs.extend(
                    parse_template(
                        msg("scope_without_evidence", ctx.lang),
                        {"item": Lit(item), "pn": Pn(pn)},
                    )
                )
            if any_na:
                na_labels = self._na_labels(ctx, pn)
                if na_labels:
                    segs.extend(
                        parse_template(
                            msg("part_na", ctx.lang), {"items": Lit(", ".join(na_labels))}
                        )
                    )
            if all_torque_na:
                outcome = OutcomeCode.N_A
            segs.append(Lit("\n\n" if len(found) > 1 else " "))
            blocks.append(self.product_card(ctx, pn))
        for pn in not_listed:
            segs.extend(
                parse_template(
                    msg("not_listed", ctx.lang), {"pn": UserEcho(pn), "edition": ctx.edition()}
                )
            )
            segs.append(Lit(" "))
            if not found:
                outcome = OutcomeCode.PART_NOT_LISTED
        return self.finish(ctx, segs, blocks, status="COMPLETED", outcome=outcome, draft=draft)

    def _lookup_lines(
        self,
        ctx: _Ctx,
        pn: str,
        service: str | None,
        frequency: Decimal | None,
    ) -> tuple[list[list[Segment]], str | None, bool, bool]:
        lines: list[list[Segment]] = []
        figs = ctx.figset.for_part(pn)
        service_figs = [f for f in figs if f.metric_key in _ANSWER_SERVICE_METRICS]
        scope_missing: str | None = None
        if service is not None:
            matching = [f for f in service_figs if same_service(f.service, service)]
            if matching:
                service_figs = matching
            elif service_figs:
                scope_missing = label(FIELD_LABELS, "service", ctx.lang)
        meas_figs = [f for f in figs if f.metric_key in _ANSWER_MEASUREMENT_METRICS]
        if frequency is not None:
            matching = [f for f in meas_figs if f.frequency_hz == frequency]
            if matching:
                meas_figs = matching
            elif meas_figs:
                scope_missing = "frequency" if ctx.lang is Language.EN else "frecuencia"
        for bf in service_figs + meas_figs:
            lines.append([Lit(f"{metric_label(bf.metric_key, ctx.lang)}: "), *self._fig(ctx, bf)])
        torque = [f for f in figs if f.metric_key in _ANSWER_SERVICE_METRICS]
        any_na = any(not f.figure.has_number for f in figs)
        all_torque_na = bool(torque) and all(not f.figure.has_number for f in torque)
        return lines, scope_missing, any_na, all_torque_na

    def _state_text(self, ctx: _Ctx, bf: BoundFigure) -> str:
        """The explicit state of a no-number figure, or "unavailable" if its
        evidence does not resolve (a withheld figure never shows a status)."""

        shown, _ = ctx.figset.presentable([bf], ctx.resolver)
        if not shown:
            ctx.withheld[bf.figure_id] = bf
            return "unavailable" if ctx.lang is Language.EN else "no disponible"
        return _status_text(bf.status, ctx.lang)

    def _na_labels(self, ctx: _Ctx, pn: str) -> list[str]:
        seen: list[str] = []
        for f in ctx.figset.for_part(pn):
            if not f.figure.has_number:
                text = f"{metric_label(f.metric_key, ctx.lang)}: {self._state_text(ctx, f)}"
                if text not in seen:
                    seen.append(text)
        return seen

    # --- search -----------------------------------------------------------------

    def search(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        *,
        total: int,
        verified: Sequence[str],
        preliminary: Sequence[str],
        page: Sequence[str],
        complete: bool,
    ) -> ComposedResponse:
        """Filtered search: exact total, verified/indeterminate split, page."""

        ctx.catalog_pns.update(page, verified, preliminary)
        ctx.figset.record_count("total_matches", total)
        ctx.figset.searched = True
        constraints = self.constraints(ctx, draft.filter_ast)
        blocks: list[ContentBlock] = []
        if total == 0:
            segs = parse_template(
                msg("no_results", ctx.lang), {"edition": ctx.edition(), "constraints": constraints}
            )
            blocks.append(MatchingPartNumbersBlock(total=0, part_numbers=[], page_size=0))
            return self.finish(
                ctx, segs, blocks, status="COMPLETED", outcome=OutcomeCode.NO_RESULTS, draft=draft
            )
        ctx.figset.record_count("verified_count", len(verified))
        ctx.figset.record_count("preliminary_count", len(preliminary))
        segs = parse_template(
            msg("search_results", ctx.lang),
            {
                "count": Count("total_matches"),
                "edition": ctx.edition(),
                "constraints": constraints,
            },
        )
        if preliminary:
            segs.extend(
                parse_template(
                    msg("search_split", ctx.lang),
                    {
                        "verified": Count("verified_count"),
                        "preliminary": Count("preliminary_count"),
                    },
                )
            )
        if not complete:
            segs.extend(parse_template(msg("search_page", ctx.lang), {}))
        blocks.append(
            MatchingPartNumbersBlock(
                total=total,
                part_numbers=list(page),
                page=1,
                page_size=len(page),
                verified=list(verified),
                preliminary=list(preliminary),
                is_complete=complete,
            )
        )
        return self.finish(
            ctx, segs, blocks, status="COMPLETED", outcome=OutcomeCode.OK, draft=draft
        )

    def constraints(self, ctx: _Ctx, node: Node | None) -> list[Segment]:
        """Render an AST with explicit grouping; user values echoed as declared."""

        if node is None:
            return [Lit("—")]
        return _ast_segments(node, ctx.lang)

    # --- comparison ---------------------------------------------------------------

    def comparison(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        pns: Sequence[str],
        extra_claims: Sequence[Claim] = (),
    ) -> ComposedResponse:
        """2–3 parts side by side via Spec 2 ``compare_parts``; no winner unless
        the context is identical and the claim verifies."""

        inputs = []
        index: dict[str, BoundFigure] = {}
        for pn in pns:
            metrics = []
            for bf in ctx.figset.for_part(pn):
                key = _composite_key(bf)
                index[f"{pn}::{key}"] = bf
                direct = bf.figure.direct
                metrics.append(
                    ComparableMetric(
                        base_pn=pn,
                        metric_key=key,
                        value=direct if direct is not None else _absent_metric(bf),
                        unit=_unit_of(bf),
                        service_context=bf.service,
                        frequency_context=bf.frequency_hz,
                        supply_context=bf.supply,
                    )
                )
            inputs.append(
                PartComparisonInput(
                    base_pn=pn, edition_id=ctx.figset.edition_id, metrics=tuple(metrics)
                )
            )
        result = compare_parts(tuple(inputs))
        if not result.ok:
            arity = parse_template(msg("clarify_compare_arity", ctx.lang), {})
            return self.finish(
                ctx,
                arity,
                [ClarificationBlock(question=_plain(arity))],
                status="NEEDS_CLARIFICATION",
                outcome=OutcomeCode.NOT_COMPARABLE,
                draft=draft,
            )
        order = list(result.part_order)
        # Group pairs by composite metric key -> per-part figure + comparability.
        rows: dict[str, dict[str, object]] = {}
        for pair in result.pairs:
            row = rows.setdefault(pair.metric_key, {"comparable": True, "hetero": False})
            row[pair.left.base_pn] = index[f"{pair.left.base_pn}::{pair.metric_key}"]
            row[pair.right.base_pn] = index[f"{pair.right.base_pn}::{pair.metric_key}"]
            row["comparable"] = bool(row["comparable"]) and pair.comparable
            row["hetero"] = bool(row["hetero"]) or pair.is_supply_heterogeneous
        segs: list[Segment] = parse_template(
            msg("comparison_intro", ctx.lang),
            {
                "pns": join([[Pn(p)] for p in order], ", "),
                "edition": ctx.edition(),
            },
        )
        metric_rows: list[ComparisonRowDTO] = []
        str_rows: list[list[str]] = []
        charts: list[ContentBlock] = []
        any_fla_hetero = False
        for key in sorted(rows):
            row = rows[key]
            cells = [row.get(p) for p in order]
            figs = [c for c in cells if isinstance(c, BoundFigure)]
            if not figs:
                continue
            base_metric = key.split("@", 1)[0]
            comparable = bool(row["comparable"])
            hetero = bool(row["hetero"])
            if base_metric in ("fla", "lra") and hetero:
                any_fla_hetero = True
            dtos = [d for d in (self.figure_dto(ctx, f) for f in figs) if d is not None]
            winner = _winner(base_metric, figs) if comparable and not hetero else None
            metric_rows.append(
                ComparisonRowDTO(
                    metric_key=base_metric,
                    label=f"{metric_label(base_metric, ctx.lang)} [{_context_tag(figs[0], ctx)}]",
                    cells=dtos,
                    comparable=comparable,
                    warning=None if comparable else "context_mismatch",
                    winner_part_number=winner,
                    supply_heterogeneous=hetero,
                )
            )
            str_rows.append(
                [metric_label(base_metric, ctx.lang)]
                + [
                    self.render_figure(ctx, c, with_context=True)
                    if isinstance(c, BoundFigure)
                    else "—"
                    for c in cells
                ]
            )
            if base_metric in _ANSWER_SERVICE_METRICS + _ANSWER_MEASUREMENT_METRICS:
                line: list[Segment] = [Lit(f" {metric_label(base_metric, ctx.lang)}: ")]
                parts: list[list[Segment]] = []
                for p, c in zip(order, cells, strict=True):
                    if isinstance(c, BoundFigure):
                        parts.append([Pn(p), Lit(" "), *self._fig(ctx, c)])
                line.extend(join(parts, f" {ctx.word('vs')} "))
                line.append(Lit("."))
                if not comparable:
                    line.extend(parse_template(msg("comparison_not_comparable", ctx.lang), {}))
                segs.extend(line)
            if base_metric in _CHART_METRICS and comparable and len(figs) >= 2:
                charts.append(self._bar_chart(ctx, base_metric, order, cells))
        if any_fla_hetero:
            segs.extend(parse_template(msg("fla_heterogeneous", ctx.lang), {}))

        claims = list(extra_claims) + _comparison_claims(ctx.figset, order)
        report = self._verifier.verify_all(claims, ctx.figset)
        for res in report.visible:
            segs.extend(_claim_segments(res.claim, ctx.lang))
        if report.insufficient_information:
            segs.extend(parse_template(msg("insufficient_information", ctx.lang), {}))
        blocks: list[ContentBlock] = [
            ComparisonTableBlock(
                columns=["metric", *order],
                rows=str_rows,
                part_numbers=order,
                metric_rows=metric_rows,
            )
        ]
        if draft.presentation_intent in (
            PresentationIntent.BAR_CHART,
            PresentationIntent.TABLE,
            PresentationIntent.DUAL_COMPARISON,
        ):
            blocks.extend(charts)
        for p in order:
            blocks.append(self.product_card(ctx, p))
        outcome = (
            OutcomeCode.INSUFFICIENT_INFORMATION
            if report.insufficient_information
            else OutcomeCode.OK
        )
        return self.finish(
            ctx,
            segs,
            blocks,
            status="COMPLETED",
            outcome=outcome,
            draft=draft,
            claims=report.results,
        )

    def _bar_chart(
        self, ctx: _Ctx, metric: str, order: Sequence[str], cells: Sequence[object]
    ) -> BarChartBlock:
        points: list[BarPointDTO] = []
        labels: list[str] = []
        values: list[float] = []
        unit = ""
        for p, c in zip(order, cells, strict=True):
            if not isinstance(c, BoundFigure):
                continue
            dto = self.figure_dto(ctx, c)
            if dto is None:
                continue
            points.append(BarPointDTO(label=p, figure=dto))
            if dto.value is not None:
                # Only documented values are drawn; N/A / absent never become a bar.
                labels.append(p)
                values.append(float(Decimal(dto.value)))
                unit = dto.unit or unit
        return BarChartBlock(
            labels=labels,
            values=values,
            unit=unit,
            metric_key=metric,
            comparable=True,
            points=points,
        )

    # --- recommendation -----------------------------------------------------------

    def recommendation(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        rec: RecommendationResult,
        *,
        verified: Sequence[str],
        preliminary: Sequence[str],
        total: int,
        rank_limited: bool = False,
    ) -> ComposedResponse:
        """Verified vs preliminary, ranking only under an accepted priority."""

        lang = ctx.lang
        ctx.catalog_pns.update(verified, preliminary)
        ctx.figset.record_count("total_matches", total)
        ctx.figset.record_count("eligible_count", rec.eligible_count)
        ctx.figset.searched = True
        segs: list[Segment] = []
        if rec.grade.value == "verified":
            segs.extend(parse_template(msg("rec_verified", lang), {"edition": ctx.edition()}))
        else:
            unmet = [GROUP_LABELS[g][lang] for g in rec.unmet_groups]
            segs.extend(
                parse_template(msg("rec_preliminary", lang), {"groups": Lit(", ".join(unmet))})
            )
            if rec.delegated_groups:
                segs.extend(
                    parse_template(
                        msg("rec_delegated", lang),
                        {
                            "groups": Lit(
                                ", ".join(GROUP_LABELS[g][lang] for g in rec.delegated_groups)
                            )
                        },
                    )
                )
            questions = [g for g in rec.unmet_groups if g not in rec.delegated_groups]
            if questions:
                segs.extend(
                    parse_template(
                        msg("rec_questions", lang),
                        {"groups": Lit(", ".join(GROUP_LABELS[g][lang] for g in questions))},
                    )
                )
        blocks: list[ContentBlock] = []
        grade = rec.grade.value
        if total == 0:
            segs.extend(
                parse_template(
                    msg("no_results", lang),
                    {
                        "edition": ctx.edition(),
                        "constraints": self.constraints(ctx, draft.filter_ast),
                    },
                )
            )
            blocks.append(MatchingPartNumbersBlock(total=0))
            return self.finish(
                ctx, segs, blocks, status="COMPLETED", outcome=OutcomeCode.NO_RESULTS, draft=draft
            )
        if draft.top_one:
            if rec.winner is not None:
                segs.extend(
                    parse_template(
                        msg("top_one", lang),
                        {"pn": Pn(rec.winner), "count": Count("eligible_count")},
                    )
                )
                blocks.append(
                    MatchingPartNumbersBlock(
                        total=rec.eligible_count,
                        part_numbers=[rec.winner],
                        page_size=1,
                        is_complete=False,
                        top_one=True,
                        winner_part_number=rec.winner,
                    )
                )
                blocks.append(self.product_card(ctx, rec.winner, grade=grade))
            else:
                self._no_winner(ctx, rec, segs, rank_limited)
                blocks.append(
                    MatchingPartNumbersBlock(
                        total=rec.eligible_count, part_numbers=[], top_one=True, is_complete=False
                    )
                )
        else:
            ctx.figset.record_count("verified_count", len(verified))
            ctx.figset.record_count("preliminary_count", len(preliminary))
            segs.append(Lit(" "))
            segs.extend(
                parse_template(
                    msg("search_results", lang),
                    {
                        "count": Count("total_matches"),
                        "edition": ctx.edition(),
                        "constraints": self.constraints(ctx, draft.filter_ast),
                    },
                )
            )
            if preliminary:
                segs.extend(
                    parse_template(
                        msg("search_split", lang),
                        {
                            "verified": Count("verified_count"),
                            "preliminary": Count("preliminary_count"),
                        },
                    )
                )
            if rec.ranked and rec.winner is not None:
                segs.extend(
                    parse_template(
                        msg("ranked", lang), {"pns": join([[Pn(p)] for p in rec.ranked], ", ")}
                    )
                )
            elif draft.ranking_requested:
                self._no_winner(ctx, rec, segs, rank_limited)
            listed = list(rec.ranked) if rec.ranked else list(verified) + list(preliminary)
            blocks.append(
                MatchingPartNumbersBlock(
                    total=total,
                    part_numbers=listed,
                    page_size=len(listed),
                    verified=list(verified),
                    preliminary=list(preliminary),
                    is_complete=True,
                )
            )
            for pn in list(rec.ranked)[:3]:
                blocks.append(self.product_card(ctx, pn, grade=grade))
        if rec.non_comparable_metric is not None or rec.needs_priority:
            blocks.append(
                ClarificationBlock(
                    question=_plain(parse_template(msg("clarify_priority", lang), {})),
                    options=[
                        metric_label(k, lang) for k in ("torque_inlbs", "operating_speed", "fla")
                    ],
                )
            )
        return self.finish(
            ctx, segs, blocks, status="COMPLETED", outcome=OutcomeCode.OK, draft=draft
        )

    def _no_winner(
        self, ctx: _Ctx, rec: RecommendationResult, segs: list[Segment], rank_limited: bool
    ) -> None:
        lang = ctx.lang
        if rank_limited:
            segs.extend(parse_template(msg("rank_limit", lang), {}))
        elif rec.no_eligible:
            segs.extend(parse_template(msg("top_one_none", lang), {}))
        elif rec.non_comparable_metric is not None:
            ctx.catalog_pns.update(rec.indeterminate)
            segs.extend(
                parse_template(
                    msg("rank_not_comparable", lang),
                    {
                        "metric": Lit(metric_label(rec.non_comparable_metric, lang)),
                        "pns": join([[Pn(p)] for p in (rec.indeterminate or rec.eligible)], ", "),
                    },
                )
            )
        elif rec.needs_priority:
            segs.extend(parse_template(" " + msg("clarify_priority", lang), {}))
        else:
            segs.extend(parse_template(msg("top_one_none", lang), {}))

    # --- derived ------------------------------------------------------------------

    def derived(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        pn: str,
        pairs: Sequence[tuple[BoundFigure, BoundFigure | None]],
    ) -> ComposedResponse:
        """Conversion results, each labeled derived with formula + precision."""

        segs: list[Segment] = []
        unavailable: list[str] = []
        for source, derived in pairs:
            if derived is None:
                unavailable.append(
                    f"{metric_label(source.metric_key, ctx.lang)}: "
                    f"{self._state_text(ctx, source)}"
                )
                continue
            segs.extend(
                parse_template(
                    msg("derived", ctx.lang),
                    {
                        "pn": Pn(pn),
                        "edition": ctx.edition(),
                        "source": self._fig(ctx, source),
                        "derived": self._fig(ctx, derived),
                    },
                )
            )
            segs.append(Lit(" "))
        if unavailable:
            segs.extend(
                parse_template(
                    msg("derived_unavailable", ctx.lang),
                    {
                        "pn": Pn(pn),
                        "edition": ctx.edition(),
                        "items": Lit(", ".join(unavailable)),
                    },
                )
            )
        outcome = OutcomeCode.OK if any(d is not None for _, d in pairs) else OutcomeCode.N_A
        return self.finish(
            ctx,
            segs,
            [self.product_card(ctx, pn)],
            status="COMPLETED",
            outcome=outcome,
            draft=draft,
        )

    # --- notes --------------------------------------------------------------------

    def notes(
        self, ctx: _Ctx, draft: DraftPlan, pn: str, result: SourceNotesResult
    ) -> ComposedResponse:
        """Literal source notes, each as data (never followed as instructions)."""

        if not result.notes:
            segs = parse_template(
                msg("notes_none", ctx.lang), {"pn": Pn(pn), "edition": ctx.edition()}
            )
            return self.finish(
                ctx, segs, [], status="COMPLETED", outcome=OutcomeCode.OK, draft=draft
            )
        segs = parse_template(
            msg("notes_intro", ctx.lang), {"pn": Pn(pn), "edition": ctx.edition()}
        )
        items: list[list[Segment]] = []
        for note in result.notes:
            key = f"note:{note.note_id}"
            ctx.notes[key] = note.printed_text
            items.append([Note(key)])
        segs.extend(join(items, "; "))
        return self.finish(ctx, segs, [], status="COMPLETED", outcome=OutcomeCode.OK, draft=draft)

    # --- gating / abstention / failures ---------------------------------------------

    def abstain(self, ctx: _Ctx, draft: DraftPlan | None) -> ComposedResponse:
        """Out-of-scope abstention naming the pinned edition (Req 10.1)."""
        segs = parse_template(msg("abstain", ctx.lang), {"edition": ctx.edition()})
        return self.finish(
            ctx, segs, [], status="COMPLETED", outcome=OutcomeCode.OUT_OF_SCOPE, draft=draft
        )

    def clarification(
        self,
        ctx: _Ctx,
        draft: DraftPlan | None,
        key: str,
        *,
        slots: dict[str, Sequence[Segment] | Segment] | None = None,
        options: Sequence[str] = (),
        outcome: OutcomeCode = OutcomeCode.NEEDS_CLARIFICATION,
    ) -> ComposedResponse:
        """A blocking clarification (no tool ran for this turn)."""

        segs = parse_template(msg(key, ctx.lang), slots or {})
        block = ClarificationBlock(question=_plain_render(self, ctx, segs), options=list(options))
        return self.finish(
            ctx, segs, [block], status="NEEDS_CLARIFICATION", outcome=outcome, draft=draft
        )

    def confirmation(
        self,
        ctx: _Ctx,
        draft: DraftPlan,
        *,
        plan_id: str,
        revision: int,
        detail_keys: Sequence[str],
    ) -> ComposedResponse:
        """A plan-review block for an exact revision awaiting confirmation."""

        segs = parse_template(msg("confirm_plan", ctx.lang), {"rev": Ident(str(revision))})
        for key in detail_keys:
            if key == "confirm_boolean":
                segs.extend(
                    parse_template(
                        msg(key, ctx.lang), {"expr": self.constraints(ctx, draft.filter_ast)}
                    )
                )
            elif key == "confirm_priority":
                pri = [
                    Lit(_priority_text(p.key, p.direction.value, ctx.lang))
                    for p in draft.proposed_priorities
                ]
                segs.extend(
                    parse_template(
                        msg(key, ctx.lang), {"priorities": join([[p] for p in pri], ", ")}
                    )
                )
            else:
                segs.extend(parse_template(msg(key, ctx.lang), {}))
        summary = self.summary(draft, ctx.lang)
        block = PlanReviewBlock(
            plan_revision=revision,
            plan_id=plan_id,
            summary=_plain_render(self, ctx, segs),
            requires_confirmation=True,
            criteria=[
                CriterionDTO(text=i.text, category=i.label.value) for i in summary.all_items()
            ],
        )
        return self.finish(
            ctx,
            segs,
            [block],
            status="AWAITING_CONFIRMATION",
            outcome=OutcomeCode.AWAITING_CONFIRMATION,
            draft=draft,
            plan=PlanRefData(plan_id, revision, True),
        )

    def simple(
        self,
        ctx: _Ctx,
        key: str,
        outcome: OutcomeCode,
        *,
        status: str = "COMPLETED",
        draft: DraftPlan | None = None,
        slots: dict[str, Sequence[Segment] | Segment] | None = None,
        plan: PlanRefData | None = None,
    ) -> ComposedResponse:
        """A single-message response (stale plan, withdrawn, failures, ...)."""
        segs = parse_template(msg(key, ctx.lang), slots or {})
        return self.finish(ctx, segs, [], status=status, outcome=outcome, draft=draft, plan=plan)

    def budget_failure(self, ctx: _Ctx, limit: str, draft: DraftPlan | None) -> ComposedResponse:
        """Fail-closed budget outcome naming the limit in user words."""
        words = BUDGET_LIMIT_LABELS.get(limit, BUDGET_LIMIT_LABELS["max_walltime"])[ctx.lang]
        return self.simple(
            ctx, "budget", OutcomeCode.BUDGET_EXHAUSTED, draft=draft, slots={"limit": Lit(words)}
        )


def summary_dto(summary: InterpretationSummary) -> InterpretationSummaryDTO:
    """Convert the summary to the Spec 3 envelope DTO."""

    def items(xs: Sequence[SummaryItem]) -> list[CriterionDTO]:
        return [CriterionDTO(text=i.text, category=i.label.value) for i in xs]

    return InterpretationSummaryDTO(
        intent=summary.intent,
        applied=items(summary.applied),
        proposed=items(summary.proposed),
        delegated=items(summary.delegated),
        ignored=items(summary.ignored),
        expected_presentation_format=summary.expected_presentation_format,
    )


# --------------------------------------------------------------------- helpers


def _status_text(status: DataStatus, lang: Language) -> str:
    return STATUS_LABELS.get(status, STATUS_LABELS[DataStatus.NOT_DOCUMENTED])[lang]


def _plain(segs: Sequence[Segment]) -> str:
    """Text of slot-free segments (used for clarification questions)."""
    return "".join(s.text for s in segs if isinstance(s, Lit | Ident | UserEcho))


def _plain_render(composer: ResponseComposer, ctx: _Ctx, segs: Sequence[Segment]) -> str:
    return render(segs, composer._slots(ctx)).text  # noqa: SLF001 - same module


def _decimal_or_none(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except ArithmeticError:
        return None


def _context_tag(bf: BoundFigure, ctx: _Ctx) -> str:
    parts: list[str] = []
    if bf.unqualified:
        parts.append(ctx.word("no_service"))
    elif bf.service:
        parts.append(bf.service)
    if bf.frequency_hz is not None:
        parts.append(f"{format_decimal(bf.frequency_hz)} Hz")
    if bf.supply:
        parts.append(bf.supply)
    return ", ".join(parts) if parts else "—"


def _composite_key(bf: BoundFigure) -> str:
    service = "unq" if bf.unqualified else (bf.service or "-")
    freq = format_decimal(bf.frequency_hz) if bf.frequency_hz is not None else "-"
    return f"{bf.metric_key}@{service}@{freq}"


def _unit_of(bf: BoundFigure) -> Unit | None:
    """The documented unit of a figure (kept for N/A / absent states too)."""
    if bf.unit is None:
        return None
    try:
        return Unit(bf.unit)
    except ValueError:
        return None


def _absent_metric(bf: BoundFigure) -> MetricValue:
    return MetricValue(None, bf.figure.status, None)


def _winner(metric: str, figs: Sequence[BoundFigure]) -> str | None:
    """A unique extremum for torque (max) / operating speed (min) only."""

    if metric not in ("torque_inlbs", "torque_nm", "operating_speed"):
        return None
    values = [
        (f.figure.direct.value, f.part_number)
        for f in figs
        if f.figure.direct is not None and f.figure.direct.value is not None
    ]
    if len(values) != len(figs) or len(values) < 2:
        return None
    best = max(values) if metric != "operating_speed" else min(values)
    if sum(1 for v, _ in values if v == best[0]) > 1:
        return None
    return best[1]


def _comparison_claims(figset: VerifiedFigureSet, order: Sequence[str]) -> list[Claim]:
    """Deterministic claim proposals for a two-part comparison (both directions)."""

    if len(order) != 2:
        return []
    a, b = order
    claims: list[Claim] = []
    services = sorted(figset.services.get(a, set()) & figset.services.get(b, set()))
    for service in services:
        for unit in ("in-lbs", "Nm"):
            claims.append(Claim(ClaimKind.HAS_MORE_TORQUE, a, b, service=service, unit=unit))
            claims.append(Claim(ClaimKind.HAS_MORE_TORQUE, b, a, service=service, unit=unit))
    freqs = sorted(figset.frequencies.get(a, set()) & figset.frequencies.get(b, set()))
    for freq in freqs:
        claims.append(Claim(ClaimKind.IS_FASTER, a, b, frequency_hz=freq))
        claims.append(Claim(ClaimKind.IS_FASTER, b, a, frequency_hz=freq))
    claims.append(Claim(ClaimKind.SAME_FREQUENCY, a, b))
    return claims


def _claim_segments(claim: Claim, lang: Language) -> list[Segment]:
    key = {
        ClaimKind.HAS_MORE_TORQUE: "claim_has_more_torque",
        ClaimKind.IS_FASTER: "claim_is_faster",
        ClaimKind.SAME_FREQUENCY: "claim_same_frequency",
    }.get(claim.kind)
    if key is None or claim.subject_pn is None or claim.object_pn is None:
        return []
    segs = parse_template(
        msg(key, lang), {"subject": Pn(claim.subject_pn), "object": Pn(claim.object_pn)}
    )
    context: list[str] = []
    if claim.service:
        context.append(f"{CONTEXT_WORDS['service'][lang]}: {claim.service}")
    if claim.unit:
        context.append(claim.unit)
    if context:
        segs.append(Lit(f" ({', '.join(context)})"))
    return segs


def _ast_segments(node: Node, lang: Language) -> list[Segment]:
    if isinstance(node, Predicate):
        return _predicate_segments(node, lang)
    if isinstance(node, And | Or):
        word = CONTEXT_WORDS["and" if isinstance(node, And) else "or"][lang]
        parts = [_ast_segments(c, lang) for c in node.children]
        inner = join(parts, f" {word.upper()} ")
        return [Lit("("), *inner, Lit(")")] if len(parts) > 1 else inner
    if isinstance(node, Not):
        return [
            Lit(f"{CONTEXT_WORDS['not'][lang].upper()} ("),
            *_ast_segments(node.child, lang),
            Lit(")"),
        ]
    return [Lit("—")]


def _predicate_segments(p: Predicate, lang: Language) -> list[Segment]:
    field_text = label(FIELD_LABELS, p.field.value, lang)
    op = OPERATOR_LABELS[p.operator][lang]
    if isinstance(p.value, tuple):
        values = ", ".join(_value_text(v) for v in p.value)
    else:
        values = _value_text(p.value)
    unit = f" {p.unit.value}" if p.unit is not None else ""
    return [Lit(f"{field_text} {op} "), UserEcho(f"{values}{unit}")]


def _value_text(v: object) -> str:
    if isinstance(v, Decimal):
        return format_decimal(v)
    return str(v)


def _predicate_text(p: Predicate, lang: Language) -> str:
    field_text = label(FIELD_LABELS, p.field.value, lang)
    op = OPERATOR_LABELS[p.operator][lang]
    if isinstance(p.value, tuple):
        values = ", ".join(_value_text(v) for v in p.value)
    else:
        values = _value_text(p.value)
    unit = f" {p.unit.value}" if p.unit is not None else ""
    return f"{field_text} {op} {values}{unit}"


def _criterion_text(
    description: str, declared: str | None, unit: str | None, lang: Language
) -> str:
    if declared is None:
        return description
    tag = CONTEXT_WORDS["your_requirement"][lang]
    return f"{description} ({tag}: {declared}{(' ' + unit) if unit else ''})"


def _priority_text(key: str, direction: str, lang: Language) -> str:
    name = metric_label(key, lang)
    if lang is Language.EN:
        return f"{name} ({'highest first' if direction == 'DESC' else 'lowest first'})"
    return f"{name} ({'mayor primero' if direction == 'DESC' else 'menor primero'})"


def _unresolved_text(kind: str, text: str, lang: Language) -> str:
    if lang is Language.EN:
        return f"{text} (not applied: could not be resolved)"
    return f"{text} (no aplicado: no se pudo resolver)"


def edition_label(edition_id: uuid.UUID) -> str:
    """User-facing label of the pinned source edition."""
    return f"series_76_electric_data.pdf, edition {str(edition_id)[:8]}"


__all__ = [
    "ComposedResponse",
    "PlanRefData",
    "ResponseComposer",
    "edition_label",
    "summary_dto",
]
