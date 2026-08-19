-- DEV-ONLY teardown: wipe all agreement + workflow-engine test data so the unified
-- module walk can be tested on a single FRESH agreement bound to the LATEST definition.
-- Flags are OFF in prod; the 33 backend tests use inline workflow bodies, not these rows.
BEGIN;
SET session_replication_role = replica;  -- disable FK triggers for a clean full wipe

-- WHERE true: these are INTENTIONAL full-table wipes (dev-only teardown) —
-- the clause states that explicitly.
DELETE FROM agreement_changes WHERE true;
DELETE FROM agreement_comments WHERE true;
DELETE FROM agreement_document_comments WHERE true;
DELETE FROM agreement_documents WHERE true;
DELETE FROM agreement_inline_comments WHERE true;
DELETE FROM agreement_internal_signatures WHERE true;
DELETE FROM agreement_negotiation_rounds WHERE true;
DELETE FROM agreement_review_documents WHERE true;
DELETE FROM agreement_review_otps WHERE true;
DELETE FROM agreement_review_tokens WHERE true;
DELETE FROM agreement_reviewer_signatures WHERE true;
DELETE FROM agreement_signed_documents WHERE true;
DELETE FROM agreement_signers WHERE true;
DELETE FROM agreement_signing_otps WHERE true;
DELETE FROM agreement_signing_tokens WHERE true;
DELETE FROM cta_assignments WHERE true;
DELETE FROM cta_placeholder_mappings WHERE true;
DELETE FROM agreements WHERE true;

DELETE FROM workflow_audit_entries WHERE true;
DELETE FROM workflow_instances WHERE true;
DELETE FROM workflow_definition_versions WHERE true;
DELETE FROM workflow_definitions WHERE true;

SET session_replication_role = DEFAULT;
COMMIT;

SELECT
  (SELECT count(*) FROM agreements)              AS agreements,
  (SELECT count(*) FROM workflow_instances)      AS instances,
  (SELECT count(*) FROM workflow_definitions)    AS defs,
  (SELECT count(*) FROM agreement_documents)     AS docs,
  (SELECT count(*) FROM agreement_signing_tokens) AS sign_tokens,
  (SELECT count(*) FROM agreement_review_tokens)  AS review_tokens;
