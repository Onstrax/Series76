package com.series76.assistant.feature.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.series76.assistant.R
import com.series76.assistant.core.render.CardModel
import com.series76.assistant.core.render.FigureView
import com.series76.assistant.core.render.RenderItem
import com.series76.assistant.core.render.RenderModel
import com.series76.assistant.core.render.SummaryModel
import com.series76.assistant.core.render.UiStrings
import com.series76.assistant.ui.categoryRes
import com.series76.assistant.ui.rememberUiStrings

/**
 * Draws an assistant turn from its [RenderModel]. Every technical figure comes
 * from a typed field (via [FigureView]); the `answer` is shown verbatim and is
 * never scanned for numbers (Spec 5 Req 1.10, 5.1, 5.2).
 */
@Composable
fun TypedBlockRenderer(model: RenderModel, expandSummaryByDefault: Boolean = false) {
    val strings = rememberUiStrings()
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(model.answer, style = MaterialTheme.typography.bodyLarge)
        model.summary?.let { InterpretationCard(it, expandSummaryByDefault) }
        model.items.forEach { item ->
            when (item) {
                is RenderItem.TextItem -> Text(item.text)
                is RenderItem.Cards -> CardsBlock(item, strings)
                is RenderItem.Table -> TableBlock(item, strings)
                is RenderItem.Matches -> MatchesBlock(item)
                is RenderItem.Chart -> ChartBlock(item, strings)
                is RenderItem.Clarify -> Column {
                    Text(item.question, style = MaterialTheme.typography.titleSmall)
                    item.options.forEach { Text("• $it") }
                }
                // The plan panel itself (with Confirm/Edit) is drawn by the chat screen.
                is RenderItem.Plan -> Text(item.summary, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/** Compact, always visible, expandable (F4-D01); categories exactly as the backend sent them. */
@Composable
fun InterpretationCard(summary: SummaryModel, expandedByDefault: Boolean) {
    var expanded by remember { mutableStateOf(expandedByDefault) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp)) {
            Text(
                stringResource(R.string.interpretation_compact, summary.intent, summary.compactCount),
                style = MaterialTheme.typography.labelLarge,
            )
            TextButton(onClick = { expanded = !expanded }) {
                Text(stringResource(if (expanded) R.string.hide_details else R.string.show_details))
            }
            if (expanded) {
                Text(stringResource(R.string.expected_format, summary.format))
                summary.groups.forEach { (group, criteria) ->
                    if (criteria.isEmpty()) return@forEach
                    Text(stringResource(groupRes(group)), style = MaterialTheme.typography.titleSmall)
                    criteria.forEach { c ->
                        Text("• ${c.text} — ${stringResource(categoryRes(c.category))}")
                    }
                }
            }
        }
    }
}

private fun groupRes(group: String): Int = when (group) {
    "applied" -> R.string.group_applied
    "proposed" -> R.string.group_proposed
    "delegated" -> R.string.group_delegated
    else -> R.string.group_ignored
}

@Composable
private fun CardsBlock(item: RenderItem.Cards, strings: UiStrings) {
    // At most three full cards (MAX_FULL_CARDS); dual-of-two selector iff >= 2.
    var selected by remember { mutableStateOf(setOf<String>()) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (item.dualSelector) {
            Text(stringResource(R.string.compare_two), style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                item.cards.forEach { card ->
                    FilterChip(
                        selected = card.partNumber in selected,
                        onClick = {
                            selected = when {
                                card.partNumber in selected -> selected - card.partNumber
                                selected.size < 2 -> selected + card.partNumber
                                else -> selected
                            }
                        },
                        label = { Text(card.partNumber) },
                    )
                }
            }
        }
        val visible = if (selected.size == 2) item.cards.filter { it.partNumber in selected } else item.cards
        visible.forEach { ProductCardView(it, strings) }
        if (item.hiddenCount > 0) Text(stringResource(R.string.cards_hidden, item.hiddenCount))
    }
}

@Composable
private fun ProductCardView(card: CardModel, strings: UiStrings) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp)) {
            Text(card.partNumber, style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() })
            card.figures.forEach { FigureLine(it, strings) }
        }
    }
}

@Composable
private fun FigureLine(figure: FigureView, strings: UiStrings) {
    val value = strings.resolve(figure.value)
    val context = figure.context.joinToString(" · ") { strings.resolve(it) }
    Column(Modifier.padding(vertical = 2.dp).semantics(mergeDescendants = true) {}) {
        Text("${figure.label}: $value", style = MaterialTheme.typography.bodyMedium)
        if (context.isNotEmpty()) Text(context, style = MaterialTheme.typography.labelSmall)
        figure.derivedNote?.let { Text(strings.resolve(it), style = MaterialTheme.typography.labelSmall) }
    }
}

@Composable
private fun TableBlock(item: RenderItem.Table, strings: UiStrings) {
    val winnerLabel = stringResource(R.string.winner)
    // Accessible headers + horizontal scrolling (Req 10.4).
    Column(Modifier.horizontalScroll(rememberScrollState())) {
        Row {
            Cell("", header = true)
            item.partNumbers.forEach { Cell(it, header = true) }
        }
        item.rows.forEach { row ->
            Row {
                Cell(row.label, header = true)
                item.partNumbers.forEach { pn ->
                    val cell = row.cells.firstOrNull { it.partNumber == pn }
                    val text = cell?.let { c ->
                        val ctx = c.context.joinToString(" · ") { strings.resolve(it) }
                        listOf(strings.resolve(c.value), ctx).filter { it.isNotEmpty() }.joinToString("\n")
                    } ?: "—"
                    val mark = if (row.winnerPartNumber == pn) " ($winnerLabel)" else ""
                    Cell(text + mark)
                }
            }
            row.notes.forEach { note ->
                Text(strings.resolve(note), style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun Cell(text: String, header: Boolean = false) {
    Text(
        text,
        style = if (header) MaterialTheme.typography.labelLarge else MaterialTheme.typography.bodySmall,
        modifier = Modifier.width(140.dp).padding(4.dp).let { m -> if (header) m.semantics { heading() } else m },
    )
}

@Composable
private fun MatchesBlock(item: RenderItem.Matches) {
    Column {
        Text(
            if (item.topOne) {
                stringResource(R.string.matches_top_one, item.count)
            } else {
                stringResource(R.string.matches_count, item.count)
            },
            style = MaterialTheme.typography.titleSmall,
        )
        // List mode: the full list of names. Top-1: the winner only (Req 5.9, 5.10).
        item.partNumbers.forEach { Text("• $it") }
        if (item.partial) Text(stringResource(R.string.partial_list), style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun ChartBlock(item: RenderItem.Chart, strings: UiStrings) {
    val primary = MaterialTheme.colorScheme.primary
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("${item.metricLabel} (${item.unit})", style = MaterialTheme.typography.titleSmall)
        // Only documented values become bars; N/A points never become a zero bar.
        item.bars.forEach { bar ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(bar.label, modifier = Modifier.width(96.dp))
                Box(
                    Modifier.weight(1f).height(16.dp).semantics {
                        contentDescription = "${bar.label}: ${bar.valueText}"
                    },
                ) {
                    Box(Modifier.fillMaxWidth(bar.fraction.coerceIn(0f, 1f)).height(16.dp).background(primary))
                }
            }
        }
        // Textual alternative for every point (Req 10.4): no information is chart-only.
        Text(stringResource(R.string.chart_alternatives), style = MaterialTheme.typography.labelLarge)
        item.textAlternatives.forEach { AssistChip(onClick = {}, label = { Text(strings.resolve(it)) }) }
    }
}
