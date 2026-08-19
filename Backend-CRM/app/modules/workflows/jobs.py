"""
jobs.py
=======

V2 Phase 4: the JOB handler registry — the seam where automated steps meet the
real world. A JOB step's config names a `kind`; the executor
(service.run_pending_jobs) looks the handler up here, awaits it, and feeds the
outcome back through the kernel as JobCompleted / JobFailed.

A handler is `async def handler(params: dict, context: dict) -> dict` — the
returned dict is the job RESULT; only the step's explicit output mapping
decides what (if anything) lands in the instance context.

This is deliberately the extension point for:
  * real notifications (register a handler that calls the existing
    mailgun/smtp integrations),
  * AI-agent steps (a handler that calls app.integrations.ai — an agent step
    IS a job, with the same retry / error-transition semantics).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import aiofiles

logger = logging.getLogger(__name__)

JobHandler = Callable[[dict, dict], Awaitable[dict]]

_HANDLERS: dict[str, JobHandler] = {}


def register_job_handler(kind: str, handler: JobHandler) -> None:
    _HANDLERS[kind] = handler


def get_job_handler(kind: str) -> JobHandler | None:
    return _HANDLERS.get(kind)


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------
# Canonical kind names. The generator emits ONLY these; the normalizer maps any
# invented kind (e.g. "generate_pdf", "send_notification") to the closest one.
KIND_NOOP = "noop"
KIND_NOTIFY = "notify"
KIND_GENERATE_DOCUMENT = "generate_document"
KIND_APPEND_DOCUMENT = "append_document"


async def _noop(params: dict, context: dict) -> dict[str, Any]:
    """Pass-through: returns params['result'] (or {}). Useful for wiring, for
    test/demo workflows, and as the SAFE FALLBACK the executor uses for any kind
    that has no registered handler — so an authored job never dead-ends a flow."""
    logger.info("workflow noop job: completing harmlessly (params keys=%s)",
                sorted(list(params)[:8]))
    return dict(params.get("result") or {})


async def _generate_document(params: dict, context: dict) -> dict[str, Any]:
    """Generate a REAL PDF by reusing the existing generator
    (app.utils.pdf_generator.html_to_pdf — the same WeasyPrint→ReportLab path the
    CDA/agreement PDFs use). NOT a rebuild and NOT a stub.

    Content precedence: params['html'] > params['content']/['text'] wrapped in a
    minimal HTML shell > a title-only page. Writes to a temp documents dir and
    returns {generated, document_path, generator, title}. If the environment has
    NO PDF backend at all (no WeasyPrint AND no ReportLab) it records the intent
    (generated=False) and returns instead of raising — a missing native lib must
    not dead-end the workflow. The step's `output` mapping decides what (if
    anything) lands in context (e.g. {"document_url": "document_path"})."""
    import tempfile
    from pathlib import Path

    title = str(params.get("title") or params.get("template") or "Document")
    if params.get("html"):
        html = str(params["html"])
    else:
        body = str(params.get("content") or params.get("text") or "")
        html = (f"<html><head><meta charset='utf-8'><title>{title}</title></head>"
                f"<body><h1>{title}</h1><div>{body}</div></body></html>")

    out_dir = Path(tempfile.gettempdir()) / "workflow_documents"
    fname = (str(params.get("filename") or title).strip() or "document").replace(" ", "_")
    if not fname.lower().endswith(".pdf"):
        fname += ".pdf"
    out_path = out_dir / fname

    # Import + generate are BOTH guarded: app.utils.pdf_generator can raise OSError at
    # import on a host missing the WeasyPrint native libs (its own guard only catches
    # ImportError), and html_to_pdf can fail at runtime. Either way we degrade to
    # "recorded intent" (generated=False) and return — a missing native lib must never
    # dead-end the workflow. On a properly-configured host this writes a real PDF.
    try:
        from app.utils.pdf_generator import (
            REPORTLAB_AVAILABLE,
            WEASYPRINT_AVAILABLE,
            html_to_pdf,
        )
        if not (WEASYPRINT_AVAILABLE or REPORTLAB_AVAILABLE):
            logger.warning("workflow generate_document: no PDF backend available; "
                           "recording intent only (title=%r)", title)
            return {"generated": False, "document_path": None, "reason": "no PDF backend",
                    "title": title}
        path = html_to_pdf(html, out_path)
        generator = "weasyprint" if WEASYPRINT_AVAILABLE else "reportlab"
        logger.info("workflow generate_document: wrote %s via %s", path, generator)
        # Persist DURABLY where signing artifacts go (Azure Blob via the shared
        # document storage). When storage isn't configured (dev), the durable URL
        # falls back to the local path so downstream steps still get a usable
        # reference. document_url is what the step's output mapping lands in
        # context for the UI/downstream to link.
        document_url = str(path)
        try:
            from app.utils.azure_storage import get_document_storage
            storage = get_document_storage()
            if storage is not None:
                import uuid
                blob_name = f"workflow_documents/{uuid.uuid4().hex}_{fname}"
                async with aiofiles.open(path, "rb") as fh:
                    data = await fh.read()
                document_url = await storage.upload_file(
                    data, blob_name, content_type="application/pdf")
                logger.info("workflow generate_document: persisted durably at %s", blob_name)
        except Exception as up_exc:  # noqa: BLE001 — durable upload best-effort; local path remains
            logger.warning("workflow generate_document: durable upload failed (%s); "
                           "keeping local path", up_exc)
        return {"generated": True, "document_path": str(path),
                "document_url": document_url, "generator": generator, "title": title}
    except Exception as exc:  # noqa: BLE001 — import/runtime PDF failure: degrade, don't dead-end
        logger.warning("workflow generate_document: PDF backend unavailable or failed "
                       "(%s); recording intent (title=%r)", exc, title)
        return {"generated": False, "document_path": None, "document_url": None,
                "reason": str(exc), "title": title}


async def _notify(params: dict, context: dict) -> dict[str, Any]:
    """Send a notification via the EXISTING email path
    (app.integrations.smtp_service.send_email_async — the same helper OTP/signing/
    review invites use). NOT log-only.

    Recipients come from params['recipients'] or params['to'] (str or list). With
    NO resolvable recipient it logs + no-ops (a notification with nobody to email
    must not dead-end the flow). On a send error it returns success=False rather
    than raising, so a misconfigured SMTP in a demo env doesn't fail the workflow;
    a real env with creds sends for real. Returns {sent, recipients, success,
    subject}."""
    recipients = params.get("recipients") or params.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = [r.strip() for r in recipients if isinstance(r, str) and r.strip()]
    subject = str(params.get("subject") or "Workflow notification")
    body = str(params.get("body") or params.get("message") or subject)

    if not recipients:
        logger.info("workflow notify job: no recipients resolved — skipping send "
                    "(subject=%r)", subject)
        return {"sent": 0, "recipients": [], "skipped": "no recipients", "subject": subject}

    from app.config import settings
    from app.integrations.smtp_service import smtp_service

    from_email = str(params.get("from_email")
                     or getattr(settings, "smtp_user", None) or "noreply@dizzaroo.com")
    try:
        result = await smtp_service.send_email_async(
            to=recipients, subject=subject, body=body, from_email=from_email,
            from_name=str(params.get("from_name") or "Clinical Trials CRM"),
            html=bool(params.get("html")),
        )
        ok = bool(result.get("success"))
        logger.info("workflow notify job: %d recipient(s) success=%s subject=%r",
                    len(recipients), ok, subject)
        return {"sent": len(recipients) if ok else 0, "recipients": recipients,
                "success": ok, "subject": subject, "error": result.get("error")}
    except Exception as exc:  # noqa: BLE001 — send failure is data, not a crash
        logger.warning("workflow notify job: send failed (%s)", exc)
        return {"sent": 0, "recipients": recipients, "success": False,
                "subject": subject, "error": str(exc)}


# ---------------------------------------------------------------------------
# append_document — attach/merge a SECOND document into the agreement as a new
# version, before signing (CTA appends the budget/Annexure A today). Reuses the
# EXISTING, tested merge primitives (render_visit_matrix_pdf + merge_pdfs, or
# append_visit_matrix_to_docx) — no new merge logic. The signing step always stamps
# the LATEST AgreementDocument version, so a version produced here gets signed.
# ---------------------------------------------------------------------------

# SOURCE SEAM. A source provider produces the APPENDIX as a standalone PDF for the
# general PDF-merge path. To support a NEW source later (e.g. {"type":"upload",...} or
# {"type":"document","id":...}) register it here — the handler below (base -> PDF +
# merge_pdfs + new version) is source-agnostic. Each provider is:
#     async def(agreement, source: dict, db) -> Optional[str]   # appendix PDF path, or None
async def _budget_appendix_pdf(agreement, source: dict, db):  # noqa: ARG001 — source reserved for future opts
    """source 'budget' = the CTA per-visit cost matrix / Annexure A, rendered from the
    site_budgeting data via the EXISTING render_visit_matrix_pdf (WeasyPrint). Returns
    None when there's no study/site or no budget data (handler then records 'nothing
    appended' rather than failing)."""
    from app.modules.agreements.utils.pdf_export import render_visit_matrix_pdf
    if not (getattr(agreement, "study_id", None) and getattr(agreement, "site_id", None)):
        return None
    return await render_visit_matrix_pdf(agreement.study_id, agreement.site_id, db)


