package com.series76.assistant.core.security.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import com.series76.assistant.core.security.BlobStore
import java.security.KeyStore
import java.util.Base64
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

/**
 * The master AES-256-GCM key lives in the Android Keystore: its material never
 * leaves secure hardware/software keystore. Returns `null` when the key cannot
 * be obtained, which every caller treats as "no data" (fail closed, Req 9.9).
 */
class KeystoreKeyProvider(private val alias: String = "series76.master.v1") : () -> SecretKey? {

    override fun invoke(): SecretKey? = try {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey) ?: generate()
    } catch (e: Exception) {
        null
    }

    private fun generate(): SecretKey {
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }
}

/**
 * A [BlobStore] over private SharedPreferences. Callers only ever store
 * ciphertext (tokens, wrapped keys, drafts); the file is excluded from backup.
 */
class SharedPrefsBlobStore(context: Context, name: String = "series76.secure") : BlobStore {
    private val prefs = context.getSharedPreferences(name, Context.MODE_PRIVATE)

    override fun put(key: String, value: ByteArray) {
        prefs.edit().putString(key, Base64.getEncoder().encodeToString(value)).apply()
    }

    override fun get(key: String): ByteArray? =
        prefs.getString(key, null)?.let { runCatching { Base64.getDecoder().decode(it) }.getOrNull() }

    override fun remove(key: String) {
        prefs.edit().remove(key).apply()
    }

    override fun keys(): Set<String> = prefs.all.keys.toSet()
}
