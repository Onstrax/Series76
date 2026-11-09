package com.series76.assistant.feature.conversations

import com.series76.assistant.core.cache.EncryptedCache
import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.SessionSummary
import com.series76.assistant.core.net.Spec3Api
import com.series76.assistant.core.session.SessionManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/** One row of the list: only the token owner's own conversations (Req 4.1). */
data class ConversationRow(
    val sessionId: String,
    val title: String?,
    val lastActivity: String,
    val pending: Boolean,
    val deleteIndeterminate: Boolean = false,
)

/** The explicit Conversations states (Req 4.4). */
sealed interface ConversationsUiState {
    data object FirstLoad : ConversationsUiState
    data class Refreshing(val items: List<ConversationRow>) : ConversationsUiState
    data object Empty : ConversationsUiState
    data class Loaded(val items: List<ConversationRow>, val nextCursor: String?) : ConversationsUiState
    /** Cached, possibly stale and possibly partial; never presented as exhaustive (Req 4.2, 7.5). */
    data class OfflineCache(val items: List<ConversationRow>, val lastSync: Long?, val partial: Boolean) :
        ConversationsUiState
    data class RecoverableError(val messageKey: String, val items: List<ConversationRow>) :
        ConversationsUiState
    data class Deleting(val sessionId: String, val items: List<ConversationRow>) : ConversationsUiState
    data class Deleted(val sessionId: String, val items: List<ConversationRow>) : ConversationsUiState
    data object SessionExpired : ConversationsUiState
}

const val MAX_TITLE = 200
const val MAX_QUERY = 200
const val DELETE_CONFIRM_TIMEOUT_MS = 30_000L

fun SessionSummary.toRow(indeterminate: Set<String> = emptySet()) = ConversationRow(
    sessionId = sessionId,
    title = title,
    lastActivity = updatedAt,
    pending = pendingJobs > 0,
    deleteIndeterminate = sessionId in indeterminate,
)

/**
 * Conversations presentation logic (Spec 5 Req 4). The backend is the single
 * source of truth; the cache only backs offline reading and is never used to
 * rebuild server state or resurrect a deleted conversation.
 */
