"""
SoA → Visit Matrix service.

Flow:
  1. normalize_soa()              — parse MongoDB doc into canonical visits + activities
  2. map_activities_to_elements() — Phase 1: string matching; Phase 2: AI for leftovers
  3. build_matrix_plan()          — produce [{visit_name, element_code, quantity}]

AI does NOT generate costs, totals, or fixed costs.
The existing cost engine (compute_final_unit_cost) handles all money.

Mapping priority:
  1. Exact code match (normalized)
  2. Exact name match (normalized)
  3. Substring / token-overlap string matching (score ≥ 0.5 → mapped)
  4. AI fallback only for unmatched activities
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

MODELS_TO_TRY = [
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
]


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


# ─── Phase 1: String-based activity → element matching ───────────────────────

# Clinical trial noise words that appear in activity names but not element codes
_NOISE_WORDS = frozenset({
    "assessment", "assessments", "evaluation", "evaluations",
    "procedure", "procedures", "test", "tests", "testing",
    "collection", "collections", "sample", "samples", "sampling",
    "measurement", "measurements", "visit", "visits",
    "screening", "baseline", "follow", "up", "day",
    "central", "local", "lab", "laboratory", "clinical",
})


def _normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(text: str, remove_noise: bool = True) -> frozenset:
    words = set(_normalize_text(text).split())
    if remove_noise:
        words -= _NOISE_WORDS
    return frozenset(words) if words else frozenset(_normalize_text(text).split())


def _token_overlap(a_tokens: frozenset, b_tokens: frozenset) -> float:
    """Jaccard-based token overlap score."""
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return intersection / union


def map_activities_string_matching(
    activity_names: List[str],
    elements: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """
    Phase 1: pure string matching — no API call required.

    Strategy (in order):
      1. Exact normalized code match            → confidence 1.0
      2. Exact normalized name match            → confidence 1.0
      3. Activity name contains element name    → confidence 0.88
      4. Element name contains activity name    → confidence 0.84
      5. Activity name contains element code    → confidence 0.80
      6. Token overlap ≥ 0.4 (noise-stripped)  → confidence = overlap × 0.85

    Returns list of {activity, element_code, confidence}.
    Unmatched → element_code=None, confidence=0.0
    """
    # Pre-build lookup tables
    norm_code_to_elem: Dict[str, Dict] = {}
    norm_name_to_elem: Dict[str, Dict] = {}
    for e in elements:
        norm_code_to_elem[_normalize_text(e["code"])]  = e
        norm_name_to_elem[_normalize_text(e["name"])]  = e

    results: List[Dict[str, Any]] = []

    for act_name in activity_names:
        norm_act = _normalize_text(act_name)
        act_tokens = _tokens(act_name)

        best_code: str | None = None
        best_conf = 0.0

        # 1. Exact code match
        if norm_act in norm_code_to_elem:
            best_code = norm_code_to_elem[norm_act]["code"]
            best_conf = 1.0

        # 2. Exact name match
        elif norm_act in norm_name_to_elem:
            best_code = norm_name_to_elem[norm_act]["code"]
            best_conf = 1.0

        else:
            # Scan elements for best substring / token match
            for e in elements:
                norm_ename = _normalize_text(e["name"])
                norm_ecode = _normalize_text(e["code"])
                conf = 0.0

                # Activity text contains element name
                if norm_ename and len(norm_ename) >= 3 and norm_ename in norm_act:
                    conf = max(conf, 0.88)
                # Element name contains activity text
                if norm_act and len(norm_act) >= 3 and norm_act in norm_ename:
                    conf = max(conf, 0.84)
                # Activity text contains element code
                if norm_ecode and len(norm_ecode) >= 3 and norm_ecode in norm_act:
                    conf = max(conf, 0.80)

                # Token overlap (noise words stripped)
                el_tokens = _tokens(e["name"])
                overlap = _token_overlap(act_tokens, el_tokens)
                if overlap >= 0.4:
                    conf = max(conf, overlap * 0.85)

                if conf > best_conf:
                    best_conf = conf
                    best_code = e["code"]

        # Apply threshold — below 0.5 counts as unmatched
        results.append({
            "activity": act_name,
            "element_code": best_code if best_conf >= 0.5 else None,
            "confidence": round(best_conf, 3),
            "match_source": "string" if best_conf >= 0.5 else "none",
        })

    matched = sum(1 for r in results if r["element_code"])
    logger.info(
        "[SOA_MATRIX] String matching: %d/%d activities matched",
        matched, len(activity_names),
    )
    return results


# ─── Step 1: SoA Normalizer ───────────────────────────────────────────────────

def normalize_soa(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse MongoDB SoA document into canonical structure.

    Actual MongoDB schema:
      visits:   [{period, day, ...}, ...]      ← indexed columns
      sections: [{title, activities: [{name, visits: [0,1,2,...]}]}]
                                               ↑ these are INDEX references into visits[]
    """
    study_id = _safe_str(
        doc.get("protocolId") or doc.get("study_id") or doc.get("protocol_id") or doc.get("studyId") or ""
    )

    # Build index → visit_name map from visits[]
    raw_visits = doc.get("visits") or []
    visit_map: Dict[int, str] = {}   # index → name
    visits_out: List[Dict[str, Any]] = []

    if isinstance(raw_visits, list):
        # Two-pass: first compute base names + days, then disambiguate any duplicate base names
        # by appending the day so e.g. "Neoadjuvant Therapy / C1D1" and "Neoadjuvant Therapy / C1D8"
        # become distinct. Without this, the apply step dedups visits by name and collapses them.
        scratch: list[dict[str, Any]] = []
        for i, v in enumerate(raw_visits):
            if not isinstance(v, dict):
                continue
            base = _safe_str(
                v.get("period") or v.get("visit_name") or v.get("name") or v.get("label") or f"Visit {i+1}"
            )
            vcode = _safe_str(v.get("visit_code") or v.get("code") or "")
            vday_raw = v.get("day") or v.get("target_day")
            vday = _safe_str(vday_raw) if vday_raw is not None else None
            scratch.append({"index": i, "base": base, "vcode": vcode, "day": vday})

        from collections import Counter
        base_counts = Counter(s["base"] for s in scratch)
        for s in scratch:
            base = s["base"]
            day = s["day"]
            # Disambiguate when (a) base appears more than once, or (b) base equals "Not Provided"/empty.
            if base_counts[base] > 1 and day:
                vname = f"{base} / {day}"
            else:
                vname = base or (day or f"Visit {s['index']+1}")
            visit_map[s["index"]] = vname
            visits_out.append({
                "index": s["index"],
                "visit_name": vname,
                "visit_code": s["vcode"],
                "target_day": day,
            })

    # Extract activities from sections[] — each activity has visits as index list
    raw_sections = doc.get("sections") or []
    all_activities: List[Dict[str, Any]] = []

    if isinstance(raw_sections, list):
        for sec in raw_sections:
            if not isinstance(sec, dict):
                continue
            section_title = _safe_str(sec.get("title") or sec.get("name") or "")
            acts = sec.get("activities") or sec.get("items") or []
            if not isinstance(acts, list):
                continue
            for a in acts:
                if not isinstance(a, dict):
                    continue
                act_name = _safe_str(a.get("name") or a.get("procedure") or a.get("assessment") or "")
                if not act_name:
                    continue

                # visits field = list of indices into visits[]
                raw_act_visits = a.get("visits") or []
                if not isinstance(raw_act_visits, list):
                    raw_act_visits = []

                # Resolve indices → visit names
                visit_names_for_act: List[str] = []
                for ref in raw_act_visits:
                    try:
                        idx = int(ref)
                        if idx in visit_map:
                            visit_names_for_act.append(visit_map[idx])
                    except (TypeError, ValueError):
                        # ref might be a visit name string directly
                        visit_names_for_act.append(_safe_str(ref))

                all_activities.append({
                    "name": act_name,
                    "category": section_title,
                    "visit_names": visit_names_for_act,  # resolved names
                    "visit_indices": [int(r) for r in raw_act_visits if str(r).isdigit()],
                })

    return {
        "study_id": study_id,
        "visit_map": visit_map,
        "visits": visits_out,
        "activities": all_activities,
    }


