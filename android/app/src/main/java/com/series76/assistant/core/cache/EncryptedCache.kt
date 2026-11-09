package com.series76.assistant.core.cache

import com.series76.assistant.core.net.MessageItem
import com.series76.assistant.core.net.SessionSummary
import com.series76.assistant.core.security.CipherBox
import com.series76.assistant.core.security.KeyUnavailableException
import com.series76.assistant.core.security.UserKeyring

/** A cached row: only ids, timestamps, flags, and an encrypted payload. */
data class RawConversationRow(
    val ownerKey: String,
    val sessionId: String,
    val payload: ByteArray,
    val updatedAt: String,
    val pendingJobs: Int,
    val lastSync: Long,
)

data class RawMessageRow(
    val ownerKey: String,
    val sessionId: String,
    val messageId: String,
    val payload: ByteArray,
    val createdAt: String,
    val lastSync: Long,
)

/** The storage seam (Room in the app, in memory in tests). No plaintext columns. */
interface RawCacheDao {
    suspend fun upsertConversations(rows: List<RawConversationRow>)
    suspend fun conversations(ownerKey: String): List<RawConversationRow>
    suspend fun deleteConversation(ownerKey: String, sessionId: String)
    suspend fun upsertMessages(rows: List<RawMessageRow>)
    suspend fun messages(ownerKey: String, sessionId: String): List<RawMessageRow>
    suspend fun purgeOwner(ownerKey: String)
}

data class CachedList(val items: List<SessionSummary>, val lastSync: Long?)

data class CachedMessages(val items: List<MessageItem>, val lastSync: Long?)

/**
 * The per-user, payload-encrypted read cache (Spec 5 Req 1.5, 9.1, 9.4, 9.9).
 *
 * - Titles and messages are AES-GCM encrypted under the account's data key with
 *   AAD binding owner + table + id; there is no plaintext index.
 * - Every read is scoped to one owner key; another account's rows are never read.
 * - If the account key is unavailable, the cache reads as empty (no ciphertext,
 *   no partial plaintext is ever exposed).
 * - The cache is never the source of truth and never re-uploaded.
 */
class EncryptedCache(private val dao: RawCacheDao, private val keyring: UserKeyring) {

    private fun aad(owner: String, table: String, id: String) = "$owner|$table|$id".toByteArray()

    suspend fun putConversations(owner: String, items: List<SessionSummary>, now: Long) {
        val box = keyring.boxFor(owner) ?: return
        dao.upsertConversations(items.map { s ->
            RawConversationRow(
                ownerKey = owner,
                sessionId = s.sessionId,
                payload = box.encrypt((s.title ?: "").toByteArray(), aad(owner, "conv", s.sessionId)),
                updatedAt = s.updatedAt,
                pendingJobs = s.pendingJobs,
                lastSync = now,
            )
        })
    }

    suspend fun conversations(owner: String): CachedList {
        val box = keyring.boxFor(owner, create = false) ?: return CachedList(emptyList(), null)
        val rows = dao.conversations(owner).filter { it.ownerKey == owner }
        val items = try {
            rows.map { r ->
                val title = box.decrypt(r.payload, aad(owner, "conv", r.sessionId)).decodeToString()
                SessionSummary(r.sessionId, title.ifEmpty { null }, "", r.updatedAt, r.pendingJobs)
            }
        } catch (e: KeyUnavailableException) {
            return CachedList(emptyList(), null)
        }
        return CachedList(items, rows.maxOfOrNull { it.lastSync })
    }

    suspend fun putMessages(owner: String, sessionId: String, items: List<MessageItem>, now: Long) {
        val box = keyring.boxFor(owner) ?: return
        dao.upsertMessages(items.map { m ->
            RawMessageRow(
                ownerKey = owner,
                sessionId = sessionId,
                messageId = m.messageId,
                payload = box.encrypt(encodeMessage(m), aad(owner, "msg", m.messageId)),
                createdAt = m.createdAt,
                lastSync = now,
            )
        })
    }

    suspend fun messages(owner: String, sessionId: String): CachedMessages {
        val box = keyring.boxFor(owner, create = false) ?: return CachedMessages(emptyList(), null)
        val rows = dao.messages(owner, sessionId).filter { it.ownerKey == owner }
            .sortedWith(compareBy({ it.createdAt }, { it.messageId }))
        val items = try {
            rows.map { r -> decodeMessage(box, owner, r) }
        } catch (e: KeyUnavailableException) {
            return CachedMessages(emptyList(), null)
        }
        return CachedMessages(items, rows.maxOfOrNull { it.lastSync })
    }

    /** A conversation the backend reports gone is purged, never re-uploaded. */
    suspend fun forget(owner: String, sessionId: String) = dao.deleteConversation(owner, sessionId)

    /** Account switch / logout purge: rows AND the wrapped key (crypto-shred). */
    suspend fun purgeOwner(owner: String) {
        dao.purgeOwner(owner)
        keyring.shred(owner)
    }

    private fun encodeMessage(m: MessageItem): ByteArray =
        listOf(m.messageId, m.role, m.createdAt, m.content, m.blocksJson)
            .joinToString(SEP) { it.replace(SEP, " ") }.toByteArray()

    private fun decodeMessage(box: CipherBox, owner: String, r: RawMessageRow): MessageItem {
        val parts = box.decrypt(r.payload, aad(owner, "msg", r.messageId)).decodeToString()
            .split(SEP, limit = 5)
        if (parts.size != 5) throw KeyUnavailableException("corrupt cache payload")
        return MessageItem(parts[0], parts[1], parts[3], parts[4], parts[2])
    }

    private companion object {
        const val SEP = "\u001F"
    }
}

/** In-memory DAO (unit tests and a no-database fallback). */
class InMemoryRawCacheDao : RawCacheDao {
    val conversationRows = mutableListOf<RawConversationRow>()
    val messageRows = mutableListOf<RawMessageRow>()

    override suspend fun upsertConversations(rows: List<RawConversationRow>) {
        rows.forEach { r ->
            conversationRows.removeAll { it.ownerKey == r.ownerKey && it.sessionId == r.sessionId }
            conversationRows += r
        }
    }

    override suspend fun conversations(ownerKey: String) =
        conversationRows.filter { it.ownerKey == ownerKey }

    override suspend fun deleteConversation(ownerKey: String, sessionId: String) {
        conversationRows.removeAll { it.ownerKey == ownerKey && it.sessionId == sessionId }
        messageRows.removeAll { it.ownerKey == ownerKey && it.sessionId == sessionId }
    }

    override suspend fun upsertMessages(rows: List<RawMessageRow>) {
        rows.forEach { r ->
            messageRows.removeAll { it.ownerKey == r.ownerKey && it.messageId == r.messageId }
            messageRows += r
        }
    }

    override suspend fun messages(ownerKey: String, sessionId: String) =
        messageRows.filter { it.ownerKey == ownerKey && it.sessionId == sessionId }

    override suspend fun purgeOwner(ownerKey: String) {
        conversationRows.removeAll { it.ownerKey == ownerKey }
        messageRows.removeAll { it.ownerKey == ownerKey }
    }
}
