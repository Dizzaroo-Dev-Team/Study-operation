-- Update South Central - Oxford REC document names in DB-configured requirements.
-- Safe to run multiple times.

WITH oxford_irbs AS (
  SELECT id
  FROM irbs
  WHERE LOWER(TRIM(COALESCE(unique_code, ''))) = 'hra_oxford_rec_uk'
     OR LOWER(TRIM(name)) = 'south central - oxford research ethics committee'
)
UPDATE irb_required_documents d
SET document_name = 'Schedule of Events Costing Template (SoECAT)'
WHERE d.irb_id IN (SELECT id FROM oxford_irbs)
  AND LOWER(TRIM(d.document_name)) = 'costing template';

WITH oxford_irbs AS (
  SELECT id
  FROM irbs
  WHERE LOWER(TRIM(COALESCE(unique_code, ''))) = 'hra_oxford_rec_uk'
     OR LOWER(TRIM(name)) = 'south central - oxford research ethics committee'
)
UPDATE irb_required_documents d
SET document_name = 'UK Local Information Pack (OID / mCTA)'
WHERE d.irb_id IN (SELECT id FROM oxford_irbs)
  AND LOWER(TRIM(d.document_name)) = 'organisation information document (oid) / schedule of events';

WITH oxford_irbs AS (
  SELECT id
  FROM irbs
  WHERE LOWER(TRIM(COALESCE(unique_code, ''))) = 'hra_oxford_rec_uk'
     OR LOWER(TRIM(name)) = 'south central - oxford research ethics committee'
)
UPDATE irb_required_documents d
SET document_name = 'Chief Investigator CV & GCP Certificates'
WHERE d.irb_id IN (SELECT id FROM oxford_irbs)
  AND LOWER(TRIM(d.document_name)) = 'chief investigator cv';

WITH oxford_irbs AS (
  SELECT id
  FROM irbs
  WHERE LOWER(TRIM(COALESCE(unique_code, ''))) = 'hra_oxford_rec_uk'
     OR LOWER(TRIM(name)) = 'south central - oxford research ethics committee'
)
DELETE FROM irb_required_documents d
WHERE d.irb_id IN (SELECT id FROM oxford_irbs)
  AND LOWER(TRIM(d.document_name)) IN (
    'draft clinical trial agreement (mcta)',
    'advertising material / patient facing document',
    'mhra clinical trial authorisation (cta)',
    'statement of activities and uk local information pack'
  );
