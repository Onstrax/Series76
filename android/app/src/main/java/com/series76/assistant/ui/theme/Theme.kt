package com.series76.assistant.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Light = lightColorScheme(
    primary = Color(0xFF1F4E79),
    secondary = Color(0xFF4A6572),
    error = Color(0xFFB3261E),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF9CC3E6),
    secondary = Color(0xFFB0C4CE),
    error = Color(0xFFF2B8B5),
)

/** Light and dark themes (Req 10.3); typography scales with the OS font size. */
@Composable
fun Series76Theme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) Dark else Light, content = content)
}

/** Offline banner and server-error colors are intentionally different (Req 7.6). */
object NoticeColors {
    val offlineContainer = Color(0xFF5F6368)
    val serverErrorContainer = Color(0xFFB3261E)
}
