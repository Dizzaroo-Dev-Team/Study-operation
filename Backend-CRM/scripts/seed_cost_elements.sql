-- Idempotent seed for element_category + cost_element + element_cost_version.
-- Matches the master list in app/modules/site_budgeting/cost_master_data.py.
-- Run when the Python seed is unavailable, e.g.:
--   psql "$DATABASE_URL" -f scripts/seed_cost_elements.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- Categories (top-level only; uq_element_category_name_parent makes name+null
-- parent unique, so ON CONFLICT DO NOTHING is safe here).
-- ---------------------------------------------------------------------------
INSERT INTO element_category (name, sort_order) VALUES
  ('REGULATORY', 10),
  ('SITE INITIATION', 20),
  ('PER-PATIENT', 30),
  ('SCREEN FAILURE', 40),
  ('IMAGING', 50),
  ('BIOMARKERS', 60),
  ('PK/ADA', 70),
  ('ONCOLOGY-SPECIFIC', 80),
  ('SAFETY', 90),
  ('MONITORING', 100),
  ('DATA MGMT', 110),
  ('CLOSE-OUT', 120),
  ('PERSONNEL', 130),
  ('OVERHEAD', 140),
  ('DRUG ACCOUNTABILITY', 150),
  ('ARCHIVAL', 160)
ON CONFLICT ON CONSTRAINT uq_element_category_name_parent DO NOTHING;