# ─── Step 2: AI maps activity names → cost_element codes ─────────────────────

def _build_mapping_prompt(activities: List[str], elements: List[Dict[str, str]]) -> str:
    """
    Ask AI ONLY to map activity names to cost element codes.
    AI must NOT generate costs, quantities, or budget totals.
    """
    acts_json = json.dumps(activities, ensure_ascii=False)
    els_json  = json.dumps(
        [{"code": e["code"], "name": e["name"], "cost_type": e.get("cost_type", "")} for e in elements],
        ensure_ascii=False,
    )
    return f"""You are mapping clinical trial SoA activities to a cost element library.

COST ELEMENT LIBRARY:
{els_json}

ACTIVITIES TO MAP:
{acts_json}

Return ONLY a JSON array. Each item must be:
{{
  "activity": "exact activity name from the list above",
  "element_code": "matching code from the library, or null if no match",
  "confidence": 0.0 to 1.0
}}

Rules:
- Match by semantic meaning (e.g. "Blood draw for PK" → PK-001)
- If no reasonable match exists, set element_code to null
- Do NOT invent codes not in the library
- Return ONLY the JSON array, no explanation"""


async def _call_gemini(prompt: str) -> str:
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    genai.configure(api_key=api_key)

    # Force deterministic generation so re-importing the same SOA gives the same
    # visit matrix (matters for SOA activity→element mapping and the follow-up
    # picker). Temperature=0 + top_p=1 + top_k=1 = greedy decoding.
    generation_config = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
    }

    for model_name in MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda m=model: m.generate_content(
                    prompt, generation_config=generation_config
                ),
            )
            if response and hasattr(response, "text") and response.text:
                logger.info("[SOA_MATRIX] Got response from %s (temp=0)", model_name)
                return response.text
        except Exception as exc:
            err = str(exc)
            logger.warning("[SOA_MATRIX] %s failed: %s", model_name, err)
            if "API key" in err or "API_KEY" in err:
                raise RuntimeError(f"Gemini API key error: {err}")
            continue

    raise RuntimeError("All Gemini models failed — check API key and quota")


