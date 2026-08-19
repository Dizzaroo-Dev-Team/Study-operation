# Fix Production Error: Missing Columns in site_status_history

## Problem
The production database is missing `triggering_event` and `reason` columns in the `site_status_history` table, causing this error:
```
asyncpg.exceptions.UndefinedColumnError: column site_status_history.triggering_event does not exist
```

## Solution
Add the missing columns to the production database.

---

## Step-by-Step Instructions

### Step 1: Connect to Production Database (Neon)

**Option A: Using Neon Console (Easiest)**
1. Go to https://console.neon.tech
2. Log in and select your project
3. Click on **"SQL Editor"** in the left sidebar
4. You're now connected to your production database

**Option B: Using psql Command Line**
```bash
# Get connection string from Neon Console → Settings → Connection Details
# Then run:
psql "postgresql://user:password@host.neon.tech/dbname"
```

---

### Step 2: Run the Migration

**In Neon SQL Editor, copy and paste this SQL:**

```sql
-- Add missing columns to site_status_history (if they don't exist)
DO $$
BEGIN
    -- Add triggering_event column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_status_history' 
        AND column_name = 'triggering_event'
    ) THEN
        ALTER TABLE site_status_history 
        ADD COLUMN triggering_event VARCHAR(100);
        RAISE NOTICE 'Added triggering_event column';
    ELSE
        RAISE NOTICE 'triggering_event column already exists';
    END IF;

    -- Add reason column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_status_history' 
        AND column_name = 'reason'
    ) THEN
        ALTER TABLE site_status_history 
        ADD COLUMN reason TEXT;
        RAISE NOTICE 'Added reason column';
    ELSE
        RAISE NOTICE 'reason column already exists';
    END IF;
END $$;
```

**Click "Run" or press Ctrl+Enter**

You should see messages like:
- `Added triggering_event column`
- `Added reason column`

---

### Step 3: Verify the Fix

**Run this verification query:**

```sql
-- Check if columns exist
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' 
  AND table_name = 'site_status_history'
  AND column_name IN ('triggering_event', 'reason')
ORDER BY column_name;
```

**Expected Result:**
```
column_name        | data_type | is_nullable
-------------------+-----------+-------------
reason             | text      | YES
triggering_event   | character varying | YES
```

---

### Step 4: Test the Application

1. **Restart your production backend** (if it's running)
   - The error should be resolved now

2. **Test the endpoint that was failing:**
   - Try accessing the site status detail endpoint
   - The error `column site_status_history.triggering_event does not exist` should be gone

3. **Check application logs:**
   - Verify no more database errors appear

---

## Troubleshooting

### If you get permission errors:
- Make sure you're using the correct database user with ALTER TABLE permissions
- Check your Neon project settings

### If columns already exist:
- That's fine! The migration checks first and won't fail
- You'll see "column already exists" messages

### If you're unsure:
- Run the verification query (Step 3) first to check current state
- The migration is safe to run multiple times

---

## Quick Reference

**Columns being added:**
- `triggering_event` (VARCHAR(100), nullable)
- `reason` (TEXT, nullable)

**Table affected:** `site_status_history`

**Safety:** ✅ Safe - only adds columns, doesn't modify or delete data
