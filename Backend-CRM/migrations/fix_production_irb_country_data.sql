-- =====================================================================
-- Production fix: IRB country tags + site profile country for US sites
-- Run once on Neon (production). Review SELECTs before UPDATEs.
-- =====================================================================

-- ---------------------------------------------------------------------
-- STEP 0: Discover site + IRB ids (run first)
-- ---------------------------------------------------------------------
SELECT id, site_id, name, country
FROM sites
WHERE name ILIKE '%Anderson%'
   OR name ILIKE '%M D %'
   OR site_id ILIKE '%anderson%';

SELECT i.id AS irb_id, i.name, a.country, a.jurisdiction
FROM irbs i
LEFT JOIN irb_administrative_info a ON a.irb_id = i.id
ORDER BY i.name;

SELECT s.name, sp.country, sp.city, sp.state
FROM sites s
LEFT JOIN site_profiles sp ON sp.site_id = s.id
WHERE s.name ILIKE '%Anderson%'
   OR s.name ILIKE '%M D %';

SELECT * FROM site_irb_mapping
WHERE site_id IN (
    SELECT id FROM sites
    WHERE name ILIKE '%Anderson%' OR name ILIKE '%M D %'
);

-- ---------------------------------------------------------------------
-- STEP 1: Fix MD Anderson IRB — country was blank, jurisdiction = Texas
-- ---------------------------------------------------------------------
UPDATE irb_administrative_info a
SET
    country = 'United States',
    jurisdiction = COALESCE(NULLIF(TRIM(a.jurisdiction), ''), 'Texas')
FROM irbs i
WHERE a.irb_id = i.id
  AND i.name ILIKE '%MD Anderson%'
  AND (
      NULLIF(TRIM(a.country), '') IS NULL
      OR LOWER(TRIM(a.country)) IN ('usa', 'us', 'u.s.', 'u.s.a.')
  );

-- ---------------------------------------------------------------------
-- STEP 2: Normalize other common US alias spellings on IRB admin rows
-- ---------------------------------------------------------------------
UPDATE irb_administrative_info
SET country = 'United States'
WHERE LOWER(TRIM(country)) IN ('usa', 'us', 'u.s.', 'u.s.a.', 'united states of america');

-- US state mistakenly stored only in jurisdiction with empty country
UPDATE irb_administrative_info
SET country = 'United States'
WHERE NULLIF(TRIM(country), '') IS NULL
  AND LOWER(TRIM(jurisdiction)) IN (
      'texas', 'tx', 'california', 'ca', 'new york', 'ny', 'florida', 'fl',
      'massachusetts', 'ma', 'pennsylvania', 'pa', 'ohio', 'oh', 'illinois', 'il'
  );

-- ---------------------------------------------------------------------
-- STEP 3: Set site_profiles.country for US Anderson site (if profile exists)
-- Replace :site_uuid with id from STEP 0
-- ---------------------------------------------------------------------
-- UPDATE site_profiles
-- SET country = 'United States'
-- WHERE site_id = ':site_uuid'
--   AND (country IS NULL OR TRIM(country) = '');

-- If no profile row exists yet, insert one (replace :site_uuid):
-- INSERT INTO site_profiles (site_id, country, city, state, created_at, updated_at)
-- SELECT id, 'United States', city, state, NOW(), NOW()
-- FROM sites
-- WHERE id = ':site_uuid'
-- ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- STEP 4: Optional — link MD Anderson site to MD Anderson IRB
-- Replace :site_uuid and :irb_id from STEP 0
-- ---------------------------------------------------------------------
-- INSERT INTO site_irb_mapping (site_id, irb_id, created_at, updated_at)
-- VALUES (':site_uuid', :irb_id, NOW(), NOW())
-- ON CONFLICT (site_id) DO UPDATE
--   SET irb_id = EXCLUDED.irb_id, updated_at = NOW();

-- ---------------------------------------------------------------------
-- STEP 5: Verify
-- ---------------------------------------------------------------------
SELECT i.id, i.name, a.country, a.jurisdiction
FROM irbs i
LEFT JOIN irb_administrative_info a ON a.irb_id = i.id
WHERE i.name ILIKE '%Anderson%' OR a.country = 'United States';
