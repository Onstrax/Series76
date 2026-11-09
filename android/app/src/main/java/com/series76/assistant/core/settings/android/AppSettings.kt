package com.series76.assistant.core.settings.android

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsStore: DataStore<Preferences> by preferencesDataStore(name = "series76_settings")

/**
 * NON-sensitive UI preferences only (Spec 5 Req 1.5). Tokens, cached content,
 * and drafts never go here — they are Keystore-encrypted elsewhere.
 */
class AppSettings(context: Context) {
    private val store = context.applicationContext.settingsStore
    private val summaryExpandedKey = booleanPreferencesKey("summary_expanded_by_default")

    val summaryExpanded: Flow<Boolean> = store.data.map { it[summaryExpandedKey] ?: false }

    suspend fun setSummaryExpanded(value: Boolean) {
        store.edit { it[summaryExpandedKey] = value }
    }
}
