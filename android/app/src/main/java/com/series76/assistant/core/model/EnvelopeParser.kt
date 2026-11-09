package com.series76.assistant.core.model

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull

/**
 * Decodes Spec 3 JSON into the client model, field by field.
 *
 * Robustness rules (Spec 5 Req 1.11, 5.1):
 * - an unknown `kind` becomes [ContentBlock.Fallback] carrying only its `text`;
 * - a block whose required typed fields are missing becomes a fallback too;
 * - a figure with contradictory typed fields is kept but marked invalid, so the
 *   renderer shows "unavailable" for it instead of fabricating a value;
 * - a JSON number in a figure's `value` is NOT accepted as a figure value
 *   (values are decimal strings at the stored precision; a float would lose it).
 */
object EnvelopeParser {

    val json: Json = Json { ignoreUnknownKeys = true; isLenient = false }

    /** Parse an envelope; `null` if the inviolable `session_id` / `answer` are missing. */
    fun parse(raw: String): Envelope? = runCatching {
        parseObject(json.parseToJsonElement(raw) as JsonObject)
    }.getOrNull()

    fun parseObject(obj: JsonObject): Envelope? {
        val sessionId = obj.str("session_id")
        val answer = obj.str("answer")
        if (sessionId.isNullOrBlank() || answer.isNullOrBlank()) return null
        val blocks = (obj["content_blocks"] as? JsonArray).orEmpty().map { parseBlock(it) }
        return Envelope(
            sessionId = sessionId,
            answer = answer,
            blocks = blocks,
            status = obj.str("status"),
            interpretationSummary = (obj["interpretation_summary"] as? JsonObject)?.let(::summary),
            plan = (obj["plan"] as? JsonObject)?.let { p ->
                val id = p.str("plan_id")
                val rev = p.int("revision")
                if (id != null && rev != null) {
                    PlanRef(id, rev, p.bool("confirmation_needed") ?: false)
                } else {
                    null
                }
            },
            warnings = obj.strList("warnings"),
            requestId = obj.str("request_id"),
            catalogEditionId = obj.str("catalog_edition_id"),
            messageId = obj.str("message_id"),
            turnId = obj.str("turn_id"),
        )
    }

    fun parseError(raw: String): ErrorEnvelope? = runCatching {
        val obj = json.parseToJsonElement(raw) as JsonObject
        val err = obj["error"] as JsonObject
        ErrorEnvelope(
            code = err.str("code") ?: return@runCatching null,
            userMessage = err.str("user_message") ?: "",
            requestId = obj.str("request_id"),
            retryable = obj.bool("retryable") ?: false,
        )
    }.getOrNull()

