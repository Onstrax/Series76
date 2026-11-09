package com.series76.assistant.core.session

import com.series76.assistant.core.cache.EncryptedCache
import com.series76.assistant.core.net.Me
import com.series76.assistant.core.net.TokenStore
import com.series76.assistant.core.security.UserKeyring
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * A per-login generation guard (Spec 5 Req 3.8, 9.7; Property 14). Every
 * in-flight request and cache write captures the epoch it started under; a
 * result whose epoch differs from the current one is discarded.
 */
class AccountEpoch {
    private val value = AtomicLong(0)
    fun current(): Long = value.get()
    fun advance(): Long = value.incrementAndGet()
    fun isCurrent(epoch: Long): Boolean = value.get() == epoch
}

/** The authenticated identity the UI may show (owner + role, from `/me`). */
data class SessionInfo(val userId: String, val email: String, val isDeveloper: Boolean, val ownerKey: String)

/**
 * Holds the authenticated session. Logout and account switch advance the epoch
 * FIRST (so late responses are discarded), then clear tokens and drop / purge
 * the cache, so no frame of a previous account's content can be rendered.
 */
class SessionManager(
    private val tokens: TokenStore,
    private val keyring: UserKeyring,
    private val cache: EncryptedCache,
    val epoch: AccountEpoch = AccountEpoch(),
) {
    private val _session = MutableStateFlow<SessionInfo?>(null)
    val session: StateFlow<SessionInfo?> = _session.asStateFlow()

    /** Called after login + `/me`. Switching to another account purges the previous one. */
    suspend fun establish(me: Me): SessionInfo {
        val ownerKey = keyring.ownerKey(me.id)
        val previous = _session.value
        if (previous != null && previous.ownerKey != ownerKey) {
            epoch.advance()
            _session.value = null
            cache.purgeOwner(previous.ownerKey) // rows + wrapped key, before any new render
        }
        val info = SessionInfo(me.id, me.email, me.isDeveloper, ownerKey)
        epoch.advance()
        _session.value = info
        return info
    }

    /**
     * Local logout. Always clears tokens and hides cached content, regardless of
     * whether the backend logout succeeded (fail closed locally, Req 3.7).
     */
    suspend fun closeLocally(purgeCache: Boolean = false) {
        val previous = _session.value
        epoch.advance()
        _session.value = null
        tokens.clear()
        if (purgeCache && previous != null) cache.purgeOwner(previous.ownerKey)
    }

    fun ownerKeyOrNull(): String? = _session.value?.ownerKey
}
