BEGIN;

-- Rename IRB catalog entry from legacy long label to short label.
UPDATE irbs
SET name = 'MD Anderson IRB'
WHERE trim(trailing '.' FROM name) = 'The Institutional Review Board of The University of Texas MD Anderson Cancer Center (MD Anderson IRB)';

-- Keep existing site packages visually consistent with the new IRB name.
UPDATE site_packages
SET "ethicsBoard" = 'MD Anderson IRB'
WHERE trim(trailing '.' FROM "ethicsBoard") = 'The Institutional Review Board of The University of Texas MD Anderson Cancer Center (MD Anderson IRB)';

COMMIT;
