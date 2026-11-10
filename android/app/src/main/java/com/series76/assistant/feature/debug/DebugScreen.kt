package com.series76.assistant.feature.debug

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.series76.assistant.AppContainer
import com.series76.assistant.R
import com.series76.assistant.ui.EmptyState
import com.series76.assistant.ui.ErrorState
import com.series76.assistant.ui.LoadingState
import kotlinx.coroutines.CoroutineScope

class DebugViewModel(container: AppContainer, private val sessionId: String, private val messageId: String) :
    ViewModel() {
    val store = DebugStore(container.api, CoroutineScope(viewModelScope.coroutineContext + container.io))

    init {
        reload()
    }

    fun reload() {
        store.load(sessionId, messageId)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DebugScreen(viewModel: DebugViewModel, onBack: () -> Unit) {
    val state by viewModel.store.state.collectAsStateWithLifecycle()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.debug_title)) },
                navigationIcon = { TextButton(onClick = onBack) { Text("‹") } },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            when (val s = state) {
                DebugUiState.Loading -> LoadingState()
                // One generic message for every denial: nothing about existence or owner.
                DebugUiState.Denied -> EmptyState(stringResource(R.string.debug_denied))
                DebugUiState.Unavailable -> ErrorState(R.string.debug_unavailable, onRetry = viewModel::reload)
                is DebugUiState.Loaded -> TraceContent(s.trace)
            }
        }
    }
}

@Composable
private fun TraceContent(trace: TraceView) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // The turn's overall execution …
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text(stringResource(R.string.debug_turn, trace.traceId), style = MaterialTheme.typography.titleSmall)
                Text(stringResource(R.string.debug_outcome, trace.outcome))
                Text(stringResource(R.string.debug_states, trace.turnStates.joinToString(" → ")))
                trace.modelCalls?.let { Text(stringResource(R.string.debug_model_calls, it)) }
                trace.durationMs?.let { Text(stringResource(R.string.debug_duration, it.toInt())) }
                if (trace.invokedNoTool) Text(stringResource(R.string.debug_no_tool))
            }
        }
        // … distinct from each tool attempt.
        trace.toolCalls.forEach { call ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(call.tool, style = MaterialTheme.typography.titleSmall)
                    Text(
                        stringResource(if (call.isAttempt) R.string.debug_attempt else R.string.debug_completed_by_backend),
                        style = MaterialTheme.typography.labelSmall,
                    )
                    Text(call.status)
                    Text(stringResource(R.string.debug_parameters), style = MaterialTheme.typography.labelSmall)
                    Text(call.arguments, style = MaterialTheme.typography.bodySmall)
                    if (call.returnedData.isNotEmpty()) {
                        Text(stringResource(R.string.debug_returned), style = MaterialTheme.typography.labelSmall)
                        Text(call.returnedData, style = MaterialTheme.typography.bodySmall)
                    }
                    if (call.ignoredServerArguments.isNotEmpty()) {
                        Text(call.ignoredServerArguments.joinToString(), style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
