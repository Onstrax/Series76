package com.series76.assistant.core.offline

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Platform connectivity signal (ConnectivityManager in the app, a fake in tests). */
interface ConnectivityMonitor {
    val online: StateFlow<Boolean>
}

class FakeConnectivity(initial: Boolean = true) : ConnectivityMonitor {
    private val state = MutableStateFlow(initial)
    override val online: StateFlow<Boolean> = state.asStateFlow()
    fun set(value: Boolean) { state.value = value }
}

/** What a screen shows about the connection — offline and server errors are distinct. */
sealed interface ConnectionNotice {
    data object None : ConnectionNotice

    /** No usable connectivity: the non-dismissible offline banner (Req 7.1). */
    data object OfflineBanner : ConnectionNotice

    /** Working transport, but the server / auth failed (503, invalid token, upstream down). */
    data class ServerError(val code: String?, val message: String?) : ConnectionNotice
}

/**
 * Offline gating (Spec 5 Req 7; Properties 26-28):
 * - offline => banner, Send disabled, composer kept, nothing POSTed or enqueued;
 * - back online => Send re-enabled only after the session and pending jobs are
 *   revalidated ([markReconciled]); the draft is never auto-sent.
 */
class OfflineController(private val connectivity: ConnectivityMonitor) {
    private val _reconciled = MutableStateFlow(true)
    val reconciled: StateFlow<Boolean> = _reconciled.asStateFlow()
    private var wasOffline = !connectivity.online.value

    val isOnline: Boolean get() = connectivity.online.value

    /** Call on every connectivity change; returns true when a reconnection happened. */
    fun onConnectivity(online: Boolean): Boolean {
        val reconnected = online && wasOffline
        if (!online) _reconciled.value = false
        wasOffline = !online
        return reconnected
    }

    fun markReconciled() {
        if (connectivity.online.value) _reconciled.value = true
    }

    /** Send is allowed only online, after reconciliation, and with non-blank text. */
    fun canSend(draft: String): Boolean =
        connectivity.online.value && _reconciled.value && draft.isNotBlank()

    fun notice(serverError: ConnectionNotice.ServerError?): ConnectionNotice = when {
        !connectivity.online.value -> ConnectionNotice.OfflineBanner
        serverError != null -> serverError
        else -> ConnectionNotice.None
    }
}
