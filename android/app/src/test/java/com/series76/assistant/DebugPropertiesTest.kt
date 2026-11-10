package com.series76.assistant

import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.feature.debug.DebugStore
import com.series76.assistant.feature.debug.DebugUiState
import com.series76.assistant.feature.debug.TraceParser
import com.series76.assistant.fakes.FakeSpec3Api
import io.kotest.property.Arb
import io.kotest.property.arbitrary.element
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import java.io.File
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Spec 5 Properties 30-31 and the Spec 5 traceability check. */
class DebugPropertiesTest {

    private fun trace(calls: List<String>, duration: Long, secret: String) = buildJsonObject {
        put("duration_ms", duration)
        put("authorization", "Bearer $secret")
        put("system_prompt", "You interpret $secret")
        put("steps", buildJsonArray {
            add(buildJsonObject {
                put("turn_id", "turn-1")
                put("outcome", "OK")
                put("model_calls", 2)
                put("turn_states", JsonArray(listOf("ACCEPTED", "COMPLETED").map { JsonPrimitive(it) }))
                put("access_token", secret)
            })
        })
        put("tool_args", buildJsonArray {
            calls.forEachIndexed { i, origin ->
                add(buildJsonObject {
                    put("tool", "get_part_details")
                    put("origin", origin)
                    put("arguments", buildJsonObject {
                        put("part_number", "76-$i")
                        put("api_key", secret)
                        put("access_token", secret)
                    })
                })
            }
        })
        put("tool_results", buildJsonArray {
            calls.forEach { _ -> add(buildJsonObject { put("tool", "get_part_details"); put("status", "OK") }) }
        })
    }

    // Feature: android-app, Property 30: Debug traces show required sanitized fields and distinguish attempts from the turn
    @Test
    fun property30_traceFieldsAndAttemptDistinction() = runTest {
        checkAll(100, Arb.list(Arb.element("agent", "coordinator"), 0..4), Arb.long(-5000L..5000L)) { calls, duration ->
            val view = TraceParser.parse(trace(calls, duration, "zz-secret-zz"))
            assertEquals("turn-1", view.traceId)
            assertEquals(calls.size, view.toolCalls.size)
            assertEquals(calls.isEmpty(), view.invokedNoTool) // no-tool turns identified
            assertTrue((view.durationMs ?: 0) >= 0) // never negative
            view.toolCalls.zip(calls).forEach { (c, origin) ->
                assertEquals(origin == "agent", c.isAttempt) // attempt vs backend-completed read
                assertTrue(c.arguments.contains("part_number"))
            }
        }
    }

    // Feature: android-app, Property 31: Debug exposes no secrets, denies without enumeration, and isolates developers
    @Test
    fun property31_noSecretsGenericDenial() = runTest {
        val scope = this
        checkAll(100, Arb.string(10..24), Arb.element(401, 403, 404)) { secret, denial ->
            val view = TraceParser.parse(trace(listOf("agent"), 10, secret))
            val rendered = view.toString()
            assertFalse(rendered.contains(secret)) // tokens / keys / prompt never displayed
            assertFalse(rendered.lowercase().contains("bearer") || rendered.contains("You interpret"))
            val api = FakeSpec3Api()
            api.traceHandler = { _, _ -> ApiResult.HttpError(denial, null) }
            val store = DebugStore(api, scope)
            store.load("someone-elses-session", "message").join()
            assertEquals(DebugUiState.Denied, store.state.value) // same state for 401/403/404
        }
    }

    @Test
    fun traceability_everyPropertyTaggedExactlyOnce() {
        val tag = Regex("""// Feature: android-app, Property (\d+): \S""")
        val counts = mutableMapOf<Int, Int>()
        File("src/test/java").walkTopDown().filter { it.isFile && it.extension == "kt" }.forEach { f ->
            tag.findAll(f.readText()).forEach { m ->
                val n = m.groupValues[1].toInt()
                counts[n] = (counts[n] ?: 0) + 1
            }
        }
        assertEquals((1..33).toSet(), counts.keys)
        assertTrue(counts.values.all { it == 1 })
    }

    @Test
    fun noSecretsInSourcesOrResources() {
        val suspicious = Regex("""(sk-[A-Za-z0-9]{16,}|OPENROUTER_API_KEY\s*=\s*\S+|password\s*=\s*"[^"]+")""")
        File("src").walkTopDown().filter { it.isFile && (it.extension == "kt" || it.extension == "xml") }
            .filterNot { it.path.contains("src/test") }
            .forEach { f -> assertFalse(f.path, suspicious.containsMatchIn(f.readText())) }
        val config = File("src/main/res/xml/network_security_config.xml").readText()
        assertTrue(config.contains("base-config cleartextTrafficPermitted=\"false\""))
        assertTrue(config.contains("<domain includeSubdomains=\"false\">10.0.2.2</domain>"))
        assertEquals(1, Regex("<domain ").findAll(config).count()) // only the emulator loopback
    }

    // Assessment: the Debug screen shows the tools, their parameters and the data they returned.
    @Test
    fun returnedDataIsShownPerToolCall() {
        val raw = buildJsonObject {
            put("steps", buildJsonArray { add(buildJsonObject { put("turn_id", "t") }) })
            put("tool_args", buildJsonArray {
                add(buildJsonObject {
                    put("tool", "get_part_details")
                    put("origin", "agent")
                    put("arguments", buildJsonObject { put("part_number", "76-100") })
                })
            })
            put("tool_results", buildJsonArray {
                add(buildJsonObject {
                    put("tool", "get_part_details")
                    put("status", "OK")
                    put("data", buildJsonObject {
                        put("facts", buildJsonArray {
                            add(buildJsonObject {
                                put("field", "On/Off:torque_inlbs")
                                put("value", "100")
                                put("unit", "in-lbs")
                            })
                        })
                    })
                })
            })
        }
        val call = TraceParser.parse(raw).toolCalls.single()
        assertTrue(call.arguments.contains("76-100"))
        assertTrue(call.returnedData.contains("On/Off:torque_inlbs"))
        assertTrue(call.returnedData.contains("100"))
    }
}
