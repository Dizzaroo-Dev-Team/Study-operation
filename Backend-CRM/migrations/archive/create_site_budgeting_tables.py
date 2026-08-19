"""
Create site budgeting tables (additive only). Safe to re-run: IF NOT EXISTS.
"""
import asyncio
import sys
import os

if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.config import settings


SQL = """
CREATE TABLE IF NOT EXISTS cost_element (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(500) NOT NULL,
    description TEXT,
    unit VARCHAR(100),
    category VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS element_cost_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cost_element_id UUID NOT NULL REFERENCES cost_element(id) ON DELETE CASCADE,
    version_label VARCHAR(100) NOT NULL,
    base_amount NUMERIC(18,4) NOT NULL,
    currency_code VARCHAR(3) NOT NULL DEFAULT 'USD',
    effective_from DATE,
    effective_to DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_element_cost_version_label UNIQUE (cost_element_id, version_label)
);
CREATE INDEX IF NOT EXISTS ix_element_cost_version_cost_element_id ON element_cost_version (cost_element_id);

CREATE TABLE IF NOT EXISTS conversion_factor_type (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    mode VARCHAR(32) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversion_factor (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factor_type_id UUID NOT NULL REFERENCES conversion_factor_type(id) ON DELETE RESTRICT,
    trial_id UUID REFERENCES studies(id) ON DELETE CASCADE,
    country_code VARCHAR(3),
    site_id UUID REFERENCES sites(id) ON DELETE CASCADE,
    sequence_order INTEGER NOT NULL DEFAULT 0,
    value NUMERIC(18,6) NOT NULL,
    currency_code VARCHAR(3),
    label VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_conversion_factor_trial_id ON conversion_factor (trial_id);
CREATE INDEX IF NOT EXISTS ix_conversion_factor_site_id ON conversion_factor (site_id);
CREATE INDEX IF NOT EXISTS ix_conversion_factor_country_code ON conversion_factor (country_code);

CREATE TABLE IF NOT EXISTS trial_factor_configuration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    conversion_factor_id UUID NOT NULL REFERENCES conversion_factor(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sequence_override INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_trial_factor_config UNIQUE (trial_id, conversion_factor_id)
);
CREATE INDEX IF NOT EXISTS ix_trial_factor_configuration_trial_id ON trial_factor_configuration (trial_id);

CREATE TABLE IF NOT EXISTS currency_exchange_rate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_currency VARCHAR(3) NOT NULL,
    to_currency VARCHAR(3) NOT NULL,
    rate NUMERIC(18,8) NOT NULL,
    effective_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_currency_exchange_rate_pair_date
    ON currency_exchange_rate (from_currency, to_currency, effective_date);

CREATE TABLE IF NOT EXISTS budget_template (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
    parent_template_id UUID REFERENCES budget_template(id) ON DELETE SET NULL,
    name VARCHAR(500) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    enrollment_planned INTEGER,
    target_currency_code VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_id ON budget_template (trial_id);
CREATE INDEX IF NOT EXISTS ix_budget_template_site_id ON budget_template (site_id);

CREATE TABLE IF NOT EXISTS budget_line_item (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES budget_template(id) ON DELETE CASCADE,
    cost_element_id UUID NOT NULL REFERENCES cost_element(id) ON DELETE RESTRICT,
    included BOOLEAN NOT NULL DEFAULT TRUE,
    excluded BOOLEAN NOT NULL DEFAULT FALSE,
    override_unit_cost NUMERIC(18,4),
    override_currency_code VARCHAR(3),
    inherited_from_parent BOOLEAN NOT NULL DEFAULT FALSE,
    parent_line_item_id UUID REFERENCES budget_line_item(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_budget_line_item_template_id ON budget_line_item (budget_template_id);
CREATE INDEX IF NOT EXISTS ix_budget_line_item_cost_element_id ON budget_line_item (cost_element_id);

CREATE TABLE IF NOT EXISTS visit_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES budget_template(id) ON DELETE CASCADE,
    visit_code VARCHAR(100),
    visit_name VARCHAR(255) NOT NULL,
    visit_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_visit_schedule_budget_template_id ON visit_schedule (budget_template_id);

CREATE TABLE IF NOT EXISTS budget_visit_matrix (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_line_item_id UUID NOT NULL REFERENCES budget_line_item(id) ON DELETE CASCADE,
    visit_schedule_id UUID NOT NULL REFERENCES visit_schedule(id) ON DELETE CASCADE,
    units NUMERIC(18,4) NOT NULL DEFAULT 1,
    CONSTRAINT uq_budget_visit_matrix_line_visit UNIQUE (budget_line_item_id, visit_schedule_id)
);

CREATE TABLE IF NOT EXISTS budget_milestone (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES budget_template(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    amount NUMERIC(18,4) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_budget_milestone_budget_template_id ON budget_milestone (budget_template_id);

CREATE TABLE IF NOT EXISTS budget_note (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES budget_template(id) ON DELETE CASCADE,
    user_id VARCHAR(255) REFERENCES users(user_id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS site_budgeting_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(20) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    user_id VARCHAR(255) REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_site_budgeting_audit_entity ON site_budgeting_audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_site_budgeting_audit_user_id ON site_budgeting_audit_log (user_id);

INSERT INTO conversion_factor_type (id, code, name, mode)
SELECT gen_random_uuid(), v.code, v.name, v.mode
FROM (VALUES
    ('MULT', 'Multiplicative default', 'MULTIPLICATIVE'),
    ('ADD', 'Additive default', 'ADDITIVE'),
    ('PASS', 'Pass-through default', 'PASS_THROUGH')
) AS v(code, name, mode)
WHERE NOT EXISTS (SELECT 1 FROM conversion_factor_type c WHERE c.code = v.code);
"""


async def run():
    print("=" * 70)
    print("Site budgeting tables migration")
    print("=" * 70)
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")

    async with AsyncSessionLocal() as session:
        try:
            # asyncpg does not allow multiple statements in one execute()
            for chunk in SQL.split(";"):
                stmt = chunk.strip()
                if not stmt:
                    continue
                await session.execute(text(stmt))
            await session.commit()
            print("[SUCCESS] Site budgeting tables created / verified.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
