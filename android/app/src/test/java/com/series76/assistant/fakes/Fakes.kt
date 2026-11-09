package com.series76.assistant.fakes

import com.series76.assistant.core.cache.EncryptedCache
import com.series76.assistant.core.cache.InMemoryRawCacheDao
import com.series76.assistant.core.model.Envelope
import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.ConfirmResult
import com.series76.assistant.core.net.JobAccepted
import com.series76.assistant.core.net.JobStatus
import com.series76.assistant.core.net.Me
import com.series76.assistant.core.net.MessageItem
import com.series76.assistant.core.net.SessionPage
import com.series76.assistant.core.net.SessionSummary
import com.series76.assistant.core.net.Spec3Api
import com.series76.assistant.core.net.TokenPair
import com.series76.assistant.core.offline.FakeConnectivity
import com.series76.assistant.core.offline.OfflineController
import com.series76.assistant.core.security.AesGcmCipherBox
import com.series76.assistant.core.security.DraftStore
import com.series76.assistant.core.security.InMemoryBlobStore
import com.series76.assistant.core.security.SecureTokenStore
import com.series76.assistant.core.security.UserKeyring
import com.series76.assistant.core.session.SessionManager
import com.series76.assistant.core.turn.JobState
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import kotlinx.serialization.json.JsonObject

/**
 * An in-memory fake of the Spec 3 HTTP contract (zero network). Every call is
 * recorded; `online = false` makes every call return [ApiResult.Offline].
 */
class FakeSpec3Api : Spec3Api {
    val calls = mutableListOf<String>()
    val posts = mutableListOf<String>()
    var online = true

    var registerArgs: Pair<String, String>? = null
    var registerResult: ApiResult<Unit> = ApiResult.Success(Unit)
    var loginResult: ApiResult<TokenPair> = ApiResult.Success(TokenPair("access-1", "refresh-1"))
    var meResult: ApiResult<Me> = ApiResult.Success(Me("user-a", "a@example.test", "user"))
    var logoutHandler: suspend () -> ApiResult<Unit> = { ApiResult.Success(Unit) }
    var listHandler: suspend (String?) -> ApiResult<SessionPage> = { ApiResult.Success(SessionPage(emptyList())) }
    val listQueries = mutableListOf<String?>()
    var messagesHandler: suspend (String) -> ApiResult<List<MessageItem>> = { ApiResult.Success(emptyList()) }
    var renameResult: ApiResult<Unit> = ApiResult.Success(Unit)
    var deleteHandler: suspend (String) -> ApiResult<Unit> = { ApiResult.Success(Unit) }
    var converseResult: ApiResult<Envelope>? = null

    /** Idempotent job acceptance keyed by Client_Request_Id (as the backend does). */
    val jobsByKey = LinkedHashMap<String, JobAccepted>()
    val submitArgs = mutableListOf<Triple<String?, String, String>>()
    var submitOverride: (suspend (String?, String, String) -> ApiResult<JobAccepted>)? = null
    var newSessionId = "session-new"
    val pollScripts = mutableMapOf<String, ArrayDeque<ApiResult<JobStatus>>>()
    val pollCalls = mutableListOf<String>()
    var confirmHandler: suspend (String, Int) -> ApiResult<ConfirmResult> =
        { _, rev -> ApiResult.Success(ConfirmResult("plan", rev, null)) }
    val confirmCalls = mutableListOf<Pair<String, Int>>()
    var traceHandler: suspend (String, String) -> ApiResult<JsonObject> = { _, _ -> ApiResult.HttpError(404, null) }

    private fun <T> gate(name: String, post: Boolean, block: () -> ApiResult<T>): ApiResult<T> {
        calls += name
        if (post) posts += name
        return if (!online) ApiResult.Offline else block()
    }

    override suspend fun register(email: String, password: String) = gate("register", true) {
        registerArgs = email to password
        registerResult
    }

