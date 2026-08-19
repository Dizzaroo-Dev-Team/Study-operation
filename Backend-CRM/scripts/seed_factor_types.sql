-- Idempotent conversion_factor_type seed (matches app.modules.site_budgeting.seed_data).
-- Complements scripts/seed_cost_elements.sql

BEGIN;

INSERT INTO conversion_factor_type (id, code, name, mode, description)
VALUES
  ('8009182e-9955-5ca7-b6ea-3acacc947a6c', 'MULT', 'Multiplicative default', 'MULTIPLICATIVE', 'Default multiplicative factor slot'),
  ('78ac517b-754f-575e-b1f8-cdc67cb2960f', 'ADD', 'Additive default', 'ADDITIVE', 'Default additive factor slot'),
  ('54ccd4af-149e-5c02-ab87-0a9e8da5caee', 'PASS', 'Pass-through default', 'PASS_THROUGH', 'Pass-through / no transform'),
  ('12b68283-a69d-5c78-9394-9cee5f611979', 'COUNTRY', 'Country Adjustment', 'MULTIPLICATIVE', 'Geographic cost multiplier by country'),
  ('1ab797fb-6d14-5b2b-a78e-722d905a4126', 'SITE', 'Site Adjustment', 'MULTIPLICATIVE', 'Site-specific cost multiplier'),
  ('9b368859-4fbb-5330-9836-488be3877336', 'TRIAL_COMPLEXITY', 'Trial Complexity', 'MULTIPLICATIVE', 'Protocol complexity multiplier'),
  ('1196f7bc-477b-53ad-a9d6-3a54e3c9d88c', 'COMPETITIVENESS', 'Market Competitiveness', 'MULTIPLICATIVE', 'Competitive site landscape multiplier')
ON CONFLICT (code) DO NOTHING;

COMMIT;
