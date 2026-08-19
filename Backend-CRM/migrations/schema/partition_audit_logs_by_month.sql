-- Migration: partition_audit_logs_by_month.sql
-- Status:    TEMPLATE — DO NOT RUN YET.
-- Trigger:   audit_logs row count > ~5 million.
-- Date:      2026-05-15 (template prepared during May 2026 perf audit)
--
-- Why
-- ---
-- The Hunt 1 indexes (idx_audit_logs_target, idx_audit_logs_user_time,
-- idx_audit_logs_action_time) handle queries efficiently up to ~5M rows.
-- Beyond that, query plans degrade and VACUUM costs become noticeable.
-- Declarative monthly partitioning keeps each partition small (typically
-- <500k rows for a steady-state user base), shrinks index size per
-- partition, and makes archive/cold-storage of old data trivial.
--
-- Before running
-- --------------
-- 1. Confirm the trigger threshold:
--      SELECT count(*) FROM audit_logs;
--    If under ~5M, defer — premature partitioning adds operational
--    complexity for no benefit.
-- 2. Pick a brief read-only window (~30-60s on a 10M-row table).
-- 3. Backup audit_logs: `pg_dump -t audit_logs ... > audit_logs.bak.sql`.
-- 4. After running this script, deploy the cron job that creates next
--    month's partition automatically (see "Ongoing maintenance" below).
--
-- Strategy
-- --------
-- 1. Rename the existing table to audit_logs_legacy.
-- 2. Create the new partitioned table audit_logs with the same schema
--    (column order matters — Postgres ATTACH PARTITION checks tuple
--    structure).
-- 3. Create one partition per month going back N months covering the
--    legacy data.
-- 4. Re-attach indexes per partition (inherited from the parent).
-- 5. Move data: `INSERT INTO audit_logs SELECT * FROM audit_logs_legacy`.
-- 6. Drop the legacy table.
--
-- Run inside a single transaction so a failure mid-migration leaves the
-- old table intact.

BEGIN;

-- ── Step 1: rename existing ─────────────────────────────────────────────
ALTER TABLE public.audit_logs RENAME TO audit_logs_legacy;

-- ── Step 2: create partitioned table with the same column shape ─────────
CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    "user" character varying(100),
    action character varying(100) NOT NULL,
    target_type character varying(50) NOT NULL,
    target_id character varying(100) NOT NULL,
    details json,
    "timestamp" timestamp with time zone DEFAULT now(),
    CONSTRAINT audit_logs_pkey PRIMARY KEY (id, "timestamp")
)
PARTITION BY RANGE ("timestamp");

-- ── Step 3: create monthly partitions covering existing data ────────────
-- Adjust the start/end below to span min(timestamp) → end of next month.
-- Replace YYYY-MM-01 placeholders before running.
--
-- The DO block below auto-creates partitions from the min timestamp in
-- the legacy table up to (today + 30 days). Idempotent.

DO $$
DECLARE
    min_ts  timestamp with time zone;
    cursor_ts timestamp with time zone;
    end_ts  timestamp with time zone;
    partition_name text;
    partition_start text;
    partition_end text;
BEGIN
    SELECT date_trunc('month', COALESCE(min("timestamp"), now()))
    INTO min_ts
    FROM public.audit_logs_legacy;

    cursor_ts := min_ts;
    end_ts := date_trunc('month', now() + interval '60 days');

    WHILE cursor_ts < end_ts LOOP
        partition_name := 'audit_logs_y' || to_char(cursor_ts, 'YYYY') ||
                          'm' || to_char(cursor_ts, 'MM');
        partition_start := to_char(cursor_ts, 'YYYY-MM-01');
        partition_end := to_char(cursor_ts + interval '1 month', 'YYYY-MM-01');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.audit_logs ' ||
            'FOR VALUES FROM (%L) TO (%L);',
            partition_name, partition_start, partition_end
        );
        RAISE NOTICE 'Created partition % (% to %)', partition_name, partition_start, partition_end;

        cursor_ts := cursor_ts + interval '1 month';
    END LOOP;
END $$;

-- ── Step 4: re-create the Hunt 1 indexes on the parent (auto-cascades) ──
CREATE INDEX IF NOT EXISTS idx_audit_logs_target
    ON public.audit_logs (target_type, target_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time
    ON public.audit_logs ("user", "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_time
    ON public.audit_logs (action, "timestamp" DESC);

-- ── Step 5: copy data from legacy → partitioned ─────────────────────────
INSERT INTO public.audit_logs (id, "user", action, target_type, target_id, details, "timestamp")
SELECT id, "user", action, target_type, target_id, details, "timestamp"
FROM public.audit_logs_legacy;

-- ── Step 6: drop legacy (only if step 5 reported the expected row count) ─
-- Compare counts:
--   SELECT count(*) FROM audit_logs_legacy;
--   SELECT count(*) FROM audit_logs;
-- If they match, the next line is safe.
DROP TABLE public.audit_logs_legacy;

COMMIT;

-- =====================================================================
-- Ongoing maintenance — schedule via cron or a Celery beat job
-- =====================================================================
--
-- Run monthly (say, 25th of each month) to pre-create next month's
-- partition. Idempotent IF NOT EXISTS so re-runs are safe.
--
--     DO $$
--     DECLARE
--         next_month_start text;
--         next_month_end text;
--         partition_name text;
--     BEGIN
--         next_month_start := to_char(date_trunc('month', now() + interval '1 month'), 'YYYY-MM-01');
--         next_month_end   := to_char(date_trunc('month', now() + interval '2 months'), 'YYYY-MM-01');
--         partition_name := 'audit_logs_y' || to_char(now() + interval '1 month', 'YYYY') ||
--                           'm' || to_char(now() + interval '1 month', 'MM');
--         EXECUTE format(
--             'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.audit_logs ' ||
--             'FOR VALUES FROM (%L) TO (%L);',
--             partition_name, next_month_start, next_month_end
--         );
--     END $$;
--
-- Old partitions can be detached (and archived to cold storage) once they
-- pass a retention threshold:
--
--     ALTER TABLE public.audit_logs DETACH PARTITION public.audit_logs_y2024m01;
--     -- export → S3 / Blob, then:
--     DROP TABLE public.audit_logs_y2024m01;
