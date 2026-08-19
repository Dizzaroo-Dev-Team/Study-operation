"""
Create a clearly-named, guaranteed-FREE test site under study MK-6482 so the unified
Agreement page shows the 'Create an agreement' template picker (it only shows when
the selected study+site has no agreement). Adds a SiteProfile so create_agreement
works. Idempotent by site code. No feature code.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.models import Site, StudySite, SiteProfile

STUDY_ID = "f29f2acc-f534-4e6d-af5b-3860930b9cc1"  # MK-6482
SITE_CODE = "ZZ-E2E"
SITE_NAME = "ZZ E2E Test Site (unified)"
RECIPIENT_EMAIL = "labesh@dizzaroo.com"


async def main():
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(text("SELECT id FROM sites WHERE site_id=:c"), {"c": SITE_CODE})).fetchone()
        if existing:
            site_id = existing[0]
        else:
            site = Site(site_id=SITE_CODE, name=SITE_NAME, status="active")
            db.add(site); await db.flush(); site_id = site.id; await db.commit()

        ss = (await db.execute(text("SELECT id FROM study_sites WHERE study_id=:s AND site_id=:si"),
                               {"s": STUDY_ID, "si": str(site_id)})).fetchone()
        if not ss:
            link = StudySite(study_id=STUDY_ID, site_id=site_id)
            db.add(link); await db.flush(); study_site_id = link.id; await db.commit()
        else:
            study_site_id = ss[0]

        prof = (await db.execute(text("SELECT id FROM site_profiles WHERE site_id=:si"), {"si": str(site_id)})).fetchone()
        if not prof:
            db.add(SiteProfile(site_id=site_id, authorized_signatory_name="Authorized Signer",
                               authorized_signatory_email=RECIPIENT_EMAIL, pi_name="Dr. Test PI",
                               pi_email=RECIPIENT_EMAIL, site_name=SITE_NAME))
            await db.commit()

        agree = (await db.execute(text("SELECT count(*) FROM agreements WHERE study_site_id=:ss"), {"ss": str(study_site_id)})).scalar()
        print("=" * 70)
        print("E2E TEST SITE READY")
        print("=" * 70)
        print(f"Study     : MK-6482 ({STUDY_ID})")
        print(f"Site      : {SITE_NAME}  (code {SITE_CODE})")
        print(f"site_id   : {site_id}")
        print(f"study_site: {study_site_id}  agreements_here={agree}")
        print(f"profile   : created (signatory {RECIPIENT_EMAIL})")
        print("Select this study+site in the app -> Agreements -> the template picker shows.")


if __name__ == "__main__":
    asyncio.run(main())
