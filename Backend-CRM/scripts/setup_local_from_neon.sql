-- =====================================================================
-- setup_local_from_neon.sql
--
-- One-shot bootstrap for a developer's LOCAL Postgres database.
-- Neon is the source of truth: this script assumes ../local_schema.sql
-- was just refreshed from Neon (see scripts/refresh_local_from_neon.ps1
-- or the pg_dump command below).
--
-- What it does:
--   1. Loads the full public schema from ../local_schema.sql
--   2. Seeds site-budgeting master data (cost elements + factor types)
--
-- What it does NOT do:
--   - It does not CREATE DATABASE. Create + connect to your local DB first.
--   - It does not copy customer / transactional data from Neon.
--   - It does not run irreversible drops; the schema file itself may
--     contain DROP/CREATE inside it (pg_dump output).
--
-- ---------------------------------------------------------------------
-- Usage (run from inside Backend-CRM/):
--
--   # 1. (Optional) refresh the schema dump from Neon — Neon is source of truth.
--   #    Replace the host/db/user with your Neon connection.
--   pg_dump \
--     --no-owner --no-privileges --schema-only --schema=public \
--     "postgresql://USER:PASSWORD@HOST/DB?sslmode=require" \
--     > local_schema.sql
--
--   # 2. Create + connect to your local DB, then load this file.
--   createdb crm_local
--   psql -d crm_local -v ON_ERROR_STOP=1 -f scripts/setup_local_from_neon.sql
--
-- Or via PowerShell wrapper that does both steps:
--   pwsh scripts/refresh_local_from_neon.ps1
-- =====================================================================

\set ON_ERROR_STOP on
\echo
\echo '==> Target database:'
SELECT current_database() AS db, current_user AS usr, version();

\echo
\echo '==> Loading schema from ../local_schema.sql ...'
\i local_schema.sql

\echo
\echo '==> Seeding site-budgeting master data ...'
\i scripts/seed_cost_elements.sql
\i scripts/seed_factor_types.sql

\echo
\echo '==> Sanity counts (non-zero means seeds applied):'
SELECT 'cost_element'           AS table, COUNT(*) AS rows FROM cost_element
UNION ALL
SELECT 'element_cost_version'   AS table, COUNT(*) AS rows FROM element_cost_version
UNION ALL
SELECT 'conversion_factor_type' AS table, COUNT(*) AS rows FROM conversion_factor_type;

\echo
\echo '==> Done. Local DB now matches Neon schema + master seed data.'
