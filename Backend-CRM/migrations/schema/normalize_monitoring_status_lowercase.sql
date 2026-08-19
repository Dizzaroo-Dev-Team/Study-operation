-- Migration: normalize_monitoring_status_lowercase.sql
-- Purpose:
--   Normalize monitoring_findings.status / .due_color and
--   monitoring_visits.status to lowercase so the dashboard query stops
--   needing `WHERE LOWER(status) <> 'resolved'` (which defeats a regular
--   b-tree index on `status`).
--
-- Date: 2026-05-15
--
-- What this script does
-- ---------------------
-- 1. Lowercases existing values in-place. Idempotent — re-running on
--    already-lowercase data is a no-op.
-- 2. Drops the functional index added in
--    `add_perf_indexes_audit_monitoring_agreements.sql`
--    (idx_monitoring_findings_lower_status). It was a workaround for
--    LOWER() in queries; after this migration the queries no longer use
--    LOWER, so a plain composite index serves them faster.
-- 3. Creates a plain (status, visit_id) index in its place.
--
-- Application code changes that pair with this migration
-- ------------------------------------------------------
--   * app/modules/monitoring/routes/dashboard.py — every
--     `WHERE LOWER(f.status) <> 'resolved'` becomes
--     `WHERE f.status <> 'resolved'`. Same for v.status.
--   * Two known status WRITES that hardcoded mixed case:
--       confirmation_letter.py:750  'Site Confirmed' → 'site confirmed'
--       findings.py:267              'Resolved'      → 'resolved'
--     Both are updated in this PR.
--
-- Production deploy
-- -----------------
-- Run during a low-traffic window. The UPDATEs touch every row whose value
-- isn't already lowercase; on a 100k-row table this is sub-second, on
-- millions of rows it's still well under a minute. CREATE INDEX
-- CONCURRENTLY for the replacement; DROP INDEX CONCURRENTLY for the
-- workaround — neither blocks writes.

BEGIN;

UPDATE public.monitoring_findings
SET status = LOWER(status)
WHERE status IS DISTINCT FROM LOWER(status);

UPDATE public.monitoring_findings
SET due_color = LOWER(due_color)
WHERE due_color IS DISTINCT FROM LOWER(due_color);

UPDATE public.monitoring_visits
SET status = LOWER(status)
WHERE status IS DISTINCT FROM LOWER(status);

COMMIT;

-- ── Index swap (run OUTSIDE the transaction; CONCURRENTLY forbids txn). ──

-- Plain composite — usable now that queries no longer wrap status in LOWER().
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_monitoring_findings_status_visit
    ON public.monitoring_findings (status, visit_id);

-- Drop the workaround functional index.
DROP INDEX CONCURRENTLY IF EXISTS public.idx_monitoring_findings_lower_status;

-- Verification:
--   SELECT status, COUNT(*) FROM monitoring_findings GROUP BY status;
--   SELECT due_color, COUNT(*) FROM monitoring_findings GROUP BY due_color;
--   SELECT status, COUNT(*) FROM monitoring_visits GROUP BY status;
-- Every row should show a lowercase value.