def _extract_json_array(text: str) -> List[Any]:
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    end   = text.rfind("]")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract JSON array from: {text[:300]}")


def map_activities_to_elements(
    activity_names: List[str],
    elements: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """
    DB-only mapping. Uses deterministic string matching against the cost-element
    catalog already stored in Postgres. **No LLM calls.** Activities that cannot be
    resolved by string match are returned with element_code=None — the caller skips
    them in the matrix-apply step. (Used to fall back to a Gemini Phase 2; that path
    has been removed at the user's request to keep results 100% reproducible.)

    Returns list of {activity, element_code, confidence, match_source}.
    """
    if not activity_names or not elements:
        return [{"activity": a, "element_code": None, "confidence": 0.0, "match_source": "none"}
                for a in activity_names]

    # Phase 1 / only phase: string matching against the DB catalog.
    string_results = map_activities_string_matching(activity_names, elements)
    result_by_activity: Dict[str, Dict[str, Any]] = {r["activity"]: r for r in string_results}

    matched = sum(1 for r in string_results if r.get("element_code"))
    unmatched = len(activity_names) - matched
    logger.info(
        "[SOA_MATRIX] DB string-match: %d/%d activities mapped, %d unmatched (skipped)",
        matched, len(activity_names), unmatched,
    )

    # Return in the input order.
    return [result_by_activity[a] for a in activity_names]


# ─── Step 3: Build visit matrix plan ─────────────────────────────────────────

def build_matrix_plan(
    normalized: Dict[str, Any],
    mappings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Combine normalized SoA + AI mappings into a flat visit matrix plan.

    Returns list of:
    {
      visit_name: str,
      activity_name: str,
      element_code: str | None,
      quantity: int,        ← always 1 per occurrence
      confidence: float,
    }
    """
    # Build activity_name → element_code + confidence lookup
    mapping_lookup: Dict[str, Dict[str, Any]] = {}
    for m in mappings:
        mapping_lookup[m["activity"]] = m

    plan: List[Dict[str, Any]] = []

    for act in normalized["activities"]:
        act_name  = act["name"]
        visit_names = act["visit_names"]
        m = mapping_lookup.get(act_name, {})
        element_code = m.get("element_code")
        confidence   = float(m.get("confidence") or 0.0)

        if not visit_names:
            # Occurs at all visits
            visit_names = [v["visit_name"] for v in normalized["visits"]]

        for vname in visit_names:
            plan.append({
                "visit_name": vname,
                "activity_name": act_name,
                "element_code": element_code,
                "quantity": 1,
                "confidence": confidence,
                "match_source": m.get("match_source", "none"),
            })

    return plan


# ─── Main preview entry point ─────────────────────────────────────────────────

async def generate_matrix_preview(
    soa_doc: Dict[str, Any],
    elements: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    SoA doc + cost element library → visit matrix plan (preview, nothing written to DB).

    Returns:
    {
      study_id, visits, activities_count,
      matrix_plan: [{visit_name, activity_name, element_code, quantity, confidence}],
      unmapped: [activity names with no element_code]
    }
    """
    normalized = normalize_soa(soa_doc)

    activity_names = list({a["name"] for a in normalized["activities"]})
    logger.info(
        "[SOA_MATRIX] Mapping %d unique activities for study_id=%s",
        len(activity_names), normalized["study_id"],
    )

    mappings = map_activities_to_elements(activity_names, elements)
    plan     = build_matrix_plan(normalized, mappings)

    unmapped = [m["activity"] for m in mappings if not m["element_code"]]

    return {
        "study_id":         normalized["study_id"],
        "visits":           [v["visit_name"] for v in normalized["visits"]],
        "activities_count": len(activity_names),
        "matrix_plan":      plan,
        "unmapped":         unmapped,
        "mappings":         mappings,
    }


# ─── Policy document → Milestones ────────────────────────────────────────────

def _extract_policy_text(document_bytes: bytes, filename: Optional[str]) -> str:
    """Extract raw text from a PDF or DOCX policy document."""
    lower = (filename or "").lower()
    is_pdf = lower.endswith(".pdf") or document_bytes[:4] == b"%PDF"
    is_docx = lower.endswith(".docx") or lower.endswith(".doc")

    if is_pdf:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(document_bytes)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            if text.strip():
                return text
            logger.warning("[POLICY] pdfplumber returned empty text, trying PyPDF2")
        except Exception as e:
            logger.warning("[POLICY] pdfplumber failed: %s — trying PyPDF2", e)

        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(document_bytes))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            if text.strip():
                return text
        except Exception as e:
            raise ValueError(f"PDF text extraction failed: {e}")
        raise ValueError("PDF appears to be image-based or encrypted — no extractable text")

    if is_docx:
        try:
            from docx import Document
            doc = Document(io.BytesIO(document_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception as e:
            raise ValueError(f"DOCX text extraction failed: {e}")

    # Fallback: treat as UTF-8 text
    try:
        return document_bytes.decode("utf-8", errors="ignore")
    except Exception:
        raise ValueError("Unsupported document type — upload a PDF or DOCX")


_POLICY_PROMPT = """You are extracting country-specific pass-through milestones from one or more clinical-trial policy/regulatory documents for a single country.

Documents follow, separated by markers like `=== DOCUMENT N: filename.pdf ===`.

Return a JSON ARRAY of milestones. For each milestone, output:
{
  "name": short label (max 80 chars),
  "unit_cost": number in USD (use 0 when no amount is specified),
  "payment_trigger": when payment is due (max 120 chars, e.g. "Upon IRB approval")
}

Rules:
- Only return real milestones — fees, regulatory approvals, ethics submissions, site activation payments, audits, renewal fees, etc.
- Deduplicate identical milestones across multiple input documents.
- Amounts without a currency symbol are assumed USD; if amount is not stated, use 0.
- Return ONLY the JSON array. No markdown, no commentary, no trailing text.

DOCUMENT(S):
---
{{TEXT}}
---
"""


_CATALOG_PROMPT = """You are picking universal study-level pass-through milestones from a clinical-trial cost element catalog.

The catalog (provided as JSON) lists every cost element used by the budgeting system. Each entry has a code, name, category, cost_type, and base_unit_cost (USD).

Identify which entries are **universal milestones** — paid once per study (or per amendment / annually) regardless of country or site. Examples: IRB renewal, database lock, study close-out, screen-failure fee, SAE processing, pharmacy setup. Skip per-visit and per-patient procedures.

Return ONLY a JSON ARRAY of objects:
{
  "name": milestone label (you may use the catalog name, max 80 chars),
  "unit_cost": number in USD (use the catalog base_unit_cost, never invent),
  "payment_trigger": short phrase, max 120 chars (infer from name/category, e.g. "Upon IRB approval", "On database lock")
}

Rules:
- ONLY pick entries already in the catalog. Do not invent milestones.
- Skip anything that is naturally per-visit or per-patient (e.g. blood draws, vital signs, ECOG).
- 5–15 milestones is typical; do not return more than 25.
- Return ONLY the JSON array — no markdown, no prose.

CATALOG (JSON):
---
{{CATALOG}}
---
"""


async def generate_milestones_from_policy(
    documents: List[tuple[bytes, Optional[str]]],
) -> List[Dict[str, Any]]:
    """
    Extract text from one or more uploaded policy documents (already country-tagged by caller),
    concatenate, and ask Gemini to return a list of country-specific milestones.

    Returns dicts with keys: name, unit_cost, payment_trigger.
    Caller is responsible for stamping country_code when persisting.
    """
    if not documents:
        raise ValueError("No policy documents provided")

    chunks: List[str] = []
    for idx, (doc_bytes, fname) in enumerate(documents, start=1):
        text = _extract_policy_text(doc_bytes, fname).strip()
        if not text:
            logger.warning("[POLICY] extracted empty text from doc #%d (%s) — skipping", idx, fname)
            continue
        chunks.append(f"=== DOCUMENT {idx}: {fname or 'doc'} ===\n{text}")

    if not chunks:
        raise ValueError("Could not extract any text from the uploaded policy document(s)")

    combined = "\n\n".join(chunks)

    # Clip to keep Gemini prompt budget in check
    MAX_CHARS = 90_000
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS]

    prompt = _POLICY_PROMPT.replace("{{TEXT}}", combined)
    raw = await _call_gemini(prompt)
    items = _extract_json_array(raw)

    cleaned: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        try:
            unit_cost = float(it.get("unit_cost") or 0)
        except (TypeError, ValueError):
            unit_cost = 0.0
        cleaned.append({
            "name": name[:500],
            "unit_cost": round(unit_cost, 2),
            "payment_trigger": (str(it.get("payment_trigger") or "").strip() or None),
        })
    return cleaned


async def generate_milestones_from_catalog(
    catalog: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Send the full cost-element catalog to Gemini and ask which entries qualify as universal
    study-level milestones. The LLM picks 5–15 entries and returns name / unit_cost / payment_trigger.
    """
    if not catalog:
        raise ValueError("Cost element catalog is empty — seed it before generating milestones")

    catalog_json = json.dumps(catalog, separators=(",", ":"))
    prompt = _CATALOG_PROMPT.replace("{{CATALOG}}", catalog_json)
    raw = await _call_gemini(prompt)
    items = _extract_json_array(raw)

    cleaned: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        try:
            unit_cost = float(it.get("unit_cost") or 0)
        except (TypeError, ValueError):
            unit_cost = 0.0
        cleaned.append({
            "name": name[:500],
            "unit_cost": round(unit_cost, 2),
            "payment_trigger": (str(it.get("payment_trigger") or "").strip() or None),
        })
    return cleaned



# ─── Follow-up window picker (used by SOA importer to decide which FU visit to scale) ─

_FOLLOWUP_PICKER_PROMPT = """You are deciding which follow-up visits in a clinical-trial Schedule of Activities should be scaled when the user changes the trial's follow-up duration.

Only the SOA's follow-up-classified visits are listed below as JSON: name + day field text.

The user wants the trial's follow-up window to last {{WEEKS}} weeks.

Return a JSON ARRAY of visit name strings — the subset of the input visits that represent the user's PRIMARY follow-up window. The cells in those visits will be multiplied by (user_weeks / picked_visit_span). Visits NOT in your array are left unchanged.

Rules:
- Most SOAs have one short follow-up window (e.g. "Follow-up" at Day 30) and one long-term/survival window (e.g. "Long-term Follow-up" running for years). Pick the SHORT one — the long-term survival window should NOT be scaled.
- Multiple visit names may belong to the same primary window; include all of them.
- Return ONLY a JSON array of strings. No markdown, no commentary.
- If you cannot decide, return an empty array [].

VISITS:
---
{{VISITS}}
---
"""


async def pick_followup_visits(
    followup_visits: List[Dict[str, Any]],
    user_followup_weeks: int,
) -> List[str]:
    """
    Ask Gemini which of the supplied follow-up visits represent the user's intended
    follow-up window. Returns a list of visit names — a subset of the input. Defensive:
    drops any names the LLM hallucinates, and falls back to an empty list on error.
    """
    if not followup_visits:
        return []

    payload = [
        {"name": v.get("visit_name") or "", "day": v.get("target_day") or ""}
        for v in followup_visits
    ]
    prompt = (
        _FOLLOWUP_PICKER_PROMPT
        .replace("{{WEEKS}}", str(int(user_followup_weeks or 0)))
        .replace("{{VISITS}}", json.dumps(payload, separators=(",", ":")))
    )
    try:
        raw = await _call_gemini(prompt)
        items = _extract_json_array(raw)
    except Exception as e:
        logger.warning("[FOLLOWUP_PICKER] LLM call failed: %s - returning empty selection", e)
        return []

    valid_names = {v.get("visit_name") for v in followup_visits if v.get("visit_name")}
    picked: List[str] = []
    for it in items:
        name = it if isinstance(it, str) else (it.get("name") if isinstance(it, dict) else None)
        if isinstance(name, str) and name in valid_names and name not in picked:
            picked.append(name)
    return picked


# ─── Budget rules from policy (no-charge, exclusion rules per country) ────────

_BUDGET_RULES_PROMPT = """You are reading a clinical-trial budget policy document for {{COUNTRY}} and identifying TWO sets of cost elements:
  (A) elements that should be EXCLUDED from the sponsor's trial budget here (covered by another payer / standard of care / not charged), AND
  (B) elements that the policy MANDATES be INCLUDED in this country's budget (regulatory fees, country-specific mandatory items, baseline must-haves, etc.).

A policy may describe rules in different ways:
- by cost CATEGORY (e.g. "routine labs", "standard imaging", "Universal Baseline")
- by PAYER (e.g. "covered by NHS / Medicare / AOK / SUS / NHI / NFZ / PBS / ESI / private payer")
- by TYPE OF CARE (e.g. "standard of care", "routine clinical procedures", "non-research procedures")
- by SPECIFIC NAME (e.g. "12-lead ECG", "Medicare Coverage Analysis", "Pharmacy Setup Fee")

Trial's cost elements already present (one per line; copy element names VERBATIM when used — keep all punctuation, casing, and trailing markers like "*1*" or "*2*" exactly):
{{ELEMENTS}}

Return a JSON ARRAY of objects, each shaped like:
{
  "element_name": "<verbatim catalog name OR a clean new name if the policy mandates an item not yet in the list>",
  "action": "exclude" | "include",
  "destination": "visit_matrix" | "milestone",
  "reason": "<short reason grounded in policy wording (quote or paraphrase the relevant policy line, max 120 chars)>"
}

How to decide ACTION:
- "exclude" — the policy says this item is NOT charged to the sponsor here (SoC, covered by national health insurance, billed elsewhere, routine care).
- "include" — the policy EXPLICITLY MANDATES this item in the country's budget (must include / mandatory inclusion / required by regulation / required pass-through). If the policy lists it in an INCLUSIONS / BUDGETABLE / IN-SCOPE / "must include" / mandatory section, return it as include. If the policy only describes an item softly (e.g. "may include", "consider", "recommended"), do NOT mark it as include.

How to decide DESTINATION (for "include" actions only — for "exclude" always use "visit_matrix"):
- "visit_matrix" — the item is a RECURRING PER-VISIT clinical procedure that appears in the Schedule of Activities (SOA) grid. Examples: Tumor Imaging, Informed Consent, AE Monitoring, blood draws, physical exam, biomarker collection, protocol-required assessments. These appear as rows in the visit matrix.
- "milestone" — the item is a ONE-TIME or MILESTONE-TRIGGERED cost: startup fees, close-out fees, regulatory submission fees, per-patient pass-throughs paid at a milestone, screen failure reimbursements, pharmacy setup, IRB fees, travel reimbursements, sample shipping, archiving fees, data-query resolution effort. Key signal: the policy refers to it as payable "within Milestone X", "upon IRB approval", "upon study close-out", or "per patient enrolled". These belong in the Milestones section, NOT the visit matrix.

Rules:
- For excludes: map the policy's exclusion categories to specific elements ONLY when there is a clear semantic match — avoid over-expansion. If a category is ambiguous or the element only loosely fits, leave it as is.
- For includes: prefer reusing an existing catalog name if the meaning matches; only invent a new name if the policy specifies a country-mandatory item that has no equivalent in the trial list yet (e.g. "Medicare Coverage Analysis Fee", "Ethics Committee Submission Fee — country specific"). When reusing a catalog name, copy it verbatim (case + punctuation + trailing markers).
- INCLUDE never overrides EXCLUDE. Treat them as separate lists. The same element_name may NOT appear in both lists.
- Match SEMANTICALLY (not by literal string). Translate categories to specific catalog names.
- Routine clinical procedures (Vital Signs, Physical Exam, ECOG, ECG, Height/Weight, Pregnancy Test) typically count as standard of care unless the policy explicitly includes them.
- For ONCOLOGY trials specifically: Tumor Imaging, RECIST, Biopsies, Archival/Fresh Tumor Tissue, PK, Biomarkers, ADA, protocol-required scans are research-specific — do NOT exclude unless the policy explicitly says so.
- Do NOT exclude research-specific items: Informed Consent, Inclusion/Exclusion Criteria, Medical History at screening, PK samples, biomarkers, study-drug administration, archival tissue, IRB / regulatory fees, monitoring, pass-through fees, screen-failure fees, dose modifications, adverse events.
- Do NOT invent rules the policy didn't state. If a category is ambiguous, leave it as is.

If the policy contains NO rules whatsoever, return [].
Return ONLY the JSON array. No markdown, no prose, no trailing text.

POLICY DOCUMENT(S):
---
{{TEXT}}
---
"""


async def extract_budget_rules_from_policy(
    documents: List[tuple[bytes, Optional[str]]],
    country_code: str,
    available_element_names: List[str],
) -> List[Dict[str, Any]]:
    """
    Read the country's policy documents and return a list of {element_name, action, reason}
    rules. Currently only supports `action="exclude"` (cost element not charged in country).
    Caller is responsible for applying rules to the COUNTRY budget template.
    """
    if not documents:
        raise ValueError("No policy documents provided")
    if not available_element_names:
        return []

    chunks: List[str] = []
    for idx, (doc_bytes, fname) in enumerate(documents, start=1):
        text = _extract_policy_text(doc_bytes, fname).strip()
        if not text:
            logger.warning("[BUDGET_RULES] empty extract from doc #%d (%s)", idx, fname)
            continue
        chunks.append(f"=== DOCUMENT {idx}: {fname or 'doc'} ===\n{text}")
    if not chunks:
        raise ValueError("Could not extract any text from the uploaded policy document(s)")

    combined = "\n\n".join(chunks)
    MAX_CHARS = 90_000
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS]

    elements_listing = "\n".join(f"- {n}" for n in available_element_names)
    prompt = (
        _BUDGET_RULES_PROMPT
        .replace("{{COUNTRY}}", country_code)
        .replace("{{ELEMENTS}}", elements_listing)
        .replace("{{TEXT}}", combined)
    )
    raw = await _call_gemini(prompt)
    items = _extract_json_array(raw)

    valid_lower = {n.lower(): n for n in available_element_names}

    def _resolve_to_catalog_name(s: str) -> Optional[str]:
        """Try exact (case-insensitive) match first, then substring fuzzy match."""
        s = (s or "").strip()
        if not s:
            return None
        # 1. Exact case-insensitive
        hit = valid_lower.get(s.lower())
        if hit:
            return hit
        # 2. Substring either direction
        s_low = s.lower()
        # Score each candidate; pick the best match (highest containment ratio).
        best = None
        best_score = 0.0
        for cand_low, cand in valid_lower.items():
            if s_low in cand_low or cand_low in s_low:
                # Score = length of shorter string / longer string  ∈ (0, 1]
                shorter = min(len(s_low), len(cand_low))
                longer = max(len(s_low), len(cand_low))
                score = shorter / max(longer, 1)
                if score > best_score:
                    best_score = score
                    best = cand
        return best if best_score >= 0.5 else None

    rules: List[Dict[str, Any]] = []
    seen_excludes: set = set()
    seen_includes: set = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        nm = str(it.get("element_name") or "").strip()
        if not nm:
            continue
        action = str(it.get("action") or "exclude").strip().lower()
        if action not in ("exclude", "include"):
            continue
        reason = (str(it.get("reason") or "").strip() or None)

        destination = str(it.get("destination") or "visit_matrix").strip().lower()
        if destination not in ("visit_matrix", "milestone"):
            destination = "visit_matrix"

        if action == "exclude":
            # Exclusions must reference an existing catalog element.
            canonical = _resolve_to_catalog_name(nm)
            if not canonical or canonical in seen_excludes:
                continue
            seen_excludes.add(canonical)
            rules.append({"element_name": canonical, "action": "exclude", "destination": "visit_matrix", "reason": reason})
        else:
            # Inclusions: try to reuse an existing catalog name; if none matches, keep
            # the LLM-provided name verbatim so the route can auto-create a new element.
            canonical = _resolve_to_catalog_name(nm) or nm[:255]
            if canonical in seen_includes:
                continue
            seen_includes.add(canonical)
            rules.append({"element_name": canonical, "action": "include", "destination": destination, "reason": reason})
    return rules
