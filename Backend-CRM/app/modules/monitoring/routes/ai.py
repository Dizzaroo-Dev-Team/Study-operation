"""REST API: monitor AI helpers - generate pre-visit summary + generate visit-report summary."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

# No prefix here - parent router in app/monitor/router.py owns /api/monitor.
router = APIRouter(tags=["monitor"])


# --- Gemini model probing ----------------------------------------------------
# Multiple model IDs are tried in order because the alias gemini-1.5-flash
# often returns 404 on v1beta.

_gemini_model = None


def _gemini_model_candidates() -> List[str]:
    env_first = os.getenv("GEMINI_MODEL", "").strip()
    ordered: List[str] = []
    if env_first:
        ordered.append(env_first)
    for name in (
        "gemini-3.5-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
    ):
        if name not in ordered:
            ordered.append(name)
    return ordered


def _get_gemini_model():
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model
    api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "gemini_api_key", None)
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini API key is not configured on the server.")
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise HTTPException(status_code=503, detail="google-generativeai package is not installed.")
    genai.configure(api_key=api_key)

    last_err: Optional[Exception] = None
    for model_name in _gemini_model_candidates():
        try:
            candidate = genai.GenerativeModel(model_name)
            probe = candidate.generate_content("Reply with the single word OK.")
            if probe and getattr(probe, "text", None):
                _gemini_model = candidate
                return _gemini_model
        except Exception as e:  # noqa: BLE001 - aggregate until we exhaust candidates
            last_err = e
            msg_l = str(e).lower()
            if "api key" in msg_l or "api_key" in msg_l or "permission denied" in msg_l:
                raise HTTPException(status_code=502, detail=f"Gemini API authentication failed: {e}") from e
            continue

    raise HTTPException(
        status_code=502,
        detail=(
            "No Gemini model accepted generateContent for this API key. "
            f"Last error: {last_err}. "
            "Set GEMINI_MODEL to a supported id (see https://ai.google.dev/gemini-api/docs/models)."
        ),
    )


# --- Pydantic models ---------------------------------------------------------

class PreVisitMetric(BaseModel):
    title: str
    value: str
    description: str


class PreVisitSiteData(BaseModel):
    metrics: List[PreVisitMetric]


class GeneratePreVisitSummaryRequest(BaseModel):
    userPrompt: str = ""
    siteData: PreVisitSiteData
    visitContext: Optional[str] = ""


class GeneratePreVisitSummaryResponse(BaseModel):
    report: str


# --- Pre-visit summary prompt ------------------------------------------------

_PREVISIT_DEFAULT_INSTRUCTIONS = (
    "Write a concise pre-visit status email for the site: one short opening paragraph, "
    "then 4–6 bullet points covering the most important status metrics."
)


def _build_previsit_summary_prompt(
    *,
    user_prompt: str,
    metrics_block: str,
    visit_context: str = "",
) -> str:
    user_instructions = user_prompt.strip() or _PREVISIT_DEFAULT_INSTRUCTIONS
    context_block = f"\nVisit context:\n{visit_context}\n" if visit_context.strip() else ""

    return f"""You are a Clinical Research Associate drafting the body of a pre-visit summary email that will be sent directly to the Principal Investigator and site staff.

USER REQUEST (follow this exactly — highest priority):
{user_instructions}

EMAIL BODY FORMAT (the surrounding email already includes "Dear [PI name]", subject line, and an acknowledgment button — do NOT duplicate those):
1. Opening paragraph (2–3 sentences): state that this is a pre-visit status summary ahead of the upcoming monitoring visit. Reference site, study, PI, and visit date from Visit context when available. Use a professional, courteous tone written for the site team (e.g. "your site", "the upcoming visit").
2. Bulleted status overview: include only metrics relevant to the user's request. Use this exact bullet pattern:
   * **Metric name:** value and brief supporting detail
3. Optional closing sentence (one line max): a brief note that the site may review these items before the visit. Do NOT ask the recipient to reply, click a link, or acknowledge receipt.

