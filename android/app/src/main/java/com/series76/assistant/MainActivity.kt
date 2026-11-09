package com.series76.assistant

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Surface
import com.series76.assistant.navigation.AppNavHost
import com.series76.assistant.ui.theme.Series76Theme

/** The single Activity hosting the Compose tree. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val container = (application as Series76App).container
        setContent {
            Series76Theme {
                Surface { AppNavHost(container) }
            }
        }
    }
}