_APPEND_SOURCES: dict[str, JobHandler] = {
    "budget": _budget_appendix_pdf,  # type: ignore[dict-item]
}

# When no explicit params.placeholder is given, a budget append AUTO-DETECTS a marker the
# template author may have placed (e.g. "{{ANNEXURE_A}}") and inserts the budget THERE
# instead of at the end — so the author controls placement just by putting the marker in
# the template. First match wins; matching is whitespace/case-insensitive.
_DEFAULT_BUDGET_MARKERS = (
    "{{ANNEXURE_A}}", "{{ANNEXURE A}}", "{{ANNEX_A}}", "{{ANNEXURE}}",
    "{{BUDGET}}", "{{SITE_BUDGET}}", "{{BUDGET_TABLE}}", "{{BUDGET_ANNEXURE}}",
)


async def _persist_append_artifact(agreement, path: str, version_seq: int = 0):
    """Persist the merged/appended artifact durably (Azure Blob) when storage is
    configured, else keep the local path — mirrors _generate_document's best-effort
    durable upload. Returns (document_file_path, document_file_url).

    The blob name MUST carry the ``_vNNN_`` sequence: the agreements module picks the
    document shown in OnlyOffice via _latest_agreement_document, which ranks by
    _extract_blob_seq (regex ``_v(\\d{3})_``) FIRST. A name without the sequence scores
    0 and loses to the v001 template doc — so the appended budget version, though newest,
    would never be displayed (the budget "vanishes" from the editor)."""
    from pathlib import Path
    ext = Path(path).suffix.lower()
    ctype = ("application/pdf" if ext == ".pdf"
             else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
             if ext == ".docx" else "application/octet-stream")
    seq = max(int(version_seq or 0), 1)
    try:
        from app.utils.azure_storage import get_document_storage
        storage = get_document_storage()
        if storage is not None:
            import uuid
            # `_v{seq:03d}_` so _extract_blob_seq ranks this as the latest version.
            blob_name = f"agreements/{agreement.id}/appended_v{seq:03d}_{uuid.uuid4().hex}{ext}"
            async with aiofiles.open(path, "rb") as fh:
                data = await fh.read()
            url = await storage.upload_file(data, blob_name, content_type=ctype)
            logger.info("append_document: persisted durably at %s", blob_name)
            return blob_name, url
    except Exception as exc:  # noqa: BLE001 — durable upload best-effort; local path remains
        logger.warning("append_document: durable upload failed (%s); keeping local path", exc)
    return path, None


