-- Migration: Add widget_schedule_visit and milestone_library_item tables
-- Date: 2026-04-14
-- Purpose: Budget module redesign — study-level visit schedule + global milestone library

-- Widget Schedule Visits (study-level canonical visit list)
CREATE TABLE IF NOT EXISTS widget_schedule_visit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    visit_code VARCHAR(100),
    visit_name VARCHAR(255) NOT NULL,
    visit_type VARCHAR(50),  -- SCREENING | TREATMENT | END_OF_TREATMENT | FOLLOW_UP | UNSCHEDULED
    target_day INTEGER,
    visit_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_widget_schedule_visit_trial_id ON widget_schedule_visit(trial_id);

-- Milestone Library (global master list of common clinical trial milestones)
CREATE TABLE IF NOT EXISTS milestone_library_item (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(500) NOT NULL,
    default_amount NUMERIC(18,4),
    payment_trigger VARCHAR(200),
    category VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_milestone_library_item_category ON milestone_library_item(category);

-- Seed standard milestone library items
INSERT INTO milestone_library_item (name, default_amount, payment_trigger, category, sort_order) VALUES
    ('Site Initiation Visit (SIV)', NULL, 'SIV completion confirmed', 'Startup', 10),
    ('IRB / IEC Approval', NULL, 'IRB/IEC approval letter received', 'Regulatory', 20),
    ('First Patient In (FPI)', NULL, 'First patient enrolled and consented', 'Enrollment', 30),
    ('Last Patient In (LPI)', NULL, 'Last patient enrolled', 'Enrollment', 40),
    ('Last Patient Last Visit (LPLV)', NULL, 'LPLV completed', 'Closeout', 50),
    ('Database Lock', NULL, 'Database lock confirmed by DM', 'Closeout', 60),
    ('Site Close-Out Visit', NULL, 'Close-out visit completed', 'Closeout', 70),
    ('Annual IRB Renewal', NULL, 'Per year — IRB renewal approved', 'Regulatory', 80),
    ('Regulatory Submission Support', NULL, 'Per regulatory submission package', 'Regulatory', 90),
    ('Protocol Deviation Review', NULL, 'Per deviation review meeting', 'Monitoring', 100),
    ('Investigator Meeting', NULL, 'Per investigator meeting attended', 'Startup', 110),
    ('Essential Documents Submission', NULL, 'Essential docs submission complete', 'Regulatory', 120)
ON CONFLICT DO NOTHING;
