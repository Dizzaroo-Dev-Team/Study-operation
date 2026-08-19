-- ---------------------------------------------------------------------------
-- Site Monitoring tab — full PostgreSQL schema (public)
-- ---------------------------------------------------------------------------
-- Source of truth: app/monitor/router.py — _ensure_monitor_tables()
-- All child tables reference monitoring_visits(id) ON DELETE CASCADE.
-- site_id / study_id on monitoring_visits are VARCHAR business keys (aligned
-- with CRM site/study identifiers in the app); there is no FK to sites/studies.
--
-- Relationship overview:
--   monitoring_visits (root)
--     ├── monitoring_visit_objectives        (1:N)
--     ├── monitoring_visit_activity         (1:N)
--     ├── monitoring_confirmation_letters   (1:1, PK = visit_id)
--     ├── monitoring_pre_visit              (1:1)
--     ├── monitoring_pre_visit_checklist      (1:N)
--     ├── monitoring_findings               (1:N)
--     ├── monitoring_documents              (1:N)
--     ├── monitoring_threads                (1:N)
--     ├── monitoring_messages               (1:N)
--     ├── monitoring_post_visit             (1:1)
--     ├── monitoring_follow_up_letters      (1:1)
--     ├── monitoring_visit_reports          (1:1, MVR JSON payload)
--     ├── monitoring_visit_review_tokens    (1:N)
--     │      └── monitoring_visit_review_comments (N:1 token, also -> visit)
--     ├── visit_reschedule_requests         (1:N)
--   monitoring_mvr_templates — org-scoped MVR JSON schemas (no visit FK)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS monitoring_visits (
    id VARCHAR(100) PRIMARY KEY,
    site_id VARCHAR(100),
    study_id VARCHAR(100),
    cra_name VARCHAR(255) NOT NULL DEFAULT '',
    cra_email VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'Scheduled',
    priority VARCHAR(20) NOT NULL DEFAULT 'Medium',
    visit_type VARCHAR(100) NOT NULL,
    visit_date VARCHAR(100) NOT NULL,
    visit_date_iso VARCHAR(40) NOT NULL DEFAULT '',
    visit_end_date VARCHAR(100) NOT NULL DEFAULT '',
    visit_end_date_iso VARCHAR(40) NOT NULL DEFAULT '',
    estimated_duration_days NUMERIC(10, 2),
    reschedule_proposed_datetime_iso VARCHAR(80) NOT NULL DEFAULT '',
    reschedule_reason TEXT NOT NULL DEFAULT '',
    reschedule_requested_at TIMESTAMP WITH TIME ZONE NULL,
    reschedule_requested_by_role VARCHAR(50) NOT NULL DEFAULT '',
    site_visit_number INTEGER,
    closed_at TIMESTAMP WITH TIME ZONE,
    duration VARCHAR(100) NOT NULL,
    protocol VARCHAR(100) NOT NULL,
    ind_number VARCHAR(100) NOT NULL,
    sponsor VARCHAR(255) NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    principal_investigator VARCHAR(255) NOT NULL,
    pi_email VARCHAR(255) NOT NULL,
    study_coordinator VARCHAR(255) NOT NULL,
    coordinator_phone VARCHAR(100) NOT NULL,
    site_address TEXT NOT NULL,
    irb_approval VARCHAR(255) NOT NULL,
    sdv_verified_subjects INTEGER NOT NULL DEFAULT 0,
    sdv_total_subjects INTEGER NOT NULL DEFAULT 0,
    subjects_enrolled VARCHAR(100) NOT NULL,
    crf_completion VARCHAR(50) NOT NULL,
    query_rate VARCHAR(100) NOT NULL,
    last_sdv_date VARCHAR(100) NOT NULL,
    action_required_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_visit_objectives (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    objective_text TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    tag_type VARCHAR(50) NOT NULL DEFAULT 'optional',
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_visit_activity (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    initials VARCHAR(20) NOT NULL,
    color VARCHAR(50) NOT NULL,
    activity_text TEXT NOT NULL,
    activity_time VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_monitoring_visit_objectives_visit_id
    ON monitoring_visit_objectives (visit_id);

CREATE INDEX IF NOT EXISTS ix_monitoring_visit_activity_visit_id
    ON monitoring_visit_activity (visit_id);

CREATE TABLE IF NOT EXISTS monitoring_confirmation_letters (
    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    last_sent VARCHAR(100) NOT NULL DEFAULT '',
    delivery_status VARCHAR(50) NOT NULL DEFAULT 'Draft',
    confirmed_by_role VARCHAR(50) NOT NULL DEFAULT '',
    confirmed_by_name VARCHAR(255) NOT NULL DEFAULT '',
    confirmed_by_email VARCHAR(255) NOT NULL DEFAULT '',
    confirmed_at TIMESTAMP WITH TIME ZONE NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_pre_visit (
    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    risk VARCHAR(20) NOT NULL DEFAULT 'high',
    agenda TEXT NOT NULL DEFAULT '',
    visit_date VARCHAR(20) NOT NULL DEFAULT '',
    pending_actions JSONB NOT NULL DEFAULT '[]'::JSONB,
    pre_visit_report_status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_pre_visit_checklist (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    item_text TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    tag_type VARCHAR(50) NOT NULL DEFAULT 'optional',
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS monitoring_findings (
    id VARCHAR(120) PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    site VARCHAR(255) NOT NULL,
    assignee_initials VARCHAR(20) NOT NULL,
    assignee_name VARCHAR(255) NOT NULL,
    assignee_color VARCHAR(50) NOT NULL,
    due_date VARCHAR(50) NOT NULL,
    due_color VARCHAR(20) NOT NULL,
    resolution TEXT NOT NULL DEFAULT '',
    subject_id VARCHAR(100) NOT NULL DEFAULT '',
    reference VARCHAR(500) NOT NULL DEFAULT ''
);

-- Perf indexes for monitoring_findings.
-- After the 2026-05-15 status-normalization migration the data is stored
-- lowercase, so a plain (status, visit_id) composite is the right index.
-- The earlier `idx_monitoring_findings_lower_status` functional index has
-- been dropped by `normalize_monitoring_status_lowercase.sql`.
CREATE INDEX IF NOT EXISTS idx_monitoring_findings_status_visit
    ON monitoring_findings (status, visit_id);
CREATE INDEX IF NOT EXISTS idx_monitoring_findings_visit
    ON monitoring_findings (visit_id);

CREATE TABLE IF NOT EXISTS monitoring_documents (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,
    icon VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    size VARCHAR(50) NOT NULL,
    date VARCHAR(100) NOT NULL,
    uploader_initials VARCHAR(20) NOT NULL,
    uploader_name VARCHAR(255) NOT NULL,
    uploader_color VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_threads (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    participants VARCHAR(500) NOT NULL,
    last_msg VARCHAR(100) NOT NULL,
    unread INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS monitoring_messages (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    sender VARCHAR(255) NOT NULL,
    initials VARCHAR(20) NOT NULL,
    color VARCHAR(50) NOT NULL,
    text VARCHAR(2000) NOT NULL,
    time VARCHAR(100) NOT NULL,
    is_me BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS monitoring_post_visit (
    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    summary TEXT NOT NULL DEFAULT '',
    critical_issues TEXT NOT NULL DEFAULT '',
    rating VARCHAR(100) NOT NULL DEFAULT 'Satisfactory',
    follow_up VARCHAR(100) NOT NULL DEFAULT 'Yes — Within 30 days',
    next_date VARCHAR(20) NOT NULL DEFAULT '',
    action_plan TEXT NOT NULL DEFAULT '',
    recommendations TEXT NOT NULL DEFAULT '',
    cra_name VARCHAR(255) NOT NULL DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_follow_up_letters (
    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ack_token VARCHAR(128) UNIQUE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    ack_status VARCHAR(50) NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS monitoring_visit_reports (
    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_visit_review_tokens (
    id UUID PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    reviewer_email VARCHAR(255) NOT NULL,
    author_email VARCHAR(255) NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP WITH TIME ZONE NULL
);

CREATE INDEX IF NOT EXISTS ix_mvrt_token ON monitoring_visit_review_tokens (token);

CREATE INDEX IF NOT EXISTS ix_mvrt_visit_id ON monitoring_visit_review_tokens (visit_id);

CREATE TABLE IF NOT EXISTS monitoring_visit_review_comments (
    id UUID PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    token_id UUID NOT NULL REFERENCES monitoring_visit_review_tokens (id) ON DELETE CASCADE,
    highlighted_text TEXT NOT NULL DEFAULT '',
    dom_path TEXT NOT NULL DEFAULT '',
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    comment_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_mvrc_visit_id ON monitoring_visit_review_comments (visit_id);

CREATE INDEX IF NOT EXISTS ix_mvrc_token_id ON monitoring_visit_review_comments (token_id);

CREATE TABLE IF NOT EXISTS visit_reschedule_requests (
    id UUID PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits (id) ON DELETE CASCADE,
    proposed_date TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT NOT NULL,
    decision_reason TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP WITH TIME ZONE NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_visit_reschedule_requests_status'
    ) THEN
        ALTER TABLE visit_reschedule_requests
        ADD CONSTRAINT ck_visit_reschedule_requests_status
        CHECK (status IN ('pending', 'approved', 'rejected'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_visit_reschedule_requests_visit_id
    ON visit_reschedule_requests (visit_id);

CREATE INDEX IF NOT EXISTS ix_visit_reschedule_requests_status_created_at
    ON visit_reschedule_requests (status, created_at DESC);

CREATE TABLE IF NOT EXISTS monitoring_mvr_templates (
    id UUID PRIMARY KEY,
    organization_id VARCHAR(100) NOT NULL DEFAULT 'default',
    name VARCHAR(255) NOT NULL DEFAULT 'MVR Template',
    schema JSONB NOT NULL DEFAULT '{}'::JSONB,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_mvr_templates_org_active
    ON monitoring_mvr_templates (organization_id, is_active);
