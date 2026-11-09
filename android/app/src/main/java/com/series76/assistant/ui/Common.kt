package com.series76.assistant.ui

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.series76.assistant.R
import com.series76.assistant.core.offline.ConnectionNotice
import com.series76.assistant.core.render.UiStrings
import com.series76.assistant.core.turn.TurnState
import com.series76.assistant.ui.theme.NoticeColors

/** Resolves [com.series76.assistant.core.render.UiText] keys against Android resources. */
class AndroidUiStrings(private val context: Context) : UiStrings {
    override fun string(key: String, args: List<String>): String {
        val id = KEY_TO_RES[key] ?: return key
        return context.getString(id, *args.toTypedArray())
    }

    private companion object {
        val KEY_TO_RES: Map<String, Int> = mapOf(
            "state_not_applicable" to R.string.state_not_applicable,
            "state_not_documented" to R.string.state_not_documented,
            "state_not_listed" to R.string.state_not_listed,
            "state_unverified" to R.string.state_unverified,
            "state_unavailable" to R.string.state_unavailable,
            "derived_note" to R.string.derived_note,
            "note_not_comparable" to R.string.note_not_comparable,
            "note_supply_heterogeneous" to R.string.note_supply_heterogeneous,
            "bar_alt_state" to R.string.bar_alt_state,
            "offline_banner" to R.string.offline_banner,
        )
    }
}

@Composable
fun rememberUiStrings(): UiStrings {
    val context = LocalContext.current
    return remember(context) { AndroidUiStrings(context) }
}

@StringRes
fun messageRes(key: String?): Int = when (key) {
    "error_auth_failed" -> R.string.error_auth_failed
    "error_register_failed" -> R.string.error_register_failed
    "error_offline" -> R.string.error_offline
    "error_server" -> R.string.error_server
    "error_rename" -> R.string.error_rename
    "error_delete" -> R.string.error_delete
    "error_delete_unconfirmed" -> R.string.error_delete_unconfirmed
    "error_not_found" -> R.string.error_not_found
    "error_rate_limited" -> R.string.error_rate_limited
    "error_validation" -> R.string.error_validation
    else -> R.string.error_generic
}

@StringRes
fun turnStateRes(state: TurnState): Int = when (state) {
    TurnState.DRAFT -> R.string.turn_draft
    TurnState.SUBMITTING -> R.string.turn_submitting
    TurnState.QUEUED -> R.string.turn_queued
    TurnState.RUNNING -> R.string.turn_running
    TurnState.NEEDS_CLARIFICATION -> R.string.turn_needs_clarification
    TurnState.AWAITING_CONFIRMATION -> R.string.turn_awaiting_confirmation
    TurnState.COMPLETED -> R.string.turn_completed
    TurnState.FAILED -> R.string.turn_failed
    TurnState.CANCELLED -> R.string.turn_cancelled
    TurnState.DISCONNECTED_RECONCILING -> R.string.turn_disconnected_reconciling
}

@StringRes
fun categoryRes(category: String): Int = when (category) {
    "documented-fact" -> R.string.category_documented_fact
    "user-assumption" -> R.string.category_user_assumption
    "proposal" -> R.string.category_proposal
    "delegation" -> R.string.category_delegation
    else -> R.string.category_uncategorized
}

/**
 * The connection notice bar. The offline banner (grey, "you are offline") and
 * a server/auth error (red, "not a connection problem") are visually and
 * textually distinct (Req 7.6). The offline banner has no dismiss action.
 */
@Composable
fun NoticeBar(notice: ConnectionNotice) {
    when (notice) {
        ConnectionNotice.None -> Unit
        ConnectionNotice.OfflineBanner -> Banner(stringResource(R.string.offline_banner), NoticeColors.offlineContainer)
        is ConnectionNotice.ServerError -> Banner(
            notice.message?.takeIf { it.isNotBlank() } ?: stringResource(R.string.server_error_banner),
            NoticeColors.serverErrorContainer,
        )
    }
}

@Composable
private fun Banner(text: String, color: Color) {
    Text(
        text = text,
        color = Color.White,
        modifier = Modifier
            .fillMaxWidth()
            .background(color)
            .padding(12.dp)
            .semantics { liveRegion = LiveRegionMode.Polite },
    )
}

@Composable
fun LoadingState(modifier: Modifier = Modifier) {
    val label = stringResource(R.string.loading)
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator()
            Text(label, modifier = Modifier.padding(top = 8.dp))
        }
    }
}

@Composable
fun EmptyState(text: String, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.bodyLarge)
    }
}

/** A failure message plus an actionable retry; never a stack trace (Req 10.5). */
@Composable
fun ErrorState(@StringRes message: Int, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(stringResource(message), color = MaterialTheme.colorScheme.error)
        Button(onClick = onRetry) { Text(stringResource(R.string.retry)) }
    }
}
