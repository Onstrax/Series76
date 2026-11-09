package com.series76.assistant.feature.chat

import com.series76.assistant.core.cache.EncryptedCache
import com.series76.assistant.core.model.ContentBlock
import com.series76.assistant.core.model.Envelope
import com.series76.assistant.core.model.EnvelopeParser
import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.MessageItem
import com.series76.assistant.core.net.Spec3Api
import com.series76.assistant.core.offline.ConnectionNotice
import com.series76.assistant.core.offline.OfflineController
import com.series76.assistant.core.render.RenderMapper
import com.series76.assistant.core.render.RenderModel
import com.series76.assistant.core.security.DraftStore
import com.series76.assistant.core.session.SessionManager
import com.series76.assistant.core.turn.ClientRequestIds
import com.series76.assistant.core.turn.JobState
import com.series76.assistant.core.turn.PollingPolicy
import com.series76.assistant.core.turn.TurnRecord
import com.series76.assistant.core.turn.TurnState
import java.util.UUID
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray

enum class Role { USER, ASSISTANT }

/** One rendered chat message. Assistant figures come only from typed blocks. */
data class ChatMessage(
    val localId: String,
    val role: Role,
    val text: String,
    val render: RenderModel? = null,
    val messageId: String? = null,
)

/** The plan awaiting confirmation (Req 5.4): exact revision echoed on Confirm. */
data class PlanPanel(val revision: Int, val planId: String?, val summary: String, val stale: Boolean = false)

data class ChatUiState(
    val sessionId: String? = null,
    val messages: List<ChatMessage> = emptyList(),
    val turns: List<TurnRecord> = emptyList(),
    val draft: String = "",
    val sendEnabled: Boolean = false,
    val notice: ConnectionNotice = ConnectionNotice.None,
    val loading: Boolean = false,
    val errorKey: String? = null,
    val plan: PlanPanel? = null,
    val lastSync: Long? = null,
    val offlineHistory: Boolean = false,
)

/**
 * Chat presentation logic (Spec 5 Req 5-7). Network work runs on [io]
 * (off the main thread); polling cadence comes from [PollingPolicy] and job
 * state only from job-endpoint responses — never from elapsed time.
 */
