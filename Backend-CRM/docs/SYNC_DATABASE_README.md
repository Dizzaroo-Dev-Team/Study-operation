# Database Setup & Sync Guide

How to get a working local Postgres for this project, and how to push schema between local and Neon.

## TL;DR — new developer, fresh machine

1. Install Postgres 15+ locally.
2. Create an empty database:
   ```sql
   CREATE DATABASE crm_local;
   ```
3. Connect to `crm_local` and paste / run the one-shot bootstrap:
   ```bash
   cd Backend-CRM
   psql -d crm_local -v ON_ERROR_STOP=1 -f scripts/setup_local_db_full.sql
   ```
   That creates all enums, tables, indexes, foreign keys, and seeds the minimum site-budgeting master data.
4. (Optional) Load the richer seed data:
   ```bash
   python migrations/seed/seed_budgeting_master_data.py
   python migrations/seed/seed_categories_and_bundles.py
   ```
5. Point your `.env` at the local DB:
   ```
   DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/crm_local
   ```

That is the supported path for new contributors.

## Refreshing local schema from Neon (Neon = source of truth)

When Neon picks up new tables/columns and you need your local to catch up, use the PowerShell wrapper:

```powershell
$env:NEON_DATABASE_URL = "postgresql://USER:PASS@HOST/DB?sslmode=require"
pwsh Backend-CRM/scripts/refresh_local_from_neon.ps1
```

It runs `pg_dump --schema-only` against Neon, drops + recreates the local DB, then loads the schema and seeds. Pass `-SkipDrop` to keep existing data, `-SkipSeeds` to skip the master-data seed.

## Pushing local table changes to Neon

If you have created new tables locally that don't exist on Neon yet:

```bash
cd Backend-CRM
python scripts/integration/sync_tables_to_neon.py
```

The script connects to both databases, finds tables that exist locally but not on Neon, extracts their DDL with `pg_dump`, and creates them on Neon. **It only adds — never drops or modifies existing Neon objects.**

### Prerequisites

- `pg_dump` on PATH (Postgres 15+ client tools).
- Environment variables:
  ```bash
  export LOCAL_DATABASE_URL="postgresql+asyncpg://crm_user:crm_pass@localhost:5432/crm_local"
  export NEON_DATABASE_URL="postgresql+asyncpg://user:password@host.neon.tech/dbname"
  ```

## Manual fallback

If the Python scripts are not an option:

```bash
# 1. Dump local schema
pg_dump --schema-only --no-owner --no-privileges \
  -h localhost -U crm_user -d crm_local > schema.sql

# 2. Edit schema.sql if needed, then push to Neon
psql "postgresql://USER:PASSWORD@HOST/DB?sslmode=require" -f schema.sql
```

## Notes

- **Data is not copied** by any of these flows — only schema. Use `pg_dump --data-only` if you need to move rows.
- The `migrations/` folder is the historical record of how the schema evolved. New devs do **not** need to run those files one by one; `setup_local_db_full.sql` already contains the final consolidated shape.
- The `migrations/archive/` folder contains superseded migrations kept only for audit purposes — do not run them in new environments.
