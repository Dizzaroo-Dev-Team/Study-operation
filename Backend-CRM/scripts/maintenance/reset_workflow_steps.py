"""
Utility script to reset site workflow steps for testing.

This mirrors the behavior of the `/sites/{site_id}/workflow/steps` DELETE
endpoint in `app/api/routes.py`, but lets you run it directly from the
command line.

Usage (from Backend-CRM folder):

    # Reset workflow steps for ONE site (by UUID or external site_id)
    python reset_workflow_steps.py <site_id_or_uuid>

    # Reset workflow steps for ALL sites
    python reset_workflow_steps.py --all

This script is NON-DESTRUCTIVE to anything except the `site_workflow_steps`
table. It only deletes rows from that table, so you can re-test the
Under Consideration workflow from a clean slate.
"""

import asyncio
import sys
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete

from app.db import AsyncSessionLocal  # same pattern as other migration scripts
from app.models import Site, SiteWorkflowStep


async def reset_for_site(site_identifier: str) -> None:
    """Reset workflow steps for a single site (by UUID or site_id string)."""
    async with AsyncSessionLocal() as session:
        # Resolve site by UUID or site_id
        site: Optional[Site] = None

        # Try UUID first
        try:
            site_uuid = UUID(str(site_identifier))
            result = await session.execute(select(Site).where(Site.id == site_uuid))
            site = result.scalar_one_or_none()
        except (ValueError, TypeError):
            # Fallback to site_id string
            result = await session.execute(select(Site).where(Site.site_id == site_identifier))
            site = result.scalar_one_or_none()

        if not site:
            print(f"[ERROR] Site not found for identifier: {site_identifier}")
            return

        # Delete workflow steps for this site
        await session.execute(
            delete(SiteWorkflowStep).where(SiteWorkflowStep.site_id == site.id)
        )
        await session.commit()

        print(f"[OK] Workflow steps reset for site {site.site_id or site.id}")


async def reset_for_all_sites() -> None:
    """Reset workflow steps for ALL sites."""
    async with AsyncSessionLocal() as session:
        # Just delete all rows from site_workflow_steps
        await session.execute(delete(SiteWorkflowStep))
        await session.commit()

        print("[OK] Workflow steps reset for ALL sites")


async def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("Usage:")
        print("  python reset_workflow_steps.py <site_id_or_uuid>")
        print("  python reset_workflow_steps.py --all")
        sys.exit(1)

    arg = argv[1]
    if arg in ("--all", "-a"):
        await reset_for_all_sites()
    else:
        await reset_for_site(arg)


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv))
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")
        sys.exit(1)
"""
Reset workflow steps for testing.

Usage:
    python reset_workflow_steps.py                    # Reset all sites
    python reset_workflow_steps.py --site-id <id>     # Reset specific site
    python reset_workflow_steps.py --site-id site1    # Reset by site_id string
"""
import asyncio
import sys
import os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Load environment variables
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from app.config import settings
from app.models import Site, SiteWorkflowStep


async def reset_workflow_steps(site_id: str = None):
    """Reset workflow steps for a specific site or all sites."""
    print("=" * 70)
    print("Reset Workflow Steps")
    print("=" * 70)
    
    # Handle Docker service name when running from host
    db_url_to_use = settings.database_url
    if 'postgres:' in db_url_to_use and 'localhost' not in db_url_to_use and '127.0.0.1' not in db_url_to_use:
        db_url_to_use = db_url_to_use.replace('postgres:', 'localhost:')
        print("Note: Using localhost instead of Docker service name for connection")
    
    print(f"Database: {db_url_to_use.split('@')[-1] if '@' in db_url_to_use else db_url_to_use}")
    print()

    # Create engine
    engine = create_async_engine(
        db_url_to_use,
        echo=False,
        future=True
    )
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with AsyncSessionLocal() as session:
        try:
            site = None
            if site_id:
                # Try to find site by UUID or site_id
                try:
                    site_uuid = UUID(str(site_id))
                    result = await session.execute(select(Site).where(Site.id == site_uuid))
                    site = result.scalar_one_or_none()
                except (ValueError, TypeError):
                    # Try by site_id string
                    result = await session.execute(select(Site).where(Site.site_id == site_id))
                    site = result.scalar_one_or_none()
                
                if not site:
                    print(f"❌ Site not found: {site_id}")
                    return
                
                print(f"Resetting workflow steps for site: {site.site_id or site.id}")
                
                # Delete all workflow steps for this site
                await session.execute(
                    delete(SiteWorkflowStep).where(SiteWorkflowStep.site_id == site.id)
                )
                await session.commit()
                
                print(f"✅ Reset complete! All workflow steps deleted for site: {site.site_id or site.id}")
            else:
                # Reset all sites
                print("Resetting workflow steps for ALL sites...")
                confirm = await asyncio.to_thread(input, "Are you sure? This will delete ALL workflow steps. Type 'yes' to confirm: ")
                
                if confirm.lower() != 'yes':
                    print("❌ Reset cancelled")
                    return
                
                # Delete all workflow steps
                await session.execute(delete(SiteWorkflowStep))
                await session.commit()
                
                print("✅ Reset complete! All workflow steps deleted for all sites")
                
        except Exception as e:
            await session.rollback()
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Reset workflow steps for testing")
    parser.add_argument("--site-id", type=str, help="Site ID or UUID to reset (optional, resets all if not provided)")
    args = parser.parse_args()
    
    asyncio.run(reset_workflow_steps(site_id=args.site_id))