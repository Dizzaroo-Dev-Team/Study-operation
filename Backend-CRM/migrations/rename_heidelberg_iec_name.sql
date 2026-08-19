BEGIN;

-- Rename Heidelberg IRB catalog entry to the new canonical label.
UPDATE irbs
SET name = 'Heidelberg University Ethics Committee (Germany)'
WHERE trim(trailing '.' FROM name) = 'Ethics Committee of the Medical Faculty of Heidelberg University,Germany';

-- Keep existing site packages visually consistent with the new IRB name.
UPDATE site_packages
SET "ethicsBoard" = 'Heidelberg University Ethics Committee (Germany)'
WHERE trim(trailing '.' FROM "ethicsBoard") = 'Ethics Committee of the Medical Faculty of Heidelberg University,Germany';

COMMIT;