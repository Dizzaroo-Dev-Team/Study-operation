-- Monitoring Visit Report (MVR): full structured form payload as JSONB per visit.
CREATE TABLE IF NOT EXISTS monitoring_visit_reports (
    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits(id) ON DELETE CASCADE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
