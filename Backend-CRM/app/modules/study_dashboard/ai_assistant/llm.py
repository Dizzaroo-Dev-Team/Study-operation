"""
Thin Gemini wrapper for the study-dashboard AI assistant.

Mirrors the model fallback / JSON-stripping pattern from app/ai_service.py but
keeps the prompt construction local to this module so it can be tuned without
touching the rest of the AI service.

Single public entry point: `call_llm(question, history)` returns the parsed
JSON from the model. The caller is responsible for SQL validation and
execution — this module never touches the database.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Optional

import google.generativeai as genai

from app.config import settings

from .sdtm_schema import get_schema_text

logger = logging.getLogger(__name__)


# Model fallback chain — same shape as app/ai_service.py.
_MODEL_FALLBACK = [
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
]

# Single-study DB for v1; can become a route param later.
_STUDY_ID = "DS8201-A-U201"


_PROMPT_TEMPLATE = """You translate clinical-trial questions into a single Postgres SQL query
against the SDTM schema below, then describe how to chart the result.

# Hard rules
- Output ONLY a JSON object — no prose, no markdown fences.
- The DB has 32 SDTM domain tables. ALL identifiers are lowercase
  (e.g. `ae`, `dm`, not `AE`, `DM`). Column names are lowercase too.
- Use SDTM column names EXACTLY as they appear in the schema below, lowercased.
  NEVER add underscores between letters. `USUBJID` is `usubjid` (NOT `usubj_id`,
  NOT `u_subj_id`). `AEDECOD` is `aedecod` (NOT `ae_decod`). Same rule for
  every `xxYYY` SDTM code: lowercase the whole thing as one token.
- Every table that has a `studyid` column MUST be filtered by
  `studyid = '{study_id}'`.
- Generate ONE statement, SELECT-only. No DDL, DML, or transaction control.
- Prefer human-readable groupings when present (e.g. `aedecod`, `aesoc`,
  `dvdecod`, `arm`) over numeric codes.
- If the user's question CANNOT be answered from the schema below, set
  `status` to `"no_data"` and explain in `reason_if_no_data`. Do NOT invent
  a column or table that isn't in the schema.

# Output JSON shape (use exactly these keys)
{{
  "status": "ok" | "no_data",
  "narrative": "1-2 sentence interpretation of the result",
  "sql": "SELECT ... ;   // or null when status='no_data'",
  "chart": {{
     "type": "bar" | "line" | "pie" | "kpi" | "table" | "stacked_bar",
     "title": "short title",
     "x_field": "<column name from SELECT, or null>",
     "y_field": "<column name from SELECT, or null>",
     "series_field": "<column name for stacked/multi-series, or null>",
     "value_field": "<column name for kpi/pie value, or null>"
  }},
  "reason_if_no_data": "<string when status='no_data', else null>"
}}

# Few-shot examples

Q: "How many adverse events are at toxicity grade 3 or higher?"
{{
  "status": "ok",
  "narrative": "Counts of grade 3+ adverse events grouped by CTCAE grade.",
  "sql": "SELECT aetoxgr::int AS grade, COUNT(*)::int AS cnt FROM ae WHERE studyid = '{study_id}' AND aetoxgr >= 3 GROUP BY aetoxgr ORDER BY aetoxgr",
  "chart": {{ "type": "bar", "title": "Severe AEs by CTCAE grade", "x_field": "grade", "y_field": "cnt", "series_field": null, "value_field": null }},
  "reason_if_no_data": null
}}

Q: "Show enrolled subjects per country."
{{
  "status": "no_data",
  "narrative": "The DM domain in this database does not include a country column.",
  "sql": null,
  "chart": null,
  "reason_if_no_data": "DM has SITEID but no COUNTRY column; site→country lookup is not in the SDTM extract."
}}

Q: "Subjects per treatment arm."
{{
  "status": "ok",
  "narrative": "Subject count grouped by planned treatment arm from DM.",
  "sql": "SELECT arm, COUNT(*)::int AS cnt FROM dm WHERE studyid = '{study_id}' AND arm IS NOT NULL GROUP BY arm ORDER BY cnt DESC",
  "chart": {{ "type": "bar", "title": "Subjects per arm", "x_field": "arm", "y_field": "cnt", "series_field": null, "value_field": null }},
  "reason_if_no_data": null
}}

# SDTM schema (verbatim)

{schema}

# Conversation so far
{history_block}

# User question
{question}

Return ONLY the JSON object now.
"""


def _is_configured() -> bool:
    return bool(settings.gemini_api_key)


def _ensure_configured() -> None:
    if not _is_configured():
        raise RuntimeError(
            "GEMINI_API_KEY is not configured — cannot call the AI assistant."
        )
    # google-generativeai reads the key once via configure(); cheap to repeat.
    genai.configure(api_key=settings.gemini_api_key)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        # Strip leading fence (```json or ```)
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        # Strip trailing fence
        raw = re.sub(r"\s*+```$", "", raw)
    return raw.strip()


def _format_history(history: Optional[list[dict]]) -> str:
    if not history:
        return "(no prior turns)"
    lines = []
    for turn in history[-6:]:  # cap at last 6 turns to keep prompt bounded
        role = str(turn.get("role", "user")).strip().lower()
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


def _build_prompt(question: str, history: Optional[list[dict]]) -> str:
    return _PROMPT_TEMPLATE.format(
        study_id=_STUDY_ID,
        schema=get_schema_text(),
        history_block=_format_history(history),
        question=question.strip(),
    )


def _generate_sync(prompt: str) -> dict[str, Any]:
    """Try each model in the fallback chain until one works. Sync — call from a thread."""
    last_err: Exception | None = None
    for model_id in _MODEL_FALLBACK:
        try:
            model = genai.GenerativeModel(model_id)
            response = model.generate_content(prompt)
            raw = getattr(response, "text", None)
            if not raw:
                raise RuntimeError(f"Empty response from {model_id}")
            stripped = _strip_fences(raw)
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as je:
                # Salvage: find the first {...} block
                m = re.search(r"\{[\s\S]*\}", stripped)
                if m:
                    return json.loads(m.group(0))
                raise RuntimeError(
                    f"Model {model_id} returned non-JSON: {stripped[:200]}"
                ) from je
        except Exception as exc:
            logger.warning("Gemini model %s failed: %s", model_id, exc)
            last_err = exc
            continue
    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}") from last_err


async def call_llm(question: str, history: Optional[list[dict]] = None) -> dict[str, Any]:
    """Call Gemini and return the parsed JSON dict (already de-fenced)."""
    _ensure_configured()
    prompt = _build_prompt(question, history)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _generate_sync, prompt)