class ChatStore(
    initialSessionId: String?,
    private val api: Spec3Api,
    private val cache: EncryptedCache,
    private val drafts: DraftStore,
    private val session: SessionManager,
    private val offline: OfflineController,
    private val scope: CoroutineScope,
    private val io: CoroutineDispatcher,
    private val ids: ClientRequestIds = ClientRequestIds(),
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val _state = MutableStateFlow(ChatUiState(sessionId = initialSessionId))
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    /** Client_Request_Id per turn intent, kept until the acceptance outcome is known. */
    private val intentOfTurn = LinkedHashMap<String, String>()

    private fun draftKey(): String = _state.value.sessionId ?: ""

    private fun refreshSend() {
        _state.update { it.copy(sendEnabled = offline.canSend(it.draft)) }
    }

    // --- opening / history ---------------------------------------------------

    fun open(): Job = scope.launch(io) {
        val owner = session.ownerKeyOrNull() ?: return@launch
        _state.update { it.copy(draft = drafts.load(owner, draftKey()), loading = true) }
        val sid = _state.value.sessionId
        if (sid == null) {
            _state.update { it.copy(loading = false) }
        } else {
            loadHistory(owner, sid)
        }
        refreshNotice(null)
        refreshSend()
    }

    private suspend fun loadHistory(owner: String, sid: String) {
        val epoch = session.epoch.current()
        val result = api.messages(sid)
        if (!session.epoch.isCurrent(epoch)) return
        when (result) {
            is ApiResult.Success -> {
                cache.putMessages(owner, sid, result.value, now())
                _state.update {
                    it.copy(messages = result.value.map(::toChatMessage), loading = false,
                        offlineHistory = false, lastSync = now(), plan = latestPlan(result.value))
                }
            }
            ApiResult.Offline -> {
                val cached = cache.messages(owner, sid)
                _state.update {
                    it.copy(messages = cached.items.map(::toChatMessage), loading = false,
                        offlineHistory = true, lastSync = cached.lastSync)
                }
            }
            is ApiResult.HttpError -> {
                // A conversation the backend reports gone is purged, never re-uploaded.
                if (result.status == 404) cache.forget(owner, sid)
                _state.update {
                    it.copy(loading = false, errorKey = if (result.status == 404) "error_not_found" else "error_server")
                }
            }
        }
    }

    private fun toChatMessage(m: MessageItem): ChatMessage {
        if (m.role != "assistant") return ChatMessage(m.messageId, Role.USER, m.content, messageId = m.messageId)
        val blocks: List<ContentBlock> = runCatching {
            (EnvelopeParser.json.parseToJsonElement(m.blocksJson) as JsonArray).map(EnvelopeParser::parseBlock)
        }.getOrDefault(emptyList())
        val envelope = Envelope(sessionId = _state.value.sessionId ?: "", answer = m.content, blocks = blocks)
        return ChatMessage(m.messageId, Role.ASSISTANT, m.content, RenderMapper.map(envelope), m.messageId)
    }

    private fun latestPlan(items: List<MessageItem>): PlanPanel? {
        val last = items.lastOrNull { it.role == "assistant" } ?: return null
        val blocks = runCatching {
            (EnvelopeParser.json.parseToJsonElement(last.blocksJson) as JsonArray).map(EnvelopeParser::parseBlock)
        }.getOrDefault(emptyList())
        val plan = blocks.filterIsInstance<ContentBlock.PlanReview>().lastOrNull() ?: return null
        return if (plan.requiresConfirmation) PlanPanel(plan.planRevision, plan.planId, plan.summary) else null
    }

    // --- composer ----------------------------------------------------------

    /** Draft edits are persisted encrypted and survive restarts (Req 7.2). */
    fun onDraftChanged(text: String) {
        _state.update { it.copy(draft = text) }
        session.ownerKeyOrNull()?.let { owner -> drafts.save(owner, draftKey(), text) }
        refreshSend()
    }

    /**
     * Send the draft as a NEW intent (a fresh Client_Request_Id). Offline, or
     * before reconnection is reconciled, this is a no-op: nothing is POSTed,
     * enqueued, or marked sent (Req 7.3).
     */
    fun send(): Job? {
        val text = _state.value.draft
        if (!offline.canSend(text)) return null
        val localId = UUID.randomUUID().toString()
        val intent = UUID.randomUUID().toString()
        intentOfTurn[localId] = intent
        val turn = TurnRecord(localId, text, ids.keyFor(intent), TurnState.SUBMITTING, _state.value.sessionId)
        _state.update {
            it.copy(
                turns = it.turns + turn,
                messages = it.messages + ChatMessage(localId, Role.USER, text),
            )
        }
        return scope.launch(io) { submit(localId) }
    }

    private fun setTurn(localId: String, transform: (TurnRecord) -> TurnRecord) {
        _state.update { s -> s.copy(turns = s.turns.map { if (it.localId == localId) transform(it) else it }) }
    }

    private fun turn(localId: String): TurnRecord? = _state.value.turns.firstOrNull { it.localId == localId }

    private suspend fun submit(localId: String) {
        val t = turn(localId) ?: return
        val epoch = session.epoch.current()
        val result = api.submitJob(t.sessionId ?: _state.value.sessionId, t.query, t.clientRequestId)
        if (!session.epoch.isCurrent(epoch)) return
        when (result) {
            is ApiResult.Success -> {
                intentOfTurn.remove(localId)?.let(ids::resolve) // acceptance known
                val accepted = result.value
                val wasNew = _state.value.sessionId == null
                _state.update { it.copy(sessionId = accepted.sessionId, draft = "") }
                session.ownerKeyOrNull()?.let { owner ->
                    drafts.save(owner, if (wasNew) "" else accepted.sessionId, "")
                }
                setTurn(localId) {
                    it.copy(sessionId = accepted.sessionId, jobId = accepted.jobId, state = accepted.status.toTurnState())
                }
                refreshSend()
                poll(localId, accepted.jobId)
            }
            // Acceptance unknown: keep the key, reconcile on reconnect (same key, no duplicate).
            ApiResult.Offline -> setTurn(localId) { it.copy(state = TurnState.DISCONNECTED_RECONCILING) }
            is ApiResult.HttpError -> {
                intentOfTurn.remove(localId)?.let(ids::resolve) // rejected: key discarded
                setTurn(localId) { it.copy(state = TurnState.FAILED) }
                _state.update { it.copy(errorKey = errorKeyFor(result)) }
                refreshNotice(result)
            }
        }
    }

    /** Poll until the job state stops polling; state only from responses. */
    private suspend fun poll(localId: String, jobId: String) {
        var attempt = 0
        var retryAfter: Long? = null
        while (true) {
            delay(PollingPolicy.nextDelaySeconds(attempt, retryAfter) * 1000)
            val epoch = session.epoch.current()
            val result = api.pollJob(jobId)
            if (!session.epoch.isCurrent(epoch)) return
            when (result) {
                is ApiResult.Success -> {
                    val status = result.value
                    setTurn(localId) { it.copy(state = status.state.toTurnState()) }
                    if (status.state.stopsPolling) {
                        status.envelope?.let(::appendAssistant)
                        if (status.state == JobState.STALE_PLAN) reloadPlan()
                        return
                    }
                    retryAfter = status.retryAfterSeconds
                    attempt++
                }
                ApiResult.Offline -> {
                    setTurn(localId) { it.copy(state = TurnState.DISCONNECTED_RECONCILING) }
                    return
                }
                is ApiResult.HttpError -> {
                    val cancelled = result.error?.code == "JOB_CANCELLED"
                    setTurn(localId) { it.copy(state = if (cancelled) TurnState.CANCELLED else TurnState.FAILED) }
                    refreshNotice(result)
                    return
                }
            }
        }
    }

    private fun appendAssistant(envelope: Envelope) {
        val render = RenderMapper.map(envelope)
        val plan = envelope.blocks.filterIsInstance<ContentBlock.PlanReview>().lastOrNull()
            ?.takeIf { it.requiresConfirmation }
            ?.let { PlanPanel(it.planRevision, it.planId, it.summary) }
        _state.update {
            it.copy(
                messages = it.messages + ChatMessage(
                    localId = envelope.messageId ?: UUID.randomUUID().toString(),
                    role = Role.ASSISTANT,
                    text = envelope.answer, // displayed verbatim, never parsed for figures
                    render = render,
                    messageId = envelope.messageId,
                ),
                plan = plan,
            )
        }
    }

    // --- plan confirmation (Req 5.4, 5.5) -----------------------------------

    /** Confirm exactly the shown revision; a 409 reloads, never re-executes. */
    fun confirmPlan(): Job? {
        val plan = _state.value.plan ?: return null
        val sid = _state.value.sessionId ?: return null
        if (!offline.isOnline) return null
        return scope.launch(io) {
            when (val result = api.confirmPlan(sid, plan.revision)) {
                is ApiResult.Success -> {
                    _state.update { it.copy(plan = null) }
                    result.value.envelope?.let(::appendAssistant)
                }
                ApiResult.Offline -> refreshNotice(null)
                is ApiResult.HttpError -> if (result.status == 409) reloadPlan() else refreshNotice(result)
            }
        }
    }

    /** "Edit": dismiss the panel and let the user write a correction (a new revision). */
    fun editPlan() {
        _state.update { it.copy(plan = null) }
    }

    private suspend fun reloadPlan() {
        val sid = _state.value.sessionId ?: return
        when (val result = api.messages(sid)) {
            is ApiResult.Success -> _state.update { s ->
                val fresh = latestPlan(result.value)
                s.copy(plan = fresh?.copy(stale = true), messages = result.value.map(::toChatMessage))
            }
            else -> _state.update { it.copy(plan = it.plan?.copy(stale = true)) }
        }
    }

    // --- connectivity (Req 7) -------------------------------------------------

    /**
     * Connectivity changed. Going offline disables Send at once. Coming back,
     * the session is revalidated and pending turns reconciled (same keys)
     * BEFORE Send is re-enabled; the draft is never sent automatically.
     */
    fun onConnectivity(online: Boolean): Job? {
        val reconnected = offline.onConnectivity(online)
        refreshNotice(null)
        refreshSend()
        if (!reconnected) return null
        return scope.launch(io) {
            val me = api.me()
            if (me is ApiResult.HttpError && me.status == 401) {
                session.closeLocally()
                return@launch
            }
            for (t in _state.value.turns) {
                if (t.state != TurnState.DISCONNECTED_RECONCILING) continue
                if (t.jobId != null) {
                    poll(t.localId, t.jobId) // reconcile the known job
                } else {
                    submit(t.localId) // same Client_Request_Id: idempotent on the backend
                }
            }
            offline.markReconciled()
            refreshNotice(null)
            refreshSend()
        }
    }

    private fun refreshNotice(error: ApiResult.HttpError?) {
        val serverError = error?.takeIf { it.status >= 500 || it.status == 401 }?.let {
            ConnectionNotice.ServerError(it.error?.code, it.error?.userMessage)
        }
        _state.update { it.copy(notice = offline.notice(serverError)) }
    }

    private fun errorKeyFor(error: ApiResult.HttpError): String = when {
        error.status == 503 -> "error_server"
        error.status == 429 -> "error_rate_limited"
        error.status == 422 -> "error_validation"
        else -> "error_server"
    }

    fun clearError() {
        _state.update { it.copy(errorKey = null) }
    }
}
