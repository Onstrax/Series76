package com.series76.assistant

import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.CredentialsBody
import com.series76.assistant.core.net.Me
import com.series76.assistant.core.net.RefreshOutcome
import com.series76.assistant.core.net.SessionSummary
import com.series76.assistant.core.net.TokenPair
import com.series76.assistant.core.net.TokenRefresher
import com.series76.assistant.core.security.AesGcmCipherBox
import com.series76.assistant.core.security.InMemoryBlobStore
import com.series76.assistant.core.security.SecureTokenStore
import com.series76.assistant.feature.auth.AuthStore
import com.series76.assistant.feature.auth.AuthUiState
import com.series76.assistant.fakes.FakeSpec3Api
import com.series76.assistant.fakes.TestWorld
import com.series76.assistant.fakes.jvmKey
import com.series76.assistant.navigation.DebugGate
import com.series76.assistant.navigation.LaunchRouter
import com.series76.assistant.navigation.StartDestination
import io.kotest.property.Arb
import io.kotest.property.arbitrary.boolean
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import java.io.File
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Spec 5 Properties 9-16, 29, 33 (JVM, fake Spec 3, JVM key in place of the Keystore). */
class AuthSecurityPropertiesTest {

    // Feature: android-app, Property 9: Registration never sends a role and invalid registration creates no session
    @Test
    fun property9_registrationNeverSendsRole() = runTest {
        val scope = this
        val injected = Arb.element("role=developer", "\"role\":\"developer\"", "admin", "x@y.z", "developer@x")
        checkAll(100, injected, Arb.boolean()) { email, rejected ->
            val body = Json.encodeToJsonElement(CredentialsBody.serializer(), CredentialsBody(email, "pw"))
            assertEquals(setOf("email", "password"), body.jsonObject.keys) // no role field can exist
            val world = TestWorld()
            if (rejected) world.api.registerResult = ApiResult.HttpError(422, null)
            val store = AuthStore(world.api, world.tokens, world.session, scope)
            store.register(email, "Secret-pass-1").join()
            assertEquals(email.trim() to "Secret-pass-1", world.api.registerArgs)
            if (rejected) {
                assertEquals(AuthUiState.Error("error_register_failed"), store.state.value)
                assertNull(world.session.session.value) // no local authenticated session
                assertNull(world.tokens.current())
            }
        }
    }

    // Feature: android-app, Property 10: Login failure is generic and the password is not retained
    @Test
    fun property10_loginFailureGenericNoPasswordRetained() = runTest {
        val scope = this
        checkAll(100, Arb.element(400, 401, 403, 404, 409, 422), Arb.string(8..20)) { status, password ->
            val world = TestWorld()
            world.api.loginResult = ApiResult.HttpError(status, null)
            val store = AuthStore(world.api, world.tokens, world.session, scope)
            store.login("someone@example.test", password).join()
            assertEquals(AuthUiState.Error("error_auth_failed"), store.state.value) // same for all
            assertFalse(store.state.value.toString().contains(password))
            assertTrue(world.blobs.allBytes().none { String(it, Charsets.ISO_8859_1).contains(password) })
        }
    }

    // Feature: android-app, Property 11: Refresh rotation is single-winner under concurrency with no replay
    @Test
    fun property11_singleRotationUnderConcurrency() = runTest {
        val scope = this
        checkAll(100, Arb.int(2..12)) { concurrent ->
            val world = TestWorld()
            world.tokens.save(TokenPair("access-1", "refresh-1"))
            val used = mutableListOf<String>()
            val refresher = TokenRefresher(world.tokens, { rt ->
                used += rt
                ApiResult.Success(TokenPair("access-${used.size + 1}", "refresh-${used.size + 1}"))
            }, onSessionClosed = {})
            val outcomes = (1..concurrent).map { scope.async { refresher.refreshAfter("access-1") } }.awaitAll()
            assertEquals(listOf("refresh-1"), used) // exactly one rotation, no replay
            assertTrue(outcomes.all { it == RefreshOutcome.Rotated("access-2") })
        }
    }

    // Feature: android-app, Property 12: Refresh failure closes the session and hides the cache
    @Test
    fun property12_refreshFailureClosesSession() = runTest {
        val scope = this
        checkAll(100, Arb.element(400, 401, 403)) { status ->
            val world = TestWorld()
            world.signIn()
            world.cache.putConversations(world.session.ownerKeyOrNull()!!, listOf(SessionSummary("s1", "Title", "", "")), 1L)
            val refresher = TokenRefresher(world.tokens, { ApiResult.HttpError(status, null) }) {
                world.session.closeLocally()
            }
            assertEquals(RefreshOutcome.Closed, refresher.refreshAfter("access-1"))
            assertNull(world.tokens.current())
            assertNull(world.session.session.value) // nothing is shown without a fresh session
            assertNull(world.session.ownerKeyOrNull())
        }
    }

    // Feature: android-app, Property 13: Logout clears local state even when the backend logout fails
    @Test
    fun property13_logoutFailClosedLocally() = runTest {
        val scope = this
        checkAll(100, Arb.element("ok", "offline", "500", "hang")) { mode ->
            val world = TestWorld()
            world.signIn()
            when (mode) {
                "offline" -> world.api.online = false
                "500" -> world.api.logoutHandler = { ApiResult.HttpError(500, null) }
                "hang" -> world.api.logoutHandler = { awaitCancellation() }
            }
            val store = AuthStore(world.api, world.tokens, world.session, scope)
            store.logout().join()
            assertNull(world.tokens.current())
            assertNull(world.session.session.value)
        }
    }

