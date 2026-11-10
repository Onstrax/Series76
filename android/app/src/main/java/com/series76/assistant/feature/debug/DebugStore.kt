package com.series76.assistant.feature.debug

import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.Spec3Api
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull

/** One tool invocation of a turn. `isAttempt` = selected by the model (vs completed by the backend). */
data class ToolCallView(
    val tool: String,
    val origin: String,
    val status: String,
    val arguments: String,
    val ignoredServerArguments: List<String>,
    val isAttempt: Boolean,
    /** What the tool returned (sanitized typed facts / search totals / failure code), as JSON. */
    val returnedData: String = "",
)

/** The turn's overall execution, distinct from its individual tool attempts (Req 8.3). */
data class TraceView(
    val traceId: String,
    val outcome: String,
    val turnStates: List<String>,
    val modelCalls: Int?,
    val durationMs: Long?,
    val toolCalls: List<ToolCallView>,
    val figuresPresented: Int?,
    val figuresWithheld: Int?,
) {
    /** Turns that invoked no tool are identified explicitly (Req 8.4). */
    val invokedNoTool: Boolean get() = toolCalls.isEmpty()
}

sealed interface DebugUiState {
    data object Loading : DebugUiState
    data class Loaded(val trace: TraceView) : DebugUiState
    /** Any denial (401/403/404): one generic state, nothing about existence/owner (Req 8.6). */
    data object Denied : DebugUiState
    data object Unavailable : DebugUiState
}

/** Key fragments never displayed, even if a backend bug let one through (Req 8.5). */
val FORBIDDEN_TRACE_KEYS = listOf(
    "password", "passwd", "secret", "token", "authorization", "cookie", "kek", "dek",
    "api_key", "apikey", "prompt", "bearer", "header", "credential", "private_key",
)

object TraceParser {

    fun scrub(element: JsonElement): JsonElement = when (element) {
        is JsonObject -> JsonObject(
            element.filterKeys { key -> FORBIDDEN_TRACE_KEYS.none { key.lowercase().contains(it) } }
                .mapValues { (_, v) -> scrub(v) },
        )
        is JsonArray -> JsonArray(element.map(::scrub))
        else -> element
    }

    /** Parses the Spec 3 trace shape: `steps`, `tool_args`, `tool_results`, `duration_ms`. */
    fun parse(raw: JsonObject): TraceView {
        val obj = scrub(raw) as JsonObject
        val step = (obj["steps"] as? JsonArray)?.firstOrNull() as? JsonObject ?: JsonObject(emptyMap())
        val results = (obj["tool_results"] as? JsonArray).orEmpty()
        val calls = (obj["tool_args"] as? JsonArray).orEmpty().mapIndexedNotNull { i, e ->
            val c = e as? JsonObject ?: return@mapIndexedNotNull null
            val origin = c.s("origin") ?: "unknown"
            ToolCallView(
                tool = c.s("tool") ?: "unknown",
                origin = origin,
                status = (results.getOrNull(i) as? JsonObject)?.s("status") ?: "",
                arguments = (c["arguments"] ?: JsonObject(emptyMap())).toString(),
                ignoredServerArguments = (c["ignored_server_arguments"] as? JsonArray).orEmpty()
                    .mapNotNull { (it as? JsonPrimitive)?.content },
                isAttempt = origin == "agent",
                returnedData = (results.getOrNull(i) as? JsonObject)?.get("data")
                    ?.takeIf { it !is JsonNull }?.toString() ?: "",
            )
        }
        val duration = (obj["duration_ms"] as? JsonPrimitive)?.longOrNull
        return TraceView(
            traceId = step.s("turn_id") ?: "",
            outcome = step.s("outcome") ?: "",
            turnStates = (step["turn_states"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.content },
            modelCalls = (step["model_calls"] as? JsonPrimitive)?.intOrNull,
            durationMs = duration?.coerceAtLeast(0), // durations are never negative
            toolCalls = calls,
            figuresPresented = (step["figures_presented"] as? JsonPrimitive)?.intOrNull,
            figuresWithheld = (step["figures_withheld"] as? JsonPrimitive)?.intOrNull,
        )
    }

    private fun JsonObject.s(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
}

/**
 * Developer Debug logic (Spec 5 Req 8). Navigation to it is gated by `/me`
 * role in the UI; the backend re-checks role + ownership on every request.
 */
class DebugStore(private val api: Spec3Api, private val scope: CoroutineScope) {
    private val _state = MutableStateFlow<DebugUiState>(DebugUiState.Loading)
    val state: StateFlow<DebugUiState> = _state.asStateFlow()

    fun load(sessionId: String, messageId: String): Job = scope.launch {
        _state.value = DebugUiState.Loading
        val next: DebugUiState = when (val result = api.trace(sessionId, messageId)) {
            is ApiResult.Success -> DebugUiState.Loaded(TraceParser.parse(result.value))
            ApiResult.Offline -> DebugUiState.Unavailable
            // 401 / 403 / 404 (incl. a deleted conversation): one generic denial.
            // Anything else (429 rate limit, 5xx, ...) is a recoverable unavailability.
            is ApiResult.HttpError -> if (result.status in DENIAL_STATUSES) {
                DebugUiState.Denied
            } else {
                DebugUiState.Unavailable
            }
        }
        _state.value = next
    }
}

private val DENIAL_STATUSES = setOf(401, 403, 404)
