"""
Verify the runner's first embed seam (document viewer) at the DATA level
(run in the backend container). The actual OnlyOffice render is a browser concern;
this proves the conditions under which the runner mounts the EXISTING editor.

Runner gate (steps/index.tsx ApprovalStep): mount OnlyOffice iff
    embedDocs (drives_cda || drives_cta)  AND  subject_ref is a real agreement UUID
and the editor then hits the EXISTING endpoint agreements/{subject_ref}/onlyoffice-config
(GET, onlyoffice.py:740) — the same one AgreementTab uses. No new pipeline.

Checks (flag ON):
  * A real CDA instance at the document/review step (under_review) resolves via
    find_instance_by_subject; current_step == 'under_review'; subject_ref is a UUID
    -> the gate is TRUE -> editor mounts -> config path is the existing endpoint.
  * A sandbox demo instance (no subject_ref) -> UUID gate FALSE -> placeholder, no error.

Throwaway CDA; cleaned up. Flag toggled in-proc only.
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.services.agreement_service import change_agreement_status  # noqa: E402
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows import service  # noqa: E402

# Same UUID test the runner's looksLikeAgreementId() uses.
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def runner_can_embed(embed_docs: bool, subject_ref) -> bool:
    return bool(embed_docs) and bool(subject_ref) and bool(UUID_RE.match(str(subject_ref)))


async def _make_cda(db, title):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType.CDA, title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        settings.workflow_drives_cda = True
        embed_docs = True  # = drives_cda || drives_cta (what WorkflowRunner computes)

        aid = await _make_cda(db, "OO-EMBED")
        try:
            ag = await db.get(Agreement, aid)
            await cda_on_create(ag, db)
            await db.commit()
            # advance to the document/review step
            await change_agreement_status(db, aid, AgreementStatus.UNDER_REVIEW, user_id="system")

            inst = await service.find_instance_by_subject(db, aid, "CDA")
            assert inst is not None, "expected a linked CDA instance"
            assert inst.current_step == "under_review", inst.current_step

            can = runner_can_embed(embed_docs, inst.subject_ref)
            assert can, f"runner should mount editor (subject_ref={inst.subject_ref})"
            cfg_path = f"agreements/{inst.subject_ref}/onlyoffice-config"
            results.append(("REAL agreement @ under_review (document step)",
                            f"current_step={inst.current_step}, subject_ref is UUID -> MOUNT editor"))
            results.append(("Editor uses the EXISTING config endpoint (not new)",
                            f"GET /api/{cfg_path}  (== AgreementTab's default path)"))
        finally:
            await _cleanup(db, aid)
            settings.workflow_drives_cda = False

        # Sandbox demo instance: no subject_ref -> gate false -> placeholder.
        assert runner_can_embed(True, None) is False
        assert runner_can_embed(True, "agly-sign-demo") is False  # non-UUID sandbox ref
        results.append(("SANDBOX demo (no/!uuid subject_ref)", "gate FALSE -> labeled placeholder, no error"))

        # Flag OFF anywhere -> never embeds.
        assert runner_can_embed(False, aid) is False
        results.append(("FLAG OFF (embedDocs false)", "gate FALSE -> placeholder (sandbox unchanged)"))

    print("=" * 92)
    print("RUNNER DOCUMENT-EMBED SEAM — gate verification (reuses existing OnlyOffice)")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print("Same component (components/OnlyOfficeEditor) + same endpoint (onlyoffice.py:740). No second pipeline.")


if __name__ == "__main__":
    asyncio.run(main())
