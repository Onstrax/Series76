package com.series76.assistant.core.security

import com.series76.assistant.core.net.TokenPair
import com.series76.assistant.core.net.TokenStore
import java.security.MessageDigest
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Tokens persisted only as AES-GCM ciphertext under the Keystore-backed master
 * key (Spec 5 Req 3.9; Property 15). Nothing is ever stored in plaintext.
 */
class SecureTokenStore(private val master: CipherBox, private val blobs: BlobStore) : TokenStore {
    private val mutex = Mutex()
    private var cached: TokenPair? = null

    override suspend fun current(): TokenPair? = mutex.withLock {
        cached ?: blobs.get(KEY)?.let { blob ->
            try {
                val text = master.decrypt(blob, KEY.toByteArray()).decodeToString()
                val (access, refresh) = text.split('\n', limit = 2)
                TokenPair(access, refresh).also { cached = it }
            } catch (e: KeyUnavailableException) {
                blobs.remove(KEY) // unreadable: treated as no session (fail closed)
                null
            } catch (e: IndexOutOfBoundsException) {
                blobs.remove(KEY)
                null
            }
        }
    }

    override suspend fun save(pair: TokenPair) = mutex.withLock {
        val plain = "${pair.accessToken}\n${pair.refreshToken}".toByteArray()
        blobs.put(KEY, master.encrypt(plain, KEY.toByteArray()))
        cached = pair
    }

    override suspend fun clear() = mutex.withLock {
        blobs.remove(KEY)
        cached = null
    }

    private companion object {
        const val KEY = "tokens.v1"
    }
}

/**
 * Per-user data keys: a random 256-bit key per account, stored only *wrapped*
 * by the Keystore master key. Purging an account removes its wrapped key, so
 * its cached ciphertext becomes permanently unreadable (crypto-shred).
 */
class UserKeyring(private val master: CipherBox, private val blobs: BlobStore) {

    /** An opaque, non-reversible partition key for an account (no plaintext id stored). */
    fun ownerKey(userId: String): String =
        MessageDigest.getInstance("SHA-256").digest(userId.toByteArray())
            .joinToString("") { "%02x".format(it) }

    /** The account's data box, creating its key on first use; `null` if unavailable. */
    fun boxFor(ownerKey: String, create: Boolean = true): CipherBox? {
        val slot = "wrapped_key.$ownerKey"
        val wrapped = blobs.get(slot)
        val raw: ByteArray = try {
            when {
                wrapped != null -> master.decrypt(wrapped, slot.toByteArray())
                create -> AesGcmCipherBox.randomKeyBytes().also { fresh ->
                    blobs.put(slot, master.encrypt(fresh, slot.toByteArray()))
                }
                else -> return null
            }
        } catch (e: KeyUnavailableException) {
            return null // Keystore key gone: the cache is treated as empty (Req 9.9)
        }
        return AesGcmCipherBox.ofRawKey(raw)
    }

    /** Remove the account's wrapped key (and anything else stored for it). */
    fun shred(ownerKey: String) {
        blobs.keys().filter { it.endsWith(".$ownerKey") || it.contains(".$ownerKey.") }
            .forEach(blobs::remove)
    }

    fun hasKey(ownerKey: String): Boolean = blobs.get("wrapped_key.$ownerKey") != null
}

/**
 * Encrypted composer drafts, per account and conversation (Req 7.2): kept
 * across background / termination / restart, never auto-sent.
 */
class DraftStore(private val keyring: UserKeyring, private val blobs: BlobStore) {

    private fun slot(ownerKey: String, conversation: String) =
        "draft.$ownerKey.${conversation.ifEmpty { "new" }}"

    fun save(ownerKey: String, conversation: String, text: String) {
        val box = keyring.boxFor(ownerKey) ?: return
        val slot = slot(ownerKey, conversation)
        if (text.isEmpty()) {
            blobs.remove(slot)
        } else {
            blobs.put(slot, box.encrypt(text.toByteArray(), slot.toByteArray()))
        }
    }

    fun load(ownerKey: String, conversation: String): String {
        val slot = slot(ownerKey, conversation)
        val blob = blobs.get(slot) ?: return ""
        val box = keyring.boxFor(ownerKey, create = false) ?: return ""
        return try {
            box.decrypt(blob, slot.toByteArray()).decodeToString()
        } catch (e: KeyUnavailableException) {
            ""
        }
    }
}
