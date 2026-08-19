BEGIN;

-- Rename the ARCHIVAL cost master element from the verbose seed label to the
-- canonical short name "Archival". Idempotent: only touches the old label so
-- re-running (or running after a manual rename) is a no-op.
UPDATE cost_element
SET name = 'Archival'
WHERE code = 'ARC-001'
  AND name = 'TMF Archival (per box, annual)';

COMMIT;
