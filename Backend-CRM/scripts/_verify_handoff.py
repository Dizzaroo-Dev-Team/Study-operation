"""CHECK 3 — #8 signing auto-handoff (end-to-end against the real DB).

For each scenario: create an agreement, publish an ordered_signing workflow (2 signer
slots), start the instance, dispatch (mints a token for slot 1 only), then SIGN slot 1
via the real unified_signing._advance_engine_slot (the exact function record_signature
calls on a completed signature). Then check whether a token for slot 2 was AUTO-minted.

  - DEFAULT handoff (no config.handoff)  -> EXPECT slot-2 token auto-minted (auto-handoff).
  - config.handoff="owner_gated"         -> EXPECT NO slot-2 token (opt-out still works).

FIDELITY: this drives the real engine advance + the real unified_signing dispatch (which
mints the AgreementSigningToken AND calls enqueue_email for the next signer). It bypasses
ONLY the PDF-stamping inside record_signature (independent of hand-off). "An email
actually arrived" needs a real SMTP/inbox; what we prove here is the next signer's token
+ secure link are auto-created and the send is invoked with NO manual action.
"""
import asyncio
import uuid

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import (
    Study, Site, StudySite, Agreement, AgreementStatus, TemplateType, AgreementSigningToken,
)
from app.models.agreement import AgreementSignatureSource
from app.modules.workflows import service
from app.modules.workflows.schemas import WorkflowDefinitionBody, CurrentUser
from app.modules.agreements.services import unified_signing

MARK = "HANDOFFTEST"


def signing_def(key, handoff=None):
    cfg = {"signers": [{"id": "s1", "name": "Signer One"}, {"id": "s2", "name": "Signer Two"}]}
    if handoff:
        cfg["handoff"] = handoff
    return {
        "key": key, "name": "Handoff verify", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "admin"},
             "transitions": [{"id": "submit", "to": "signing", "label": "Send", "action": "submit"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signatures", "config": cfg,
             "transitions": [
                 {"id": "done", "to": "end", "label": "All signed", "action": "all_signed"},
                 {"id": "declined", "to": "rej", "label": "Declined", "action": "signing_declined"}]},
            {"id": "end", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rej", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }


async def _make_agreement(db):
    study = Study(id=uuid.uuid4(), study_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} study")
    site = Site(id=uuid.uuid4(), site_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} site")
    db.add_all([study, site]); await db.flush()
    ss = StudySite(id=uuid.uuid4(), study_id=study.id, site_id=site.id)
    db.add(ss); await db.flush()
    ag = Agreement(id=uuid.uuid4(), site_id=site.id, study_id=study.id, study_site_id=ss.id,
                   title=f"{MARK} agreement", status=AgreementStatus.SENT_FOR_SIGNATURE,
                   is_legacy="false", signature_source=AgreementSignatureSource.INTERNAL,
                   agreement_type=TemplateType.CTA, created_by="handoff-tester")
    db.add(ag); await db.flush()
    return ag


async def _active_token_roles(db, agreement_id):
    rows = (await db.execute(
        select(AgreementSigningToken.role)
        .where(AgreementSigningToken.agreement_id == agreement_id)
        .where(AgreementSigningToken.is_active == "true")
    )).scalars().all()
    return sorted(rows)


async def scenario(db, handoff_label, handoff_cfg):
    ag = await _make_agreement(db)
    key = f"{MARK}_{(handoff_cfg or 'default')}_{uuid.uuid4().hex[:6]}"
    body = WorkflowDefinitionBody.model_validate(signing_def(key, handoff_cfg))
    await service.create_or_update_definition(db, body, publish=True, published_by=MARK)
    inst = await service.start_instance(db, key, {}, subject_ref=str(ag.id))
    await db.flush()
    # draft -> signing
    await service.perform_action(db, inst.id, CurrentUser(id="handoff-tester", roles=["admin"]),
                                 "submit", {}, None)
    await db.flush()
    # dispatch BOTH emails (ordered: only s1 opens + gets a token; both emails kept in ctx)
    await unified_signing.dispatch(db, ag, {"s1": "s1@test.local", "s2": "s2@test.local"},
                                   created_by="handoff-tester")
    await db.flush()
    before = await _active_token_roles(db, ag.id)
    # SIGN slot 1 via the real advance path (what record_signature calls on completion)
    await unified_signing._advance_engine_slot(db, ag, "s1", "s1@test.local")
    await db.flush()
    after = await _active_token_roles(db, ag.id)
    await db.commit()
    print(f"\n----- {handoff_label} (agreement={ag.id}) -----")
    print(f"  active signing-token roles AFTER dispatch (before signing s1): {before}")
    print(f"  active signing-token roles AFTER signing s1:                    {after}")
    s2_auto = "s2" in after and "s2" not in before
    print(f"  -> slot-2 token auto-minted on s1 signature? {s2_auto}")
    return s2_auto


async def main():
    async with AsyncSessionLocal() as db:
        print("================ #8 AUTO-HANDOFF ================")
        auto = await scenario(db, "DEFAULT handoff (expect AUTO-advance: s2 token minted)", None)
        gated = await scenario(db, "owner_gated handoff (expect NO auto-advance)", "owner_gated")
        print("\n================ VERDICT ================")
        print(f"  default -> s2 auto-dispatched: {auto}   (EXPECT True)")
        print(f"  owner_gated -> s2 auto-dispatched: {gated}   (EXPECT False)")


if __name__ == "__main__":
    asyncio.run(main())
