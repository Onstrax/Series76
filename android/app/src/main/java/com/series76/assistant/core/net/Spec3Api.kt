package com.series76.assistant.core.net

import com.series76.assistant.core.model.Envelope
import com.series76.assistant.core.model.ErrorEnvelope
import com.series76.assistant.core.turn.JobState
import kotlinx.serialization.json.JsonObject

/**
 * The outcome of one call to the Spec 3 backend.
 *
 * [Offline] means no usable connectivity (no transport, or no response within
 * the connect timeout). It is deliberately a different type from [HttpError]
 * (e.g. a `503` with working transport), so the UI can never attribute a
 * server/auth failure to a lack of internet (Spec 5 Req 7.6).
 */
sealed interface ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>
    data class HttpError(
        val status: Int,
        val error: ErrorEnvelope?,
        val retryAfterSeconds: Long? = null,
    ) : ApiResult<Nothing>
    data object Offline : ApiResult<Nothing>
}

inline fun <T, R> ApiResult<T>.map(transform: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Success -> ApiResult.Success(transform(value))
    is ApiResult.HttpError -> this
    ApiResult.Offline -> ApiResult.Offline
}

data class TokenPair(val accessToken: String, val refreshToken: String)

data class Me(val id: String, val email: String, val role: String) {
    val isDeveloper: Boolean get() = role == "developer"
}

data class SessionSummary(
    val sessionId: String,
    val title: String?,
    val createdAt: String,
    val updatedAt: String,
    val pendingJobs: Int = 0,
)

/** One page of the owner's sessions in the backend's stable order. */
data class SessionPage(val items: List<SessionSummary>, val nextCursor: String? = null)

data class MessageItem(
    val messageId: String,
    val role: String,
    val content: String,
    val blocksJson: String,
    val createdAt: String,
)

data class JobAccepted(val jobId: String, val sessionId: String, val status: JobState)

data class JobStatus(
    val jobId: String,
    val state: JobState,
    val retryAfterSeconds: Long?,
    val envelope: Envelope?,
)

data class ConfirmResult(val planId: String, val planRevision: Int, val envelope: Envelope?)

/** The Spec 3 HTTP contract as seen by the app (implemented over Retrofit). */
interface Spec3Api {
    suspend fun register(email: String, password: String): ApiResult<Unit>
    suspend fun login(email: String, password: String): ApiResult<TokenPair>
    suspend fun refresh(refreshToken: String): ApiResult<TokenPair>
    suspend fun logout(): ApiResult<Unit>
    suspend fun me(): ApiResult<Me>
    suspend fun listSessions(titleQuery: String?, cursor: String?): ApiResult<SessionPage>
    suspend fun messages(sessionId: String): ApiResult<List<MessageItem>>
    suspend fun rename(sessionId: String, title: String): ApiResult<Unit>
    suspend fun delete(sessionId: String): ApiResult<Unit>
    suspend fun converse(sessionId: String?, query: String, clientRequestId: String): ApiResult<Envelope>
    suspend fun submitJob(sessionId: String?, query: String, clientRequestId: String): ApiResult<JobAccepted>
    suspend fun pollJob(jobId: String): ApiResult<JobStatus>
    suspend fun cancelJob(jobId: String): ApiResult<Unit>
    suspend fun confirmPlan(sessionId: String, revision: Int): ApiResult<ConfirmResult>
    suspend fun trace(sessionId: String, messageId: String): ApiResult<JsonObject>
}
