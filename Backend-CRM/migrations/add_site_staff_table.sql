-- Site staff table: stores staff members per site
CREATE TABLE IF NOT EXISTS site_staff (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    staff_id VARCHAR(50) NOT NULL,
    staff_name VARCHAR(255) NOT NULL,
    study_role VARCHAR(255) NOT NULL DEFAULT '',
    email VARCHAR(255),
    phone VARCHAR(50),
    start_date DATE,
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_site_staff_site_id ON site_staff (site_id);
