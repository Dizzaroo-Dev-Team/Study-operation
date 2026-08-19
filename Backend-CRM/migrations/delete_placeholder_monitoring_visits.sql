-- Remove monitoring visits corrupted by partial PATCH (no site/study, TBD date, N/A placeholders).
-- Child rows (findings, objectives, etc.) CASCADE from monitoring_visits.
--
-- Preview:
-- SELECT id, site_id, study_id, visit_date, visit_date_iso, status, protocol, site_address
-- FROM monitoring_visits
-- WHERE (site_id IS NULL OR BTRIM(site_id) = '')
--   AND (study_id IS NULL OR BTRIM(study_id) = '')
--   AND (BTRIM(COALESCE(visit_date_iso, '')) = '')
--   AND BTRIM(COALESCE(protocol, '')) = 'N/A'
--   AND BTRIM(COALESCE(site_address, '')) = 'N/A'
--   AND (
--     LOWER(BTRIM(COALESCE(visit_date, ''))) LIKE '%tbd%'
--     OR BTRIM(COALESCE(visit_date, '')) = ''
--   );

DELETE FROM monitoring_visits
WHERE (site_id IS NULL OR BTRIM(site_id) = '')
  AND (study_id IS NULL OR BTRIM(study_id) = '')
  AND (BTRIM(COALESCE(visit_date_iso, '')) = '')
  AND BTRIM(COALESCE(protocol, '')) = 'N/A'
  AND BTRIM(COALESCE(site_address, '')) = 'N/A'
  AND (
    LOWER(BTRIM(COALESCE(visit_date, ''))) LIKE '%tbd%'
    OR BTRIM(COALESCE(visit_date, '')) = ''
  );
