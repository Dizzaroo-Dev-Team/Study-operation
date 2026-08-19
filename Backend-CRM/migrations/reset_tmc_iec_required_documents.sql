BEGIN;

-- Step 1: Identify IRB by exact name.
WITH target_irb AS (
    SELECT id
    FROM irbs
    WHERE name = 'Tata Memorial Centre Institutional Ethics Committee (TMC-IEC)'
    ORDER BY id ASC
    LIMIT 1
)
-- Step 2: Remove all existing requirement rows for this IRB.
DELETE FROM irb_required_documents d
USING target_irb t
WHERE d.irb_id = t.id;

-- Step 3: Insert the standardized document list.
WITH target_irb AS (
    SELECT id
    FROM irbs
    WHERE name = 'Tata Memorial Centre Institutional Ethics Committee (TMC-IEC)'
    ORDER BY id ASC
    LIMIT 1
), docs(document_name, is_mandatory) AS (
    VALUES
        ('Cover Letter', TRUE),
        ('IEC Application Form', TRUE),
        ('Principal Investigator Undertaking', TRUE),
        ('Conflict of Interest (COI) Declaration', TRUE),
        ('Main Clinical Trial Protocol', TRUE),
        ('Master Informed Consent Document (ICD) - English', TRUE),
        ('Translated ICDs', TRUE),
        ('Translation Certificates / Back Translations', TRUE),
        ('PI & Co-I CVs and Medical Registrations', TRUE),
        ('Good Clinical Practice (GCP) Certificates', TRUE),
        ('Clinical Trial Agreement (CTA) / Draft Budget', TRUE),
        ('Insurance Policy / Certificate', TRUE),
        ('Patient Compensation Formula / Undertaking', TRUE),
        ('Investigator''s Brochure (IB)', FALSE),
        ('Patient Diaries / Questionnaires / PROs', FALSE),
        ('Patient Recruitment Materials', FALSE),
        ('CDSCO / DCGI Approval (NOC)', FALSE),
        ('CTRI Registration Proof', FALSE),
        ('HMSC Approval / Proof of Submission', FALSE)
)
INSERT INTO irb_required_documents (irb_id, document_name, is_mandatory)
SELECT t.id, d.document_name, d.is_mandatory
FROM target_irb t
CROSS JOIN docs d;

COMMIT;
