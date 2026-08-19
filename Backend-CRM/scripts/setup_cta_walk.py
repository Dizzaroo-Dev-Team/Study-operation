"""
Seed a clean, unambiguous env for re-walking the corrected CTA flow. No feature code.
Idempotent (reuse by template-name / site-code). Fresh TEMPLATE with NO workflow (so
the builder opens for a fresh regenerate) + fresh empty SITE + profile.
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Site, StudySite, SiteProfile, StudyTemplate, TemplateType  # noqa: E402

STUDY_ID = "f29f2acc-f534-4e6d-af5b-3860930b9cc1"   # 'MK-6482'
LOCAL_DOCX = "uploads/templates/template_75a4022f-98fb-4c2f-a483-91bdbbae1a1a.docx"
TEMPLATE_NAME = "ZZ CTA Walk (local DOCX)"
SITE_CODE = "ZZ-CTA"
SITE_NAME = "ZZ CTA Walk Site"
RECIPIENT = "labesh@dizzaroo.com"


async def main():
    if not os.path.isfile(LOCAL_DOCX):
        print(f"BLOCKER: local DOCX missing at {LOCAL_DOCX}"); return
    async with AsyncSessionLocal() as db:
        study_name = (await db.execute(text("SELECT name FROM studies WHERE id=:s"), {"s": STUDY_ID})).scalar()

        row = (await db.execute(text("SELECT id FROM study_templates WHERE template_name=:n AND study_id=:s"),
                                {"n": TEMPLATE_NAME, "s": STUDY_ID})).fetchone()
        if row:
            template_id = str(row[0])
        else:
            t = StudyTemplate(study_id=STUDY_ID, template_name=TEMPLATE_NAME, template_type=TemplateType.CDA,
                              template_file_path=LOCAL_DOCX, template_file_url=None, is_active="true")
            db.add(t); await db.flush(); template_id = str(t.id); await db.commit()

        srow = (await db.execute(text("SELECT id FROM sites WHERE site_id=:c"), {"c": SITE_CODE})).fetchone()
        if srow:
            site_id = srow[0]
        else:
            s = Site(site_id=SITE_CODE, name=SITE_NAME, status="active"); db.add(s); await db.flush()
            site_id = s.id; await db.commit()

        ss = (await db.execute(text("SELECT id FROM study_sites WHERE study_id=:s AND site_id=:si"),
                               {"s": STUDY_ID, "si": str(site_id)})).fetchone()
        if ss:
            study_site_id = ss[0]
        else:
            link = StudySite(study_id=STUDY_ID, site_id=site_id); db.add(link); await db.flush()
            study_site_id = link.id; await db.commit()

        if not (await db.execute(text("SELECT id FROM site_profiles WHERE site_id=:si"), {"si": str(site_id)})).fetchone():
            db.add(SiteProfile(site_id=site_id, authorized_signatory_name="Authorized Signer",
                               authorized_signatory_email=RECIPIENT, pi_name="Dr. Test PI",
                               pi_email=RECIPIENT, site_name=SITE_NAME))
            await db.commit()

        key = f"tpl:{template_id}"
        has_def = (await db.execute(text("SELECT count(*) FROM workflow_definitions WHERE key=:k"), {"k": key})).scalar()
        n_agree = (await db.execute(text("SELECT count(*) FROM agreements WHERE study_site_id=:ss"), {"ss": str(study_site_id)})).scalar()
        print("=" * 78)
        print("CTA WALK ENV READY")
        print("=" * 78)
        print(f"Study      : {study_name}  ({STUDY_ID})")
        print(f"Site       : {SITE_NAME}  (code {SITE_CODE})  site_id={site_id}")
        print(f"study_site : {study_site_id}  agreements_here={n_agree} (want 0)")
        print(f"Template   : {TEMPLATE_NAME}  id={template_id}")
        print(f"Workflow   : key={key}  exists={bool(has_def)} (want False -> builder opens)")
        print(f"Recipient  : {RECIPIENT}")
        print("Pick Study 'MK-6482' that lists Site 'ZZ CTA Walk Site' -> Agreements -> template picker.")


if __name__ == "__main__":
    asyncio.run(main())
