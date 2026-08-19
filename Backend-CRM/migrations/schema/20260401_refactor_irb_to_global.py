"""
Migration: Refactor IRB to global reusable master entity.

Goal
----
- `irbs` becomes global (no site_id/study_id); add `unique_code`.
- `irb_administrative_info` becomes 1:1 with `irbs` via `irb_id`.
- Add `site_irb_mapping` (site+study -> irb).
- Add `irb_required_documents` (IRB-driven requirements).

This migration is designed to be safe on existing installations:
- It creates new columns/tables first.
- It backfills mapping from existing data where possible.
- It drops legacy constraints/columns only after backfill.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

# Ensure `app.*` imports work when run directly
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import AsyncSessionLocal  # noqa: E402


SQL_STATEMENTS = [
    # ---------------------------------------------------------------------
    # 1) New column on irbs (global identifier)
    # ---------------------------------------------------------------------
    """
    ALTER TABLE IF EXISTS irbs
    ADD COLUMN IF NOT EXISTS unique_code TEXT;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'ix_irbs_unique_code'
        ) THEN
            CREATE UNIQUE INDEX ix_irbs_unique_code ON irbs (unique_code);
        END IF;
    END $$;
    """,
    # ---------------------------------------------------------------------
    # 2) Create mapping + requirements tables
    # ---------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS site_irb_mapping (
        id SERIAL PRIMARY KEY,
        site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
        study_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
        irb_id INTEGER NOT NULL REFERENCES irbs(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_site_irb_mapping_site_study UNIQUE (site_id, study_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_irb_mapping_site_id ON site_irb_mapping (site_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_irb_mapping_study_id ON site_irb_mapping (study_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_irb_mapping_irb_id ON site_irb_mapping (irb_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS irb_required_documents (
        id SERIAL PRIMARY KEY,
        irb_id INTEGER NOT NULL REFERENCES irbs(id) ON DELETE CASCADE,
        document_name TEXT NOT NULL,
        is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_irb_required_documents_irb_id ON irb_required_documents (irb_id);
    """,
    # ---------------------------------------------------------------------
    # 3) Add irb_id to irb_administrative_info (1:1)
    # ---------------------------------------------------------------------
    """
    ALTER TABLE IF EXISTS irb_administrative_info
    ADD COLUMN IF NOT EXISTS irb_id INTEGER;
    """,
    """
    DO $$
    BEGIN
        -- Add FK if not present
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'fk_irb_admin_irb'
        ) THEN
            ALTER TABLE irb_administrative_info
            ADD CONSTRAINT fk_irb_admin_irb
            FOREIGN KEY (irb_id) REFERENCES irbs(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        -- Ensure 1 admin record per IRB (unique irb_id), but only after we backfill.
        -- We'll create the unique index later once data is consistent.
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'ix_irb_admin_irb_id'
        ) THEN
            CREATE INDEX ix_irb_admin_irb_id ON irb_administrative_info (irb_id);
        END IF;
    END $$;
    """,
    # ---------------------------------------------------------------------
    # 4) Backfill: create global IRBs from existing admin info org names
    # ---------------------------------------------------------------------
    """
    INSERT INTO irbs (name)
    SELECT DISTINCT
        COALESCE(NULLIF(TRIM(a.irb_name), ''), NULLIF(TRIM(a.iec_name), '')) AS primary_name
    FROM irb_administrative_info a
    WHERE COALESCE(NULLIF(TRIM(a.irb_name), ''), NULLIF(TRIM(a.iec_name), '')) IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM irbs i
        WHERE i.name = COALESCE(NULLIF(TRIM(a.irb_name), ''), NULLIF(TRIM(a.iec_name), ''))
      );
    """,
    # Map irb_administrative_info -> irb_id via matching name
    """
    UPDATE irb_administrative_info a
    SET irb_id = x.id
    FROM (
        SELECT name, MIN(id) AS id
        FROM irbs
        GROUP BY name
    ) x
    WHERE a.irb_id IS NULL
      AND COALESCE(NULLIF(TRIM(a.irb_name), ''), NULLIF(TRIM(a.iec_name), '')) = x.name;
    """,
    # Backfill site_irb_mapping from legacy `irbs` table if it still has site_id/study_id columns
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='irbs' AND column_name='site_id'
        )
        AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='irbs' AND column_name='study_id'
        ) THEN
            -- Link legacy irbs rows to global irbs via name
            INSERT INTO site_irb_mapping (site_id, study_id, irb_id)
            SELECT old.site_id, old.study_id, named.id
            FROM irbs old
            JOIN (
                SELECT name, MIN(id) AS id
                FROM irbs
                GROUP BY name
            ) named ON named.name = old.name
            WHERE old.site_id IS NOT NULL
              AND old.study_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM sites s
                  WHERE s.id = old.site_id
              )
              AND EXISTS (
                  SELECT 1 FROM studies st
                  WHERE st.id = old.study_id
              )
            ON CONFLICT (site_id, study_id) DO UPDATE SET irb_id = EXCLUDED.irb_id;
        END IF;
    END $$;
    """,
    # ---------------------------------------------------------------------
    # 5) Seed baseline required documents per IRB (only if empty for that IRB)
    # ---------------------------------------------------------------------
    """
    INSERT INTO irb_required_documents (irb_id, document_name, is_mandatory)
    SELECT i.id, d.document_name, d.is_mandatory
    FROM irbs i
    CROSS JOIN (
        VALUES
            ('Protocol', TRUE),
            ('Informed Consent form', TRUE),
            ('Investigators Brochure/ Product Monograph', TRUE),
            ('Study Budget/ Clinical trial Agreement(CTA)', TRUE),
            ('Safety Monitoring Plan', TRUE),
            ('Regulatory approvals', TRUE),
            ('Data management plan', TRUE),
            ('Principal Investigators CV and other information', TRUE),
            ('Conflict of Interest Declarations', TRUE),
            ('Recruitment materials', TRUE)
    ) AS d(document_name, is_mandatory)
    WHERE NOT EXISTS (
        SELECT 1 FROM irb_required_documents r
        WHERE r.irb_id = i.id
    );
    """,
    # ---------------------------------------------------------------------
    # 6) Drop legacy uniqueness constraints and columns (after backfill)
    # ---------------------------------------------------------------------
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_study_site_irb') THEN
            ALTER TABLE irbs DROP CONSTRAINT unique_study_site_irb;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'irbs_site_id_name_key') THEN
            ALTER TABLE irbs DROP CONSTRAINT irbs_site_id_name_key;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_irbs_site_id_name') THEN
            ALTER TABLE irbs DROP CONSTRAINT uq_irbs_site_id_name;
        END IF;
    END $$;
    """,
    # Drop old columns from irbs if present
    """
    ALTER TABLE IF EXISTS irbs
    DROP COLUMN IF EXISTS site_id,
    DROP COLUMN IF EXISTS study_id;
    """,
    # Drop old columns from irb_administrative_info if present
    """
    ALTER TABLE IF EXISTS irb_administrative_info
    DROP COLUMN IF EXISTS site_id,
    DROP COLUMN IF EXISTS study_id;
    """,
    # Enforce 1:1 admin info per IRB (unique irb_id) after cleanup
    """
    DO $$
    BEGIN
        -- Deduplicate legacy admin rows so each IRB has exactly one admin profile.
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='irb_administrative_info'
              AND column_name='irb_id'
        ) THEN
            DELETE FROM irb_administrative_info a
            USING irb_administrative_info b
            WHERE a.irb_id = b.irb_id
              AND a.id > b.id;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'uq_irb_admin_irb_id'
        ) THEN
            CREATE UNIQUE INDEX uq_irb_admin_irb_id ON irb_administrative_info (irb_id);
        END IF;
    END $$;
    """,
]


async def main() -> None:
    print("=" * 70)
    print("Refactor IRB to global reusable system")
    print("=" * 70)
    async with AsyncSessionLocal() as session:
        for stmt in SQL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())

