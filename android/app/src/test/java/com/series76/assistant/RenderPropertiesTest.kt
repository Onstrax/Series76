package com.series76.assistant

import com.series76.assistant.core.model.ContentBlock
import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.render.KNOWN_CATEGORIES
import com.series76.assistant.core.render.MAX_FULL_CARDS
import com.series76.assistant.core.render.RenderItem
import com.series76.assistant.core.render.RenderMapper
import com.series76.assistant.core.render.TableUiStrings
import com.series76.assistant.core.render.UiText
import com.series76.assistant.fakes.Fixtures
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Spec 5 Properties 1-7 and 32: pure rendering logic (JVM, zero network). */
class RenderPropertiesTest {

    private val values = Arb.int(0..9999).map { it.toString() }

    private fun rawTexts(items: List<RenderItem>): List<String> = items.flatMap { item ->
        when (item) {
            is RenderItem.Cards -> item.cards.flatMap { c ->
                c.figures.flatMap { f -> listOf(f.value) + f.context }.filterIsInstance<UiText.Raw>().map { it.text }
            }
            is RenderItem.Table -> item.rows.flatMap { r -> r.cells.map { it.value } }
                .filterIsInstance<UiText.Raw>().map { it.text }
            is RenderItem.Chart -> item.bars.map { it.valueText }
            else -> emptyList()
        }
    }

    // Feature: android-app, Property 1: Technical figures are read only from typed fields, never parsed from prose
    @Test
    fun property1_figuresOnlyFromTypedFields() = runTest {
        checkAll(100, values, values, Arb.int(1..5)) { typed, prose, n ->
            val figures = (1..n).map { i -> Fixtures.figure("f$i", "76-$i", value = typed) }
            val answer = "The torque is $prose in-lbs and FLA ${prose}9 A."
            val env = EnvelopeParser.parse(Fixtures.envelope(answer, listOf(Fixtures.card("76-1", figures))))
            assertNotNull(env)
            val model = RenderMapper.map(env!!)
            assertEquals(answer, model.answer) // verbatim
            // Every displayed value is exactly the typed field; the prose numbers never appear.
            val shown = model.items.filterIsInstance<RenderItem.Cards>()
                .flatMap { it.cards }.flatMap { it.figures }.map { it.value }
            assertTrue(shown.isNotEmpty())
            shown.forEach { assertEquals(UiText.Raw("$typed in-lbs"), it) }
        }
    }

    // Feature: android-app, Property 2: Unknown or malformed blocks degrade to a safe fallback and never fabricate
    @Test
    fun property2_unknownOrMalformedDegrades() = runTest {
        checkAll(100, Arb.string(1..12), Arb.element("number", "garbage", "", "1.2.3", "NaN")) { kind, bad ->
            val unknown = buildJsonObject { put("kind", "x_$kind"); put("text", "safe text") }
            val malformedCard = buildJsonObject { put("kind", "product_card") } // no part_number
            val badFigure = Fixtures.figure("f1", "76-1", value = null, status = "AVAILABLE")
            val numericValue = buildJsonObject {
                put("figure_id", "f2"); put("metric_key", "fla"); put("label", "FLA")
                put("value", JsonPrimitive(1.5)); put("status", "AVAILABLE"); put("part_number", "76-1")
            }
            val wrong = Fixtures.figure("f3", "76-1", value = bad.ifEmpty { "x" })
            val env = EnvelopeParser.parse(
                Fixtures.envelope("ok", listOf(unknown, malformedCard, Fixtures.card("76-1", listOf(badFigure, numericValue, wrong)))),
            )!!
            assertTrue(env.blocks[0] is ContentBlock.Fallback)
            assertTrue(env.blocks[1] is ContentBlock.Fallback)
            val model = RenderMapper.map(env)
            val card = model.items.filterIsInstance<RenderItem.Cards>().single().cards.single()
            card.figures.forEach { f ->
                assertEquals(UiText.Res("state_unavailable"), f.value) // never a guessed value
                assertFalse(f.available)
            }
        }
    }

    // Feature: android-app, Property 3: N/A and absent values are never zero, a zero-bar, or a winner
    @Test
    fun property3_naNeverZeroBarOrWinner() = runTest {
        checkAll(100, Arb.element("NOT_APPLICABLE", "NOT_DOCUMENTED", "UNVERIFIED", "NOT_LISTED"), values) { status, v ->
            val na = Fixtures.figure("na", "76-A", value = null, status = status)
            val ok = Fixtures.figure("ok", "76-B", value = v)
            val env = EnvelopeParser.parse(
                Fixtures.envelope("a", listOf(
                    Fixtures.chart(listOf("76-A" to na, "76-B" to ok), comparable = true),
                    Fixtures.table(listOf("76-A", "76-B"), listOf(na, ok), comparable = true, winner = "76-A", hetero = false),
                )),
            )!!
            val model = RenderMapper.map(env)
            val chart = model.items.filterIsInstance<RenderItem.Chart>().single()
            assertTrue(chart.bars.none { it.label == "76-A" }) // no zero-height bar
            assertEquals(2, chart.textAlternatives.size) // but stated textually
            val row = model.items.filterIsInstance<RenderItem.Table>().single().rows.single()
            assertNull(row.winnerPartNumber) // N/A is never a winner
            val naCell = row.cells.first { it.partNumber == "76-A" }
            assertTrue(naCell.value is UiText.Res)
            assertFalse((naCell.value as UiText.Res).key.contains("0"))
        }
    }

