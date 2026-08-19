# Clear Agreement Data - Instructions

## Fixed Issues

1. ✅ **Backend Error Fixed**: `TypeError: 'bool' object is not subscriptable`
   - Fixed in `build_agreement_response()` function
   - `check_can_upload_new_version` returns `bool`, not tuple

2. ✅ **Reset Script Emoji Issues Fixed**: Removed all emoji characters for Windows compatibility

## How to Clear Agreement Data

### Option 1: Using SQL File (Recommended)

1. **Find your PostgreSQL container name**:
   ```bash
   docker ps | grep postgres
   ```

2. **Run the SQL script**:
   ```bash
   # If using docker-compose
   docker-compose exec postgres psql -U postgres -d crm_db < clear_agreement_data.sql
   
   # Or if you know the container name
   docker exec -i <postgres_container_name> psql -U postgres -d crm_db < clear_agreement_data.sql
   ```

### Option 2: Using Python Script (If Database is Accessible)

```bash
cd Backend-CRM
python reset_agreement_workflow_data.py --confirm-reset
```

**Note**: This requires the database to be accessible from your host machine. If running in Docker, use Option 1.

### Option 3: Direct SQL Commands

Connect to your database and run:

```sql
DELETE FROM agreement_inline_comments;
DELETE FROM agreement_comments;
DELETE FROM agreement_documents;
DELETE FROM agreement_versions;
DELETE FROM agreements;
DELETE FROM study_templates;
```

## What Gets Deleted

✅ **Deleted**:
- `agreement_inline_comments`
- `agreement_comments`
- `agreement_documents`
- `agreement_versions`
- `agreements`
- `study_templates`

❌ **NOT Deleted** (Safe):
- Users
- Sites
- Studies
- IAM tables
- Notice board
- Site status
- Any other CRM tables

## Verification

After running the script, verify all tables are empty:

```sql
SELECT 
    'agreement_inline_comments' as table_name, COUNT(*) as remaining_rows FROM agreement_inline_comments
UNION ALL
SELECT 'agreement_comments', COUNT(*) FROM agreement_comments
UNION ALL
SELECT 'agreement_documents', COUNT(*) FROM agreement_documents
UNION ALL
SELECT 'agreement_versions', COUNT(*) FROM agreement_versions
UNION ALL
SELECT 'agreements', COUNT(*) FROM agreements
UNION ALL
SELECT 'study_templates', COUNT(*) FROM study_templates;
```

All counts should be 0.

---

**Files Created**:
- `clear_agreement_data.sql` - SQL script to run directly
- `clear_agreement_data_docker.sh` - Docker execution helper (for reference)
