package com.series76.assistant.feature.conversations

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.series76.assistant.AppContainer
import com.series76.assistant.R
import com.series76.assistant.core.offline.ConnectionNotice
import com.series76.assistant.ui.EmptyState
import com.series76.assistant.ui.ErrorState
import com.series76.assistant.ui.LoadingState
import com.series76.assistant.ui.NoticeBar
import com.series76.assistant.ui.messageRes
import java.text.DateFormat
import java.util.Date
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch

class ConversationsViewModel(private val container: AppContainer) : ViewModel() {
    val store = ConversationsStore(
        container.api,
        container.cache,
        container.session,
        CoroutineScope(viewModelScope.coroutineContext + container.io),
    )
    val online = container.connectivity.online
    val session = container.session.session

    init {
        store.load()
        viewModelScope.launch {
            container.connectivity.online.drop(1).collect { isOnline ->
                if (container.offline.onConnectivity(isOnline)) store.onReconnected()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConversationsScreen(
    viewModel: ConversationsViewModel,
    onOpen: (String?) -> Unit,
    onLogout: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    val state by viewModel.store.state.collectAsStateWithLifecycle()
    val online by viewModel.online.collectAsStateWithLifecycle()
    val session by viewModel.session.collectAsStateWithLifecycle()
    var query by remember { mutableStateOf("") }
    var pendingDelete by remember { mutableStateOf<String?>(null) }
    var renaming by remember { mutableStateOf<ConversationRow?>(null) }

    LaunchedEffect(state) {
        if (state is ConversationsUiState.SessionExpired) onSessionExpired()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.conversations_title)) },
                actions = { TextButton(onClick = onLogout) { Text(stringResource(R.string.logout)) } },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            NoticeBar(if (online) ConnectionNotice.None else ConnectionNotice.OfflineBanner)
            session?.let {
                Text(
                    stringResource(R.string.signed_in_as, it.email),
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
            Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { text ->
                        query = text.take(MAX_QUERY)
                        viewModel.store.search(query)
                    },
                    label = { Text(stringResource(R.string.search_hint)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Button(onClick = { onOpen(null) }) { Text(stringResource(R.string.new_conversation)) }
            }
            when (val s = state) {
                ConversationsUiState.FirstLoad -> LoadingState()
                ConversationsUiState.Empty -> EmptyState(stringResource(R.string.empty_conversations))
                ConversationsUiState.SessionExpired -> EmptyState(stringResource(R.string.session_expired))
                is ConversationsUiState.RecoverableError -> Column {
                    ErrorState(messageRes(s.messageKey), onRetry = viewModel.store::retry)
                    ConversationList(s.items, onOpen, { pendingDelete = it }, { renaming = it })
                }
                is ConversationsUiState.OfflineCache -> Column {
                    Text(
                        stringResource(R.string.offline_partial_result) + " " + syncLabel(s.lastSync),
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(horizontal = 16.dp),
                    )
                    ConversationList(s.items, onOpen, { pendingDelete = it }, { renaming = it })
                }
                is ConversationsUiState.Loaded ->
                    ConversationList(s.items, onOpen, { pendingDelete = it }, { renaming = it })
                is ConversationsUiState.Refreshing ->
                    ConversationList(s.items, onOpen, { pendingDelete = it }, { renaming = it })
                is ConversationsUiState.Deleting ->
                    ConversationList(s.items, onOpen, { pendingDelete = it }, { renaming = it })
                is ConversationsUiState.Deleted ->
                    ConversationList(s.items, onOpen, { pendingDelete = it }, { renaming = it })
            }
        }
    }

    pendingDelete?.let { id ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text(stringResource(R.string.delete_confirm_title)) },
            text = { Text(stringResource(R.string.delete_confirm_body)) },
            confirmButton = {
                TextButton(onClick = { pendingDelete = null; viewModel.store.confirmDelete(id) }) {
                    Text(stringResource(R.string.confirm))
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }

    renaming?.let { row ->
        var title by remember(row.sessionId) { mutableStateOf(row.title ?: "") }
        AlertDialog(
            onDismissRequest = { renaming = null },
            title = { Text(stringResource(R.string.rename)) },
            text = {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it.take(MAX_TITLE) },
                    label = { Text(stringResource(R.string.rename_title)) },
                    singleLine = true,
                )
            },
            confirmButton = {
                TextButton(
                    enabled = title.isNotBlank(),
                    onClick = { viewModel.store.rename(row.sessionId, title); renaming = null },
                ) { Text(stringResource(R.string.confirm)) }
            },
            dismissButton = { TextButton(onClick = { renaming = null }) { Text(stringResource(R.string.cancel)) } },
        )
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
private fun ConversationList(
    items: List<ConversationRow>,
    onOpen: (String?) -> Unit,
    onDelete: (String) -> Unit,
    onRename: (ConversationRow) -> Unit,
) {
    val pendingLabel = stringResource(R.string.pending_job)
    LazyColumn(Modifier.fillMaxSize()) {
        items(items, key = { it.sessionId }) { row ->
            Card(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)
                    .clickable { onOpen(row.sessionId) },
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text(row.title ?: "—", style = MaterialTheme.typography.titleMedium)
                    Text(row.lastActivity, style = MaterialTheme.typography.labelSmall)
                    if (row.pending) {
                        Text(
                            pendingLabel,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.semantics { contentDescription = pendingLabel },
                        )
                    }
                    if (row.deleteIndeterminate) Text(stringResource(R.string.delete_indeterminate))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { onRename(row) }) { Text(stringResource(R.string.rename)) }
                        TextButton(onClick = { onDelete(row.sessionId) }) { Text(stringResource(R.string.delete)) }
                    }
                }
            }
        }
    }
}