-- ---------------------------------------------------------------------------
-- Cost elements (resolved via category name).
-- description blob: `Subcategory: X | Unit: Y | Cost Type: FIXED|VARIABLE | Pass-Thru: Y|N`
-- cost_type_enum is the derived backend math enum (PER_VISIT|PER_PATIENT|FIXED|PASS_THROUGH).
-- ---------------------------------------------------------------------------
INSERT INTO cost_element (code, name, description, unit_of_measure, category_id, element_type, cost_type, is_active)
SELECT v.code, v.name, v.description, v.payment_type, c.id, 'ATOMIC', v.cost_type_enum, TRUE
FROM (VALUES
  ('REG-001',  'IRB/IEC Initial Submission Fee',            'Subcategory: IRB/Ethics | Unit: Per Document | Cost Type: FIXED | Pass-Thru: Y',         'ONCE',       'REGULATORY',           'PASS_THROUGH'),
  ('REG-002',  'IRB Annual Continuing Review',              'Subcategory: IRB/Ethics | Unit: Per Submission | Cost Type: FIXED | Pass-Thru: Y',       'ANNUAL',     'REGULATORY',           'PASS_THROUGH'),
  ('REG-003',  'IRB Protocol Amendment Fee',                'Subcategory: IRB/Ethics | Unit: Per Amendment | Cost Type: FIXED | Pass-Thru: Y',        'PER EVENT',  'REGULATORY',           'PASS_THROUGH'),
  ('REG-004',  'CTA/IND Filing Fee (Country)',              'Subcategory: Reg Authority | Unit: Lump Sum | Cost Type: FIXED | Pass-Thru: Y',          'ONCE',       'REGULATORY',           'PASS_THROUGH'),
  ('REG-005',  'Regulatory Document Preparation',           'Subcategory: Regulatory | Unit: Per Package | Cost Type: FIXED | Pass-Thru: N',          'ONCE',       'REGULATORY',           'FIXED'),
  ('INIT-001', 'Site Qualification Visit (SQV)',            'Subcategory: Site Activation | Unit: Lump Sum | Cost Type: FIXED | Pass-Thru: N',        'ONCE',       'SITE INITIATION',      'FIXED'),
  ('INIT-002', 'Site Initiation Visit (SIV)',               'Subcategory: Site Activation | Unit: Lump Sum | Cost Type: FIXED | Pass-Thru: N',        'ONCE',       'SITE INITIATION',      'FIXED'),
  ('INIT-003', 'Site Setup / Admin Fee',                    'Subcategory: Admin | Unit: Lump Sum | Cost Type: FIXED | Pass-Thru: N',                  'ONCE',       'SITE INITIATION',      'FIXED'),
  ('INIT-004', 'Pharmacy Setup Fee',                        'Subcategory: Pharmacy | Unit: Lump Sum | Cost Type: FIXED | Pass-Thru: N',               'ONCE',       'SITE INITIATION',      'FIXED'),
  ('INIT-005', 'Staff GCP Training (Initial)',              'Subcategory: Training | Unit: Per Staff | Cost Type: FIXED | Pass-Thru: N',              'ONCE',       'SITE INITIATION',      'FIXED'),
  ('VISIT-001','Screening Visit (Composite)',               'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER PATIENT','PER-PATIENT',          'PER_PATIENT'),
  ('VISIT-002','Baseline Visit (Composite)',                'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER PATIENT','PER-PATIENT',          'PER_PATIENT'),
  ('VISIT-003','Treatment Visit – Cycle 1',                 'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER PATIENT','PER-PATIENT',          'PER_PATIENT'),
  ('VISIT-004','Treatment Visit – Cycles 2–6',              'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER VISIT',  'PER-PATIENT',          'PER_VISIT'),
  ('VISIT-005','Treatment Visit – Cycle 7+',                'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER VISIT',  'PER-PATIENT',          'PER_VISIT'),
  ('VISIT-006','End-of-Treatment Visit',                    'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER PATIENT','PER-PATIENT',          'PER_PATIENT'),
  ('VISIT-007','30-Day Safety Follow-up',                   'Subcategory: Visits | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',             'PER PATIENT','PER-PATIENT',          'PER_PATIENT'),
  ('VISIT-008','Long-term Follow-up (Annual)',              'Subcategory: Visits | Unit: Per Year | Cost Type: VARIABLE | Pass-Thru: N',              'ANNUAL',     'PER-PATIENT',          'PER_VISIT'),
  ('VISIT-009','Unscheduled/Urgent Visit',                  'Subcategory: Visits | Unit: Per Event | Cost Type: VARIABLE | Pass-Thru: N',             'PER EVENT',  'PER-PATIENT',          'PER_VISIT'),
  ('SF-001',   'Screen Failure Fee',                        'Subcategory: Screen Failure | Unit: Per Patient | Cost Type: VARIABLE | Pass-Thru: N',   'PER PATIENT','SCREEN FAILURE',       'PER_PATIENT'),
  ('IMG-001',  'CT Scan (Oncology Multi-region)',           'Subcategory: Radiology | Unit: Per Scan | Cost Type: VARIABLE | Pass-Thru: Y',           'PER VISIT',  'IMAGING',              'PASS_THROUGH'),
  ('IMG-002',  'MRI Whole Body/Target Lesion',              'Subcategory: Radiology | Unit: Per Scan | Cost Type: VARIABLE | Pass-Thru: Y',           'PER VISIT',  'IMAGING',              'PASS_THROUGH'),
  ('IMG-003',  'PET-CT (Baseline/On-treatment)',            'Subcategory: Nuclear Med | Unit: Per Scan | Cost Type: VARIABLE | Pass-Thru: Y',         'PER VISIT',  'IMAGING',              'PASS_THROUGH'),
  ('IMG-004',  'RECIST 1.1 Assessment (Radiologist)',       'Subcategory: RECIST | Unit: Per Read | Cost Type: VARIABLE | Pass-Thru: N',              'PER VISIT',  'IMAGING',              'PER_VISIT'),
  ('IMG-005',  'Independent Central Imaging Review',        'Subcategory: BICR | Unit: Per Time-Point | Cost Type: VARIABLE | Pass-Thru: Y',          'PER VISIT',  'IMAGING',              'PASS_THROUGH'),
  ('IMG-006',  'MUGA Scan / Echo (Cardiac Safety)',         'Subcategory: Cardiology | Unit: Per Scan | Cost Type: VARIABLE | Pass-Thru: Y',          'PER VISIT',  'IMAGING',              'PASS_THROUGH'),
  ('BIO-001',  'ctDNA NGS (Tumor-informed)',                'Subcategory: ctDNA | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',             'PER SAMPLE', 'BIOMARKERS',           'PASS_THROUGH'),
  ('BIO-002',  'ctDNA NGS (Tumor-agnostic)',                'Subcategory: ctDNA | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',             'PER SAMPLE', 'BIOMARKERS',           'PASS_THROUGH'),
  ('BIO-003',  'PD-L1 IHC Testing',                         'Subcategory: IHC | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',               'PER SAMPLE', 'BIOMARKERS',           'PASS_THROUGH'),
  ('BIO-004',  'TMB Assessment (Tumor Mutational Burden)',  'Subcategory: NGS | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',               'PER SAMPLE', 'BIOMARKERS',           'PASS_THROUGH'),
  ('BIO-005',  'Multiplex Cytokine Panel',                  'Subcategory: Cytokines | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',         'PER SAMPLE', 'BIOMARKERS',           'PASS_THROUGH'),
  ('PK-001',   'PK Sample Collection (per time-point)',     'Subcategory: PK | Unit: Per Time-Point | Cost Type: VARIABLE | Pass-Thru: N',            'PER SAMPLE', 'PK/ADA',               'PER_VISIT'),
  ('PK-002',   'ADA Screening Assay',                       'Subcategory: Immunogenicity | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',    'PER SAMPLE', 'PK/ADA',               'PASS_THROUGH'),
  ('PK-003',   'Neutralizing Antibody (NAb) Assay',         'Subcategory: Immunogenicity | Unit: Per Sample | Cost Type: VARIABLE | Pass-Thru: Y',    'PER SAMPLE', 'PK/ADA',               'PASS_THROUGH'),
  ('ONC-001',  'Infusion Chair Time (per hour)',            'Subcategory: Infusion | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',            'PER HOUR',   'ONCOLOGY-SPECIFIC',    'PER_VISIT'),
  ('ONC-002',  'Extended Infusion Chair (>6h)',             'Subcategory: Infusion | Unit: Per Hour (add-on) | Cost Type: VARIABLE | Pass-Thru: N',   'PER HOUR',   'ONCOLOGY-SPECIFIC',    'PER_VISIT'),
  ('ONC-003',  'Cytotoxic Drug Preparation',                'Subcategory: Pharmacy | Unit: Per Dose | Cost Type: VARIABLE | Pass-Thru: N',            'PER DOSE',   'ONCOLOGY-SPECIFIC',    'PER_VISIT'),
  ('ONC-004',  'Leukapheresis Procedure',                   'Subcategory: CAR-T | Unit: Per Session | Cost Type: VARIABLE | Pass-Thru: Y',            'PER PATIENT','ONCOLOGY-SPECIFIC',    'PASS_THROUGH'),
  ('ONC-005',  'CAR-T Infusion Administration',             'Subcategory: CAR-T | Unit: Per Infusion | Cost Type: VARIABLE | Pass-Thru: N',           'PER PATIENT','ONCOLOGY-SPECIFIC',    'PER_PATIENT'),
  ('ONC-006',  'CRS Monitoring (Inpatient, per day)',       'Subcategory: CAR-T Safety | Unit: Per Day | Cost Type: VARIABLE | Pass-Thru: N',         'PER DAY',    'ONCOLOGY-SPECIFIC',    'PER_VISIT'),
  ('ONC-007',  'Fresh Core Biopsy (Tumor)',                 'Subcategory: Biopsy | Unit: Per Procedure | Cost Type: VARIABLE | Pass-Thru: Y',         'PER PATIENT','ONCOLOGY-SPECIFIC',    'PASS_THROUGH'),
  ('ONC-008',  'Archival Tissue Retrieval (FFPE)',          'Subcategory: Pathology | Unit: Per Block | Cost Type: VARIABLE | Pass-Thru: Y',          'PER PATIENT','ONCOLOGY-SPECIFIC',    'PASS_THROUGH'),
  ('ONC-009',  'Central Pathology Review',                  'Subcategory: Pathology | Unit: Per Case | Cost Type: VARIABLE | Pass-Thru: Y',           'PER PATIENT','ONCOLOGY-SPECIFIC',    'PASS_THROUGH'),
  ('ONC-010',  'irAE Management (per event)',               'Subcategory: Safety | Unit: Per Event | Cost Type: VARIABLE | Pass-Thru: N',             'PER EVENT',  'ONCOLOGY-SPECIFIC',    'PER_VISIT'),
  ('ONC-011',  'Radiation Therapy Review',                  'Subcategory: Radiation Onc | Unit: Per Review | Cost Type: VARIABLE | Pass-Thru: N',     'PER PATIENT','ONCOLOGY-SPECIFIC',    'PER_PATIENT'),
  ('SAF-001',  'SAE Reporting (Initial + Follow-up)',       'Subcategory: SAE | Unit: Per SAE | Cost Type: VARIABLE | Pass-Thru: N',                  'PER EVENT',  'SAFETY',               'PER_VISIT'),
  ('SAF-002',  'DSMB Meeting (per meeting)',                'Subcategory: DSMB | Unit: Per Meeting | Cost Type: FIXED | Pass-Thru: N',                'PER EVENT',  'SAFETY',               'FIXED'),
  ('MON-001',  'On-site Monitoring Visit (OSV)',            'Subcategory: SDV | Unit: Per Visit | Cost Type: VARIABLE | Pass-Thru: N',                'PER VISIT',  'MONITORING',           'PER_VISIT'),
  ('MON-002',  'Remote SDR (per hour)',                     'Subcategory: SDR | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',                 'PER HOUR',   'MONITORING',           'PER_VISIT'),
  ('DATA-001', 'EDC Data Entry Support (per month)',        'Subcategory: EDC | Unit: Per Month | Cost Type: FIXED | Pass-Thru: N',                   'MONTHLY',    'DATA MGMT',            'FIXED'),
  ('DATA-002', 'Query Response (per query)',                'Subcategory: Queries | Unit: Per Query | Cost Type: VARIABLE | Pass-Thru: N',            'PER EVENT',  'DATA MGMT',            'PER_VISIT'),
  ('CLO-001',  'Site Close-out Visit (COV)',                'Subcategory: COV | Unit: Lump Sum | Cost Type: FIXED | Pass-Thru: N',                    'ONCE',       'CLOSE-OUT',            'FIXED'),
  ('PERS-001', 'Principal Investigator (per hour)',         'Subcategory: PI | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',                  'PER HOUR',   'PERSONNEL',            'PER_VISIT'),
  ('PERS-002', 'Sub-Investigator / Oncologist (per hour)',  'Subcategory: Sub-I | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',               'PER HOUR',   'PERSONNEL',            'PER_VISIT'),
  ('PERS-003', 'Study Coordinator (per hour)',              'Subcategory: Coordinator | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',         'PER HOUR',   'PERSONNEL',            'PER_VISIT'),
  ('PERS-004', 'Research Nurse (per hour)',                 'Subcategory: Nurse | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',               'PER HOUR',   'PERSONNEL',            'PER_VISIT'),
  ('PERS-005', 'Oncology Pharmacist (per hour)',            'Subcategory: Pharmacist | Unit: Per Hour | Cost Type: VARIABLE | Pass-Thru: N',          'PER HOUR',   'PERSONNEL',            'PER_VISIT'),
  ('OVH-001',  'Institutional Overhead (% of directs)',     'Subcategory: Overhead | Unit: % of Total Directs | Cost Type: FIXED | Pass-Thru: N',     'PERCENTAGE', 'OVERHEAD',             'FIXED'),
  ('OVH-002',  'Site Administrative Overhead',              'Subcategory: Admin | Unit: Per Month | Cost Type: FIXED | Pass-Thru: N',                 'MONTHLY',    'OVERHEAD',             'FIXED'),
  ('OVH-003',  'IMP Storage (Temperature-monitored)',       'Subcategory: Storage | Unit: Per Month | Cost Type: FIXED | Pass-Thru: N',               'MONTHLY',    'DRUG ACCOUNTABILITY',  'FIXED'),
  ('ARC-001',  'Archival',                                  'Subcategory: TMF | Unit: Per Box/Year | Cost Type: FIXED | Pass-Thru: Y',                'ANNUAL',     'ARCHIVAL',             'PASS_THROUGH'),
  ('ARC-002',  'Biobank Sample Storage (per sample/year)',  'Subcategory: Biobank | Unit: Per Sample/Year | Cost Type: FIXED | Pass-Thru: Y',         'ANNUAL',     'ARCHIVAL',             'PASS_THROUGH')
) AS v(code, name, description, payment_type, category_name, cost_type_enum)
LEFT JOIN element_category c ON c.name = v.category_name AND c.parent_id IS NULL
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Initial FMV cost version per element (label = 'FMV-2026').
-- ---------------------------------------------------------------------------
INSERT INTO element_cost_version (element_id, version_label, base_unit_cost, reference_currency, effective_from, source)
SELECT ce.id, 'FMV-2026', v.base_unit_cost, 'USD', CURRENT_DATE, 'oncology_master_2026'
FROM (VALUES
  ('REG-001',  2500.00),
  ('REG-002',  1200.00),
  ('REG-003',   750.00),
  ('REG-004',  4800.00),
  ('REG-005',  1800.00),
  ('INIT-001', 2800.00),
  ('INIT-002', 3200.00),
  ('INIT-003', 1500.00),
  ('INIT-004', 1200.00),
  ('INIT-005',  350.00),
  ('VISIT-001', 850.00),
  ('VISIT-002', 680.00),
  ('VISIT-003',1200.00),
  ('VISIT-004', 950.00),
  ('VISIT-005', 800.00),
  ('VISIT-006', 750.00),
  ('VISIT-007', 450.00),
  ('VISIT-008', 280.00),
  ('VISIT-009', 480.00),
  ('SF-001',    450.00),
  ('IMG-001',  1850.00),
  ('IMG-002',  2200.00),
  ('IMG-003',  3800.00),
  ('IMG-004',   285.00),
  ('IMG-005',   420.00),
  ('IMG-006',   850.00),
  ('BIO-001',  1850.00),
  ('BIO-002',   980.00),
  ('BIO-003',   380.00),
  ('BIO-004',  1200.00),
  ('BIO-005',   420.00),
  ('PK-001',     85.00),
  ('PK-002',    280.00),
  ('PK-003',    420.00),
  ('ONC-001',   185.00),
  ('ONC-002',    95.00),
  ('ONC-003',   185.00),
  ('ONC-004',  4200.00),
  ('ONC-005',  2500.00),
  ('ONC-006',   850.00),
  ('ONC-007',  1200.00),
  ('ONC-008',   180.00),
  ('ONC-009',   650.00),
  ('ONC-010',  1200.00),
  ('ONC-011',   950.00),
  ('SAF-001',   320.00),
  ('SAF-002',  8500.00),
  ('MON-001',  2200.00),
  ('MON-002',   185.00),
  ('DATA-001',  380.00),
  ('DATA-002',   45.00),
  ('CLO-001',  2500.00),
  ('PERS-001',  425.00),
  ('PERS-002',  325.00),
  ('PERS-003',   95.00),
  ('PERS-004',  125.00),
  ('PERS-005',  165.00),
  ('OVH-001',    20.00),
  ('OVH-002',   650.00),
  ('OVH-003',   150.00),
  ('ARC-001',    85.00),
  ('ARC-002',    45.00)
) AS v(code, base_unit_cost)
JOIN cost_element ce ON ce.code = v.code
ON CONFLICT ON CONSTRAINT uq_element_cost_version_label DO NOTHING;

COMMIT;
