package com.series76.assistant

import android.content.Context
import com.series76.assistant.core.cache.EncryptedCache
import com.series76.assistant.core.cache.android.CacheDatabase
import com.series76.assistant.core.cache.android.RoomRawCacheDao
import com.series76.assistant.core.net.RetrofitSpec3Api
import com.series76.assistant.core.net.Spec3Api
import com.series76.assistant.core.offline.ConnectivityMonitor
import com.series76.assistant.core.offline.OfflineController
import com.series76.assistant.core.offline.android.AndroidConnectivityMonitor
import com.series76.assistant.core.security.AesGcmCipherBox
import com.series76.assistant.core.security.DraftStore
import com.series76.assistant.core.security.SecureTokenStore
import com.series76.assistant.core.security.UserKeyring
import com.series76.assistant.core.security.android.KeystoreKeyProvider
import com.series76.assistant.core.security.android.SharedPrefsBlobStore
import com.series76.assistant.core.session.SessionManager
import com.series76.assistant.core.settings.android.AppSettings
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers

/**
 * Manual composition root (Spec 5 Req 1.6): no DI framework. Everything the
 * ViewModels need is built once here and handed down explicitly.
 */
class AppContainer(context: Context) {
    private val appContext = context.applicationContext

    /** Network, database and crypto work never runs on the main thread (Req 10.6). */
    val io: CoroutineDispatcher = Dispatchers.IO

    private val blobs = SharedPrefsBlobStore(appContext)
    private val master = AesGcmCipherBox(KeystoreKeyProvider())

    val tokens = SecureTokenStore(master, blobs)
    val keyring = UserKeyring(master, blobs)
    val drafts = DraftStore(keyring, blobs)
    val cache = EncryptedCache(RoomRawCacheDao(CacheDatabase.create(appContext)), keyring)
    val session = SessionManager(tokens, keyring, cache)

    /** Non-sensitive preferences (DataStore). */
    val settings = AppSettings(appContext)

    val connectivity: ConnectivityMonitor = AndroidConnectivityMonitor(appContext)
    val offline = OfflineController(connectivity)

    val api: Spec3Api = RetrofitSpec3Api(
        baseUrl = BuildConfig.API_BASE_URL,
        tokens = tokens,
        onSessionClosed = { session.closeLocally() },
    )
}
