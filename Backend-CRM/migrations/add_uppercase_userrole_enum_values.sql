-- The Python `UserRole` enum maps `STUDY_MANAGER → "study_manager"` etc, but
-- SQLAlchemy's `SQLEnum(UserRole)` serialises the Python enum NAME
-- ("STUDY_MANAGER"), not the value. The Postgres enum was originally created
-- with only the lowercase values for newer roles, so inserts blew up with:
--     invalid input value for enum userrole: "STUDY_MANAGER"
-- This migration adds the uppercase variants so both representations work
-- without forcing a global SQLAlchemy `values_callable` change. Idempotent.

ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'CRA';
ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'STUDY_MANAGER';
ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'MEDICAL_MONITOR';