STRICT RULES:
- Use ONLY facts from REFERENCE DATA. Never invent metrics, dates, names, or action items.
- Never use placeholder brackets such as [Current Date], [CRA Name], or [Site Number].
- Do NOT include salutation (Dear…), sign-off (Sincerely…), subject line, or memo headers (DATE, TO, FROM, SUBJECT).
- Do NOT use markdown headings (# or ##). Use plain paragraphs and bullet lists only.
- Do NOT dump every metric — include only what the user asked for or what is most material.
- Avoid internal CRA jargon, ALL CAPS labels, or memo-style section titles.
- Keep length proportional to the request; default max ~200 words unless the user asks for more detail.
- Do NOT mention pre-visit checklists, regulatory readiness lists, startup tasks, or preparation item lists (e.g. IRB approval, DOA log, CTA, eTMF, GCP certificates).

REFERENCE DATA (status board metrics only):
{context_block}Status metrics:
{metrics_block}

Write the email body:"""


def _clean_previsit_report(text: str) -> str:
    """Strip salutations, memo headers, and other boilerplate the model sometimes adds."""
    if not text:
        return text
    lines = text.splitlines()
    skip_starts = (
        "date:",
        "to:",
        "from:",
        "subject:",
        "**date:",
        "**to:",
        "**from:",
        "**subject:",
        "pre-visit summary report",
        "**pre-visit summary report**",
        "dear ",
        "hi ",
        "hello ",
        "sincerely",
        "best regards",
        "kind regards",
        "warm regards",
        "thank you,",
        "thanks,",
        "---",
    )
    skip_exact = {"---", "***", "___"}
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        low = stripped.lower().lstrip("#* ").strip()
        if low.startswith("#"):
            # Drop markdown headings; keep the heading text as a plain paragraph.
            heading_text = re.sub(r"^#+\s*", "", stripped).strip()
            if heading_text:
                out.append(heading_text)
            continue
        if stripped in skip_exact:
            continue
        if any(low.startswith(s) for s in skip_starts):
            continue
        out.append(line)

    cleaned = "\n".join(out).strip()
    # Collapse excessive blank lines.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned or text.strip()


# --- Endpoints ---------------------------------------------------------------

@router.post("/generate-previsit-summary", response_model=GeneratePreVisitSummaryResponse)
async def generate_previsit_summary(body: GeneratePreVisitSummaryRequest):
    """
    Accepts status-board metrics from the Pre-Visit tab and returns a Gemini-generated summary.
    """
    model = _get_gemini_model()

    metrics_block = "\n".join(
        f"  • {m.title}: {m.value} — {m.description}"
        for m in body.siteData.metrics
    ) or "(No metrics provided)"

    prompt = _build_previsit_summary_prompt(
        user_prompt=body.userPrompt,
        metrics_block=metrics_block,
        visit_context=(body.visitContext or "").strip(),
    )

    try:
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={"temperature": 0.35, "max_output_tokens": 1200},
        )
        generated_text = _clean_previsit_report((response.text or "").strip())
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API error: {exc}",
        )

    return GeneratePreVisitSummaryResponse(report=generated_text)


@router.post("/generate-summary")
async def generate_visit_summary(payload: Dict[str, Any]):
    """
    Use Google Gemini to auto-generate the 'Summary of the Visit' section
    from the structured Visit Report form data.
    """
    from app.integrations.ai import ai_service  # reuse the shared singleton

    if not ai_service.is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "AI service is unavailable. "
                "Please update GEMINI_API_KEY in .env with a valid key from "
                "https://aistudio.google.com and restart the backend."
            ),
        )

    def _format_payload(data: Dict[str, Any]) -> str:
        """Convert nested form data into a readable text block for the prompt."""

        def _label(key: str) -> str:
            return key.replace("_", " ").replace("q", "Q").replace("s", "S").title()

        lines: list[str] = []

        # Study & visit basics
        for field in ("studyTitle", "sponsor", "studyType", "site", "pi", "visitPurpose"):
            val = data.get(field)
            if val:
                lines.append(f"{_label(field)}: {val}")
        visit_start = (data.get("visitStartDate") or data.get("visitDate") or "").strip()
        visit_end = (data.get("visitEndDate") or "").strip()
        if visit_start:
            lines.append(f"Start Visit Date: {visit_start}")
        if visit_end:
            lines.append(f"End Visit Date: {visit_end}")

        # Participant numbers
        pt_fields = [
            ("ptPlanned", "Planned"), ("ptScreened", "Screened"), ("ptEnrolled", "Enrolled"),
            ("ptActive", "Active"), ("ptDropouts", "Drop-outs"), ("ptCompleted", "Completed"),
        ]
        pt_parts = [f"{lbl}={data[k]}" for k, lbl in pt_fields if data.get(k)]
        if pt_parts:
            lines.append("Participant Status: " + ", ".join(pt_parts))

        # Checklist answers (Q/A sections 2-12)
        checklist_keys = [k for k in data if k.startswith("q") and isinstance(data[k], str) and data[k]]
        for k in sorted(checklist_keys):
            lines.append(f"  {_label(k)}: {data[k]}")

        # Section comments
        comment_keys = [k for k in data if k.endswith("Comments") and data.get(k)]
        for k in sorted(comment_keys):
            lines.append(f"  {_label(k)}: {data[k]}")

        # Deviations
        dev_rows = data.get("devRows", [])
        if isinstance(dev_rows, list) and any(r.get("description") for r in dev_rows):
            lines.append("Protocol Deviations:")
            for r in dev_rows:
                desc = r.get("description", "").strip()
                if desc:
                    lines.append(f"  - {desc} (Severity: {r.get('severity','?')}, Status: {r.get('status','?')})")

        # Action items
        action_rows = data.get("actionRows", [])
        if isinstance(action_rows, list) and any(r.get("description") for r in action_rows):
            lines.append("Outstanding Action Items:")
            for r in action_rows:
                desc = r.get("description", "").strip()
                if desc:
                    lines.append(f"  - [{r.get('priority','?')}] {desc} (Due: {r.get('deadline','?')})")

        # Additional comments
        if data.get("additionalComments"):
            lines.append(f"Additional Comments: {data['additionalComments']}")

        return "\n".join(lines)

    system_instruction = (
        "You are an expert Clinical Research Associate (CRA). "
        "Review the following structured data from a clinical monitoring visit. "
        "Write a comprehensive but concise 'Summary of the Visit'. "
        "The summary should highlight: "
        "1. Overall site performance and recruitment progress, "
        "2. Key issues regarding protocol compliance, safety, or drug accountability, "
        "3. The most critical action items the site must address. "
        "Do not invent any data. Use a professional, objective tone. "
        "Write in plain paragraphs — no bullet points, no markdown formatting."
    )

    formatted_data = _format_payload(payload)
    prompt = f"{system_instruction}\n\n--- VISIT REPORT DATA ---\n{formatted_data}\n--- END OF DATA ---\n\nSummary:"

    try:
        response = await asyncio.to_thread(ai_service.model.generate_content, prompt)
        generated_text = response.text.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc

    return {"summary": generated_text}
