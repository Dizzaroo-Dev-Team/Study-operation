"""PHI / record-content guard for derived memory.

The critical adaptation over generic memory: an item may ONLY be written if it is
a concise, non-sensitive fact about how the user works. Anything that looks like
patient/subject data, a specific record's contents, or clinical detail must be
skipped BEFORE it is ever persisted.

This runs at derivation time (off the request path) as the last gate before a
write. It is deliberately conservative: when in doubt, reject. Losing a borderline
useful memory is fine; leaking PHI is not.

The filter is heuristic (regex + keyword), not a classifier — it never sees the
network. The distiller prompt is *also* instructed to avoid PHI; this is the
belt-and-suspenders that does not trust the model.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Signals that an item is (or references) protected / record content.
# ---------------------------------------------------------------------------

# Direct identifiers & contact data.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\s\-().]?){7,}\d(?!\w)")
# US SSN / MRN-ish long digit runs.
_LONG_NUMBER = re.compile(r"(?<!\w)\d{6,}(?!\w)")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DATE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
)

# Clinical / subject vocabulary — a derived *preference* never needs these.
_CLINICAL_TERMS = re.compile(
    r"\b("
    r"patient|patients|subject|subjects|participant id|enroll|enrolled|enrollment|"
    r"diagnos|diagnosis|diagnosed|adverse event|\bae\b|\bsae\b|dose|dosing|mg\b|"
    r"biopsy|tumou?r|lesion|specimen|lab result|labs?\b|vitals?|"
    r"date of birth|\bdob\b|\bmrn\b|\bssn\b|medical record|randomi[sz]|"
    r"screening id|visit \d|blood|serum|plasma|histolog|pathology|oncolog"
    r")\b",
    re.IGNORECASE,
)

# Phrases that mark the text as a record's *content* rather than a habit.
_RECORD_CONTENT = re.compile(
    r"\b(said|wrote|replied|the (message|note|comment|email) (says|reads|is))\b",
    re.IGNORECASE,
)

# A derived item should be a SHORT phrase. Anything long is probably a transcript
# fragment, not a distilled fact.
_MAX_LEN = 200


def looks_like_phi(text: str) -> bool:
    """True if `text` shows any sign of PHI / record content and must be skipped."""
    if not text:
        return False
    t = text.strip()
    if len(t) > _MAX_LEN:
        return True
    for pat in (_EMAIL, _PHONE, _SSN, _LONG_NUMBER, _DATE, _CLINICAL_TERMS, _RECORD_CONTENT):
        if pat.search(t):
            return True
    return False


def is_safe_memory(text: str) -> bool:
    """A memory item is safe iff it's a non-empty, concise, PHI-free phrase."""
    if not text or not text.strip():
        return False
    return not looks_like_phi(text)


# ---------------------------------------------------------------------------
# Redaction (live-eval judge gate). Unlike the boolean gate above — which
# REJECTS whole candidates — this SCRUBS direct identifiers out of text that
# must leave the box (e.g. answer/evidence sent to the LLM judge). It reuses
# the same compiled patterns so there is one source of truth for what counts
# as an identifier. Deliberately identifier-focused: emails, phones, SSN,
# long numeric ids, dates, and subject/patient labels get placeholders;
# general clinical vocabulary stays (it isn't identifying on its own and
# removing it would make grounding judgments meaningless).
# ---------------------------------------------------------------------------

_SUBJECT_LABEL = re.compile(r"\b(subject|patient|participant)\s*#?\s*[\w-]+\b", re.IGNORECASE)

_SCRUB_ORDER = (
    ("EMAIL", _EMAIL),
    ("SSN", _SSN),
    ("PHONE", _PHONE),
    ("SUBJECT-ID", _SUBJECT_LABEL),
    ("DATE", _DATE),
    ("NUMBER", _LONG_NUMBER),
)


def scrub_text(text: str) -> str:
    """Replace direct identifiers with [REDACTED-<kind>] placeholders."""
    if not text:
        return ""
    out = text
    for kind, pattern in _SCRUB_ORDER:
        out = pattern.sub(f"[REDACTED-{kind}]", out)
    return out


# Study codes worth keeping as a *reference* (e.g. "MK-6482", "BREAST-DP-01").
# Uppercase-alnum with a dash — deliberately narrow so free text isn't captured.
_STUDY_CODE = re.compile(r"\b[A-Z]{1,6}-?\d{2,6}[A-Z0-9-]*\b")


def extract_study_reference(text: str) -> str | None:
    """Pull a study-code-shaped token from a `context` item, if any. Returned as
    an opaque reference to be RE-VALIDATED against entitlements at load — never
    surfaced blindly."""
    if not text:
        return None
    m = _STUDY_CODE.search(text)
    return m.group(0) if m else None
