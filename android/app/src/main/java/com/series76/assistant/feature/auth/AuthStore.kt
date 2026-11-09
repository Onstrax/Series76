package com.series76.assistant.feature.auth

import com.series76.assistant.core.net.ApiResult
import com.series76.assistant.core.net.Spec3Api
import com.series76.assistant.core.net.TokenStore
import com.series76.assistant.core.session.SessionInfo
import com.series76.assistant.core.session.SessionManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/** Login / Register screen state. Errors are generic message keys (Req 3.3). */
sealed interface AuthUiState {
    data object Idle : AuthUiState
    data object Submitting : AuthUiState
    data class Error(val messageKey: String) : AuthUiState
    data class Authenticated(val session: SessionInfo) : AuthUiState
}

/**
 * Authentication presentation logic (Spec 5 Req 3). The password is only a
 * function argument: it is never placed in state, stored, or logged.
 */
class AuthStore(
    private val api: Spec3Api,
    private val tokens: TokenStore,
    private val session: SessionManager,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow<AuthUiState>(AuthUiState.Idle)
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    private fun emit(next: AuthUiState) {
        _state.value = next
    }

    /** Registers with email + password ONLY (no role field exists), then logs in. */
    fun register(email: String, password: String): Job = scope.launch {
        emit(AuthUiState.Submitting)
        val r = api.register(email.trim(), password)
        when (r) {
            is ApiResult.Success -> loginInternal(email.trim(), password)
            ApiResult.Offline -> emit(AuthUiState.Error("error_offline"))
            // Invalid or duplicate: stay on Register, no local session is created.
            is ApiResult.HttpError -> emit(
                AuthUiState.Error(if (r.status in 400..499) "error_register_failed" else "error_server"),
            )
        }
    }

    fun login(email: String, password: String): Job = scope.launch {
        emit(AuthUiState.Submitting)
        loginInternal(email.trim(), password)
    }

    private suspend fun loginInternal(email: String, password: String) {
        val r = api.login(email, password)
        when (r) {
            is ApiResult.Success -> {
                tokens.save(r.value)
                val me = api.me()
                if (me is ApiResult.Success) {
                    emit(AuthUiState.Authenticated(session.establish(me.value)))
                } else {
                    session.closeLocally()
                    emit(AuthUiState.Error("error_auth_failed"))
                }
            }
            ApiResult.Offline -> emit(AuthUiState.Error("error_offline"))
            // One generic message: never distinguishes unknown email from wrong password.
            is ApiResult.HttpError -> emit(
                AuthUiState.Error(if (r.status == 503) "error_server" else "error_auth_failed"),
            )
        }
    }

    /** Logout always clears local tokens and hides the cache, even if the backend fails. */
    fun logout(): Job = scope.launch {
        withTimeoutOrNull(LOGOUT_TIMEOUT_MS) { api.logout() }
        session.closeLocally()
        emit(AuthUiState.Idle)
    }

    fun clearError() {
        if (_state.value is AuthUiState.Error) emit(AuthUiState.Idle)
    }

    companion object {
        const val LOGOUT_TIMEOUT_MS = 5_000L
    }
}
