package com.series76.assistant.core.net

import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.turn.JobState
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.intOrNull
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.ResponseBody
import okhttp3.Route
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** Request bodies. Registration carries ONLY email + password — no role (Req 3.1). */
@Serializable
data class CredentialsBody(val email: String, val password: String)

@Serializable
data class RefreshBody(val refresh_token: String)

@Serializable
data class RenameBody(val title: String)

/** `session_id` is omitted entirely when null (a new conversation, Req 6.1). */
@Serializable
data class TurnBody(
    val query: String,
    val client_request_id: String,
    val session_id: String? = null,
)

/** Retrofit surface over the Spec 3 endpoints. */
interface Spec3Service {
    @POST("api/auth/register") suspend fun register(@Body body: CredentialsBody): Response<ResponseBody>
    @POST("api/auth/login") suspend fun login(@Body body: CredentialsBody): Response<ResponseBody>
    @POST("api/auth/refresh") suspend fun refresh(@Body body: RefreshBody): Response<ResponseBody>
    @POST("api/auth/logout") suspend fun logout(): Response<ResponseBody>
    @GET("api/auth/me") suspend fun me(): Response<ResponseBody>
    @GET("api/sessions") suspend fun sessions(@Query("q") q: String?): Response<ResponseBody>
    @GET("api/sessions/{id}/messages") suspend fun messages(@Path("id") id: String): Response<ResponseBody>
    @PATCH("api/sessions/{id}") suspend fun rename(@Path("id") id: String, @Body body: RenameBody): Response<ResponseBody>
    @DELETE("api/sessions/{id}") suspend fun delete(@Path("id") id: String): Response<ResponseBody>
    @POST("api/conversation") suspend fun converse(@Body body: TurnBody): Response<ResponseBody>
    @POST("api/conversation/jobs") suspend fun submitJob(@Body body: TurnBody): Response<ResponseBody>
    @GET("api/jobs/{id}") suspend fun job(@Path("id") id: String): Response<ResponseBody>
    @POST("api/jobs/{id}/cancel") suspend fun cancel(@Path("id") id: String): Response<ResponseBody>
    @POST("api/sessions/{id}/plans/{rev}/confirm")
    suspend fun confirm(@Path("id") id: String, @Path("rev") rev: Int): Response<ResponseBody>
    @GET("api/sessions/{id}/messages/{mid}/trace")
    suspend fun trace(@Path("id") id: String, @Path("mid") mid: String): Response<ResponseBody>
}

/** Attaches the current access token (read off the main thread by OkHttp). */
class BearerInterceptor(private val tokens: TokenStore) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val token = runBlocking { tokens.current()?.accessToken }
        val request = if (token != null) {
            chain.request().newBuilder().header("Authorization", "Bearer $token").build()
        } else {
            chain.request()
        }
        return chain.proceed(request)
    }
}

/** On `401`: one synchronized rotation, then a single retry (never a loop). */
class RefreshAuthenticator(private val refresher: TokenRefresher) : Authenticator {
    override fun authenticate(route: Route?, response: okhttp3.Response): Request? {
        val header = response.request.header("Authorization") ?: return null
        if (response.priorResponse != null) return null // already retried once
        val failed = header.removePrefix("Bearer ").trim()
        return when (val outcome = runBlocking { refresher.refreshAfter(failed) }) {
            is RefreshOutcome.Rotated ->
                response.request.newBuilder().header("Authorization", "Bearer ${outcome.accessToken}").build()
            else -> null
        }
    }
}

