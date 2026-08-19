-- Clear Agreement Workflow Data
-- This script safely deletes ONLY agreement-related data
-- Does NOT affect: Users, Sites, Studies, IAM, Notice Board, Site Status, or any other CRM tables

-- Delete in dependency order to respect foreign keys.
-- WHERE true: these are INTENTIONAL full-table wipes (this is a maintenance
-- teardown script) — the clause states that explicitly.
DELETE FROM agreement_inline_comments WHERE true;
DELETE FROM agreement_comments WHERE true;
DELETE FROM agreement_documents WHERE true;
DELETE FROM agreement_versions WHERE true;
DELETE FROM agreements WHERE true;
DELETE FROM study_templates WHERE true;

-- Verify deletion
SELECT 
    'agreement_inline_comments' as table_name, COUNT(*) as remaining_rows FROM agreement_inline_comments
UNION ALL
SELECT 'agreement_comments', COUNT(*) FROM agreement_comments
UNION ALL
SELECT 'agreement_documents', COUNT(*) FROM agreement_documents
UNION ALL
SELECT 'agreement_versions', COUNT(*) FROM agreement_versions
UNION ALL
SELECT 'agreements', COUNT(*) FROM agreements
UNION ALL
SELECT 'study_templates', COUNT(*) FROM study_templates;
