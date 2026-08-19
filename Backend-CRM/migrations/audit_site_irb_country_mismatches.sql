-- =====================================================================
-- One-time audit: find site ↔ IRB mappings where countries do not match
-- Run on production, then fix rows returned (UI or UPDATE by irb name).
-- =====================================================================

SELECT
    s.id AS site_uuid,
    s.site_id AS site_code,
    s.name AS site_name,
    COALESCE(NULLIF(TRIM(sp.country), ''), NULLIF(TRIM(s.country), '')) AS site_country,
    m.irb_id,
    i.name AS irb_name,
    a.country AS irb_country,
    a.jurisdiction AS irb_jurisdiction
FROM site_irb_mapping m
JOIN sites s ON s.id = m.site_id
LEFT JOIN site_profiles sp ON sp.site_id = s.id
JOIN irbs i ON i.id = m.irb_id
LEFT JOIN irb_administrative_info a ON a.irb_id = i.id
WHERE LOWER(TRIM(COALESCE(NULLIF(TRIM(sp.country), ''), NULLIF(TRIM(s.country), ''), '')))
      IS DISTINCT FROM
      LOWER(TRIM(COALESCE(NULLIF(TRIM(a.country), ''), NULLIF(TRIM(a.jurisdiction), ''), '')))
  AND COALESCE(NULLIF(TRIM(sp.country), ''), NULLIF(TRIM(s.country), '')) IS NOT NULL
ORDER BY s.name;

-- Fix example (use irb NAME — ids differ per environment):
-- UPDATE site_irb_mapping
-- SET irb_id = (SELECT id FROM irbs WHERE name ILIKE '%MD Anderson%' LIMIT 1),
--     updated_at = NOW()
-- WHERE site_id = '128fb082-1297-4356-91f0-f6d1f93e3089';
