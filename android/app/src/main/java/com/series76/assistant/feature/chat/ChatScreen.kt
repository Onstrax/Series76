package com.series76.assistant.feature.chat

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.series76.assistant.AppContainer
import com.series76.assistant.R
import com.series76.assistant.core.offline.ConnectionNotice
import com.series76.assistant.core.turn.TurnRecord
import com.series76.assistant.ui.LoadingState
import com.series76.assistant.ui.NoticeBar
import com.series76.assistant.ui.messageRes
import com.series76.assistant.ui.turnStateRes
import java.text.DateFormat
import java.util.Date
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

class ChatViewModel(container: AppContainer, sessionId: String?) : ViewModel() {
    val store = ChatStore(
        initialSessionId = sessionId,
        api = container.api,
        cache = container.cache,
        drafts = container.drafts,
        session = container.session,
        offline = container.offline,
        scope = CoroutineScope(viewModelScope.coroutineContext + container.io),
        io = container.io,
    )
    val isDeveloper = container.session.session
    val summaryExpanded = container.settings.summaryExpanded

    init {
        store.open()
        viewModelScope.launch {
            container.connectivity.online.collect { store.onConnectivity(it) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    viewModel: ChatViewModel,
    onBack: () -> Unit,
    onOpenTrace: (sessionId: String, messageId: String) -> Unit,
) {
    val state by viewModel.store.state.collectAsStateWithLifecycle()
    val session by viewModel.isDeveloper.collectAsStateWithLifecycle()
    val summaryExpanded by viewModel.summaryExpanded.collectAsStateWithLifecycle(initialValue = false)
    // UI convenience only: the backend re-verifies role + ownership per trace call.
    val developer = session?.isDeveloper == true

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.chat_title)) },
                navigationIcon = { TextButton(onClick = onBack) { Text("‹") } },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
            NoticeBar(state.notice)
            if (state.offlineHistory) {
                Text(
                    syncLabel(state.lastSync),
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
            state.errorKey?.let {
                Text(stringResource(messageRes(it)), color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp))
            }
            if (state.loading) {
                LoadingState(Modifier.weight(1f))
            } else {
                LazyColumn(
                    Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(state.messages, key = { it.localId }) { message ->
                        MessageBubble(
                            message = message,
                            turn = state.turns.firstOrNull { it.localId == message.localId },
                            developer = developer,
                            summaryExpanded = summaryExpanded,
                            onTrace = { mid -> state.sessionId?.let { sid -> onOpenTrace(sid, mid) } },
                        )
                    }
                }
            }
            state.plan?.let { plan ->
                PlanPanelView(plan, onConfirm = { viewModel.store.confirmPlan() }, onEdit = viewModel.store::editPlan)
            }
            Composer(
                draft = state.draft,
                sendEnabled = state.sendEnabled,
                offline = state.notice == ConnectionNotice.OfflineBanner,
                onDraftChanged = viewModel.store::onDraftChanged,
                onSend = { viewModel.store.send() },
            )
        }
    }
}

@Composable
private fun syncLabel(lastSync: Long?): String =
    if (lastSync == null) {
        stringResource(R.string.never_synced)
    } else {
        stringResource(R.string.last_sync, DateFormat.getDateTimeInstance().format(Date(lastSync)))
    }

@Composable
private fun MessageBubble(
    message: ChatMessage,
    turn: TurnRecord?,
    developer: Boolean,
    summaryExpanded: Boolean,
    onTrace: (String) -> Unit,
) {
    val isUser = message.role == Role.USER
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (isUser) MaterialTheme.colorScheme.secondaryContainer
            else MaterialTheme.colorScheme.surfaceVariant,
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(10.dp)) {
            if (isUser || message.render == null) {
                Text(message.text) // user text / plain assistant text, verbatim
            } else {
                TypedBlockRenderer(message.render, expandSummaryByDefault = summaryExpanded)
            }
            turn?.let { Text(stringResource(turnStateRes(it.state)), style = MaterialTheme.typography.labelSmall) }
            if (!isUser && developer && message.messageId != null) {
                TextButton(onClick = { onTrace(message.messageId) }) { Text(stringResource(R.string.debug)) }
            }
        }
    }
}

@Composable
private fun PlanPanelView(plan: PlanPanel, onConfirm: () -> Unit, onEdit: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(8.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(stringResource(R.string.plan_title, plan.revision), style = MaterialTheme.typography.titleSmall)
            if (plan.stale) Text(stringResource(R.string.plan_stale), color = MaterialTheme.colorScheme.error)
            Text(plan.summary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onConfirm) { Text(stringResource(R.string.plan_confirm)) }
                OutlinedButton(onClick = onEdit) { Text(stringResource(R.string.plan_edit)) }
            }
        }
    }
}

/**
 * The composer is always present. Offline (or before reconnection is
 * reconciled) Send is disabled with an announced state description, and the
 * encrypted draft is kept — nothing is queued or sent automatically (Req 7.2-7.4).
 */
@Composable
private fun Composer(
    draft: String,
    sendEnabled: Boolean,
    offline: Boolean,
    onDraftChanged: (String) -> Unit,
    onSend: () -> Unit,
) {
    val disabledDescription = stringResource(if (offline) R.string.send_disabled_offline else R.string.send_disabled)
    Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = draft,
            onValueChange = onDraftChanged,
            label = { Text(stringResource(R.string.composer_hint)) },
            modifier = Modifier.weight(1f),
        )
        Button(
            onClick = onSend,
            enabled = sendEnabled,
            modifier = Modifier.semantics { if (!sendEnabled) stateDescription = disabledDescription },
        ) { Text(stringResource(R.string.send)) }
    }
}
