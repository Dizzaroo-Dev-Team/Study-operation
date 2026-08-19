 BEGIN;

-- Step 1: Identify the exact MD Anderson IRB record.
WITH target_irb AS (
    SELECT id
    FROM irbs
    WHERE trim(trailing '.' FROM name) IN (
        'The Institutional Review Board of The University of Texas MD Anderson Cancer Center (MD Anderson IRB)',
        'MD Anderson IRB'
    )
    ORDER BY id ASC
    LIMIT 1
)
-- Step 2: Remove all existing requirement rows for this IRB.
DELETE FROM irb_required_documents d
USING target_irb t
WHERE d.irb_id = t.id;

-- Step 3: Insert the standardized 20-document list.
WITH target_irb AS (
    SELECT id
    FROM irbs
    WHERE trim(trailing '.' FROM name) IN (
        'The Institutional Review Board of The University of Texas MD Anderson Cancer Center (MD Anderson IRB)',
        'MD Anderson IRB'
    )
    ORDER BY id ASC
    LIMIT 1
), docs(document_name, is_mandatory) AS (
    VALUES
        ('Cover Letter', TRUE),
        ('IRB Form (SmartForm Data)', TRUE),
        ('Conflict of Interest (COI) Disclosures', TRUE),
        ('PI & Sub-I CVs and Medical Licenses', TRUE),
        ('CITI Training Records', TRUE),
        ('Site Good Clinical Practice (GCP) Certificates', TRUE),
        ('Departmental Review Board (DRB) Approval', TRUE),
        ('Scientific Review (PRMC) Approval', TRUE),
        ('Main Clinical Protocol', TRUE),
        ('Investigator''s Brochure (IB)', TRUE),
        ('Master Informed Consent Form (ICF)', TRUE),
        ('IND Approval Documentation', FALSE),
        ('FDA Form 1572 / Investigator Agreement', FALSE),
        ('Investigational Product (IP) / Pharmacy Manual', FALSE),
        ('Data and Safety Monitoring Plan (DSMP) / Charter', FALSE),
        ('Grant Application', FALSE),
        ('Assent / Short Forms', FALSE),
        ('Patient Diaries / e-PRO / Questionnaires', FALSE),
        ('Patient Recruitment Materials', FALSE),
        ('External Site Permission Letters', FALSE)
)
INSERT INTO irb_required_documents (irb_id, document_name, is_mandatory)
SELECT t.id, d.document_name, d.is_mandatory
FROM target_irb t
CROSS JOIN docs d;

COMMIT;