    // Feature: android-app, Property 4: Card cap, dual-of-two selector, and comparable-only bars with textual alternatives
    @Test
    fun property4_cardCapDualSelectorComparableBars() = runTest {
        checkAll(100, Arb.int(0..7), Arb.boolean(), Arb.int(1..4)) { cards, comparable, points ->
            val blocks = (1..cards).map { Fixtures.card("76-$it", listOf(Fixtures.figure("f$it", "76-$it"))) } +
                Fixtures.chart((1..points).map { "76-$it" to Fixtures.figure("c$it", "76-$it") }, comparable)
            val model = RenderMapper.map(EnvelopeParser.parse(Fixtures.envelope("a", blocks))!!)
            val cardItem = model.items.filterIsInstance<RenderItem.Cards>().singleOrNull()
            val shown = cardItem?.cards?.size ?: 0
            assertTrue(shown <= MAX_FULL_CARDS)
            assertEquals(minOf(cards, MAX_FULL_CARDS), shown)
            if (cardItem != null) assertEquals(shown >= 2, cardItem.dualSelector)
            val charts = model.items.filterIsInstance<RenderItem.Chart>()
            if (comparable) {
                assertEquals(1, charts.size)
                assertEquals(points, charts.single().textAlternatives.size)
            } else {
                assertTrue(charts.isEmpty())
            }
        }
    }

    // Feature: android-app, Property 5: List mode shows count and full PN list; top-1 mode shows winner and count only
    @Test
    fun property5_listVersusTopOne() = runTest {
        checkAll(100, Arb.list(Arb.int(100..999), 1..12), Arb.boolean()) { nums, topOne ->
            val pns = nums.distinct().map { "76-$it" }
            val block = if (topOne) Fixtures.matches(pns.size, listOf(pns.first()), topOne = true, winner = pns.first())
            else Fixtures.matches(pns.size, pns)
            val item = RenderMapper.map(EnvelopeParser.parse(Fixtures.envelope("a", listOf(block)))!!)
                .items.filterIsInstance<RenderItem.Matches>().single()
            assertEquals(pns.size, item.count)
            if (topOne) assertEquals(listOf(pns.first()), item.partNumbers) else assertEquals(pns, item.partNumbers)
        }
    }

    // Feature: android-app, Property 6: Technical values carry unit, service, and frequency context without an energy claim
    @Test
    fun property6_contextAndNoEnergyClaim() = runTest {
        checkAll(100, values, Arb.element("50", "60"), Arb.element("On/Off", "Modulating"), Arb.boolean()) { v, hz, svc, hetero ->
            val a = Fixtures.figure("a", "76-A", metric = "fla", value = v, unit = "A", service = svc, frequency = hz, supply = "24 V AC")
            val b = Fixtures.figure("b", "76-B", metric = "fla", value = v, unit = "A", service = svc, frequency = hz,
                supply = if (hetero) "120 V AC" else "24 V AC")
            val model = RenderMapper.map(EnvelopeParser.parse(Fixtures.envelope("a", listOf(
                Fixtures.card("76-A", listOf(a)),
                Fixtures.table(listOf("76-A", "76-B"), listOf(a, b), comparable = !hetero, winner = "76-B", hetero = hetero),
            )))!!)
            val f = model.items.filterIsInstance<RenderItem.Cards>().single().cards.single().figures.single()
            assertEquals(UiText.Raw("$v A"), f.value)
            assertTrue(f.context.contains(UiText.Raw(svc)) && f.context.contains(UiText.Raw("$hz Hz")))
            val row = model.items.filterIsInstance<RenderItem.Table>().single().rows.single()
            if (hetero) {
                assertTrue(row.notes.contains(UiText.Res("note_supply_heterogeneous")))
                assertNull(row.winnerPartNumber)
            }
            val all = rawTexts(model.items).joinToString(" ").lowercase()
            assertFalse(all.contains("efficien") || all.contains("energy"))
        }
    }

    // Feature: android-app, Property 7: Interpretation summary is compact-and-expandable with backend categories only
    @Test
    fun property7_summaryCategoriesFromBackendOnly() = runTest {
        val cats = Arb.element("documented-fact", "user-assumption", "proposal", "delegation", "invented", "")
        checkAll(100, Arb.list(cats, 0..6)) { categories ->
            val env = EnvelopeParser.parse(Fixtures.envelope("a", emptyList(), summary = Fixtures.summary(categories)))!!
            val summary = RenderMapper.map(env).summary
            assertNotNull(summary)
            val applied = summary!!.groups.first { it.first == "applied" }.second
            val kept = categories.filter { it.isNotEmpty() }
            assertEquals(kept.size, applied.size)
            applied.zip(kept).forEach { (shown, sent) ->
                assertEquals(if (sent in KNOWN_CATEGORIES) sent else "uncategorized", shown.category)
            }
            assertEquals(applied.size, summary.compactCount)
        }
    }

    // Feature: android-app, Property 32: A language switch changes only the UI, never a technical value
    @Test
    fun property32_languageSwitchKeepsValues() = runTest {
        checkAll(100, values, Arb.element("NOT_APPLICABLE", "AVAILABLE")) { v, status ->
            val fig = Fixtures.figure("f", "76-X", value = if (status == "AVAILABLE") v else null, status = status)
            val model = RenderMapper.map(EnvelopeParser.parse(Fixtures.envelope("a", listOf(Fixtures.card("76-X", listOf(fig)))))!!)
            val en = TableUiStrings("en")
            val es = TableUiStrings("es")
            val f = model.items.filterIsInstance<RenderItem.Cards>().single().cards.single().figures.single()
            (listOf(f.value) + f.context).forEach { t ->
                if (t is UiText.Raw) assertEquals(en.resolve(t), es.resolve(t)) // data never translated
            }
            assertEquals("missing_key", es.string("missing_key")) // fallback, never crash
            assertEquals(en.string("state_unavailable"), TableUiStrings("fr").string("state_unavailable"))
        }
    }
}
