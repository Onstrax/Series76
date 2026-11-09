package com.series76.assistant.core.turn

import java.util.UUID

/** Client-side UI state of one chat turn (Spec 5 Req 6.2): exactly one at a time. */
enum class TurnState {
    DRAFT, SUBMITTING, QUEUED, RUNNING, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION,
    COMPLETED, FAILED, CANCELLED, DISCONNECTED_RECONCILING;

    val isTerminal: Boolean get() = this == COMPLETED || this == FAILED || this == CANCELLED
}

/** Server-authoritative job state (Spec 3), observed only by polling. */
enum class JobState {
    QUEUED, RUNNING, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION, COMPLETED, FAILED,
    CANCELLED, STALE_PLAN, CATALOG_WITHDRAWN;

    /** True for states after which polling stops (terminal, or waiting on the user). */
    val stopsPolling: Boolean
        get() = this != QUEUED && this != RUNNING

    /** The single Turn_State a job state maps to (terminal mapping per Req 6.6). */
    fun toTurnState(): TurnState = when (this) {
        QUEUED -> TurnState.QUEUED
        RUNNING -> TurnState.RUNNING
        NEEDS_CLARIFICATION -> TurnState.NEEDS_CLARIFICATION
        AWAITING_CONFIRMATION, STALE_PLAN -> TurnState.AWAITING_CONFIRMATION
        COMPLETED -> TurnState.COMPLETED
        FAILED, CATALOG_WITHDRAWN -> TurnState.FAILED
        CANCELLED -> TurnState.CANCELLED
    }

    companion object {
        fun parse(raw: String?): JobState? = entries.firstOrNull { it.name == raw }
    }
}

/**
 * One turn record. The state is a single field, so a turn can never hold two
 * states at once; `clientRequestId` is generated once per user intent.
 */
data class TurnRecord(
    val localId: String,
    val query: String,
    val clientRequestId: String,
    val state: TurnState,
    val sessionId: String? = null,
    val jobId: String? = null,
)

/** Idempotency keys: one per genuine user intent, reused on transport retries. */
class ClientRequestIds(private val generator: () -> String = { UUID.randomUUID().toString() }) {
    private val byIntent = LinkedHashMap<String, String>()

    /** The key for an intent; the same intent always gets the same key until resolved. */
    fun keyFor(intentId: String): String = byIntent.getOrPut(intentId) { generator() }

    /** Discard a key once the acceptance outcome is known (accepted or rejected). */
    fun resolve(intentId: String) {
        byIntent.remove(intentId)
    }

    fun pending(intentId: String): String? = byIntent[intentId]
}

/**
 * Polling cadence (Req 1.7, 6.4): exponential backoff starting at 1 s and
 * doubling to a 30 s ceiling; a server `Retry-After` is honored, clamped to
 * 1-300 s, as a lower bound on the next wait.
 */
object PollingPolicy {
    const val INITIAL_SECONDS = 1L
    const val MAX_BACKOFF_SECONDS = 30L
    const val RETRY_AFTER_MIN = 1L
    const val RETRY_AFTER_MAX = 300L

    fun backoffSeconds(attempt: Int): Long {
        var d = INITIAL_SECONDS
        repeat(attempt.coerceAtLeast(0)) { d = (d * 2).coerceAtMost(MAX_BACKOFF_SECONDS) }
        return d
    }

    fun nextDelaySeconds(attempt: Int, retryAfterSeconds: Long?): Long {
        val backoff = backoffSeconds(attempt)
        val floor = retryAfterSeconds?.coerceIn(RETRY_AFTER_MIN, RETRY_AFTER_MAX) ?: 0L
        return maxOf(backoff, floor)
    }
}
