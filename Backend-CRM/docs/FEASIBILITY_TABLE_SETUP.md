# Feasibility Custom Questions Table Setup

## Quick Answer

**Which Database?** PostgreSQL (your main CRM database - same as where `studies` table is)  
**Where to run?** In your Backend-CRM directory  
**What to run?** Use the migration script or SQL directly

---

## Option 1: Run Migration Script (Recommended)

### Step 1: Navigate to Backend-CRM directory
```bash
cd Backend-CRM
```

### Step 2: Run the migration script
```bash
python create_feasibility_custom_questions_table.py
```

This script will:
- ✅ Check if table already exists
- ✅ Create the table if it doesn't exist
- ✅ Create indexes automatically
- ✅ Handle Docker/localhost connection automatically

---

## Option 2: Run SQL Directly

### If using Docker PostgreSQL:

**Step 1:** Connect to PostgreSQL container
```bash
docker-compose exec postgres psql -U crm_user -d crm_db
```

**Step 2:** Run this SQL:
```sql
CREATE TABLE IF NOT EXISTS project_feasibility_custom_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id UUID NOT NULL,
    workflow_step VARCHAR(50) NOT NULL DEFAULT 'feasibility',
    question_text TEXT NOT NULL,
    section VARCHAR(255),
    expected_response_type VARCHAR(50),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_project_feasibility_custom_questions_study
        FOREIGN KEY(study_id) 
        REFERENCES studies(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_project_feasibility_custom_questions_study_id 
    ON project_feasibility_custom_questions (study_id);

CREATE INDEX IF NOT EXISTS ix_project_feasibility_custom_questions_workflow_step 
    ON project_feasibility_custom_questions (workflow_step);
```

**Step 3:** Exit psql
```bash
\q
```

---

### If using External PostgreSQL (e.g., Neon, Azure, etc.):

**Step 1:** Connect using your database tool (pgAdmin, DBeaver, etc.) or psql:
```bash
psql "your-postgresql-connection-string"
```

**Step 2:** Run the same SQL as above

---

## Verify Table Creation

After running the migration, verify the table exists:

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name = 'project_feasibility_custom_questions';
```

You should see one row returned.

---

## Database Connection Details

The table goes into the **same PostgreSQL database** where you have:
- `studies` table
- `sites` table  
- `users` table
- `site_workflow_steps` table

**Connection info from docker-compose.yml:**
- Database: `crm_db`
- User: `crm_user` (or from your `.env` file)
- Password: `crm_pass` (or from your `.env` file)
- Port: `5432` (if using Docker)

**Your `.env` file should have:**
```bash
DATABASE_URL=postgresql+asyncpg://crm_user:crm_pass@postgres:5432/crm_db
```

---

## Troubleshooting

### Error: "relation 'studies' does not exist"
**Solution:** Make sure the `studies` table exists first. Run `create_study_site_tables.py` if needed.

### Error: "permission denied"
**Solution:** Make sure you're using the correct database user with CREATE TABLE permissions.

### Error: "connection refused"
**Solution:** 
- If using Docker: Make sure `docker-compose up -d postgres` is running
- If using external DB: Check your connection string in `.env`

---

## Summary

✅ **Database:** PostgreSQL (main CRM database)  
✅ **Table Name:** `project_feasibility_custom_questions`  
✅ **Migration Script:** `create_feasibility_custom_questions_table.py`  
✅ **Runs on:** Same database as your `studies` table
