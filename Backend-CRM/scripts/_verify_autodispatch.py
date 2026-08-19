"""Verify DocuSign-style auto-dispatch: signer contacts resolved UP FRONT from role
assignees (reusing placeholder DB resolution), then auto-sent with NO manual email.

Scenario: ordered_signing [pi -> site_director], handoff defaults to auto. A SiteProfile
holds pi_email + authorized_signatory_email. We dispatch with NO recipients (so the only
way a token gets minted is via up-front resolution), check slot 1 (pi) was emailed to the
resolved PI address, then SIGN slot 1 and confirm slot 2 (site_director) is auto-dispatched
to the resolved authorized-signatory address. Tokens carry the recipient_email, which is
the real signal the resolution + auto-send worked (delivery itself needs a real inbox).
"""
import asyncio
import uuid

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import (
    Study, Site, StudySite, Agreement, AgreementStatus, TemplateType, AgreementSigningToken,
)
from app.models.agreement import AgreementSignatureSource
from app.models.site_status import SiteProfile
from app.modules.workflows import service
from app.modules.workflows.schemas import WorkflowDefinitionBody, CurrentUser
from app.modules.agreements.services import unified_signing

MARK = "AUTODISPATCH"
PI_EMAIL = "pi.resolved@site.test"
DIRECTOR_EMAIL = "director.resolved@site.test"


def signing_def(key):
    return {
        "key": key, "name": "Auto-dispatch verify", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "admin"},
             "transitions": [{"id": "submit", "to": "signing", "label": "Send", "action": "submit"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signatures",
             "config": {"signers": [
                 {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "pi"}},
                 {"id": "site_director", "name": "Site Director",
                  "assignee": {"type": "role", "value": "site_director"}}]},
             "transitions": [
                 {"id": "done", "to": "end", "label": "All signed", "action": "all_signed"},
                 {"id": "dec", "to": "rej", "label": "Declined", "action": "signing_declined"}]},
            {"id": "end", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rej", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }


async def _tokens(db, agreement_id):
    rows = (await db.execute(
        select(AgreementSigningToken.role, AgreementSigningToken.recipient_email)
        .where(AgreementSigningToken.agreement_id == agreement_id)
        .where(AgreementSigningToken.is_active == "true")
    )).all()
    return {r[0]: r[1] for r in rows}


async def main():
    async with AsyncSessionLocal() as db:
        study = Study(id=uuid.uuid4(), study_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} study")
        site = Site(id=uuid.uuid4(), site_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} site")
        db.add_all([study, site]); await db.flush()
        ss = StudySite(id=uuid.uuid4(), study_id=study.id, site_id=site.id)
        db.add(ss); await db.flush()
        # SOURCE of the resolved contacts (the SAME fields placeholder auto-fill uses)
        db.add(SiteProfile(id=uuid.uuid4(), site_id=site.id,
                           pi_email=PI_EMAIL, authorized_signatory_email=DIRECTOR_EMAIL))
        ag = Agreement(id=uuid.uuid4(), site_id=site.id, study_id=study.id, study_site_id=ss.id,
                       title=f"{MARK} agreement", status=AgreementStatus.SENT_FOR_SIGNATURE,
                       is_legacy="false", signature_source=AgreementSignatureSource.INTERNAL,
                       agreement_type=TemplateType.CTA, created_by="auto-tester")
        db.add(ag); await db.flush()

        key = f"{MARK}_{uuid.uuid4().hex[:6]}"
        body = WorkflowDefinitionBody.model_validate(signing_def(key))
        await service.create_or_update_definition(db, body, publish=True, published_by=MARK)
        inst = await service.start_instance(db, key, {}, subject_ref=str(ag.id))
        await db.flush()
        await service.perform_action(db, inst.id, CurrentUser(id="auto-tester", roles=["admin"]),
                                     "submit", {}, None)
        await db.flush()

        # AUTO-DISPATCH with NO recipients -> contacts must resolve from role assignees.
        await unified_signing.dispatch(db, ag, {}, created_by="system:auto-dispatch")
        await db.flush()
        after_dispatch = await _tokens(db, ag.id)

        # SIGN slot 1 (pi) -> engine advances -> slot 2 (site_director) auto-dispatched.
        await unified_signing._advance_engine_slot(db, ag, "pi", PI_EMAIL)
        await db.flush()
        after_sign = await _tokens(db, ag.id)
        await db.commit()

        print("\n================ AUTO-DISPATCH (up-front contact resolution) ================")
        print(f"  SiteProfile pi_email={PI_EMAIL}  authorized_signatory_email={DIRECTOR_EMAIL}")
        print(f"  active tokens AFTER dispatch (no recipients given): {after_dispatch}")
        print(f"  active tokens AFTER signing slot 1 (pi):            {after_sign}")
        print("\n================ VERDICT ================")
        ok1 = after_dispatch.get("pi") == PI_EMAIL
        ok2 = "site_director" not in after_dispatch
        ok3 = after_sign.get("site_director") == DIRECTOR_EMAIL
        print(f"  slot 1 (pi) auto-emailed to RESOLVED pi address:            {ok1}  (EXPECT True)")
        print(f"  slot 2 NOT sent before slot 1 signs:                        {ok2}  (EXPECT True)")
        print(f"  slot 2 (site_director) AUTO-dispatched to RESOLVED address: {ok3}  (EXPECT True)")


if __name__ == "__main__":
    asyncio.run(main())