async def _append_docx_budget(agreement, source: dict, db, docx_path: str,
                              markers=None) -> str:  # noqa: ARG001
    """DOCX (review-visible) append for the budget: reuse append_visit_matrix_to_docx so
    the reviewer sees the budget table inside OnlyOffice. Budget-only today (other
    sources have no docx appender yet — use format 'pdf'). ``markers`` (e.g.
    {{ANNEXURE_A}}) place the budget AT the author's marker instead of at the end."""
    from app.modules.agreements.utils.pdf_export import append_visit_matrix_to_docx
    if not (getattr(agreement, "study_id", None) and getattr(agreement, "site_id", None)):
        raise ValueError("append_document: budget docx append needs the agreement's study_id + site_id")
    return await append_visit_matrix_to_docx(
        docx_path, agreement.study_id, agreement.site_id, db, markers=markers)


async def _append_document(params: dict, context: dict) -> dict[str, Any]:
    """GENERAL 'attach/merge a second document into the agreement' job. Source-pluggable
    via params['source'] (e.g. {"type":"budget"} = the visit-matrix / Annexure A today;
    future {"type":"upload"|"document",...} register in _APPEND_SOURCES). Produces a NEW
    AgreementDocument version — the merged artifact the signing step then stamps (signing
    always stamps the LATEST version) — and returns {appended, source, document_url,
    version}.

    An UNKNOWN source type raises (job fails loudly) rather than silently doing nothing,
    so a mis-authored append surfaces instead of shipping an un-merged agreement.

    params['format']: "docx" appends the source as a review-visible table inside the DOCX
    (append_visit_matrix_to_docx) so it shows in OnlyOffice review — budget only. "pdf"
    appends it as a PDF appendix after the agreement (render -> merge_pdfs). DEFAULT is
    source-aware: "docx" for the budget (so it renders in the reviewed document), "pdf"
    for every other source. An explicit params.format always wins.

    params['placeholder'] (or 'at'), optional: an author-placed marker like
    "{{ANNEXURE_A}}" / "{{BUDGET}}" (same braces convention as {{SIGNATURE_<ROLE>}}).
    When given AND found in the base PDF, the appendix is inserted right after the page
    carrying the marker (DETERMINISTIC — placement is wherever the author put the marker,
    nothing AI decides it). When omitted or not found, it appends at the END. The result's
    'placement' field reports which path ran (at_placeholder | end | end_placeholder_not_found).
    Placeholder placement applies to the PDF path (the signed artifact); the docx path
    always appends at the end. Place this step BEFORE signing so the signed doc includes it."""
    agreement_id = context.get("agreement_id") or context.get("subject_ref")
    if not agreement_id:
        raise ValueError("append_document: no agreement_id/subject_ref in workflow context")

    source = params.get("source") or {}
    if isinstance(source, str):
        source = {"type": source}
    stype = str((source or {}).get("type") or "").strip().lower()
    if not stype:
        raise ValueError('append_document: params.source.type is required (e.g. {"type":"budget"})')
    # Format default is source-aware. BUDGET defaults to "docx" so the appended
    # visit-matrix is baked INTO the review DOCX and renders inside the same document
    # the reviewer/owner opens in OnlyOffice (a "pdf" appendix is invisible there — it
    # only shows in the final signed artifact, which is why an appended budget appeared
    # "nowhere to be seen" during the review/send-back cycle). This matches the initial
    # fill-placeholders flow, which already bakes the budget in via append_visit_matrix_to_docx.
    # Other sources keep "pdf" (no docx appender). An explicit params.format always wins.
    fmt = str(params.get("format") or ("docx" if stype == "budget" else "pdf")).strip().lower()
    # Optional author-placed marker (e.g. "{{ANNEXURE_A}}", "{{BUDGET}}"). DETERMINISTIC:
    # the appendix lands at the page carrying this marker; nothing AI decides placement.
    placeholder = str(params.get("placeholder") or params.get("at") or "").strip() or None

    from app.db import AsyncSessionLocal
    from app.models import Agreement
    from app.modules.agreements.services import doc_convert, document_versioning

    async with AsyncSessionLocal() as db:
        agreement = await db.get(Agreement, agreement_id)
        if agreement is None:
            raise ValueError(f"append_document: agreement {agreement_id} not found")
        latest = await document_versioning.latest_document(db, agreement.id)
        if latest is None or not latest.document_file_path:
            raise ValueError("append_document: agreement has no base document to append to")
        # The version this append will create — used to name the blob with the _vNNN_
        # sequence so the editor's _latest_agreement_document picks it as the latest.
        next_seq = (getattr(latest, "version_number", 0) or 0) + 1
        # Resolve the base document to LOCAL bytes (downloads from Azure Blob Storage when
        # the doc is Azure-stored) so conversion/append never "source file not found"s on a
        # blob name. Shared resolver — same one signing uses.
        base_local = await doc_convert.resolve_local_path(
            latest.document_file_path, getattr(latest, "document_file_url", None))
        if not base_local:
            raise ValueError(
                f"append_document: base document bytes unavailable (path={latest.document_file_path}) "
                f"— is Azure Blob Storage configured/reachable?")

        # Marker set shared by BOTH formats: an explicit params.placeholder wins; else
        # AUTO-DETECT a budget marker the author placed in the template (e.g.
        # {{ANNEXURE_A}}) so it's honored without the workflow author wiring it. The docx
        # path inserts the budget AT the marker (and removes the marker line); the pdf
        # path inserts the appendix page after the marker page.
        markers = ([placeholder] if placeholder
                   else (list(_DEFAULT_BUDGET_MARKERS) if stype == "budget" else []))

        placement = "end"
        if fmt == "docx":
            # Review-visible budget table baked into the DOCX (budget-only today),
            # inserted at the author's marker when present (else at the end).
            if stype != "budget":
                raise ValueError(
                    f"append_document: format 'docx' is only supported for source 'budget', not {stype!r}")
            new_path = await _append_docx_budget(agreement, source, db, base_local, markers=markers)
            durable_path, durable_url = await _persist_append_artifact(agreement, new_path, next_seq)
            # placement is reported best-effort for docx; the appender logs the exact
            # outcome (inserted at marker vs appended at end).
            placement = "at_marker_or_end_docx" if markers else "end"
        else:
            provider = _APPEND_SOURCES.get(stype)
            if provider is None:
                raise ValueError(
                    f"append_document: unknown source type {stype!r}; supported: {sorted(_APPEND_SOURCES)}")
            appendix_pdf = await provider(agreement, source, db)  # type: ignore[misc]
            if not appendix_pdf:
                logger.info("append_document: source %r produced no content; nothing appended", stype)
                return {"appended": False, "source": stype, "reason": f"no {stype} content"}
            from app.modules.agreements.utils.pdf_export import (
                find_placeholder_page, insert_pdf_after_page, merge_pdfs,
            )
            base_pdf = await doc_convert.to_pdf(base_local)  # already local-resolved above
            page, used_marker = None, None
            for mk in markers:
                page = find_placeholder_page(base_pdf, mk)
                if page is not None:
                    used_marker = mk
                    break
            if page is not None:
                merged = insert_pdf_after_page(base_pdf, appendix_pdf, page)
                placement = "at_placeholder"
                placeholder = used_marker  # report which marker the budget landed at
            elif placeholder:
                # An EXPLICIT marker was given but not found → end-append, flagged.
                merged = merge_pdfs(base_pdf, appendix_pdf)
                placement = "end_placeholder_not_found"
            else:
                merged = merge_pdfs(base_pdf, appendix_pdf)
            durable_path, durable_url = await _persist_append_artifact(agreement, merged, next_seq)

        new_doc = await document_versioning.add_document_version(
            db, agreement.id, durable_path, is_signed=False,
            created_by="system:append_document", document_file_url=durable_url)
        await db.commit()
        logger.info("append_document: appended %r into agreement %s as v%s (format=%s, placement=%s)",
                    stype, agreement.id, new_doc.version_number, fmt, placement)
        return {"appended": True, "source": stype, "placement": placement,
                "placeholder": placeholder,
                "document_url": durable_url or durable_path,
                "version": new_doc.version_number}


def registered_kinds() -> set[str]:
    """The job kinds with a live handler — the generator/normalizer use this to
    emit/repair to kinds that can ACTUALLY run."""
    return set(_HANDLERS)


register_job_handler(KIND_NOOP, _noop)
register_job_handler(KIND_NOTIFY, _notify)
register_job_handler(KIND_GENERATE_DOCUMENT, _generate_document)
register_job_handler(KIND_APPEND_DOCUMENT, _append_document)
