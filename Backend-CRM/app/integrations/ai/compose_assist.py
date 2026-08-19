"""AI compose-assist: multi-draft reply generation + pre-send checks."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.integrations.ai.client import AIClient


async def compose_reply(
    client: AIClient,
    history_text: str,
    latest_draft: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Generate multiple reply drafts + summary + key facts for an email thread.

    This is a generic helper; the caller is responsible for preparing
    ``history_text`` (conversation or thread) and passing any partial draft.
    """
    if not client.is_available():
        return None

    draft_section = f"\nUser current draft (may be empty):\n{latest_draft}\n" if latest_draft else "\nUser has not written a draft yet.\n"

    prompt = f"""
You are an AI assistant helping a CRM user reply to an email thread.
Read the full thread below and generate suggested replies.

Thread history:
{history_text}
{draft_section}

Your task:
1. Propose three alternative reply drafts:
   - professional: well‑structured, formal but friendly.
   - short: very concise, minimal but clear.
   - detailed: longer, addresses all points explicitly.
2. Write a short overall summary of the thread.
3. Extract key facts as a bullet‑style list (names, dates, commitments, decisions, open questions).

CRITICAL OUTPUT FORMAT:
Respond with ONLY valid JSON, no extra text, with this exact structure:
{{
  "drafts": {{
    "professional": "string",
    "short": "string",
    "detailed": "string"
  }},
  "summary": "string",
  "facts": ["string", "string"]
}}

Make sure the JSON is syntactically valid and does not contain comments.
"""

    # First, try strict JSON mode
    data = await client.generate_json(prompt)
    if data:
        drafts = data.get("drafts") or {}
        return {
            "drafts": {
                "professional": str(drafts.get("professional") or ""),
                "short": str(drafts.get("short") or ""),
                "detailed": str(drafts.get("detailed") or ""),
            },
            "summary": str(data.get("summary") or ""),
            "facts": [str(f) for f in (data.get("facts") or [])],
        }

    # Fallback: ask for three labelled drafts in plain text and parse them
    try:
        loop = asyncio.get_event_loop()
        fallback_prompt = f"""
You are helping a CRM user reply to an email thread.

Thread history:
{history_text}

User draft (may be empty):
{latest_draft or "(no draft)"}

Write THREE alternative reply drafts in this exact plain‑text format (no JSON, no markdown fences):

[PROFESSIONAL]
<professional_reply_here>

[SHORT]
<short_reply_here>

[DETAILED]
<detailed_reply_here>

Do not add any extra commentary before or after these sections.
"""
        response = await loop.run_in_executor(
            None,
            lambda: client.model.generate_content(fallback_prompt)
        )
        raw = response.text if hasattr(response, "text") else str(response)
        raw = (raw or "").strip()
    except Exception as e:
        print(f"Error in compose_reply fallback: {e}")
        return None

    # Simple parser for the labelled sections
    professional = ""
    short = ""
    detailed = ""
    try:
        sections = raw.split("[PROFESSIONAL]")
        if len(sections) > 1:
            rest = sections[1]
            parts = rest.split("[SHORT]")
            professional = parts[0].strip()
            if len(parts) > 1:
                rest2 = parts[1]
                parts2 = rest2.split("[DETAILED]")
                short = parts2[0].strip()
                if len(parts2) > 1:
                    detailed = parts2[1].strip()
    except Exception as e:
        print(f"Error parsing compose_reply fallback output: {e}")

    # If parsing failed badly, fall back to using the whole text for all
    if not (professional or short or detailed):
        professional = raw
        short = raw
        detailed = raw

    return {
        "drafts": {
            "professional": professional,
            "short": short,
            "detailed": detailed,
        },
        "summary": "",
        "facts": [],
    }


async def check_message_before_send(
    client: AIClient,
    context_text: str,
    draft_body: str,
    attachments: List[str],
) -> Optional[Dict[str, Any]]:
    """Ask Gemini to check a draft message for missing information.

    Returns dict: { 'issues': [...], 'okToSend': bool }.
    """
    issues: List[Dict[str, str]] = []
    body_lower = (draft_body or "").lower()

    # ------------------------------------------------------------------
    # Deterministic rule-based checks (run even if Gemini is unavailable)
    # ------------------------------------------------------------------

    # 1) Relative time words without any explicit date digits -> missing_date
    relative_keywords = ["tomorrow", "tonight", "next week", "next month", "next year", "this week"]
    has_relative = any(k in body_lower for k in relative_keywords)
    has_digit = any(ch.isdigit() for ch in body_lower)
    if has_relative and not has_digit:
        issues.append({
            "type": "missing_date",
            "message": "You used a relative time (e.g. 'tomorrow') but did not specify an exact date/time."
        })

    # 2) Mentions of attachments but no actual files selected -> missing_attachment
    if ("attach" in body_lower or "attached" in body_lower) and not attachments:
        issues.append({
            "type": "missing_attachment",
            "message": "You mentioned an attachment but have not added any file."
        })

    # 3) Vague 'follow steps' without any list -> unclear_next_step
    if "follow the steps" in body_lower or "follow steps" in body_lower:
        has_list = any(prefix in body_lower for prefix in ["1.", "1)", "step 1", "first,"])
        if not has_list:
            issues.append({
                "type": "unclear_next_step",
                "message": "You asked the recipient to 'follow steps' but did not list the steps."
            })

    # ------------------------------------------------------------------
    # Optional AI-based checks via Gemini (augment, not replace)
    # ------------------------------------------------------------------
    attachments_list = ", ".join(attachments) if attachments else "none"

    prompt = f"""
You are reviewing an email draft before it is sent from a CRM.

Conversation / thread context:
{context_text}

Draft message body:
{draft_body}

Attachments currently selected (file names): {attachments_list}

Identify potential issues before sending, such as:
- missing or ambiguous dates / times,
- mentioned attachments that are not actually attached,
- missing clear next step,
- any other critical missing information.

Respond STRICTLY with JSON:
{{
  "issues": [
    {{
      "type": "missing_date|missing_attachment|unclear_next_step|other",
      "message": "human readable guidance"
    }}
  ],
  "okToSend": true|false
}}

If there are no issues, use an empty array and okToSend = true.
"""
    data = None
    if client.is_available():
        data = await client.generate_json(prompt)

    if data:
        issues_raw = data.get("issues") or []
        for item in issues_raw:
            try:
                itype = str(item.get("type") or "other")
                msg = str(item.get("message") or "")
                if msg:
                    issues.append({"type": itype, "message": msg})
            except Exception:
                continue
        ai_ok = bool(data.get("okToSend")) if issues_raw else True
    else:
        ai_ok = True  # if AI fails, rely on deterministic rules only

    # If any issues (either from rules or AI), default to okToSend = False,
    # otherwise fall back to AI's ok flag or True.
    ok_to_send = False if issues else ai_ok

    return {
        "issues": issues,
        "okToSend": ok_to_send,
    }
