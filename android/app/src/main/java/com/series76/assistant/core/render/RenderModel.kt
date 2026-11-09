package com.series76.assistant.core.render

import com.series76.assistant.core.model.Availability
import com.series76.assistant.core.model.ContentBlock
import com.series76.assistant.core.model.Criterion
import com.series76.assistant.core.model.Envelope
import com.series76.assistant.core.model.Figure
import java.math.BigDecimal

/**
 * Pure mapping from a typed [Envelope] to what the screen draws.
 *
 * Invariants (Spec 5 Properties 1-7, 32):
 * - every figure text comes from a typed [Figure] field ([UiText.Raw]); the
 *   `answer` is carried verbatim and never scanned;
 * - N/A / absent / invalid figures render as an explicit localized state
 *   ([UiText.Res]) — never zero, never a bar, never a winner;
 * - at most three full product cards; a dual-of-two selector iff >= 2 cards;
 * - bars only for `comparable` charts, each with a textual alternative;
 * - top-1 shows the winner and the eligible count only.
 */

/** Text that is either a localized UI string key or raw backend data. */
sealed interface UiText {
    /** Backend data (part numbers, values, units, contexts): never translated. */
    data class Raw(val text: String) : UiText

    /** A UI string resolved per locale (see [UiStrings]). */
    data class Res(val key: String, val args: List<String> = emptyList()) : UiText
}

/** A figure as displayed: value (or explicit state) plus its context chips. */
data class FigureView(
    val figureId: String,
    val label: String,
    val value: UiText,
    val context: List<UiText>,
    val available: Boolean,
    val derivedNote: UiText?,
    val partNumber: String,
)

data class CardModel(val partNumber: String, val figures: List<FigureView>, val grade: String?)

data class RowModel(
    val label: String,
    val cells: List<FigureView>,
    val comparable: Boolean,
    val winnerPartNumber: String?,
    val notes: List<UiText>,
)

data class BarModel(val label: String, val valueText: String, val fraction: Float)

sealed interface RenderItem {
    data class TextItem(val text: String) : RenderItem
    data class Cards(val cards: List<CardModel>, val hiddenCount: Int, val dualSelector: Boolean) :
        RenderItem
    data class Table(val partNumbers: List<String>, val rows: List<RowModel>) : RenderItem
    data class Matches(
        val count: Int,
        val partNumbers: List<String>,
        val topOne: Boolean,
        val partial: Boolean,
    ) : RenderItem
    data class Chart(
        val metricLabel: String,
        val unit: String,
        val bars: List<BarModel>,
        val textAlternatives: List<UiText>,
    ) : RenderItem
    data class Clarify(val question: String, val options: List<String>) : RenderItem
    data class Plan(
        val revision: Int,
        val planId: String?,
        val summary: String,
        val criteria: List<Criterion>,
        val needsConfirmation: Boolean,
    ) : RenderItem
}

data class SummaryModel(
    val intent: String,
    val format: String,
    val groups: List<Pair<String, List<Criterion>>>,
) {
    /** The compact, always-visible line (F4-D01). */
    val compactCount: Int get() = groups.sumOf { it.second.size }
}

data class RenderModel(
    val answer: String,
    val summary: SummaryModel?,
    val items: List<RenderItem>,
    val warnings: List<String>,
)

/** The categories a summary criterion may carry (backend vocabulary only). */
val KNOWN_CATEGORIES = setOf("documented-fact", "user-assumption", "proposal", "delegation")

const val MAX_FULL_CARDS = 3

object RenderMapper {