    // Feature: android-app, Property 14: Account switch purges the prior account and discards its late responses
    @Test
    fun property14_accountSwitchPurgesAndDiscards() = runTest {
        val scope = this
        checkAll(100, Arb.string(3..10), Arb.string(3..10)) { titleA, titleB ->
            val world = TestWorld()
            world.signIn(Me("user-a", "a@x", "user"))
            val ownerA = world.session.ownerKeyOrNull()!!
            world.cache.putConversations(ownerA, listOf(SessionSummary("sa", "A-$titleA", "", "")), 1L)
            val epochA = world.session.epoch.current()
            world.signIn(Me("user-b", "b@x", "user")) // switch
            val ownerB = world.session.ownerKeyOrNull()!!
            assertTrue(world.dao.conversationRows.none { it.ownerKey == ownerA }) // rows purged
            assertFalse(world.keyring.hasKey(ownerA)) // wrapped key shredded
            assertFalse(world.session.epoch.isCurrent(epochA)) // late A responses are discarded
            assertTrue(world.cache.conversations(ownerB).items.none { (it.title ?: "").startsWith("A-") })
            world.cache.putConversations(ownerB, listOf(SessionSummary("sb", "B-$titleB", "", "")), 2L)
            assertEquals(listOf("B-$titleB"), world.cache.conversations(ownerB).items.map { it.title })
        }
    }

    // Feature: android-app, Property 15: Tokens and cache are Keystore-wrapped, never plaintext, and backup-excluded
    @Test
    fun property15_noPlaintextAtRest() = runTest {
        val scope = this
        checkAll(100, Arb.string(12..40), Arb.string(6..30), Arb.string(6..60)) { token, title, message ->
            val world = TestWorld()
            world.tokens.save(TokenPair("acc-$token", "ref-$token"))
            world.signIn()
            val owner = world.session.ownerKeyOrNull()!!
            world.cache.putConversations(owner, listOf(SessionSummary("s1", "T-$title", "", "")), 1L)
            world.cache.putMessages(owner, "s1", listOf(
                com.series76.assistant.core.net.MessageItem("m1", "user", "M-$message", "[]", "2026-01-01"),
            ), 1L)
            val stored = world.blobs.allBytes() + world.dao.conversationRows.map { it.payload } +
                world.dao.messageRows.map { it.payload }
            for (needle in listOf("acc-$token", "ref-$token", "T-$title", "M-$message")) {
                assertTrue(stored.none { String(it, Charsets.ISO_8859_1).contains(needle) })
            }
        }
        val manifest = File("src/main/AndroidManifest.xml").readText()
        assertTrue(manifest.contains("android:allowBackup=\"false\""))
        assertTrue(File("src/main/res/xml/data_extraction_rules.xml").readText().contains("exclude"))
    }

    // Feature: android-app, Property 16: An unavailable Keystore key yields an empty cache with no leakage
    @Test
    fun property16_keyUnavailableEmptyCache() = runTest {
        val scope = this
        checkAll(100, Arb.string(4..20), Arb.boolean()) { title, wrongKey ->
            val world = TestWorld()
            world.signIn()
            val owner = world.session.ownerKeyOrNull()!!
            world.cache.putConversations(owner, listOf(SessionSummary("s1", title, "", "")), 1L)
            if (wrongKey) {
                // A different Keystore key (e.g. after a reset) cannot unwrap the data key.
                val other = com.series76.assistant.core.security.UserKeyring(
                    AesGcmCipherBox { jvmKey() }, world.blobs,
                )
                val cache = com.series76.assistant.core.cache.EncryptedCache(world.dao, other)
                assertTrue(cache.conversations(owner).items.isEmpty())
            } else {
                world.keyAvailable = false
                assertTrue(world.cache.conversations(owner).items.isEmpty())
                val tokens = SecureTokenStore(world.master, InMemoryBlobStore())
                assertNull(tokens.current())
            }
        }
    }

    // Feature: android-app, Property 29: The Developer Debug entry is revealed only to a developer and fails closed
    @Test
    fun property29_debugRevealedOnlyToDeveloper() = runTest {
        val scope = this
        checkAll(100, Arb.element("user", "developer", "admin", "Developer", ""), Arb.element("ok", "offline", "401", "500")) { role, outcome ->
            val result: ApiResult<Me> = when (outcome) {
                "ok" -> ApiResult.Success(Me("id", "e@x", role))
                "offline" -> ApiResult.Offline
                "401" -> ApiResult.HttpError(401, null)
                else -> ApiResult.HttpError(500, null)
            }
            assertEquals(outcome == "ok" && role == "developer", DebugGate.reveal(result))
            assertFalse(DebugGate.reveal(null))
        }
    }

    // Feature: android-app, Property 33: Launch routing follows stored-session acceptance
    @Test
    fun property33_launchRouting() = runTest {
        val scope = this
        checkAll(100, Arb.boolean(), Arb.element("ok", "offline", "401", "500")) { hasToken, me ->
            val world = TestWorld()
            if (hasToken) world.tokens.save(TokenPair("access-1", "refresh-1"))
            world.api.meResult = when (me) {
                "ok" -> ApiResult.Success(Me("u", "e@x", "user"))
                "offline" -> ApiResult.Offline
                "401" -> ApiResult.HttpError(401, null)
                else -> ApiResult.HttpError(500, null)
            }
            val api: FakeSpec3Api = world.api
            val dest = LaunchRouter.route(world.tokens, api, world.session)
            val expected = if (hasToken && me == "ok") StartDestination.CONVERSATIONS else StartDestination.LOGIN
            assertEquals(expected, dest)
        }
    }
}
