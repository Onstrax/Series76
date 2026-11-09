package com.series76.assistant.fakes

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Builders for Spec 3 / Spec 4 wire JSON (what the backend actually sends). */
object Fixtures {

    fun figure(
        id: String,
        pn: String,
        metric: String = "torque_inlbs",
        value: String? = "100",
        unit: String? = "in-lbs",
        status: String = if (value != null) "AVAILABLE" else "NOT_APPLICABLE",
        service: String? = "On/Off",
        frequency: String? = null,
        supply: String? = "24 V AC/DC",
        cells: List<Long> = listOf(11L),
        derived: Boolean = false,
        formula: String? = null,
    ): JsonObject = buildJsonObject {
        put("figure_id", id)
        put("metric_key", metric)
        put("label", "torque (in-lbs)")
        put("value", value?.let { JsonPrimitive(it) } ?: JsonNull)
        put("unit", unit?.let { JsonPrimitive(it) } ?: JsonNull)
        put("status", status)
        put("part_number", pn)
        put("service", service?.let { JsonPrimitive(it) } ?: JsonNull)
        put("frequency_hz", frequency?.let { JsonPrimitive(it) } ?: JsonNull)
        put("supply", supply?.let { JsonPrimitive(it) } ?: JsonNull)
        put("derived", derived)
        put("formula", formula?.let { JsonPrimitive(it) } ?: JsonNull)
        put("evidence", buildJsonObject {
            put("cell_refs", JsonArray(cells.map { JsonPrimitive(it) }))
            put("row_refs", JsonArray(emptyList()))
            put("note_refs", JsonArray(emptyList()))
        })
    }

    fun card(pn: String, figures: List<JsonObject>): JsonObject = buildJsonObject {
        put("kind", "product_card")
        put("schema_version", 1)
        put("part_number", pn)
        put("figures", JsonArray(figures))
    }

    fun matches(total: Int, pns: List<String>, topOne: Boolean = false, winner: String? = null) =
        buildJsonObject {
            put("kind", "matching_part_numbers")
            put("total", total)
            put("part_numbers", JsonArray(pns.map { JsonPrimitive(it) }))
            put("top_one", topOne)
            put("winner_part_number", winner?.let { JsonPrimitive(it) } ?: JsonNull)
            put("is_complete", true)
        }

    fun chart(points: List<Pair<String, JsonObject>>, comparable: Boolean) = buildJsonObject {
        put("kind", "bar_chart")
        put("metric_key", "torque_inlbs")
        put("unit", "in-lbs")
        put("comparable", comparable)
        put("points", buildJsonArray {
            points.forEach { (label, fig) -> add(buildJsonObject { put("label", label); put("figure", fig) }) }
        })
    }

    fun table(pns: List<String>, cells: List<JsonObject>, comparable: Boolean, winner: String?, hetero: Boolean) =
        buildJsonObject {
            put("kind", "comparison_table")
            put("part_numbers", JsonArray(pns.map { JsonPrimitive(it) }))
            put("metric_rows", buildJsonArray {
                add(buildJsonObject {
                    put("metric_key", "fla")
                    put("label", "FLA")
                    put("cells", JsonArray(cells))
                    put("comparable", comparable)
                    put("winner_part_number", winner?.let { JsonPrimitive(it) } ?: JsonNull)
                    put("supply_heterogeneous", hetero)
                })
            })
        }

    fun planReview(revision: Int) = buildJsonObject {
        put("kind", "plan_review")
        put("plan_revision", revision)
        put("plan_id", "plan-$revision")
        put("summary", "Review the plan")
        put("requires_confirmation", true)
        put("criteria", JsonArray(emptyList()))
    }

    fun envelope(
        answer: String,
        blocks: List<JsonElement>,
        summary: JsonObject? = null,
        session: String = "session-1",
    ): String = buildJsonObject {
        put("session_id", session)
        put("answer", answer)
        put("content_blocks", JsonArray(blocks))
        if (summary != null) put("interpretation_summary", summary)
    }.toString()

    fun summary(categories: List<String>) = buildJsonObject {
        put("intent", "Exact part lookup")
        put("expected_presentation_format", "Product card")
        put("applied", buildJsonArray {
            categories.forEachIndexed { i, c -> add(buildJsonObject { put("text", "criterion $i"); put("category", c) }) }
        })
        put("proposed", JsonArray(emptyList()))
        put("delegated", JsonArray(emptyList()))
        put("ignored", JsonArray(emptyList()))
    }
}