    fun parseBlock(element: JsonElement): ContentBlock {
        val obj = element as? JsonObject ?: return ContentBlock.Fallback("")
        val text = obj.str("text") ?: ""
        return when (obj.str("kind")) {
            "text" -> ContentBlock.Text(text)
            "product_card" -> {
                val pn = obj.str("part_number") ?: return ContentBlock.Fallback(text)
                ContentBlock.ProductCard(pn, obj.figures("figures"), obj.str("grade"))
            }
            "comparison_table" -> ContentBlock.ComparisonTable(
                partNumbers = obj.strList("part_numbers"),
                rows = (obj["metric_rows"] as? JsonArray).orEmpty().mapNotNull { r ->
                    val row = r as? JsonObject ?: return@mapNotNull null
                    ComparisonRow(
                        metricKey = row.str("metric_key") ?: return@mapNotNull null,
                        label = row.str("label") ?: "",
                        cells = row.figures("cells"),
                        comparable = row.bool("comparable") ?: false,
                        warning = row.str("warning"),
                        winnerPartNumber = row.str("winner_part_number"),
                        supplyHeterogeneous = row.bool("supply_heterogeneous") ?: false,
                    )
                },
            )
            "matching_part_numbers" -> ContentBlock.MatchingPartNumbers(
                total = obj.int("total") ?: return ContentBlock.Fallback(text),
                partNumbers = obj.strList("part_numbers"),
                verified = obj.strList("verified"),
                preliminary = obj.strList("preliminary"),
                isComplete = obj.bool("is_complete") ?: true,
                topOne = obj.bool("top_one") ?: false,
                winnerPartNumber = obj.str("winner_part_number"),
            )
            "bar_chart" -> ContentBlock.BarChart(
                metricKey = obj.str("metric_key") ?: "",
                unit = obj.str("unit") ?: "",
                comparable = obj.bool("comparable") ?: false,
                points = (obj["points"] as? JsonArray).orEmpty().mapNotNull { p ->
                    val point = p as? JsonObject ?: return@mapNotNull null
                    val fig = (point["figure"] as? JsonObject)?.let(::figure)
                        ?: return@mapNotNull null
                    BarPoint(point.str("label") ?: fig.partNumber, fig)
                },
            )
            "clarification" -> ContentBlock.Clarification(
                obj.str("question") ?: "",
                obj.strList("options"),
            )
            "plan_review" -> ContentBlock.PlanReview(
                planRevision = obj.int("plan_revision") ?: return ContentBlock.Fallback(text),
                planId = obj.str("plan_id"),
                summary = obj.str("summary") ?: "",
                requiresConfirmation = obj.bool("requires_confirmation") ?: true,
                criteria = obj.criteria("criteria"),
            )
            else -> ContentBlock.Fallback(text)
        }
    }

    fun figure(obj: JsonObject): Figure {
        val rawValue = obj["value"]
        // Only a JSON string is a figure value; numbers would lose precision.
        val value = (rawValue as? JsonPrimitive)?.takeIf { it.isString }?.content
        val ev = obj["evidence"] as? JsonObject
        return Figure(
            figureId = obj.str("figure_id") ?: "",
            metricKey = obj.str("metric_key") ?: "",
            label = obj.str("label") ?: "",
            value = value,
            unit = obj.str("unit"),
            availability = if (rawValue != null && rawValue !is JsonNull && value == null) {
                Availability.UNKNOWN // a non-string value is malformed
            } else {
                Availability.parse(obj.str("status"))
            },
            partNumber = obj.str("part_number") ?: "",
            service = obj.str("service"),
            frequencyHz = obj.str("frequency_hz"),
            supply = obj.str("supply"),
            derived = obj.bool("derived") ?: false,
            formula = obj.str("formula"),
            precisionDecimals = obj.int("precision_decimals"),
            evidence = Evidence(
                cellRefs = ev?.longList("cell_refs").orEmpty(),
                rowRefs = ev?.longList("row_refs").orEmpty(),
                noteRefs = ev?.longList("note_refs").orEmpty(),
            ),
        )
    }

    private fun summary(obj: JsonObject): InterpretationSummary = InterpretationSummary(
        intent = obj.str("intent") ?: "",
        applied = obj.criteria("applied"),
        proposed = obj.criteria("proposed"),
        delegated = obj.criteria("delegated"),
        ignored = obj.criteria("ignored"),
        expectedPresentationFormat = obj.str("expected_presentation_format") ?: "",
    )

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.strList(key: String): List<String> =
        (this[key] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content
        }

    private fun JsonObject.longList(key: String): List<Long> =
        (this[key] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> !p.isString }?.longOrNull
        }

    private fun JsonObject.figures(key: String): List<Figure> =
        (this[key] as? JsonArray).orEmpty().mapNotNull { (it as? JsonObject)?.let(::figure) }

    private fun JsonObject.criteria(key: String): List<Criterion> =
        (this[key] as? JsonArray).orEmpty().mapNotNull { c ->
            val o = c as? JsonObject ?: return@mapNotNull null
            val text = o.str("text") ?: return@mapNotNull null
            val category = o.str("category") ?: return@mapNotNull null
            Criterion(text, category)
        }
}
