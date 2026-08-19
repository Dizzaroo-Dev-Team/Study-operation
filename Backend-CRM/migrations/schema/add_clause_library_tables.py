"""
Migration: add Clause Library tables + composition_mode column to study_templates.

Creates:
  - clauses                  (Clause identity + metadata)
  - clause_versions          (Immutable append-only version rows)
  - template_clauses         (Ordered composition join: template ↔ clause)

Modifies:
  - study_templates          (add composition_mode column)

Safe to run multiple times (idempotent via IF NOT EXISTS / DO $$ patterns).
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from app.config import settings  # noqa: E402


async def run():
    db_url = settings.database_url
    if "postgres:" in db_url and "localhost" not in db_url and "127.0.0.1" not in db_url:
        db_url = db_url.replace("postgres:", "localhost:")
        print("Note: using localhost instead of Docker service name")

    print("=" * 70)
    print("Clause Library Migration")
    print("DB:", db_url.split("@")[-1] if "@" in db_url else db_url)
    print("=" * 70)

    engine = create_async_engine(db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        try:
            # ------------------------------------------------------------------
            # 1. ENUM types
            # ------------------------------------------------------------------
            await session.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE clause_lock_policy AS ENUM (
                        'STANDARD_LOCKED',
                        'EDITABLE',
                        'ALTERNATE'
                    );
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """))

            await session.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE clause_version_status AS ENUM (
                        'DRAFT',
                        'APPROVED',
                        'RETIRED'
                    );
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """))

            await session.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE composition_mode AS ENUM (
                        'DOCX_UPLOAD',
                        'CLAUSE_COMPOSED'
                    );
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """))

            await session.commit()
            print("  [OK] Enum types created / verified")

            # ------------------------------------------------------------------
            # 2. clause_versions (created BEFORE clauses so the FK in clauses
            #    can reference it; the FK from clause_versions → clauses uses
            #    DEFERRABLE INITIALLY DEFERRED to handle the circular dep)
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS clause_versions (
                    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    clause_id        UUID        NOT NULL,
                    version_number   INTEGER     NOT NULL,
                    content_json     JSONB       NOT NULL,
                    status           clause_version_status NOT NULL DEFAULT 'DRAFT',
                    created_by       VARCHAR(255),
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_clause_version UNIQUE (clause_id, version_number)
                )
            """))
            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_clause_versions_clause_id "
                "ON clause_versions (clause_id)"
            ))

            print("  [OK] clause_versions table created / verified")

            # ------------------------------------------------------------------
            # 3. clauses
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS clauses (
                    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    title               VARCHAR(255) NOT NULL,
                    category            VARCHAR(100) NOT NULL,
                    description         TEXT,
                    lock_policy         clause_lock_policy NOT NULL DEFAULT 'STANDARD_LOCKED',
                    current_version_id  UUID        REFERENCES clause_versions(id) ON DELETE SET NULL,
                    created_by          VARCHAR(255),
                    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_clauses_category ON clauses (category)"
            ))
            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_clauses_title ON clauses (title)"
            ))

            print("  [OK] clauses table created / verified")

            # ------------------------------------------------------------------
            # 4. Add FK clause_versions.clause_id → clauses.id (deferred to
            #    break the circular dependency at INSERT time)
            # ------------------------------------------------------------------
            await session.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_clause_versions_clause_id'
                    ) THEN
                        ALTER TABLE clause_versions
                            ADD CONSTRAINT fk_clause_versions_clause_id
                            FOREIGN KEY (clause_id) REFERENCES clauses(id)
                            ON DELETE CASCADE
                            DEFERRABLE INITIALLY DEFERRED;
                    END IF;
                END $$;
            """))

            print("  [OK] clause_versions.clause_id FK added / verified")

            # ------------------------------------------------------------------
            # 5. template_clauses
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS template_clauses (
                    id                      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
                    template_id             UUID    NOT NULL REFERENCES study_templates(id) ON DELETE CASCADE,
                    clause_id               UUID    NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
                    pinned_clause_version_id UUID   REFERENCES clause_versions(id) ON DELETE SET NULL,
                    sort_order              INTEGER NOT NULL DEFAULT 0,
                    is_locked               VARCHAR(10) NOT NULL DEFAULT 'true',
                    is_editable             VARCHAR(10) NOT NULL DEFAULT 'false',
                    override_content_json   JSONB,
                    CONSTRAINT uq_template_clause UNIQUE (template_id, clause_id)
                )
            """))
            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_template_clauses_template_id "
                "ON template_clauses (template_id, sort_order)"
            ))

            print("  [OK] template_clauses table created / verified")

            # ------------------------------------------------------------------
            # 6. Add composition_mode to study_templates
            # ------------------------------------------------------------------
            await session.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'study_templates'
                          AND column_name = 'composition_mode'
                    ) THEN
                        ALTER TABLE study_templates
                            ADD COLUMN composition_mode composition_mode
                            NOT NULL DEFAULT 'DOCX_UPLOAD';
                    END IF;
                END $$;
            """))

            await session.commit()
            print("  [OK] study_templates.composition_mode column added / verified")

            print()
            print("=" * 70)
            print("[SUCCESS] Clause Library migration complete.")
            print("=" * 70)

        except Exception as exc:
            await session.rollback()
            print()
            print("=" * 70)
            print(f"[ERROR] Migration failed: {exc}")
            print("=" * 70)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