    fun map(envelope: Envelope): RenderModel {
        val items = mutableListOf<RenderItem>()
        val cards = envelope.blocks.filterIsInstance<ContentBlock.ProductCard>()
        var cardsEmitted = false
        for (block in envelope.blocks) {
            when (block) {
                is ContentBlock.Text -> if (block.text.isNotBlank()) {
                    items += RenderItem.TextItem(block.text)
                }
                is ContentBlock.Fallback -> if (block.text.isNotBlank()) {
                    items += RenderItem.TextItem(block.text)
                }
                is ContentBlock.ProductCard -> if (!cardsEmitted) {
                    cardsEmitted = true
                    val shown = cards.take(MAX_FULL_CARDS).map { card ->
                        CardModel(card.partNumber, card.figures.map(::figureView), card.grade)
                    }
                    items += RenderItem.Cards(
                        cards = shown,
                        hiddenCount = (cards.size - shown.size).coerceAtLeast(0),
                        dualSelector = shown.size >= 2,
                    )
                }
                is ContentBlock.ComparisonTable -> items += RenderItem.Table(
                    partNumbers = block.partNumbers,
                    rows = block.rows.map { row ->
                        val cells = row.cells.map(::figureView)
                        val winnerCell = cells.firstOrNull { it.partNumber == row.winnerPartNumber }
                        val winnerOk = row.comparable && !row.supplyHeterogeneous &&
                            cells.all { it.available } && winnerCell != null
                        val notes = buildList {
                            if (!row.comparable) add(UiText.Res("note_not_comparable"))
                            if (row.supplyHeterogeneous) add(UiText.Res("note_supply_heterogeneous"))
                        }
                        RowModel(
                            label = row.label,
                            cells = cells,
                            comparable = row.comparable,
                            winnerPartNumber = if (winnerOk) row.winnerPartNumber else null,
                            notes = notes,
                        )
                    },
                )
                is ContentBlock.MatchingPartNumbers -> items += if (block.topOne) {
                    RenderItem.Matches(
                        count = block.total,
                        partNumbers = listOfNotNull(block.winnerPartNumber),
                        topOne = true,
                        partial = false,
                    )
                } else {
                    RenderItem.Matches(
                        count = block.total,
                        partNumbers = block.partNumbers,
                        topOne = false,
                        partial = !block.isComplete,
                    )
                }
                is ContentBlock.BarChart -> chart(block)?.let { items += it }
                is ContentBlock.Clarification -> items += RenderItem.Clarify(block.question, block.options)
                is ContentBlock.PlanReview -> items += RenderItem.Plan(
                    revision = block.planRevision,
                    planId = block.planId,
                    summary = block.summary,
                    criteria = block.criteria.map { it.copy(category = category(it.category)) },
                    needsConfirmation = block.requiresConfirmation,
                )
            }
        }
        return RenderModel(
            answer = envelope.answer,
            summary = envelope.interpretationSummary?.let { s ->
                SummaryModel(
                    intent = s.intent,
                    format = s.expectedPresentationFormat,
                    groups = listOf(
                        "applied" to s.applied,
                        "proposed" to s.proposed,
                        "delegated" to s.delegated,
                        "ignored" to s.ignored,
                    ).map { (name, list) -> name to list.map { it.copy(category = category(it.category)) } },
                )
            },
            items = items,
            warnings = envelope.warnings,
        )
    }

    /** Backend categories are shown as-is; an unknown one is not invented into a known one. */
    private fun category(raw: String): String = if (raw in KNOWN_CATEGORIES) raw else "uncategorized"

    fun figureView(figure: Figure): FigureView {
        val valid = figure.isValid && figure.evidence.isResolvable
        val value: UiText = when {
            !valid -> UiText.Res("state_unavailable")
            figure.availability == Availability.AVAILABLE ->
                UiText.Raw(listOfNotNull(figure.value, figure.unit?.takeIf { it != "count" }).joinToString(" "))
            figure.availability == Availability.NOT_APPLICABLE -> UiText.Res("state_not_applicable")
            figure.availability == Availability.NOT_DOCUMENTED -> UiText.Res("state_not_documented")
            figure.availability == Availability.NOT_LISTED -> UiText.Res("state_not_listed")
            figure.availability == Availability.UNVERIFIED -> UiText.Res("state_unverified")
            else -> UiText.Res("state_unavailable")
        }
        val context = buildList<UiText> {
            figure.service?.let { add(UiText.Raw(it)) }
            figure.frequencyHz?.let { add(UiText.Raw("$it Hz")) }
            figure.supply?.let { add(UiText.Raw(it)) }
        }
        return FigureView(
            figureId = figure.figureId,
            label = figure.label,
            value = value,
            context = context,
            available = valid && figure.availability == Availability.AVAILABLE,
            derivedNote = if (valid && figure.derived) {
                UiText.Res("derived_note", listOfNotNull(figure.formula))
            } else {
                null
            },
            partNumber = figure.partNumber,
        )
    }

    private fun chart(block: ContentBlock.BarChart): RenderItem.Chart? {
        // Bars are drawn only for metrics the backend marks comparable (F4-D02).
        if (!block.comparable) return null
        val views = block.points.map { it.label to figureView(it.figure) }
        val available = block.points.filter { figureView(it.figure).available }
        val max = available.maxOfOrNull { BigDecimal(it.figure.value!!) } ?: BigDecimal.ZERO
        val bars = available.map { p ->
            val v = BigDecimal(p.figure.value!!)
            val fraction = if (max.signum() > 0) v.divide(max, 6, java.math.RoundingMode.HALF_EVEN).toFloat() else 0f
            BarModel(p.label, listOfNotNull(p.figure.value, p.figure.unit).joinToString(" "), fraction)
        }
        // Every point (including N/A ones) gets a textual alternative.
        val alternatives = views.map { (label, view) ->
            when (val v = view.value) {
                is UiText.Raw -> UiText.Raw("$label: ${v.text}")
                is UiText.Res -> UiText.Res("bar_alt_state", listOf(label, v.key))
            }
        }
        return RenderItem.Chart(
            metricLabel = block.points.firstOrNull()?.figure?.label ?: block.metricKey,
            unit = block.unit,
            bars = bars,
            textAlternatives = alternatives,
        )
    }
}
