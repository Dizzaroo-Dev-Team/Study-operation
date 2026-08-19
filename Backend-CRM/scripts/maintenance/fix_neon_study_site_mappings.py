"""
Fix Neon database: Ensure all studies have study_sites mappings and workflow steps.

This script:
1. Verifies all studies exist in Neon
2. Creates study_sites mappings for all studies + the site
3. Initializes workflow steps if they don't exist

Usage:
    Set NEON_DATABASE_URL environment variable, then run:
    python fix_neon_study_site_mappings.py
"""

import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Load environment variables
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from app.models import Study, Site, StudySite, SiteWorkflowStep, WorkflowStepName


async def fix_neon_study_site_mappings():
    """Fix study_sites mappings and workflow steps in Neon."""
    print("=" * 70)
    print("Fix Neon: Study-Site Mappings & Workflow Steps")
    print("=" * 70)
    print()
    
    # Get Neon connection string
    neon_db_url = os.getenv("NEON_DATABASE_URL")
    
    if not neon_db_url:
        print("❌ ERROR: NEON_DATABASE_URL environment variable not set")
        print("   Example: postgresql+asyncpg://user:pass@neon-host/dbname")
        sys.exit(1)
    
    neon_db_url = neon_db_url.strip().strip('"').strip("'")
    
    print(f"☁️  Neon Database: {neon_db_url.split('@')[-1] if '@' in neon_db_url else neon_db_url}")
    print()
    
    # Create engine
    neon_engine = create_async_engine(neon_db_url, echo=False)
    neon_session_maker = async_sessionmaker(neon_engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with neon_session_maker() as session:
            # ------------------------------------------------------------------
            # Step 1: Get all studies and the site
            # ------------------------------------------------------------------
            print("📖 Reading studies and sites from Neon...")
            studies_result = await session.execute(select(Study))
            studies = studies_result.scalars().all()
            
            sites_result = await session.execute(select(Site))
            sites = sites_result.scalars().all()
            
            print(f"   Found {len(studies)} studies")
            print(f"   Found {len(sites)} sites")
            
            if len(studies) == 0:
                print("⚠️  No studies found in Neon!")
                return
            
            if len(sites) == 0:
                print("⚠️  No sites found in Neon!")
                return
            
            # Use the first site (or you can filter by site_id if needed)
            site = sites[0]
            print(f"   Using site: {site.site_id} ({site.name})")
            print()
            
            # ------------------------------------------------------------------
            # Step 2: Create study_sites mappings for all studies
            # ------------------------------------------------------------------
            print("🔗 Creating study_sites mappings...")
            mappings_created = 0
            mappings_existing = 0
            
            for study in studies:
                # Check if mapping already exists
                existing_result = await session.execute(
                    select(StudySite).where(
                        StudySite.study_id == study.id,
                        StudySite.site_id == site.id
                    )
                )
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    mappings_existing += 1
                    print(f"   ✓ {study.study_id}: mapping already exists")
                else:
                    # Create new mapping
                    study_site = StudySite(
                        study_id=study.id,
                        site_id=site.id
                    )
                    session.add(study_site)
                    mappings_created += 1
                    print(f"   ✓ {study.study_id}: created mapping")
            
            await session.commit()
            print(f"\n   Created {mappings_created} new mappings, {mappings_existing} already existed")
            print()
            
            # ------------------------------------------------------------------
            # Step 3: Initialize workflow steps for all study_site combinations
            # ------------------------------------------------------------------
            print("📋 Initializing workflow steps...")
            steps_created = 0
            steps_existing = 0
            
            # Get all study_sites mappings
            study_sites_result = await session.execute(
                select(StudySite).where(StudySite.site_id == site.id)
            )
            study_sites = study_sites_result.scalars().all()
            
            # Workflow step names that are study-specific
            study_specific_steps = [
                WorkflowStepName.SITE_IDENTIFICATION,
                WorkflowStepName.CDA_EXECUTION,
                WorkflowStepName.FEASIBILITY,
                WorkflowStepName.SITE_SELECTION_OUTCOME,
            ]
            
            for study_site in study_sites:
                for step_name in study_specific_steps:
                    # Check if step already exists
                    existing_step_result = await session.execute(
                        select(SiteWorkflowStep).where(
                            SiteWorkflowStep.study_site_id == study_site.id,
                            SiteWorkflowStep.step_name == step_name
                        )
                    )
                    existing_step = existing_step_result.scalar_one_or_none()
                    
                    if existing_step:
                        steps_existing += 1
                    else:
                        # Create new workflow step
                        workflow_step = SiteWorkflowStep(
                            study_site_id=study_site.id,
                            site_id=site.id,
                            step_name=step_name,
                            status="not_started"
                        )
                        session.add(workflow_step)
                        steps_created += 1
            
            await session.commit()
            print(f"   Created {steps_created} new workflow steps, {steps_existing} already existed")
            print()
            
            # ------------------------------------------------------------------
            # Step 4: Verify everything
            # ------------------------------------------------------------------
            print("✅ Verifying setup...")
            
            # Count study_sites
            study_sites_count_result = await session.execute(
                select(StudySite).where(StudySite.site_id == site.id)
            )
            study_sites_count = len(study_sites_count_result.scalars().all())
            
            # Count workflow steps
            workflow_steps_count_result = await session.execute(
                select(SiteWorkflowStep).where(SiteWorkflowStep.site_id == site.id)
            )
            workflow_steps_count = len(workflow_steps_count_result.scalars().all())
            
            print(f"   Study-Site mappings: {study_sites_count} (expected: {len(studies)})")
            print(f"   Workflow steps: {workflow_steps_count} (expected: {len(studies) * 4})")
            print()
            
            # List all studies
            print("📚 Studies in Neon:")
            for study in studies:
                print(f"   - {study.study_id}: {study.name}")
            print()
            
            print("=" * 70)
            print("[SUCCESS] Neon database fixed!")
            print("=" * 70)
            print(f"   Site: {site.site_id} ({site.name})")
            print(f"   Studies: {len(studies)}")
            print(f"   Study-Site Mappings: {study_sites_count}")
            print(f"   Workflow Steps: {workflow_steps_count}")
            print("=" * 70)
            
    except Exception as e:
        print()
        print("=" * 70)
        print(f"[ERROR] Failed to fix Neon: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await neon_engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(fix_neon_study_site_mappings())
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
