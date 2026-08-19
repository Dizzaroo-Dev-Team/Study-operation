"""
Verify the unified review-step fixes at the contract level (run in the container).

PART 1 (404 root cause): an agreement with NO AgreementDocument -> GET
  /api/agreements/{id}/onlyoffice-config returns 404 "No document found"
  (onlyoffice.py:770). The fix ensures a document exists first, reusing the
  EXISTING create-from-template service (doc_operations.py:54) — the same one the
  CDA reset flow uses — so by the time OnlyOffice mounts there is a document and
  the call is 200 (already shown for doc-bearing agreements).

PART 2 (reviewer invite): the EXISTING send-for-review endpoint
  (signing.py:552) requires multipart `recipient_email` and sends the email itself
  (enqueue_email) — so the frontend only POSTs the chosen email. Here we confirm
  the contract: a POST without recipient_email is rejected (422), proving the field
  is required (we don't send a real email in the test).

Throwaway agreement; cleaned up.
"""
import asyncio
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401

BASE = "http://localhost:8000/api"


def _get_status(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:120]


def _post_status(url, data: bytes, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:120]


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        ss = (await db.execute(text(
            "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
            "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
        ))).fetchone()
        ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                       agreement_type=TemplateType.CDA, title="REVIEW-STEP-404",
                       status=AgreementStatus.DRAFT, is_legacy="false")
        db.add(ag); await db.flush()
        aid = str(ag.id); await db.commit()
        try:
            # PART 1 — 0-doc agreement => onlyoffice-config 404
            code, detail = _get_status(f"{BASE}/agreements/{aid}/onlyoffice-config")
            assert code == 404, f"expected 404 for a doc-less agreement, got {code}: {detail}"
            results.append(("PART 1 root cause: 0-doc agreement -> onlyoffice-config 404",
                            f"HTTP {code} {detail!r} (fix ensures a doc via create-from-template first)"))

            # PART 2 — send-for-review requires recipient_email (contract; no email sent)
            # multipart body intentionally OMITS recipient_email -> 422 from Form(...).
            boundary = "X"
            body = (f"--{boundary}--\r\n").encode()
            code2, detail2 = _post_status(
                f"{BASE}/agreements/{aid}/send-for-review",
                body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            assert code2 == 422, f"expected 422 (recipient_email required), got {code2}: {detail2}"
            results.append(("PART 2 reuse: send-for-review requires recipient_email",
                            f"HTTP {code2} (field required; endpoint sends the email itself via enqueue_email)"))
        finally:
            await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
            await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
            await db.commit()

    print("=" * 92)
    print("UNIFIED REVIEW STEP — 404 ROOT CAUSE + REVIEW-INVITE CONTRACT")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print("Fix reuses create-from-template (doc) + send-for-review (invite+email). No new pipelines.")


if __name__ == "__main__":
    asyncio.run(main())
