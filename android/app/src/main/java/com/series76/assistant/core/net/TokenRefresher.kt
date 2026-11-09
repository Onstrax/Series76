package com.series76.assistant.core.net

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Where the current token pair lives (Keystore-backed in the app). */
interface TokenStore {
    suspend fun current(): TokenPair?
    suspend fun save(pair: TokenPair)
    suspend fun clear()
}

/**
 * Single-flight refresh rotation (Spec 5 Req 1.8, 3.4, 9.6; Property 11).
 *
 * Every request that saw a `401` calls [refreshAfter] with the access token it
 * used. Under one mutex, only the first caller whose token is still current
 * performs the rotation; later callers find a newer token and reuse it. A
 * rotated refresh token is therefore never replayed, and exactly one rotation
 * is consumed per stale token. On failure the session is closed.
 */
class TokenRefresher(
    private val store: TokenStore,
    private val rotate: suspend (refreshToken: String) -> ApiResult<TokenPair>,
    private val onSessionClosed: suspend () -> Unit,
) {
    private val mutex = Mutex()

    /** Rotate (or reuse an already-rotated token) after a `401`. */
    suspend fun refreshAfter(failedAccessToken: String?): RefreshOutcome = mutex.withLock {
        val current = store.current() ?: return@withLock RefreshOutcome.Closed
        if (failedAccessToken != null && current.accessToken != failedAccessToken) {
            // Another caller already rotated: reuse, never replay the old refresh token.
            return@withLock RefreshOutcome.Rotated(current.accessToken)
        }
        when (val result = rotate(current.refreshToken)) {
            is ApiResult.Success -> {
                store.save(result.value)
                RefreshOutcome.Rotated(result.value.accessToken)
            }
            // No connectivity is not an authentication failure: keep the session.
            ApiResult.Offline -> RefreshOutcome.Offline
            is ApiResult.HttpError -> {
                store.clear()
                onSessionClosed()
                RefreshOutcome.Closed
            }
        }
    }
}

sealed interface RefreshOutcome {
    data class Rotated(val accessToken: String) : RefreshOutcome
    data object Offline : RefreshOutcome
    data object Closed : RefreshOutcome
}
