"""
INVESTIGATE (run in backend container): same template T, two DIFFERENT sites in ONE
study. Self-contained — publishes the tpl:T definition, makes two fresh empty sites
with profiles, then for each (study, site) prints:
  * agreement id + study_site_id  (must DIFFER per site -> distinct agreements)
  * the workflow DEFINITION key    (must be the SHARED tpl:T -> reuse is correct)
  * the resolved INSTANCE          (subject_ref + definition_key + id -> per agreement)
and whether creating the 2nd site is BLOCKED. Then proves each agreement reopens to
its OWN instance. Cleans up everything it creates (sites, agreements, instances, def).
"""
import asyncio
import sys
from uuid import UUID

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Site, StudySite, SiteProfile  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

STUDY_ID = "f29f2acc-f534-4e6d-af5b-3860930b9cc1"          # MK-6482
TEMPLATE_ID = "0ebcd210-07bf-4972-bd4b-f56d3c22e26a"       # E2E Unified template
KEY = f"tpl:{TEMPLATE_ID}"
SITES = [("ZZ-INV-X", "ZZ Investigate Site X"), ("ZZ-INV-Y", "ZZ Investigate Site Y")]
EMAIL = "labesh@dizzaroo.com"
LEFTOVER = "8355c149-a943-4d93-a7a3-94bd0afa94d6"          # stray from the prior aborted run


def chain_body():
    return {"key": KEY, "name": "E2E Unified — all modules", "start_step": "draft", "context_schema": [],
            "steps": [
                {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
                 "transitions": [{"id": "submit", "to": "end", "label": "Done", "action": "submit"}]},
                {"id": "end", "type": "terminal", "name": "Done", "transitions": []}]}


async def _purge_agreement(db, aid):
    for t in ("agreement_internal_signatures", "agreement_signed_documents", "agreement_signing_otps",
              "agreement_signing_tokens", "agreement_review_otps", "agreement_review_tokens",
              "agreement_documents", "agreement_comments", "agreement_changes"):
        await db.execute(text(f"DELETE FROM {t} WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})


async def main():
    print("flags:", {"unified": settings.workflow_unified, "drives_cda": settings.workflow_drives_cda,
                     "drives_cta": settings.workflow_drives_cta})
    from app.modules.agreements.routes.crud import create_agreement
    from app.schemas import agreement as A

    created = []  # (label, aid)
    site_ids = []
    async with AsyncSessionLocal() as db:
        # 0) remove the stray agreement from the aborted run
        await _purge_agreement(db, LEFTOVER)
        await db.commit()

        # 1) publish the shared tpl:T definition (idempotent enough for a probe)
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(chain_body()),
                                                 publish=True, published_by="investigate")

        # 2) two fresh empty sites under the same study, each with a profile
        for code, name in SITES:
            row = (await db.execute(text("SELECT id FROM sites WHERE site_id=:c"), {"c": code})).fetchone()
            if row:
                sid = row[0]
            else:
                s = Site(site_id=code, name=name, status="active"); db.add(s); await db.flush(); sid = s.id
            site_ids.append(sid)
            ss = (await db.execute(text("SELECT id FROM study_sites WHERE study_id=:s AND site_id=:si"),
                                   {"s": STUDY_ID, "si": str(sid)})).fetchone()
            if not ss:
                db.add(StudySite(study_id=STUDY_ID, site_id=sid)); await db.flush()
            if not (await db.execute(text("SELECT id FROM site_profiles WHERE site_id=:si"), {"si": str(sid)})).fetchone():
                db.add(SiteProfile(site_id=sid, authorized_signatory_name="Signer", authorized_signatory_email=EMAIL,
                                   pi_name="PI", pi_email=EMAIL, site_name=name))
            await db.commit()

        # 3) create an agreement on template T at EACH site, ensure its instance
        for (code, name), sid in zip(SITES, site_ids):
            print("\n" + "=" * 84); print(f"{name}  (site={sid})")
            try:
                res = await create_agreement(
                    site_id=str(sid),
                    agreement_data=A.AgreementCreate(title=f"INV {code}", status="DRAFT", template_id=UUID(TEMPLATE_ID)),
                    study_id=UUID(STUDY_ID), current_user={"user_id": "investigator", "email": EMAIL}, db=db)
                aid = str(getattr(res, "id", None) or res.get("id"))
                ssid = (await db.execute(text("SELECT study_site_id FROM agreements WHERE id=:a"), {"a": aid})).scalar()
                print(f"  CREATE: OK  agreement_id={aid}  study_site_id={ssid}")
                created.append((name, aid))
            except HTTPException as e:
                print(f"  CREATE: BLOCKED -> HTTP {e.status_code}: {e.detail}")
                continue
            async with transactional(db):
                inst = await wf.ensure_instance(db, KEY, aid, {"agreement_id": aid, "template_id": TEMPLATE_ID})
            print(f"  DEFINITION KEY (shared blueprint) : {KEY}")
            print(f"  INSTANCE (per agreement)          : id={inst.id} subject_ref={inst.subject_ref} key={inst.definition_key} step={inst.current_step}")

        # 4) independence: reopen each agreement -> its OWN instance
        print("\n" + "=" * 84); print("INDEPENDENCE (reopen each site's agreement):")
        ids = []
        for label, aid in created:
            inst = await wf.find_instance_by_subject(db, aid)
            ids.append(inst.id if inst else None)
            print(f"  {label}: agreement {aid} -> instance {inst.id if inst else None}")
        ok = len(set(ids)) == len(ids) == len(SITES) and all(i is not None for i in ids) and len(created) == len(SITES)
        print(f"\n  RESULT: {'PASS — two sites, two distinct per-agreement instances, neither blocked' if ok else 'FAIL'}")

        # 5) cleanup everything created
        print("\ncleanup…")
        for _l, aid in created:
            await _purge_agreement(db, aid)
        await db.commit()
        d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
        if d:
            await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
            await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
        for sid in site_ids:
            await db.execute(text("DELETE FROM site_profiles WHERE site_id=:si"), {"si": str(sid)})
            await db.execute(text("DELETE FROM study_sites WHERE site_id=:si"), {"si": str(sid)})
            await db.execute(text("DELETE FROM sites WHERE id=:si"), {"si": str(sid)})
        await db.commit()
        print("done.")


if __name__ == "__main__":
    asyncio.run(main())
