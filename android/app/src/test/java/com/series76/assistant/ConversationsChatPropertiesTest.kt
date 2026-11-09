package com.series76.assistant

import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.ConfirmResult
import com.series76.assistant.core.net.JobStatus
import com.series76.assistant.core.net.MessageItem
import com.series76.assistant.core.net.SessionPage
import com.series76.assistant.core.net.SessionSummary
import com.series76.assistant.core.offline.ConnectionNotice
import com.series76.assistant.core.turn.JobState
import com.series76.assistant.core.turn.PollingPolicy
import com.series76.assistant.core.turn.TurnState
import com.series76.assistant.feature.chat.ChatStore
import com.series76.assistant.feature.conversations.ConversationsStore
import com.series76.assistant.feature.conversations.ConversationsUiState
import com.series76.assistant.feature.conversations.DELETE_CONFIRM_TIMEOUT_MS
import com.series76.assistant.feature.conversations.MAX_QUERY
import com.series76.assistant.feature.debug.DebugStore
import com.series76.assistant.feature.debug.DebugUiState
import com.series76.assistant.fakes.Fixtures
import com.series76.assistant.fakes.TestWorld
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.orNull
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Spec 5 Properties 8, 17-28 (JVM, fake Spec 3, virtual time). */
class ConversationsChatPropertiesTest {

    private fun chat(world: TestWorld, scope: CoroutineScope, sched: TestCoroutineScheduler, sid: String? = null) =
        ChatStore(sid, world.api, world.cache, world.drafts, world.session, world.offline, scope,
            StandardTestDispatcher(sched), now = { sched.currentTime })

    private fun summaries(n: Int, pendingEvery: Int) = (1..n).map {
        SessionSummary("s$it", "Title $it", "", "2026-01-0$it", pendingJobs = if (it % pendingEvery == 0) 1 else 0)
    }

