-- Rename Oxford site/IRB label to the new canonical name.
-- Safe to run multiple times.

-- Requested canonical label (kept exactly as provided).
-- Note: spelling/spacing intentionally preserved.
--   The Oxford Cancer & Heamatology Centre , United Kingdom

UPDATE irbs
SET name = 'The Oxford Cancer & Heamatology Centre , United Kingdom'
WHERE LOWER(TRIM(COALESCE(unique_code, ''))) = 'hra_oxford_rec_uk'
   OR LOWER(TRIM(name)) IN (
      'south central - oxford research ethics committee',
      'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
      'health research authority (hra) and south central - oxford rec (uk)',
      'the oxford cancer & heamatology centre , united kingdom',
      'the oxford cancer & hematology centre , united kingdom'
   );

UPDATE site_packages
SET "ethicsBoard" = 'The Oxford Cancer & Heamatology Centre , United Kingdom'
WHERE LOWER(TRIM(COALESCE("ethicsBoard", ''))) IN (
  'south central - oxford research ethics committee',
  'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
  'health research authority (hra) and south central - oxford rec (uk)',
  'the oxford cancer & heamatology centre , united kingdom',
  'the oxford cancer & hematology centre , united kingdom'
);

UPDATE irb_administrative_info
SET iec_name = 'The Oxford Cancer & Heamatology Centre , United Kingdom'
WHERE LOWER(TRIM(COALESCE(iec_name, ''))) IN (
  'south central - oxford research ethics committee',
  'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
  'health research authority (hra) and south central - oxford rec (uk)',
  'the oxford cancer & heamatology centre , united kingdom',
  'the oxford cancer & hematology centre , united kingdom'
);

UPDATE irb_administrative_info
SET irb_name = 'The Oxford Cancer & Heamatology Centre , United Kingdom'
WHERE LOWER(TRIM(COALESCE(irb_name, ''))) IN (
  'south central - oxford research ethics committee',
  'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
  'health research authority (hra) and south central - oxford rec (uk)',
  'the oxford cancer & heamatology centre , united kingdom',
  'the oxford cancer & hematology centre , united kingdom'
);

UPDATE sites
SET name = 'The Oxford Cancer & Heamatology Centre , United Kingdom'
WHERE LOWER(TRIM(COALESCE(name, ''))) IN (
  'south central - oxford research ethics committee',
  'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
  'health research authority (hra) and south central - oxford rec (uk)',
  'the oxford cancer & heamatology centre , united kingdom',
  'the oxford cancer & hematology centre , united kingdom'
);
