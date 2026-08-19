-- Performance indexes for monitoring dashboard + visit-detail queries.
-- Idempotent — safe to run on every deploy; also applied at startup via aggregator.

CREATE INDEX IF NOT EXISTS idx_monitoring_findings_visit_id
    ON monitoring_findings (visit_id);

CREATE INDEX IF NOT EXISTS idx_monitoring_findings_status
    ON monitoring_findings (status);

CREATE INDEX IF NOT EXISTS idx_monitoring_visits_site_status_date
    ON monitoring_visits (site_id, status, visit_date_iso);

CREATE INDEX IF NOT EXISTS idx_monitoring_pre_visit_checklist_visit_id
    ON monitoring_pre_visit_checklist (visit_id);

CREATE INDEX IF NOT EXISTS idx_monitoring_documents_visit_id
    ON monitoring_documents (visit_id);
