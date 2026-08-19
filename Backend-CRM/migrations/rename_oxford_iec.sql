-- Rename UK IEC label to the new canonical name.
-- Safe to run multiple times.

UPDATE irbs
SET name = 'South Central - Oxford Research Ethics Committee'
WHERE id = 6
   OR LOWER(TRIM(name)) IN (
      'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
      'health research authority (hra) and south central - oxford rec (uk)',
      'south central - oxford research ethics committee'
   );

UPDATE site_packages
SET "ethicsBoard" = 'South Central - Oxford Research Ethics Committee'
WHERE LOWER(TRIM("ethicsBoard")) IN (
  'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
  'health research authority (hra) and south central - oxford rec (uk)'
);

UPDATE irb_administrative_info
SET iec_name = 'South Central - Oxford Research Ethics Committee'
WHERE LOWER(TRIM(COALESCE(iec_name, ''))) IN (
  'health research authority (hra) and a recognized research ethics committee (rec), typically the south central - oxford rec..',
  'health research authority (hra) and south central - oxford rec (uk)'
);
