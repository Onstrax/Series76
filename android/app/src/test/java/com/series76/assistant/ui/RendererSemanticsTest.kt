package com.series76.assistant.ui

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertIsDisplayed
import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.render.RenderMapper
import com.series76.assistant.fakes.Fixtures
import com.series76.assistant.feature.chat.TypedBlockRenderer
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Compose semantics checks of the renderer (Robolectric, JVM). Written for the
 * Android unit-test task; like every Android test here it is to be run with
 * Gradle (not executed in the assessment authoring environment).
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RendererSemanticsTest {
    @get:Rule val compose = createComposeRule()

    @Test
    fun rendersTypedFiguresNaStateAndChartAlternatives() {
        val na = Fixtures.figure("na", "76-A", value = null, status = "NOT_APPLICABLE")
        val ok = Fixtures.figure("ok", "76-B", value = "150")
        val env = EnvelopeParser.parse(
            Fixtures.envelope(
                "Answer prose with a misleading 999 number.",
                listOf(
                    Fixtures.card("76-A", listOf(na)),
                    Fixtures.card("76-B", listOf(ok)),
                    Fixtures.chart(listOf("76-A" to na, "76-B" to ok), comparable = true),
                ),
            ),
        )!!
        compose.setContent { TypedBlockRenderer(RenderMapper.map(env)) }
        compose.onNodeWithText("Answer prose with a misleading 999 number.").assertIsDisplayed()
        compose.onNodeWithText("torque (in-lbs): 150 in-lbs").assertIsDisplayed()
        compose.onNodeWithText("torque (in-lbs): N/A (not applicable)").assertIsDisplayed()
        // The N/A point is described textually, never drawn as a zero bar.
        assertEquals(1, compose.onAllNodesWithText("76-B: 150 in-lbs").fetchSemanticsNodes().size)
    }
}
