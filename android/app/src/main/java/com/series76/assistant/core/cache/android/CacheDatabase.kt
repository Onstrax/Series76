package com.series76.assistant.core.cache.android

import android.content.Context
import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Upsert
import androidx.room.withTransaction
import com.series76.assistant.core.cache.RawCacheDao
import com.series76.assistant.core.cache.RawConversationRow
import com.series76.assistant.core.cache.RawMessageRow

/**
 * Room read cache (Spec 5 Req 1.5, 9.4). Rows hold only an opaque owner key,
 * ids, timestamps, flags, and an AES-GCM `payload`; there is no plaintext
 * title / message column, hence no plaintext index.
 */
@Entity(tableName = "cached_conversations", primaryKeys = ["ownerKey", "sessionId"])
data class ConversationEntity(
    val ownerKey: String,
    val sessionId: String,
    @ColumnInfo(typeAffinity = ColumnInfo.BLOB) val payload: ByteArray,
    val updatedAt: String,
    val pendingJobs: Int,
    val lastSync: Long,
)

@Entity(tableName = "cached_messages", primaryKeys = ["ownerKey", "messageId"])
data class MessageEntity(
    val ownerKey: String,
    val sessionId: String,
    val messageId: String,
    @ColumnInfo(typeAffinity = ColumnInfo.BLOB) val payload: ByteArray,
    val createdAt: String,
    val lastSync: Long,
)

@Dao
interface CacheDao {
    @Upsert
    suspend fun upsertConversations(rows: List<ConversationEntity>)

    @Query("SELECT * FROM cached_conversations WHERE ownerKey = :owner")
    suspend fun conversations(owner: String): List<ConversationEntity>

    @Query("DELETE FROM cached_conversations WHERE ownerKey = :owner AND sessionId = :sessionId")
    suspend fun deleteConversation(owner: String, sessionId: String)

    @Query("DELETE FROM cached_messages WHERE ownerKey = :owner AND sessionId = :sessionId")
    suspend fun deleteMessagesOf(owner: String, sessionId: String)

    @Upsert
    suspend fun upsertMessages(rows: List<MessageEntity>)

    @Query(
        "SELECT * FROM cached_messages WHERE ownerKey = :owner AND sessionId = :sessionId " +
            "ORDER BY createdAt ASC, messageId ASC",
    )
    suspend fun messages(owner: String, sessionId: String): List<MessageEntity>

    @Query("DELETE FROM cached_conversations WHERE ownerKey = :owner")
    suspend fun purgeConversations(owner: String)

    @Query("DELETE FROM cached_messages WHERE ownerKey = :owner")
    suspend fun purgeMessages(owner: String)
}

@Database(entities = [ConversationEntity::class, MessageEntity::class], version = 1, exportSchema = false)
abstract class CacheDatabase : RoomDatabase() {
    abstract fun dao(): CacheDao

    companion object {
        fun create(context: Context): CacheDatabase =
            Room.databaseBuilder(context, CacheDatabase::class.java, "series76-cache.db")
                .fallbackToDestructiveMigration()
                .build()
    }
}

/** Adapts Room to the pure [RawCacheDao] seam used by the encrypted cache. */
class RoomRawCacheDao(private val db: CacheDatabase) : RawCacheDao {
    private val dao = db.dao()

    override suspend fun upsertConversations(rows: List<RawConversationRow>) =
        dao.upsertConversations(rows.map {
            ConversationEntity(it.ownerKey, it.sessionId, it.payload, it.updatedAt, it.pendingJobs, it.lastSync)
        })

    override suspend fun conversations(ownerKey: String): List<RawConversationRow> =
        dao.conversations(ownerKey).map {
            RawConversationRow(it.ownerKey, it.sessionId, it.payload, it.updatedAt, it.pendingJobs, it.lastSync)
        }

    override suspend fun deleteConversation(ownerKey: String, sessionId: String) =
        db.withTransaction {
            dao.deleteConversation(ownerKey, sessionId)
            dao.deleteMessagesOf(ownerKey, sessionId)
        }

    override suspend fun upsertMessages(rows: List<RawMessageRow>) =
        dao.upsertMessages(rows.map {
            MessageEntity(it.ownerKey, it.sessionId, it.messageId, it.payload, it.createdAt, it.lastSync)
        })

    override suspend fun messages(ownerKey: String, sessionId: String): List<RawMessageRow> =
        dao.messages(ownerKey, sessionId).map {
            RawMessageRow(it.ownerKey, it.sessionId, it.messageId, it.payload, it.createdAt, it.lastSync)
        }

    override suspend fun purgeOwner(ownerKey: String) = db.withTransaction {
        dao.purgeConversations(ownerKey)
        dao.purgeMessages(ownerKey)
    }
}
