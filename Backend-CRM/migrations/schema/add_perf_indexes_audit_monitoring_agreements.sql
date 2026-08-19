-- Migration: add_perf_indexes_audit_monitoring_agreements.sql
-- Purpose: Add the missing indexes flagged by the May 2026 performance audit.
-- Tables:  audit_logs, site_status_history, monitoring_findings, agreement_changes
-- Date:    2026-05-14
--
-- IMPORTANT — production deploy notes
-- -----------------------------------
-- All statements use CREATE INDEX CONCURRENTLY so live writes are NOT blocked.
-- BUT: CONCURRENTLY cannot run inside an explicit transaction, and on large
-- tables (audit_logs > 1M rows) each build can take minutes to hours.
--
-- Run with `psql --single-transaction=off` (the default for `psql -f`), and
-- run during a low-traffic window if any of these tables are huge in prod.
-- If a CONCURRENTLY build fails, Postgres leaves the index marked INVALID;
-- drop it and re-run rather than letting the planner pick a half-built one:
--
--   SELECT indexname FROM pg_indexes WHERE indexname LIKE 'idx_audit_logs_%';
--   -- if any show as INVALID in \d, drop with: DROP INDEX CONCURRENTLY idx_…;
--
-- All indexes use IF NOT EXISTS so the script is idempotent.

-- =============================================================================
-- audit_logs — currently has NO indexes outside the primary key. Every filter
-- (target lookup, by-user audit trail, by-action search, time-range queries)
-- falls back to a sequential scan today.
-- =============================================================================
-- Lookup "what happened to this object?" — by far the most common query.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_target
    ON public.audit_logs (target_type, target_id, "timestamp" DESC);

-- "What did this user do recently?" — admin audit / SOC investigations.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_user_time
    ON public.audit_logs ("user", "timestamp" DESC);

-- "Show all <action> events" — feeds change-of-status streams and dashboards.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_action_time
    ON public.audit_logs (action, "timestamp" DESC);

-- =============================================================================
-- site_status_history — append-only ledger, no indexes today. Dashboards that
-- ask "status history for site X" or "recent transitions in last N days"
-- sequential-scan the whole table.
-- =============================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_site_status_history_site_time
    ON public.site_status_history (site_id, changed_at DESC);

-- =============================================================================
-- monitoring_findings — the dashboard query
--   SELECT ... FROM monitoring_findings f WHERE LOWER(f.status) <> 'resolved'
-- (app/modules/monitoring/routes/dashboard.py) is index-defeating because of
-- LOWER(). Two indexes here:
--
--   1) Functional index on LOWER(status) — usable by the existing query NOW.
--   2) Composite (status, visit_id) — usable by anything that pre-normalizes
--      the status string in app code, which Task 20 of the perf plan will do.
--
-- Both live side by side until Task 20 lands, then idx_monitoring_findings_lower_status
-- can be dropped if/when the column is normalized to lowercase.
-- =============================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_monitoring_findings_lower_status
    ON public.monitoring_findings (LOWER(status), visit_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_monitoring_findings_visit
    ON public.monitoring_findings (visit_id);

-- =============================================================================
-- agreement_changes — the audit UI repeatedly filters by:
--     agreement_id  AND  is_external_change  AND  is_accepted
-- (varchar 'true'/'false' columns, not bool — a separate clean-up). Today the
-- pk index does not help and each filter is a seq-scan of every change row for
-- that agreement.
-- =============================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_agreement_changes_filter
    ON public.agreement_changes (agreement_id, is_accepted, is_external_change);

-- Helps "latest changes on this agreement" timelines.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_agreement_changes_agreement_time
    ON public.agreement_changes (agreement_id, created_at DESC);

-- =============================================================================
-- Verification (run by hand after the script completes)
-- =============================================================================
--   \d+ audit_logs
--   \d+ site_status_history
--   \d+ monitoring_findings
--   \d+ agreement_changes
--
--   -- Confirm none of the new indexes are marked INVALID:
--   SELECT indexrelid::regclass AS index, indrelid::regclass AS table, indisvalid
--   FROM pg_index
--   WHERE indexrelid::regclass::text LIKE 'idx_audit_logs_%'
--      OR indexrelid::regclass::text LIKE 'idx_site_status_history_%'
--      OR indexrelid::regclass::text LIKE 'idx_monitoring_findings_%'
--      OR indexrelid::regclass::text LIKE 'idx_agreement_changes_%';
