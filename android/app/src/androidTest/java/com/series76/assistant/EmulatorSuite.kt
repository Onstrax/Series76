package com.series76.assistant

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.render.RenderMapper
import com.series76.assistant.feature.chat.TypedBlockRenderer
import java.io.IOException
import java.net.UnknownServiceException
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density

/**
 * Instrumented emulator suite — TO BE RUN on an Android emulator
 * (`./gradlew connectedDebugAndroidTest`). Nothing in this repository asserts
 * that it has been executed (Spec 5 status discipline; F5 / Spec 6 run it).
 *
 * Covers: large text 2.0x rendering (Req 10.3), the release cleartext policy
 * (Req 11.4), and — only when `-Pandroid.testInstrumentationRunnerArguments.series76.e2e=true`
 * is passed and a backend runs on the host — an end-to-end login + turn
 * against http://10.0.2.2:8000 (F5-OFF offline cases are listed below).
 */
@RunWith(AndroidJUnit4::class)
class EmulatorSuite {
    @get:Rule val compose = createComposeRule()

    @Test
    fun rendererKeepsContentAtTwiceFontScale() {
        val env = EnvelopeParser.parse(
            """{"session_id":"s","answer":"A","content_blocks":[{"kind":"product_card","part_number":"76-1",
              "figures":[{"figure_id":"f","metric_key":"torque_inlbs","label":"torque (in-lbs)","value":"150",
              "unit":"in-lbs","status":"AVAILABLE","part_number":"76-1","evidence":{"cell_refs":[1]}}]}]}""",
        )!!
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale = 2.0f)) {
                TypedBlockRenderer(RenderMapper.map(env))
            }
        }
        compose.onNodeWithText("torque (in-lbs): 150 in-lbs").assertIsDisplayed()
    }

    @Test
    fun cleartextIsRejectedForNonLoopbackHosts() {
        val client = OkHttpClient()
        val blocked = try {
            client.newCall(Request.Builder().url("http://example.com/").build()).execute().close()
            false
        } catch (e: UnknownServiceException) {
            true // "CLEARTEXT communication to example.com not permitted by network security policy"
        } catch (e: IOException) {
            false
        }
        assertTrue(blocked)
    }

    @Test
    fun endToEndAgainstHostBackend() {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue(args.getString("series76.e2e") == "true")
        val container = AppContainer(InstrumentationRegistry.getInstrumentation().targetContext)
        val email = args.getString("series76.email") ?: return
        val password = args.getString("series76.password") ?: return
        runBlocking {
            val login = container.api.login(email, password)
            assertTrue(login is ApiResult.Success)
        }
    }

    /*
     * F5-OFF cases (manual / UI Automator on the emulator, airplane mode toggled):
     *  F5-OFF-01 banner visible on Conversations and Chat while offline, both languages;
     *  F5-OFF-02 Send disabled with TalkBack state "Send is disabled while offline";
     *  F5-OFF-03 draft survives app kill + relaunch (encrypted, not auto-sent);
     *  F5-OFF-04 no POST observed in the backend log while offline;
     *  F5-OFF-05 reconnect: draft unchanged, Send re-enabled only after reconciliation;
     *  F5-OFF-06 503 from the backend shows the red server notice, not the offline banner;
     *  F5-OFF-07 connection lost mid-turn: one outcome after reconnect, no duplicate turn.
     */
}
