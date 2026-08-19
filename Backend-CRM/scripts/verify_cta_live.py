"""
LIVE verification for WORKFLOW_DRIVES_CTA (run in the backend container).

CTA routes every status change through change_agreement_status (the funnel) — no
direct status writes — so the funnel-mirror covers CTA signing too (no OTP-bypass
edit needed). This walks a throwaway CTA through the REAL funnel for flag ON/OFF,
and proves the ordered-signing slot-by-slot advancement + CRO branch against the
REAL CTA_V2 definition via the pure engine.

DISCOVERED PRE-EXISTING CONSTRAINT (not modified — shared, affects all types):
  change_agreement_status has a lock that only permits SENT_FOR_SIGNATURE ->
  EXECUTED (it raises on SENT_FOR_SIGNATURE -> AWAITING_SPONSOR_SIGNATURE). So the
  funnel-reachable completion is SENT_FOR_SIGNATURE -> EXECUTED; the bridge records
  all signing slots (director, pi, vp) at EXECUTED. The AWAITING_SPONSOR phase is
  blocked by that lock for everyone (CTA's own route 1308 would raise it too).

Stubbed edges: none here — we drive the real funnel directly (the convergence
point of every CTA endpoint). The CTA endpoints' own AI-placeholder-fill / OTP /
OnlyOffice side-effects are unchanged & reused; they are not re-invoked in this
script (that would require live Gemini/OnlyOffice/SMTP + template fixtures).
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementComment, AgreementStatus, TemplateType  # noqa: E402
from app.modules.workflows.models import WorkflowAuditEntry, WorkflowInstance  # noqa: E402
from app.modules.agreements.services.agreement_service import change_agreement_status  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.types.cta.service import cta_on_create  # noqa: E402
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows.engine import WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402
from app.modules.workflows.cta_bridge import CTA_V2_BODY  # noqa: E402


def U(uid="u"):
    return CurrentUser(id=uid, roles=[])


async def _instance(db, aid, key="CTA"):
    return await db.scalar(
        select(WorkflowInstance).where(WorkflowInstance.subject_ref == str(aid))
        .where(WorkflowInstance.definition_key == key).order_by(WorkflowInstance.id.desc()))


async def _make(db, atype, title):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type=:t AND study_site_id IS NOT NULL) LIMIT 1"
    ), {"t": atype})).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType(atype), title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush(); await db.commit()
    return ag


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": str(aid)})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": str(aid)})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": str(aid)})
    await db.commit()


def _line(stage, status, step, extra=""):
    print(f"  {stage:<26} status={status:<24} engine={str(step):<16} {extra}")


# Funnel path that the shared lock permits (SENT -> EXECUTED).
FUNNEL_PATH = [
    (AgreementStatus.AWAITING_INTERNAL_REVIEW, "internal_review"),
    (AgreementStatus.INTERNAL_REVIEW_APPROVED, "internal_approved"),
    (AgreementStatus.SENT_FOR_SIGNATURE, "signing"),
    (AgreementStatus.EXECUTED, "executed"),
]


async def walk_funnel(flag_on: bool):
    settings.workflow_drives_cta = flag_on
    settings.workflow_drives_cda = False  # CDA flag stays OFF throughout
    label = "ON" if flag_on else "OFF"
    print(f"\n========== CTA FUNNEL WALK — FLAG {label} ==========")
    async with AsyncSessionLocal() as db:
        ag = await _make(db, "CTA", f"VERIFY-CTA-{label}")
        aid = ag.id
        try:
            await cta_on_create(ag, db); await db.commit()
            inst = await _instance(db, aid)
            _line("create", ag.status.value, inst.current_step if inst else "(none)")
            assert (inst and inst.current_step == "draft") if flag_on else (inst is None)

            for st, step in FUNNEL_PATH:
                await change_agreement_status(db, str(aid), st, "verify")
                fresh = await db.get(Agreement, aid)
                inst = await _instance(db, aid)
                _line(st.value, fresh.status.value, inst.current_step if inst else "(none)")
                assert fresh.status == st
                assert (inst.current_step == step) if flag_on else (inst is None)

            if flag_on:
                slots = (inst.context or {}).get("_branches", {}).get("signing", {})
                _line("signing slots @EXECUTED", "-", "-",
                      f"{ {k: v['decision'] for k, v in slots.items()} }")
                assert {k: v["decision"] for k, v in slots.items()} == \
                    {"director": "signed", "pi": "signed", "vp": "signed"}
                audit = (await db.execute(select(WorkflowAuditEntry)
                         .where(WorkflowAuditEntry.instance_id == inst.id)
                         .order_by(WorkflowAuditEntry.id))).scalars().all()
                print("  --- engine audit trail ---")
                for a in audit:
                    b = f" [{a.payload.get('branch_id')}]" if a.payload.get("branch_id") else ""
                    print(f"      {a.action:<14}{b:<12} {str(a.from_step):<18} -> {a.to_step}")
                assert any(a.action == "started" for a in audit)
                assert sum(1 for a in audit if a.action == "signed") == 3
            comments = (await db.execute(select(AgreementComment)
                        .where(AgreementComment.agreement_id == aid))).scalars().all()
            print(f"  funnel SYSTEM comments (existing service fired): {len(comments)}")
            print(f"  RESULT FLAG {label}: " + (
                "engine mirrored every funnel phase; slots director,pi,vp signed -> EXECUTED; audit OK"
                if flag_on else "REAL funnel ran; NO instance; status identical to today"))
        finally:
            await _cleanup(db, aid)


async def cda_unaffected():
    """With CTA flag ON and CDA flag OFF, a CDA agreement gets NO instance."""
    settings.workflow_drives_cta = True
    settings.workflow_drives_cda = False
    print("\n========== CDA UNAFFECTED (CTA flag on, CDA flag off) ==========")
    async with AsyncSessionLocal() as db:
        ag = await _make(db, "CDA", "VERIFY-CDA-UNAFFECTED")
        aid = ag.id
        try:
            await cda_on_create(ag, db); await db.commit()
            inst = await _instance(db, aid, key="CDA")
            await change_agreement_status(db, str(aid), AgreementStatus.UNDER_REVIEW, "verify")
            inst2 = await _instance(db, aid, key="CDA")
            _line("CDA create+review", "UNDER_REVIEW", "(none)" if not inst2 else inst2.current_step)
            assert inst is None and inst2 is None, "CDA must not be driven when only CTA flag is on"
            print("  RESULT: CDA unaffected — no instance, behaves as today")
        finally:
            await _cleanup(db, aid)


def engine_proofs():
    """Pure-engine proofs against the REAL CTA_V2 definition."""
    print("\n========== ENGINE PROOFS (real CTA_V2 definition) ==========")
    body = WorkflowDefinitionBody.model_validate(CTA_V2_BODY)
    eng = WorkflowEngine(body, enforce_roles=False)

    # CRO branch — has_cro True -> cro_review ; False -> skip to internal_approved
    def to_after_review(has_cro):
        r = eng.start({"has_cro": has_cro})
        r = eng.perform("draft", "submit", r.context, U())
        r = eng.perform("internal_review", "legal:approve", r.context, U())
        return eng.perform("internal_review", "financial:approve", r.context, U())
    r_t = to_after_review(True)
    r_f = to_after_review(False)
    print(f"  CRO branch: has_cro=True -> {r_t.step_id} ; has_cro=False -> {r_f.step_id}")
    assert r_t.step_id == "cro_review" and r_f.step_id == "internal_approved"

    # Ordered signing — only the current slot is offered; director -> pi -> vp
    r = eng.perform("cro_review", "cro_legal:approve", r_t.context, U())
    r = eng.perform("cro_review", "cro_financial:approve", r.context, U())   # -> internal_approved
    r = eng.perform("internal_approved", "send", r.context, U())            # -> signing
    offered = {a.transition_id.rsplit(":", 1)[0] for a in eng.available_actions("signing", r.context, U())}
    assert offered == {"director"}, offered
    r = eng.perform("signing", "director:sign", r.context, U())
    assert {a.transition_id.rsplit(":", 1)[0] for a in eng.available_actions("signing", r.context, U())} == {"pi"}
    r = eng.perform("signing", "pi:sign", r.context, U())
    assert {a.transition_id.rsplit(":", 1)[0] for a in eng.available_actions("signing", r.context, U())} == {"vp"}
    r = eng.perform("signing", "vp:sign", r.context, U())                   # all_signed -> executed
    print(f"  ordered signing director->pi->vp -> {r.step_id}")
    assert r.step_id == "executed"
    print("  RESULT: CRO branch + ordered signing (Director->PI->VP) proven on CTA_V2")


async def main():
    await walk_funnel(flag_on=True)
    await walk_funnel(flag_on=False)
    await cda_unaffected()
    engine_proofs()
    print("\nCTA VERIFICATION COMPLETE — all assertions passed.")


if __name__ == "__main__":
    asyncio.run(main())
