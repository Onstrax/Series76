package com.series76.assistant.core.model

/**
 * Client-side model of the Spec 3 `Response_Envelope` and its typed
 * `content_blocks` (populated by Spec 4). Pure Kotlin — no Android types.
 *
 * Every technical figure the app can ever display lives in a [Figure]: a typed
 * value string (decimal at the backend's stored precision), its unit, its
 * availability, and its service / frequency / supply context and evidence. The
 * free-text `answer` is carried verbatim and is never scanned for numbers.
 */

/** The documented state of a figure (Spec 2 `DataStatus`), plus [UNKNOWN]. */
enum class Availability {
    AVAILABLE, NOT_APPLICABLE, NOT_DOCUMENTED, NOT_LISTED, UNVERIFIED, UNKNOWN;

    companion object {
        fun parse(raw: String?): Availability =
            entries.firstOrNull { it.name == raw } ?: UNKNOWN
    }
}

/** Provenance of a figure: the published source cells / rows / notes. */
data class Evidence(
    val cellRefs: List<Long> = emptyList(),
    val rowRefs: List<Long> = emptyList(),
    val noteRefs: List<Long> = emptyList(),
) {
    val isResolvable: Boolean get() = cellRefs.isNotEmpty() || rowRefs.isNotEmpty()
}

/**
 * One typed figure. [isValid] is false when the typed fields are missing or
 * contradictory (e.g. AVAILABLE without a decimal value, or a value on an N/A
 * figure); such a figure is rendered as "unavailable", never guessed.
 */
data class Figure(
    val figureId: String,
    val metricKey: String,
    val label: String,
    val value: String?,
    val unit: String?,
    val availability: Availability,
    val partNumber: String,
    val service: String? = null,
    val frequencyHz: String? = null,
    val supply: String? = null,
    val derived: Boolean = false,
    val formula: String? = null,
    val precisionDecimals: Int? = null,
    val evidence: Evidence = Evidence(),
) {
    val isValid: Boolean
        get() = when (availability) {
            Availability.AVAILABLE -> value != null && DECIMAL.matches(value)
            Availability.UNKNOWN -> false
            else -> value == null
        }

    companion object {
        val DECIMAL = Regex("^-?\\d+(\\.\\d+)?$")
    }
}

data class ComparisonRow(
    val metricKey: String,
    val label: String,
    val cells: List<Figure>,
    val comparable: Boolean,
    val warning: String?,
    val winnerPartNumber: String?,
    val supplyHeterogeneous: Boolean,
)

data class BarPoint(val label: String, val figure: Figure)

data class Criterion(val text: String, val category: String)

/** The canonical Spec 3 `content_blocks` union (plus a safe fallback). */
sealed interface ContentBlock {
    data class Text(val text: String) : ContentBlock

    data class ProductCard(
        val partNumber: String,
        val figures: List<Figure>,
        val grade: String?,
    ) : ContentBlock

    data class ComparisonTable(
        val partNumbers: List<String>,
        val rows: List<ComparisonRow>,
    ) : ContentBlock

    data class MatchingPartNumbers(
        val total: Int,
        val partNumbers: List<String>,
        val verified: List<String>,
        val preliminary: List<String>,
        val isComplete: Boolean,
        val topOne: Boolean,
        val winnerPartNumber: String?,
    ) : ContentBlock

    data class BarChart(
        val metricKey: String,
        val unit: String,
        val comparable: Boolean,
        val points: List<BarPoint>,
    ) : ContentBlock

    data class Clarification(val question: String, val options: List<String>) : ContentBlock

    data class PlanReview(
        val planRevision: Int,
        val planId: String?,
        val summary: String,
        val requiresConfirmation: Boolean,
        val criteria: List<Criterion>,
    ) : ContentBlock

    /** Unknown kind or malformed block: shown as plain text, never as data. */
    data class Fallback(val text: String) : ContentBlock
}

data class InterpretationSummary(
    val intent: String,
    val applied: List<Criterion>,
    val proposed: List<Criterion>,
    val delegated: List<Criterion>,
    val ignored: List<Criterion>,
    val expectedPresentationFormat: String,
)

data class PlanRef(val planId: String, val revision: Int, val confirmationNeeded: Boolean)

data class Envelope(
    val sessionId: String,
    val answer: String,
    val blocks: List<ContentBlock> = emptyList(),
    val status: String? = null,
    val interpretationSummary: InterpretationSummary? = null,
    val plan: PlanRef? = null,
    val warnings: List<String> = emptyList(),
    val requestId: String? = null,
    val catalogEditionId: String? = null,
    val messageId: String? = null,
    val turnId: String? = null,
)

/** The Spec 3 `Error_Envelope`. */
data class ErrorEnvelope(
    val code: String,
    val userMessage: String,
    val requestId: String?,
    val retryable: Boolean,
)
