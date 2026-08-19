BEGIN;

-- Rename CHCAMS IRB catalog entry to the new canonical label.
UPDATE irbs
SET name = 'National Cancer Center / CHCAMS Institutional Ethics Committee, China.'
WHERE trim(trailing '.' FROM name) = 'Ethics Committee of National Cancer Center / Cancer Hospital, Chinese Academy of Medical Sciences and Peking Union Medical College (CHCAMS Ethics Committee),China';

-- Keep existing site packages visually consistent with the new IRB name.
UPDATE site_packages
SET "ethicsBoard" = 'National Cancer Center / CHCAMS Institutional Ethics Committee, China.'
WHERE trim(trailing '.' FROM "ethicsBoard") = 'Ethics Committee of National Cancer Center / Cancer Hospital, Chinese Academy of Medical Sciences and Peking Union Medical College (CHCAMS Ethics Committee),China';

COMMIT;
