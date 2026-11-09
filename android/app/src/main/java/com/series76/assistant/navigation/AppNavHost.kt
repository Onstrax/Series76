package com.series76.assistant.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.series76.assistant.AppContainer
import com.series76.assistant.R
import com.series76.assistant.feature.auth.AuthScreen
import com.series76.assistant.feature.auth.AuthViewModel
import com.series76.assistant.feature.chat.ChatScreen
import com.series76.assistant.feature.chat.ChatViewModel
import com.series76.assistant.feature.conversations.ConversationsScreen
import com.series76.assistant.feature.conversations.ConversationsViewModel
import com.series76.assistant.feature.debug.DebugScreen
import com.series76.assistant.feature.debug.DebugViewModel
import com.series76.assistant.ui.EmptyState
import com.series76.assistant.ui.LoadingState

/**
 * Single NavHost: auth graph (Login <-> Register) and main graph
 * (Conversations -> Chat(sessionId) -> Debug(sessionId, messageId)).
 * Only identifiers travel through routes (Req 1.3, 2.1, 2.2).
 */
@Composable
fun AppNavHost(container: AppContainer, nav: NavHostController = rememberNavController()) {
    var start by remember { mutableStateOf<StartDestination?>(null) }
    val session by container.session.session.collectAsStateWithLifecycle()
    val authVm: AuthViewModel = viewModel { AuthViewModel(container) }

    LaunchedEffect(Unit) {
        start = LaunchRouter.route(container.tokens, container.api, container.session)
    }

    val resolved = start
    if (resolved == null) {
        LoadingState()
        return
    }

    // A closed session (logout, refresh failure, account switch) always lands on
    // Login, and the main graph is popped so no cached screen stays visible.
    LaunchedEffect(session) {
        val onMainGraph = nav.currentBackStackEntry?.destination?.route?.let { route ->
            !route.contains("LoginRoute") && !route.contains("RegisterRoute")
        } ?: false
        if (session == null && onMainGraph) {
            nav.navigate(LoginRoute) { popUpTo(nav.graph.id) { inclusive = true } }
        }
    }

    NavHost(
        navController = nav,
        startDestination = if (resolved == StartDestination.CONVERSATIONS) ConversationsRoute else LoginRoute,
    ) {
        composable<LoginRoute> {
            AuthScreen(
                viewModel = authVm,
                register = false,
                onAuthenticated = { nav.navigate(ConversationsRoute) { popUpTo(nav.graph.id) { inclusive = true } } },
                onSwitchMode = { nav.navigate(RegisterRoute) },
            )
        }
        composable<RegisterRoute> {
            AuthScreen(
                viewModel = authVm,
                register = true,
                onAuthenticated = { nav.navigate(ConversationsRoute) { popUpTo(nav.graph.id) { inclusive = true } } },
                onSwitchMode = { nav.popBackStack() },
            )
        }
        composable<ConversationsRoute> {
            val vm: ConversationsViewModel = viewModel { ConversationsViewModel(container) }
            ConversationsScreen(
                viewModel = vm,
                onOpen = { id -> nav.navigate(ChatRoute(id)) },
                onLogout = { authVm.store.logout() },
                onSessionExpired = { nav.navigate(LoginRoute) { popUpTo(nav.graph.id) { inclusive = true } } },
            )
        }
        composable<ChatRoute> { entry ->
            val route: ChatRoute = entry.toRoute()
            val vm: ChatViewModel = viewModel(key = "chat-${route.sessionId ?: "new"}") {
                ChatViewModel(container, route.sessionId)
            }
            ChatScreen(
                viewModel = vm,
                onBack = { nav.popBackStack() },
                onOpenTrace = { sid, mid -> nav.navigate(DebugRoute(sid, mid)) },
            )
        }
        composable<DebugRoute> { entry ->
            val route: DebugRoute = entry.toRoute()
            if (session?.isDeveloper != true) {
                // Fail closed: no trace request is even attempted for a non-developer.
                EmptyState(stringResource(R.string.debug_denied))
            } else {
                val vm: DebugViewModel = viewModel(key = "debug-${route.messageId}") {
                    DebugViewModel(container, route.sessionId, route.messageId)
                }
                DebugScreen(viewModel = vm, onBack = { nav.popBackStack() })
            }
        }
    }
}