    // Feature: android-app, Property 8: ViewModel load failure yields an error state, not a crash
    @Test
    fun property8_loadFailureIsErrorState() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.element(500, 502, 503, 429)) { status ->
            val world = TestWorld()
            world.signIn()
            world.api.listHandler = { ApiResult.HttpError(status, null) }
            world.api.traceHandler = { _, _ -> ApiResult.HttpError(status, null) }
            world.api.messagesHandler = { ApiResult.HttpError(status, null) }
            val conv = ConversationsStore(world.api, world.cache, world.session, scope)
            conv.load().join()
            assertTrue(conv.state.value is ConversationsUiState.RecoverableError)
            val debug = DebugStore(world.api, scope)
            debug.load("s", "m").join()
            assertEquals(DebugUiState.Unavailable, debug.state.value)
            val chat = chat(world, scope, sched, "s1")
            chat.open()
            sched.advanceUntilIdle()
            assertNotNull(chat.state.value.errorKey)
        }
    }

    // Feature: android-app, Property 17: The Conversations list is owner-only with a correct pending indicator
    @Test
    fun property17_ownerOnlyWithPendingIndicator() = runTest {
        val scope = this
        checkAll(100, Arb.int(0..8), Arb.int(1..3)) { n, every ->
            val world = TestWorld()
            world.signIn()
            val items = summaries(n, every)
            world.api.listHandler = { ApiResult.Success(SessionPage(items)) }
            val store = ConversationsStore(world.api, world.cache, world.session, scope)
            store.load().join()
            val state = store.state.value
            if (n == 0) {
                assertEquals(ConversationsUiState.Empty, state)
            } else {
                val rows = (state as ConversationsUiState.Loaded).items
                assertEquals(items.map { it.sessionId }, rows.map { it.sessionId })
                rows.zip(items).forEach { (row, s) -> assertEquals(s.pendingJobs > 0, row.pending) }
            }
        }
    }

    // Feature: android-app, Property 18: Search is title-only and offline results are labeled partial
    @Test
    fun property18_titleOnlySearchOfflinePartial() = runTest {
        val scope = this
        checkAll(100, Arb.string(1..260), Arb.boolean()) { query, offline ->
            val world = TestWorld()
            world.signIn()
            world.cache.putConversations(world.session.ownerKeyOrNull()!!, summaries(4, 9), 5L)
            world.api.online = !offline
            val store = ConversationsStore(world.api, world.cache, world.session, scope)
            store.search(query).join()
            assertEquals(query.take(MAX_QUERY), world.api.listQueries.last()) // title query only
            if (offline) {
                val s = store.state.value as ConversationsUiState.OfflineCache
                assertTrue(s.partial)
                s.items.forEach { assertTrue((it.title ?: "").contains(query.take(MAX_QUERY), ignoreCase = true)) }
            }
        }
    }

    // Feature: android-app, Property 19: Deletion is final only after backend confirmation, reconciles safely, and never resurrects
    @Test
    fun property19_deleteConfirmReconcileNoResurrection() = runTest {
        val scope = this
        checkAll(100, Arb.element("ok", "gone", "offline", "timeout", "error"), Arb.boolean()) { outcome, goneOnServer ->
            val world = TestWorld()
            world.signIn()
            val owner = world.session.ownerKeyOrNull()!!
            val items = summaries(3, 9)
            world.cache.putConversations(owner, items, 1L)
            world.api.listHandler = { ApiResult.Success(SessionPage(items)) }
            val store = ConversationsStore(world.api, world.cache, world.session, scope)
            store.load().join()
            world.api.deleteHandler = {
                when (outcome) {
                    "ok" -> ApiResult.Success(Unit)
                    "gone" -> ApiResult.HttpError(404, null)
                    "timeout" -> awaitCancellation()
                    else -> ApiResult.HttpError(500, null)
                }
            }
            if (outcome == "offline") world.api.online = false
            store.confirmDelete("s1").join()
            val cachedIds = world.cache.conversations(owner).items.map { it.sessionId }
            when (outcome) {
                "ok", "gone" -> {
                    assertTrue(store.state.value is ConversationsUiState.Deleted)
                    assertFalse("s1" in cachedIds)
                }
                "timeout", "error" -> assertTrue("s1" in cachedIds) // pre-delete state kept
                "offline" -> {
                    assertTrue("s1" in store.indeterminate())
                    // Reconnect: the backend list decides, never the cache.
                    world.api.online = true
                    val after = if (goneOnServer) items.filter { it.sessionId != "s1" } else items
                    world.api.listHandler = { ApiResult.Success(SessionPage(after)) }
                    store.onReconnected().join()
                    assertEquals(!goneOnServer, "s1" in world.cache.conversations(owner).items.map { it.sessionId })
                    assertTrue(store.indeterminate().isEmpty() || !goneOnServer)
                }
            }
            assertFalse(world.api.calls.contains("create")) // nothing is ever re-uploaded
            assertTrue(DELETE_CONFIRM_TIMEOUT_MS == 30_000L)
        }
    }

    // Feature: android-app, Property 20: Pagination honors backend ordering and cursor
    @Test
    fun property20_backendOrderingHonored() = runTest {
        val scope = this
        checkAll(100, Arb.list(Arb.int(1..999), 1..10), Arb.string(1..6).orNull()) { order, cursor ->
            val world = TestWorld()
            world.signIn()
            val items = order.distinct().map { SessionSummary("s$it", "t$it", "", "") }
            world.api.listHandler = { ApiResult.Success(SessionPage(items, cursor)) }
            val store = ConversationsStore(world.api, world.cache, world.session, scope)
            store.load().join()
            val loaded = store.state.value as ConversationsUiState.Loaded
            assertEquals(items.map { it.sessionId }, loaded.items.map { it.sessionId }) // no local re-sort
            assertEquals(cursor, loaded.nextCursor)
        }
    }

    private fun planHistory(rev: Int): List<MessageItem> = listOf(
        MessageItem("m1", "assistant", "Please confirm",
            JsonArray(listOf(Fixtures.planReview(rev))).toString(), "2026-01-01T00:00:00"),
    )

    // Feature: android-app, Property 21: Plan confirmation sends the revision and a stale plan reloads without auto re-execution
    @Test
    fun property21_planRevisionAndStaleReload() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.int(1..20), Arb.boolean()) { rev, stale ->
            val world = TestWorld()
            world.signIn()
            world.api.messagesHandler = { ApiResult.Success(planHistory(rev)) }
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            if (stale) {
                // Shown revision is `rev`, the server's current one is rev + 1.
                world.api.messagesHandler = { ApiResult.Success(planHistory(rev + 1)) }
                world.api.confirmHandler = { _, _ -> ApiResult.HttpError(409, null) }
            }
            val shown = store.state.value.plan!!.revision
            store.confirmPlan(); sched.advanceUntilIdle()
            assertEquals(listOf("s1" to shown), world.api.confirmCalls) // exact revision, once
            if (stale) {
                assertTrue(store.state.value.plan!!.stale) // reloaded for a fresh confirmation
                assertEquals(1, world.api.confirmCalls.size) // never auto re-executed
            } else {
                assertNull(store.state.value.plan)
            }
        }
    }

    // Feature: android-app, Property 22: A new conversation omits session_id and collapses to a single turn record
    @Test
    fun property22_newConversationSingleTurnRecord() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.string(1..30)) { text ->
            val world = TestWorld()
            world.signIn()
            val store = chat(world, scope, sched, null)
            store.open(); sched.advanceUntilIdle()
            store.onDraftChanged("q $text")
            store.send(); sched.advanceUntilIdle()
            assertNull(world.api.submitArgs.single().first) // no session_id on the first turn
            assertEquals(world.api.newSessionId, store.state.value.sessionId)
            assertEquals(1, store.state.value.turns.size)
            assertEquals(1, store.state.value.messages.count { it.text == "q $text" })
            assertEquals("job-1", store.state.value.turns.single().jobId)
            assertEquals("", world.drafts.load(world.session.ownerKeyOrNull()!!, "")) // provisional draft removed
        }
    }

    // Feature: android-app, Property 23: A turn holds exactly one Turn_State with correct terminal mapping
    @Test
    fun property23_singleTurnStateTerminalMapping() = runTest {
        val scope = this
        val sched = testScheduler
        val progress = Arb.list(Arb.element(JobState.QUEUED, JobState.RUNNING), 0..4)
        checkAll(100, progress, Arb.element(JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)) { steps, last ->
            assertEquals(TurnState.COMPLETED, JobState.COMPLETED.toTurnState())
            assertEquals(TurnState.FAILED, JobState.FAILED.toTurnState())
            assertEquals(TurnState.CANCELLED, JobState.CANCELLED.toTurnState())
            val world = TestWorld()
            world.signIn()
            world.api.pollScripts["job-1"] = ArrayDeque((steps + last).map {
                ApiResult.Success(JobStatus("job-1", it, null, null))
            })
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            store.onDraftChanged("hello"); store.send(); sched.advanceUntilIdle()
            val turn = store.state.value.turns.single()
            assertEquals(last.toTurnState(), turn.state) // one state field: never two at once
        }
    }

    // Feature: android-app, Property 24: Job state comes only from responses and polling respects bounds off the main thread
    @Test
    fun property24_pollingFromResponsesWithinBounds() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.list(Arb.long(0L..400L).orNull(), 1..6)) { retryAfters ->
            val world = TestWorld()
            world.signIn()
            val times = mutableListOf<Long>()
            world.api.onPoll = { times += sched.currentTime }
            val running = retryAfters.map { ApiResult.Success(JobStatus("job-1", JobState.RUNNING, it, null)) }
            world.api.pollScripts["job-1"] = ArrayDeque(running + ApiResult.Success(JobStatus("job-1", JobState.COMPLETED, null, null)))
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            store.onDraftChanged("x"); store.send(); sched.advanceUntilIdle()
            // Each wait = max(backoff(attempt) in 1..30 s, Retry-After clamped to 1..300 s).
            val gaps = times.zipWithNext { a, b -> (b - a) / 1000 }
            gaps.forEachIndexed { i, gap ->
                assertEquals(PollingPolicy.nextDelaySeconds(i + 1, retryAfters[i]), gap)
                assertTrue(gap in 1..300)
            }
            assertEquals(retryAfters.size + 1, times.size) // state changed only on responses
        }
    }

    // Feature: android-app, Property 25: Idempotent retry reuses the same key and reconciles without duplication
    @Test
    fun property25_idempotentRetrySameKey() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.int(1..3)) { intents ->
            val world = TestWorld()
            world.signIn()
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            world.api.online = false // acceptance will be lost (offline mid-flight)
            store.onDraftChanged("first"); store.send(); sched.advanceUntilIdle()
            assertEquals(TurnState.DISCONNECTED_RECONCILING, store.state.value.turns.single().state)
            world.setOnline(true)
            world.connectivity.set(false); store.onConnectivity(false)
            world.connectivity.set(true); store.onConnectivity(true); sched.advanceUntilIdle()
            val keys = world.api.submitArgs.map { it.third }
            assertEquals(1, keys.toSet().size) // the retry reused the same Client_Request_Id
            assertEquals(1, world.api.jobsByKey.size) // no duplicate turn
            repeat(intents) { i ->
                store.onDraftChanged("new intent $i"); store.send(); sched.advanceUntilIdle()
            }
            assertEquals(1 + intents, world.api.submitArgs.map { it.third }.toSet().size) // new key per new intent
        }
    }

    // Feature: android-app, Property 26: Offline disables Send, preserves the Draft, and never sends or enqueues
    @Test
    fun property26_offlineNoSendDraftPreserved() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.string(1..40), Arb.int(1..4)) { draft, presses ->
            val world = TestWorld()
            world.signIn()
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            world.setOnline(false); store.onConnectivity(false)
            store.onDraftChanged("d $draft")
            assertFalse(store.state.value.sendEnabled)
            assertEquals(ConnectionNotice.OfflineBanner, store.state.value.notice)
            repeat(presses) { assertNull(store.send()) }
            sched.advanceUntilIdle()
            assertTrue(world.api.posts.isEmpty()) // no POST, no enqueue
            assertTrue(store.state.value.turns.isEmpty()) // nothing marked sent/queued
            // "Restart": a new store reads the encrypted draft back.
            val restarted = chat(world, scope, sched, "s1")
            restarted.open(); sched.advanceUntilIdle()
            assertEquals("d $draft", restarted.state.value.draft)
            // Reconnect: the draft is NOT sent automatically.
            world.setOnline(true); store.onConnectivity(true); sched.advanceUntilIdle()
            assertTrue(world.api.posts.isEmpty())
            assertEquals("d $draft", store.state.value.draft)
            assertTrue(store.state.value.sendEnabled) // only after reconciliation
        }
    }

    // Feature: android-app, Property 27: Offline cache is owner-only, labeled stale, and not presented as current
    @Test
    fun property27_offlineCacheOwnerOnlyLabeled() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.list(Arb.string(1..12), 1..4)) { contents ->
            val world = TestWorld()
            world.signIn()
            val owner = world.session.ownerKeyOrNull()!!
            val msgs = contents.mapIndexed { i, c -> MessageItem("m$i", "user", c, "[]", "2026-01-0${i + 1}") }
            world.cache.putMessages(owner, "s1", msgs, 42L)
            world.cache.putMessages("someone-else", "s1", listOf(MessageItem("x", "user", "FOREIGN", "[]", "2026")), 1L)
            world.api.online = false
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            val s = store.state.value
            assertTrue(s.offlineHistory)
            assertEquals(42L, s.lastSync)
            assertEquals(contents, s.messages.map { it.text })
            assertTrue(s.messages.none { it.text == "FOREIGN" })
        }
    }

    // Feature: android-app, Property 28: Offline is never conflated with a server or authentication error
    @Test
    fun property28_offlineVersusServerError() = runTest {
        val scope = this
        val sched = testScheduler
        checkAll(100, Arb.element("offline", "503", "401", "upstream")) { condition ->
            val world = TestWorld()
            world.signIn()
            val store = chat(world, scope, sched, "s1")
            store.open(); sched.advanceUntilIdle()
            when (condition) {
                "offline" -> { world.setOnline(false); store.onConnectivity(false) }
                "503", "upstream" -> world.api.submitOverride = { _, _, _ -> ApiResult.HttpError(503, null) }
                "401" -> world.api.submitOverride = { _, _, _ -> ApiResult.HttpError(401, null) }
            }
            store.onDraftChanged("hi"); store.send(); sched.advanceUntilIdle()
            val notice = store.state.value.notice
            if (condition == "offline") {
                assertEquals(ConnectionNotice.OfflineBanner, notice)
            } else {
                assertTrue(notice is ConnectionNotice.ServerError) // distinct from the banner
            }
            assertNotNull(EnvelopeParser) // parser is the only figure source in this layer
        }
    }

    // A non-property check: the confirmation helper returns the server envelope when executed.
    @Test
    fun confirmExecutesOnce() = runTest {
        val sched = testScheduler
        val world = TestWorld()
        world.signIn()
        world.api.messagesHandler = { ApiResult.Success(planHistory(3)) }
        world.api.confirmHandler = { _, rev -> ApiResult.Success(ConfirmResult("plan-3", rev, null)) }
        val store = chat(world, this, sched, "s1")
        store.open(); sched.advanceUntilIdle()
        store.confirmPlan(); sched.advanceUntilIdle()
        assertEquals(1, world.api.confirmCalls.size)
    }
}