    override suspend fun login(email: String, password: String) = gate("login", true) { loginResult }
    override suspend fun refresh(refreshToken: String) =
        gate("refresh", true) { ApiResult.Success(TokenPair("access-2", "refresh-2")) }

    override suspend fun logout(): ApiResult<Unit> {
        calls += "logout"; posts += "logout"
        return if (!online) ApiResult.Offline else logoutHandler()
    }

    override suspend fun me() = gate("me", false) { meResult }

    override suspend fun listSessions(titleQuery: String?, cursor: String?): ApiResult<SessionPage> {
        calls += "list"; listQueries += titleQuery
        return if (!online) ApiResult.Offline else listHandler(titleQuery)
    }

    override suspend fun messages(sessionId: String): ApiResult<List<MessageItem>> {
        calls += "messages"
        return if (!online) ApiResult.Offline else messagesHandler(sessionId)
    }

    override suspend fun rename(sessionId: String, title: String) = gate("rename", true) { renameResult }

    override suspend fun delete(sessionId: String): ApiResult<Unit> {
        calls += "delete"; posts += "delete"
        return if (!online) ApiResult.Offline else deleteHandler(sessionId)
    }

    override suspend fun converse(sessionId: String?, query: String, clientRequestId: String) =
        gate("converse", true) { converseResult ?: ApiResult.HttpError(500, null) }

    override suspend fun submitJob(sessionId: String?, query: String, clientRequestId: String): ApiResult<JobAccepted> {
        calls += "submit"; posts += "submit"
        submitArgs += Triple(sessionId, query, clientRequestId)
        if (!online) return ApiResult.Offline
        submitOverride?.let { return it(sessionId, query, clientRequestId) }
        val accepted = jobsByKey.getOrPut(clientRequestId) {
            JobAccepted("job-${jobsByKey.size + 1}", sessionId ?: newSessionId, JobState.QUEUED)
        }
        return ApiResult.Success(accepted)
    }

    var onPoll: () -> Unit = {}

    override suspend fun pollJob(jobId: String): ApiResult<JobStatus> {
        calls += "poll"; pollCalls += jobId
        onPoll()
        if (!online) return ApiResult.Offline
        val script = pollScripts[jobId]
        return script?.removeFirstOrNull()
            ?: ApiResult.Success(JobStatus(jobId, JobState.COMPLETED, null, null))
    }

    override suspend fun cancelJob(jobId: String) = gate("cancel", true) { ApiResult.Success(Unit) }

    override suspend fun confirmPlan(sessionId: String, revision: Int): ApiResult<ConfirmResult> {
        calls += "confirm"; posts += "confirm"; confirmCalls += sessionId to revision
        return if (!online) ApiResult.Offline else confirmHandler(sessionId, revision)
    }

    override suspend fun trace(sessionId: String, messageId: String): ApiResult<JsonObject> {
        calls += "trace"
        return if (!online) ApiResult.Offline else traceHandler(sessionId, messageId)
    }
}

fun jvmKey(): SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

/** A wired set of pure collaborators, as the AppContainer builds them on device. */
class TestWorld(val api: FakeSpec3Api = FakeSpec3Api(), online: Boolean = true) {
    val blobs = InMemoryBlobStore()
    private val key = jvmKey()
    var keyAvailable = true
    val master = AesGcmCipherBox { if (keyAvailable) key else null }
    val tokens = SecureTokenStore(master, blobs)
    val keyring = UserKeyring(master, blobs)
    val drafts = DraftStore(keyring, blobs)
    val dao = InMemoryRawCacheDao()
    val cache = EncryptedCache(dao, keyring)
    val session = SessionManager(tokens, keyring, cache)
    val connectivity = FakeConnectivity(online)
    val offline = OfflineController(connectivity)

    suspend fun signIn(me: Me = Me("user-a", "a@example.test", "user")) {
        tokens.save(TokenPair("access-1", "refresh-1"))
        session.establish(me)
    }

    fun setOnline(value: Boolean) {
        api.online = value
        connectivity.set(value)
    }
}
