# Dual-Database Architecture Documentation

## Overview

This backend has been refactored to use a **dual-database architecture**:
- **PostgreSQL** for structured CRM data (Users, Studies, Sites, Access Control, Audit Logs)
- **MongoDB** for flexible, high-volume data (Conversations, Messages, Threads, Attachments)

## Database Mapping

### PostgreSQL (Structured Data)
- `users` - User accounts and authentication
- `studies` - Clinical studies
- `sites` - Study sites
- `user_sites` - User-site associations
- `user_profiles` - User profile information
- `rd_studies` - R&D studies
- `iis_studies` - IIS studies
- `events` - User events
- `conversation_access` - Access control grants (links Postgres users to MongoDB conversations)
- `audit_logs` - System audit logs
- `chat_messages` - Private AI chat messages
- `chat_documents` - Private AI chat documents

### MongoDB (Flexible/High-Volume Data)
- `conversations` - All conversation documents
- `messages` - All message documents
- `attachments` - All attachment documents
- `threads` - Thread documents
- `thread_participants` - Thread participant documents
- `thread_messages` - Thread message documents
- `thread_attachments` - Thread attachment link documents
- `thread_from_conversations` - Thread-from-conversation link documents

## Architecture Changes

### 1. Repository Pattern

All database access now goes through repository classes:

**MongoDB Repositories** (`app/repositories/mongo_repository.py`):
- `ConversationRepository`
- `MessageRepository`
- `AttachmentRepository`
- `ThreadRepository`
- `ThreadParticipantRepository`
- `ThreadMessageRepository`
- `ThreadAttachmentRepository`
- `ThreadFromConversationRepository`

**PostgreSQL Repositories** (`app/repositories/postgres_repository.py`):
- `UserRepository`
- `ConversationAccessRepository`
- `StudyRepository`
- `SiteRepository`

### 2. CRUD Layer Changes

The `crud.py` module has been updated to:
- Use MongoDB repositories for conversation/message/thread operations
- Use PostgreSQL repositories for user/study/site operations
- Return dictionaries instead of SQLAlchemy models for MongoDB-backed entities (for compatibility)

### 3. Data Model Changes

**Conversations, Messages, Threads** are now stored as JSON documents in MongoDB with:
- UUID `id` fields stored as strings
- Timestamps as `datetime` objects
- Enum values stored as strings
- Flexible JSON structure for metadata

**Access Control** remains in PostgreSQL:
- `ConversationAccess` table links Postgres `user_id` to MongoDB `conversation_id` (UUID stored as string)

## Migration Notes

### Backward Compatibility

The API layer maintains backward compatibility:
- API endpoints return the same response structure
- Pydantic schemas handle dict-to-model conversion
- Existing frontend code should work without changes

### Data Migration

**TODO: DATA MIGRATION SCRIPT NEEDED**

To migrate existing PostgreSQL conversations/messages to MongoDB:

1. Export conversations from PostgreSQL
2. Transform to MongoDB document format
3. Import into MongoDB collections
4. Verify data integrity
5. Update any hardcoded references

See `scripts/migrate_to_dual_db.py` (to be created) for migration script.

## Environment Variables

Add to `.env`:

```bash
# MongoDB Configuration
MONGODB_URI=mongodb://mongo:27017
MONGODB_DATABASE=crm_db
```

## Running Locally

1. **Start Docker services:**
   ```bash
   docker-compose up -d postgres redis mongo
   ```

2. **Verify MongoDB connection:**
   ```bash
   docker-compose exec backend python -c "from app.db.mongo import get_mongo_client; import asyncio; asyncio.run(get_mongo_client())"
   ```

3. **Start backend:**
   ```bash
   docker-compose up backend worker
   ```

## Known Limitations / TODOs

1. **Statistics Aggregation**: `get_conversation_stats()` still needs MongoDB aggregation pipeline implementation
2. **Thread Functions**: Some thread CRUD functions may still need refactoring
3. **Channel Filtering**: Channel-based filtering in `list_conversations()` may need MongoDB aggregation
4. **Data Migration**: No migration script yet for existing PostgreSQL data

## Logging

All MongoDB operations are logged with `[MONGO]` prefix:
- `[MONGO] Created conversation: ...`
- `[MONGO] Created message: ...`

PostgreSQL operations continue to use standard SQLAlchemy logging.

## Error Handling

- MongoDB connection errors are caught and logged
- API endpoints return consistent error responses regardless of database
- Missing documents return `None` (same as SQLAlchemy)

## Testing

When testing:
1. Ensure both PostgreSQL and MongoDB are running
2. Test conversation/message creation (MongoDB)
3. Test user/study/site operations (PostgreSQL)
4. Test access control (cross-database: Postgres users → MongoDB conversations)