class RetrofitSpec3Api(
    private val baseUrl: String,
    tokens: TokenStore,
    onSessionClosed: suspend () -> Unit,
    baseClient: OkHttpClient = OkHttpClient(),
) : Spec3Api {

    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private val plainClient = baseClient.newBuilder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .build()

    private fun retrofit(client: OkHttpClient): Spec3Service = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(Spec3Service::class.java)

    /** Unauthenticated calls (register / login / refresh) never carry a token. */
    private val authService = retrofit(plainClient)

    val refresher = TokenRefresher(tokens, { rt -> refresh(rt) }, onSessionClosed)

    private val service = retrofit(
        plainClient.newBuilder()
            .addInterceptor(BearerInterceptor(tokens))
            .authenticator(RefreshAuthenticator(refresher))
            .build(),
    )

    override suspend fun register(email: String, password: String) =
        call({ authService.register(CredentialsBody(email, password)) }) { }

    override suspend fun login(email: String, password: String) =
        call({ authService.login(CredentialsBody(email, password)) }, ::tokenPair)

    override suspend fun refresh(refreshToken: String) =
        call({ authService.refresh(RefreshBody(refreshToken)) }, ::tokenPair)

    override suspend fun logout() = call({ service.logout() }) { }

    override suspend fun me() = call({ service.me() }) { body ->
        val o = obj(body)
        Me(o.s("id")!!, o.s("email")!!, o.s("role")!!)
    }

    override suspend fun listSessions(titleQuery: String?, cursor: String?) =
        call({ service.sessions(titleQuery?.takeIf { it.isNotEmpty() }) }) { body ->
            val items = (json.parseToJsonElement(body) as JsonArray).map { e ->
                val o = e as JsonObject
                SessionSummary(
                    sessionId = o.s("session_id")!!,
                    title = o.s("title"),
                    createdAt = o.s("created_at") ?: "",
                    updatedAt = o.s("updated_at") ?: "",
                    pendingJobs = (o["pending_jobs"] as? JsonPrimitive)?.intOrNull ?: 0,
                )
            }
            SessionPage(items, nextCursor = null)
        }

    override suspend fun messages(sessionId: String) = call({ service.messages(sessionId) }) { body ->
        (json.parseToJsonElement(body) as JsonArray).map { e ->
            val o = e as JsonObject
            MessageItem(
                messageId = o.s("message_id")!!,
                role = o.s("role") ?: "assistant",
                content = o.s("content") ?: "",
                blocksJson = (o["blocks"] ?: JsonArray(emptyList())).toString(),
                createdAt = o.s("created_at") ?: "",
            )
        }
    }

    override suspend fun rename(sessionId: String, title: String) =
        call({ service.rename(sessionId, RenameBody(title)) }) { }

    override suspend fun delete(sessionId: String) = call({ service.delete(sessionId) }) { }

    override suspend fun converse(sessionId: String?, query: String, clientRequestId: String) =
        call({ service.converse(TurnBody(query, clientRequestId, sessionId)) }) { body ->
            EnvelopeParser.parse(body) ?: error("response violates the session_id/answer contract")
        }

    override suspend fun submitJob(sessionId: String?, query: String, clientRequestId: String) =
        call({ service.submitJob(TurnBody(query, clientRequestId, sessionId)) }) { body ->
            val o = obj(body)
            JobAccepted(o.s("job_id")!!, o.s("session_id")!!, JobState.parse(o.s("status")) ?: JobState.QUEUED)
        }

    override suspend fun pollJob(jobId: String): ApiResult<JobStatus> {
        var retryAfter: Long? = null
        return call({ service.job(jobId).also { retryAfter = retryAfterSeconds(it) } }) { body ->
            val o = obj(body)
            JobStatus(
                jobId = o.s("job_id") ?: jobId,
                state = JobState.parse(o.s("status")) ?: error("unknown job state"),
                retryAfterSeconds = retryAfter,
                envelope = (o["response"] as? JsonObject)?.let(EnvelopeParser::parseObject),
            )
        }
    }

    override suspend fun cancelJob(jobId: String) = call({ service.cancel(jobId) }) { }

    override suspend fun confirmPlan(sessionId: String, revision: Int) =
        call({ service.confirm(sessionId, revision) }) { body ->
            val o = obj(body)
            ConfirmResult(
                planId = o.s("plan_id") ?: "",
                planRevision = (o["plan_revision"] as? JsonPrimitive)?.intOrNull ?: revision,
                envelope = (o["result"] as? JsonObject)?.let(EnvelopeParser::parseObject),
            )
        }

    override suspend fun trace(sessionId: String, messageId: String) =
        call({ service.trace(sessionId, messageId) }) { body -> obj(body) }

    // --- plumbing -------------------------------------------------------------

    private fun tokenPair(body: String): TokenPair {
        val o = obj(body)
        return TokenPair(o.s("access_token")!!, o.s("refresh_token")!!)
    }

    private fun obj(body: String): JsonObject = json.parseToJsonElement(body) as JsonObject

    private fun JsonObject.s(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun retryAfterSeconds(response: Response<*>): Long? =
        response.headers()["Retry-After"]?.trim()?.toLongOrNull()

    private suspend fun <T> call(
        request: suspend () -> Response<ResponseBody>,
        parse: (String) -> T,
    ): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) {
            val text = response.body()?.string().orEmpty()
            try {
                ApiResult.Success(parse(text))
            } catch (e: RuntimeException) {
                ApiResult.HttpError(response.code(), null) // malformed body: a server fault
            }
        } else {
            val text = response.errorBody()?.string().orEmpty()
            ApiResult.HttpError(response.code(), EnvelopeParser.parseError(text), retryAfterSeconds(response))
        }
    } catch (e: IOException) {
        // No transport / no response within the timeout: offline, never a server error.
        ApiResult.Offline
    }
}
