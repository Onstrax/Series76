package com.series76.assistant.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.series76.assistant.AppContainer
import com.series76.assistant.R
import com.series76.assistant.ui.messageRes
import kotlinx.coroutines.CoroutineScope

class AuthViewModel(container: AppContainer) : ViewModel() {
    val store = AuthStore(
        container.api,
        container.tokens,
        container.session,
        CoroutineScope(viewModelScope.coroutineContext + container.io),
    )
}

/**
 * Shared Login / Register form. There is NO role selector: registration sends
 * email + password only (Req 3.1). The password lives only in this composable's
 * transient state and is cleared after each submission (Req 3.3); it is never
 * saved across process death.
 */
@Composable
fun AuthScreen(
    viewModel: AuthViewModel,
    register: Boolean,
    onAuthenticated: () -> Unit,
    onSwitchMode: () -> Unit,
) {
    val state by viewModel.store.state.collectAsStateWithLifecycle()
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }

    LaunchedEffect(state) {
        if (state is AuthUiState.Authenticated) onAuthenticated()
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(if (register) R.string.register_title else R.string.login_title),
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.semantics { heading() },
        )
        OutlinedTextField(
            value = email,
            onValueChange = { email = it; viewModel.store.clearError() },
            label = { Text(stringResource(R.string.email)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = password,
            onValueChange = { password = it; viewModel.store.clearError() },
            label = { Text(stringResource(R.string.password)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        (state as? AuthUiState.Error)?.let { error ->
            Text(stringResource(messageRes(error.messageKey)), color = MaterialTheme.colorScheme.error)
        }
        val submitting = state is AuthUiState.Submitting
        Button(
            enabled = !submitting && email.isNotBlank() && password.isNotEmpty(),
            onClick = {
                val secret = password
                password = "" // not retained beyond the attempt
                if (register) viewModel.store.register(email, secret) else viewModel.store.login(email, secret)
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (submitting) {
                CircularProgressIndicator(Modifier.padding(2.dp))
            } else {
                Text(stringResource(if (register) R.string.register_button else R.string.login_button))
            }
        }
        TextButton(onClick = onSwitchMode) {
            Text(stringResource(if (register) R.string.go_to_login else R.string.go_to_register))
        }
    }
}