class ConversationsStore(
    private val api: Spec3Api,
    private val cache: EncryptedCache,
    private val session: SessionManager,
    private val scope: CoroutineScope,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val _state = MutableStateFlow<ConversationsUiState>(ConversationsUiState.FirstLoad)
    val state: StateFlow<ConversationsUiState> = _state.asStateFlow()

    /** Deletions sent while connectivity dropped: indeterminate until reconciled. */
    private val indeterminateDeletes = LinkedHashSet<String>()
    private var lastQuery: String? = null
    private var lastRetry: (() -> Unit)? = null

    private fun emit(next: ConversationsUiState) {
        _state.value = next
    }

    private fun currentItems(): List<ConversationRow> = when (val s = _state.value) {
        is ConversationsUiState.Loaded -> s.items
        is ConversationsUiState.Refreshing -> s.items
        is ConversationsUiState.OfflineCache -> s.items
        is ConversationsUiState.RecoverableError -> s.items
        is ConversationsUiState.Deleting -> s.items
        is ConversationsUiState.Deleted -> s.items
        else -> emptyList()
    }

    /** Load (or search, title-only, case-insensitive on the backend) the owner's list. */
    fun load(query: String? = lastQuery): Job = scope.launch {
        val owner = session.ownerKeyOrNull()
        if (owner == null) {
            emit(ConversationsUiState.SessionExpired)
            return@launch
        }
        val q = query?.take(MAX_QUERY)?.takeIf { it.isNotEmpty() }
        lastQuery = q
        lastRetry = { load(q) }
        val epoch = session.epoch.current()
        val previous = currentItems()
        emit(if (previous.isEmpty()) ConversationsUiState.FirstLoad else ConversationsUiState.Refreshing(previous))
        val result = api.listSessions(q, null)
        if (!session.epoch.isCurrent(epoch)) return@launch // late response of a previous account
        val next: ConversationsUiState = when (result) {
            is ApiResult.Success -> {
                val items = result.value.items
                // Reconcile: any indeterminate deletion is settled by the backend list.
                val present = items.map { it.sessionId }.toSet()
                indeterminateDeletes.filter { it !in present }.forEach { gone ->
                    cache.forget(owner, gone)
                }
                indeterminateDeletes.retainAll(present)
                if (q == null) {
                    // Rows the backend no longer reports are purged, never re-uploaded.
                    val cached = cache.conversations(owner).items.map { it.sessionId }
                    cached.filter { it !in present }.forEach { cache.forget(owner, it) }
                    cache.putConversations(owner, items, now())
                }
                if (items.isEmpty()) {
                    ConversationsUiState.Empty
                } else {
                    ConversationsUiState.Loaded(
                        items.map { it.toRow(indeterminateDeletes) },
                        result.value.nextCursor,
                    )
                }
            }
            ApiResult.Offline -> {
                val cached = cache.conversations(owner)
                val filtered = cached.items.filter { s ->
                    q == null || (s.title ?: "").contains(q, ignoreCase = true)
                }
                ConversationsUiState.OfflineCache(
                    filtered.map { it.toRow(indeterminateDeletes) },
                    cached.lastSync,
                    partial = true,
                )
            }
            is ApiResult.HttpError -> if (result.status == 401) {
                session.closeLocally()
                ConversationsUiState.SessionExpired
            } else {
                ConversationsUiState.RecoverableError("error_server", previous)
            }
        }
        emit(next)
    }

    fun search(text: String) = load(text.take(MAX_QUERY))

    fun retry() {
        lastRetry?.invoke() ?: load()
    }

    /** Rename with a 1-200 character title (validated before any request). */
    fun rename(sessionId: String, title: String): Job? {
        val clean = title.trim()
        if (clean.isEmpty() || clean.length > MAX_TITLE) return null
        return scope.launch {
            val result = api.rename(sessionId, clean)
            if (result is ApiResult.HttpError) {
                emit(ConversationsUiState.RecoverableError("error_rename", currentItems()))
            } else {
                load()
            }
        }
    }

    /**
     * Delete after the user confirmed it in the dialog. Final only when the
     * backend confirms; unconfirmed after 30 s keeps the conversation; a lost
     * connection holds it as indeterminate until reconciled with the backend.
     */
    fun confirmDelete(sessionId: String): Job = scope.launch {
        val owner = session.ownerKeyOrNull() ?: return@launch
        val epoch = session.epoch.current()
        val before = currentItems()
        emit(ConversationsUiState.Deleting(sessionId, before))
        val result = withTimeoutOrNull(DELETE_CONFIRM_TIMEOUT_MS) { api.delete(sessionId) }
        if (!session.epoch.isCurrent(epoch)) return@launch
        val gone = result is ApiResult.Success ||
            (result is ApiResult.HttpError && (result.status == 404 || result.status == 410))
        if (result == null) {
            // Not confirmed within 30 s: the conversation stays in its pre-delete state.
            emit(ConversationsUiState.RecoverableError("error_delete_unconfirmed", before))
        } else if (gone) {
            cache.forget(owner, sessionId)
            emit(ConversationsUiState.Deleted(sessionId, before.filter { it.sessionId != sessionId }))
        } else if (result == ApiResult.Offline) {
            indeterminateDeletes += sessionId
            emit(
                ConversationsUiState.OfflineCache(
                    before.map { if (it.sessionId == sessionId) it.copy(deleteIndeterminate = true) else it },
                    null,
                    partial = true,
                ),
            )
        } else {
            emit(ConversationsUiState.RecoverableError("error_delete", before))
        }
    }

    /** On reconnect: the backend list is authoritative for every indeterminate deletion. */
    fun onReconnected(): Job = load()

    fun indeterminate(): Set<String> = indeterminateDeletes.toSet()
}
