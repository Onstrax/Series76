package com.series76.assistant

import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.JobStatus
import com.series76.assistant.core.net.Me
import com.series76.assistant.core.net.MessageItem
import com.series76.assistant.core.net.SessionPage
import com.series76.assistant.core.net.SessionSummary
import com.series76.assistant.core.render.RenderItem
import com.series76.assistant.core.render.RenderMapper
import com.series76.assistant.core.render.TableUiStrings
import com.series76.assistant.core.render.UiText
import com.series76.assistant.core.turn.JobState
import com.series76.assistant.fakes.Fixtures
import com.series76.assistant.fakes.TestWorld
import com.series76.assistant.feature.auth.AuthStore
import com.series76.assistant.feature.chat.ChatStore
import com.series76.assistant.feature.conversations.ConversationsStore
import com.series76.assistant.feature.debug.DebugStore
import com.series76.assistant.feature.debug.DebugUiState
import com.series76.assistant.navigation.DebugGate
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Spec 6 Android QA properties (Test_Level 10, JVM). They exercise the Spec 5
 * client through the same fakes as the Spec 5 suite. Like every Android test
 * in this repository they must be run with Gradle (`./gradlew test`); they
 * were not executed in the authoring environment (no Android SDK).
 */
class Spec6AndroidQAPropertiesTest {

    private fun chat(world: TestWorld, scope: CoroutineScope, sched: TestCoroutineScheduler, sid: String? = "s1") =
        ChatStore(sid, world.api, world.cache, world.drafts, world.session, world.offline, scope,
            StandardTestDispatcher(sched), now = { sched.currentTime })

    // Feature: evaluation-and-reproducibility, Property 29: Android logout/switch purges prior cache
    @Test
    fun property29_logoutOrSwitchPurgesPriorCache() = runTest {
        val scope = this
        checkAll(100, Arb.string(3..12), Arb.boolean()) { title, switch ->
            val world = TestWorld()
            world.signIn(Me("user-a", "a@x", "user"))
            val ownerA = world.session.ownerKeyOrNull()!!
            world.cache.putConversations(ownerA, listOf(SessionSummary("sa", "A-$title", "", "")), 1L)
            world.cache.putMessages(ownerA, "sa", listOf(MessageItem("m1", "user", "A-$title", "[]", "")), 1L)
            if (switch) {
                world.signIn(Me("user-b", "b@x", "user"))
            } else {
                AuthStore(world.api, world.tokens, world.session, scope).logout().join()
            }
            // Purged from on-device storage, and the wrapped key is shredded.
            assertTrue(world.dao.conversationRows.none { it.ownerKey == ownerA })
            assertTrue(world.dao.messageRows.none { it.ownerKey == ownerA })
            assertFalse(world.keyring.hasKey(ownerA))
            // Not retrievable through any client query.
            assertTrue(world.cache.conversations(ownerA).items.isEmpty())
            assertTrue(world.cache.messages(ownerA, "sa").items.isEmpty())
            world.session.ownerKeyOrNull()?.let { current ->
                assertTrue(world.cache.conversations(current).items.none { (it.title ?: "").startsWith("A-") })
            }
        }
    }

    // Feature: evaluation-and-reproducibility, Property 30: Offline remote-delete is not restored
    @Test
    fun property30_offlineRemoteDeleteNotRestored() = runTest {
        val scope = this
        checkAll(100, Arb.int(2..6), Arb.int(0..5)) { n, victimIndex ->
            val world = TestWorld()
            world.signIn()
            val owner = world.session.ownerKeyOrNull()!!
            val items = (1..n).map { SessionSummary("s$it", "T$it", "", "2026-01-01") }
            val victim = items[victimIndex % n].sessionId
            world.cache.putConversations(owner, items, 1L)
            world.api.online = false
            val store = ConversationsStore(world.api, world.cache, world.session, scope)
            store.load().join() // offline: shows the cache
            // Meanwhile the conversation was deleted on the server.
            world.api.online = true
            world.api.listHandler = { ApiResult.Success(SessionPage(items.filter { it.sessionId != victim })) }
            store.onReconnected().join()
            assertFalse(victim in world.cache.conversations(owner).items.map { it.sessionId })
            assertFalse(world.api.posts.any { it == "converse" || it == "submit" }) // never re-uploaded
            store.load().join()
            assertFalse(victim in world.cache.conversations(owner).items.map { it.sessionId })
        }
    }

