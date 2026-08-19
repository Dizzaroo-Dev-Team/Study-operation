"""
Verify the dev reset buttons:

  * reset_agreement  (study+site SPECIFIC — the agreement-screen button): deletes ONE
    agreement + its workflow instance(s) + children, and KEEPS the shared template
    definition AND every OTHER site's agreement/instance.
  * reset_definition (template-level — the bind-view "redefine"): deletes the shared
    definition + all versions/instances, and does NOT delete agreements.

Also confirms both gates (403 when WORKFLOW_UNIFIED off). Self-contained throwaway
data on free study_sites; touches no real agreements; cleans up.
"""
import asyncio
import sys
import tempfile

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import bindparam, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import (  # noqa: E402
    Agreement, AgreementStatus, AgreementDocument, AgreementComment, CommentType, TemplateType,
)
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import AgreementResetRequest, ResetRequest, WorkflowDefinitionBody  # noqa: E402
from app.modules.workflows.router import (  # noqa: E402
    reset_agreement as reset_agreement_route, reset_definition as reset_definition_route,
)

KEY = "tpl:zz-reset-test-0000"


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def body():
    return {"key": KEY, "name": "Reset test", "start_step": "a", "context_schema": [],
            "steps": [
                {"id": "a", "type": "form", "name": "A",
                 "transitions": [{"id": "go", "to": "end", "label": "Go", "action": "submit"}]},
                {"id": "end", "type": "terminal", "name": "End", "transitions": []}]}


def _in(tbl, col):
    return text(f"SELECT count(*) FROM {tbl} WHERE {col}::text IN :ids").bindparams(bindparam("ids", expanding=True))


async def ag_state(db, aid):
    return {
        "agreement": (await db.execute(_in("agreements", "id"), {"ids": [aid]})).scalar(),
        "documents": (await db.execute(_in("agreement_documents", "agreement_id"), {"ids": [aid]})).scalar(),
        "comments": (await db.execute(_in("agreement_comments", "agreement_id"), {"ids": [aid]})).scalar(),
        "instances": (await db.execute(text("SELECT count(*) FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})).scalar(),
    }


async def def_state(db):
    return {
        "definitions": (await db.execute(text("SELECT count(*) FROM workflow_definitions WHERE key=:k"), {"k": KEY})).scalar(),
        "instances_on_key": (await db.execute(text("SELECT count(*) FROM workflow_instances WHERE definition_key=:k"), {"k": KEY})).scalar(),
    }


async def make_agreement(db, ss_row, template_id):
    ag = Agreement(site_id=ss_row[2], study_id=ss_row[1], study_site_id=ss_row[0], agreement_type=TemplateType.CDA,
                   title="ZZ-RESET", status=AgreementStatus.DRAFT, is_legacy="false", created_by="t")
    db.add(ag); await db.flush()
    db.add(AgreementDocument(agreement_id=ag.id, version_number=1,
                             document_file_path=await asyncio.to_thread(_tmpfile, ".docx"),
                             created_from_template_id=template_id, created_by="t", is_signed_version="false"))
    db.add(AgreementComment(agreement_id=ag.id, comment_type=CommentType.SYSTEM, content="seed", created_by=None))
    aid = str(ag.id); await db.commit()
    async with transactional(db):
        await wf.start_instance(db, KEY, {"agreement_id": aid}, subject_ref=aid)
    return aid


async def main():
    settings.workflow_unified = True
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            await wf.reset_definition(db, KEY)  # pre-clean leftover

        study_id = (await db.execute(text("SELECT id FROM studies LIMIT 1"))).scalar()
        from app.models import StudyTemplate
        tmpl = StudyTemplate(study_id=study_id, template_name="ZZ Reset Test Template",
                             template_type=TemplateType.CDA,
                             template_file_path=await asyncio.to_thread(_tmpfile, ".docx"),
                             is_active="true")
        db.add(tmpl); await db.flush(); template_id = tmpl.id; await db.commit()

        ss = (await db.execute(text(
            "SELECT id,study_id,site_id FROM study_sites WHERE id NOT IN "
            "(SELECT study_site_id FROM agreements WHERE study_site_id IS NOT NULL) LIMIT 2"))).fetchall()
        assert len(ss) >= 2, "need 2 free study_sites"
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(body()), publish=True, published_by="t")
        site_x = await make_agreement(db, ss[0], template_id)   # the one we reset
        site_y = await make_agreement(db, ss[1], template_id)   # must survive
        print("seeded  X:", await ag_state(db, site_x), " Y:", await ag_state(db, site_y), " def:", await def_state(db))

        # ── GATE: per-agreement reset 403 when flag off ──
        settings.workflow_unified = False
        try:
            await reset_agreement_route(AgreementResetRequest(subject_ref=site_x), db=db)
            raise AssertionError("expected 403")
        except HTTPException as e:
            assert e.status_code == 403
        print("PASS gate: reset-agreement 403 when flag off")
        settings.workflow_unified = True

        # ── PER-AGREEMENT (study+site) RESET of Site X ──
        result = await reset_agreement_route(AgreementResetRequest(subject_ref=site_x), db=db)
        print("reset-agreement returned:", result)
        x_after = await ag_state(db, site_x)
        y_after = await ag_state(db, site_y)
        d_after = await def_state(db)
        print("after  X:", x_after, " Y:", y_after, " def:", d_after)
        assert x_after == {"agreement": 0, "documents": 0, "comments": 0, "instances": 0}, x_after
        assert y_after == {"agreement": 1, "documents": 1, "comments": 1, "instances": 1}, ("Site Y must survive", y_after)
        assert d_after["definitions"] == 1 and d_after["instances_on_key"] == 1, ("definition + Y instance kept", d_after)
        assert result["agreements_deleted"] == 1 and result["instances_deleted"] == 1
        tmpl_alive = (await db.execute(text("SELECT count(*) FROM study_templates WHERE id=:t"), {"t": str(template_id)})).scalar()
        assert tmpl_alive == 1
        print("PASS per-agreement reset: Site X gone; Site Y + shared definition + template ALL kept")

        # ── TEMPLATE-LEVEL reset (redefine): removes def + remaining instance, keeps agreement ──
        result2 = await reset_definition_route(ResetRequest(key=KEY), db=db)
        print("reset-definition returned:", result2)
        assert (await def_state(db)) == {"definitions": 0, "instances_on_key": 0}
        y_after2 = await ag_state(db, site_y)
        assert y_after2["agreement"] == 1 and y_after2["instances"] == 0, ("definition reset keeps agreement, drops instance", y_after2)
        print("PASS template reset: definition + instances gone; agreement NOT deleted")

        # cleanup
        await wf.reset_definition(db, KEY)  # no-op (already gone)
        from app.modules.workflows.service import _delete_agreements, _existing_agreement_ids
        async with transactional(db):
            await _delete_agreements(db, await _existing_agreement_ids(db, [site_x, site_y]))
            await db.execute(text("DELETE FROM study_templates WHERE id=:t"), {"t": str(template_id)})

    print("\nRESET: per-agreement (study+site specific) + template-level both verified")


if __name__ == "__main__":
    asyncio.run(main())
