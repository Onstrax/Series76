package com.series76.assistant.navigation

import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.Me
import com.series76.assistant.core.net.Spec3Api
import com.series76.assistant.core.net.TokenStore
import com.series76.assistant.core.session.SessionManager
import kotlinx.serialization.Serializable

/**
 * Type-safe destinations (Navigation Compose). Routes carry only lightweight
 * identifiers — never a message or a conversation payload (Spec 5 Req 1.3).
 */
@Serializable data object LoginRoute

@Serializable data object RegisterRoute

@Serializable data object ConversationsRoute

/** `sessionId == null` starts a new conversation (first turn sends no session_id). */
@Serializable data class ChatRoute(val sessionId: String? = null)

/** Developer-only trace detail for one assistant message. */
@Serializable data class DebugRoute(val sessionId: String, val messageId: String)

enum class StartDestination { LOGIN, CONVERSATIONS }

/**
 * Launch routing (Req 2.3; Property 33): Conversations iff a stored token
 * exists AND the backend accepts it (`/me` succeeds, refreshing once via the
 * HTTP layer if needed); otherwise Login.
 */
object LaunchRouter {
    suspend fun route(tokens: TokenStore, api: Spec3Api, session: SessionManager): StartDestination {
        if (tokens.current() == null) return StartDestination.LOGIN
        return when (val me = api.me()) {
            is ApiResult.Success -> {
                session.establish(me.value)
                StartDestination.CONVERSATIONS
            }
            is ApiResult.HttpError -> {
                if (me.status == 401) session.closeLocally()
                StartDestination.LOGIN
            }
            ApiResult.Offline -> StartDestination.LOGIN
        }
    }
}

/**
 * The Developer Debug entry is revealed iff `/me` succeeded and reports role
 * `developer`; any failure hides it (fail closed, Req 2.4, 2.5; Property 29).
 * The backend re-verifies role and ownership on every trace request.
 */
object DebugGate {
    fun reveal(me: ApiResult<Me>?): Boolean =
        me is ApiResult.Success && me.value.role == "developer"
}