    // Feature: evaluation-and-reproducibility, Property 31: Accessibility holds across elements and themes
    @Test
    fun property31_textAlternativesAndLabels() = runTest {
        checkAll(100, Arb.list(Arb.element("100", "150", null), 1..5), Arb.element("en", "es")) { values, lang ->
            val strings = TableUiStrings(lang)
            val points = values.mapIndexed { i, v -> "76-$i" to Fixtures.figure("f$i", "76-$i", value = v) }
            val env = EnvelopeParser.parse(Fixtures.envelope("answer", listOf(Fixtures.chart(points, comparable = true))))!!
            val charts = RenderMapper.map(env).items.filterIsInstance<RenderItem.Chart>()
            for (chart in charts) {
                // Every chart has a textual alternative per point, carrying the unit or an explicit state.
                assertEquals(values.size, chart.textAlternatives.size)
                chart.textAlternatives.zip(values).forEach { (alt, v) ->
                    val text = strings.resolve(alt)
                    assertTrue(text.isNotBlank())
                    if (v != null) assertTrue(text.contains("in-lbs"))
                }
                assertTrue(chart.metricLabel.isNotBlank())
            }
            // No UiText key is left unresolved (raw key shown) in either language.
            charts.flatMap { it.textAlternatives }.filterIsInstance<UiText.Res>().forEach {
                assertFalse(strings.resolve(it) == it.key)
            }
        }
    }

    // Feature: evaluation-and-reproducibility, Property 33: Developer Debug grants no trace content without the role
    @Test
    fun property33_debugWithoutRoleShowsNoTrace() = runTest {
        val scope = this
        checkAll(100, Arb.element("user", "", "admin", "Developer"), Arb.element(401, 403, 404)) { role, denial ->
            val world = TestWorld()
            world.signIn(Me("u", "e@x", role))
            assertFalse(DebugGate.reveal(ApiResult.Success(Me("u", "e@x", role))))
            // Direct navigation still reaches the screen; the backend denies, nothing is shown.
            world.api.traceHandler = { _, _ -> ApiResult.HttpError(denial, null) }
            val store = DebugStore(world.api, scope)
            store.load("s1", "m1").join()
            assertEquals(DebugUiState.Denied, store.state.value)
        }
    }

    // Feature: evaluation-and-reproducibility, Property 34: Heavy work stays off the main thread
    @Test
    fun property34_pollingStopsWhenScreenStopped() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.int(1..4)) { runningPolls ->
            val world = TestWorld()
            world.signIn()
            world.api.pollScripts["job-1"] = ArrayDeque(
                List(runningPolls) { ApiResult.Success(JobStatus("job-1", JobState.RUNNING, 1L, null)) } +
                    ApiResult.Success(JobStatus("job-1", JobState.COMPLETED, null, null)),
            )
            val store = chat(world, scope, sched)
            store.open(); sched.advanceUntilIdle()
            store.onScreenStopped()
            store.onDraftChanged("q"); store.send()
            sched.advanceTimeBy(600_000) // ten minutes stopped
            assertTrue(world.api.pollCalls.isEmpty()) // no request while stopped
            store.onScreenStarted(); sched.advanceUntilIdle()
            assertEquals(runningPolls + 1, world.api.pollCalls.size) // resumes and completes
        }
    }

    // Feature: evaluation-and-reproducibility, Property 35: Offline draft is preserved and not auto-sent
    @Test
    fun property35_offlineDraftPreservedNotAutoSent() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.string(1..60), Arb.int(1..3)) { draft, flaps ->
            val world = TestWorld()
            world.signIn()
            val store = chat(world, scope, sched)
            store.open(); sched.advanceUntilIdle()
            world.setOnline(false); store.onConnectivity(false)
            store.onDraftChanged(draft)
            repeat(flaps) {
                world.setOnline(true); store.onConnectivity(true); sched.advanceUntilIdle()
                world.setOnline(false); store.onConnectivity(false)
            }
            world.setOnline(true); store.onConnectivity(true); sched.advanceUntilIdle()
            assertEquals(draft, store.state.value.draft) // unchanged
            assertTrue(world.api.submitArgs.isEmpty()) // not transmitted
            store.send(); sched.advanceUntilIdle() // explicit new send
            assertEquals(listOf(draft), world.api.submitArgs.map { it.second })
        }
    }

}
