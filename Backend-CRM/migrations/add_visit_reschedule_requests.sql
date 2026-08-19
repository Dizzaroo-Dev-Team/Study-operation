-- Persist site-initiated visit reschedule requests for sponsor review.
CREATE TABLE IF NOT EXISTS visit_reschedule_requests (
    id UUID PRIMARY KEY,
    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
    proposed_date TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT NOT NULL,
    decision_reason TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP WITH TIME ZONE NULL
);

ALTER TABLE visit_reschedule_requests
ADD COLUMN IF NOT EXISTS decision_reason TEXT NOT NULL DEFAULT '';

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
ON visit_reschedule_requests(visit_id);

CREATE INDEX IF NOT EXISTS ix_visit_reschedule_requests_status_created_at
ON visit_reschedule_requests(status, created_at DESC);
