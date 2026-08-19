from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
except Exception:
    HAS_PDFPLUMBER = False

try:
    import PyPDF2

    HAS_PYPDF2 = True
except Exception:
    HAS_PYPDF2 = False


PROTOCOL_PATTERNS = [
    r"\bMK[-\s]?\d{4}(?:[-\s]\d+)*\b",
    r"\bDS[-\s]?\d{4}(?:[-\s][A-Z0-9]+)*\b",
    r"\bDESTINY[-\s][A-Za-z]+\d+\b",
    r"\b[A-Z]{2,6}[-\s]\d{3,6}(?:[-\s][A-Z0-9]+)*\b",
]

PURPOSE_SECTION_MARKERS = [
    "protocol summary",
    "study rationale",
    "study objectives",
    "purpose of the study",
    "objectives and purpose",
    "primary objective",
    "study overview",
    "synopsis",
    "background and rationale",
]

VERSION_PATTERNS = [
    r"(?:Protocol\s+)?Version\s*[:\-]?\s*(\d+(?:\.\d+)*)",
    r"v(?:er(?:sion)?)?\s*\.?\s*(\d+(?:\.\d+)+)",
    r"Amendment\s+(\d+(?:\.\d+)?)",
]

DATE_PATTERNS = [
    r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b",
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})\b",
    r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2})\b",
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2})\b",
    r"\b(\d{1,2}/\d{1,2}/20\d{2})\b",
]


def _extract_text_pdfplumber(pdf_path: str, max_pages: int) -> str:
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                pages_text.append(f"\n--- PAGE {i + 1} ---\n{text}")
    return "\n".join(pages_text)


def _extract_text_pypdf2(pdf_path: str, max_pages: int) -> str:
    pages_text = []
    with open(pdf_path, "rb") as fh:
        reader = PyPDF2.PdfReader(fh)
        for i in range(min(max_pages, len(reader.pages))):
            text = reader.pages[i].extract_text() or ""
            pages_text.append(f"\n--- PAGE {i + 1} ---\n{text}")
    return "\n".join(pages_text)


def extract_text(pdf_path: str, max_pages: int = 5) -> str:
    if HAS_PDFPLUMBER:
        try:
            return _extract_text_pdfplumber(pdf_path, max_pages)
        except Exception:
            pass
    if HAS_PYPDF2:
        return _extract_text_pypdf2(pdf_path, max_pages)
    raise RuntimeError("No supported PDF extraction library available")


def _clean_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.replace("\r", "\n")
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    cleaned = re.sub(r"-\s*\n\s*", "", cleaned)
    cleaned = re.sub(r"[^\S\n]*+\n\s*+", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or None


def _find_protocol_number(text: str) -> Optional[str]:
    labelled = re.search(
        r"(?:Protocol\s++(?:Number|No\.?+|ID|Code|Title)\s*+[:\-]?+\s*+)([A-Z0-9][A-Z0-9\-/\s]{3,30})",
        text,
        re.IGNORECASE,
    )
    if labelled:
        candidate = labelled.group(1).strip().split("\n")[0].strip()
        if len(candidate) >= 4:
            return candidate
    for pattern in PROTOCOL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _find_study_title(text: str) -> Optional[str]:
    labelled = re.search(
        r"(?:^|\n)\s*(?:Study\s+)?Title\s*[:\-]\s*(.+?)(?=\n\s*\n|\n[A-Z][A-Z]|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if labelled:
        title = " ".join(labelled.group(1).split())
        if 20 <= len(title) <= 600:
            return title
    phase_match = re.search(
        r"(?:a\s++)?(?:phase\s++[I1-4IViv/]++[a-z]*+,?\s+.{15,400}?)(?:study|trial|investigation|evaluation)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if phase_match:
        title = " ".join(phase_match.group(0).split())
        if 20 <= len(title) <= 600:
            return title
    return None


def _find_study_description(text: str) -> Optional[str]:
    text_lower = text.lower()
    for marker in PURPOSE_SECTION_MARKERS:
        idx = text_lower.find(marker)
        if idx == -1:
            continue
        window = text[idx : idx + 1500]
        lines = window.split("\n")
        body_lines = [l.strip() for l in lines[1:] if l.strip()]
        body = " ".join(body_lines)
        sentences = re.split(r"(?<=[.!?])\s+", body)
        good = [s for s in sentences if len(s) > 40 and not re.match(r"^\d+\.", s)]
        if good:
            excerpt = " ".join(good[:3]).strip()
            if len(excerpt) > 60:
                return excerpt
    broad = re.findall(
        r"(?:This|The)\s+study\s+(?:is\s+)?(?:designed\s+to\s+|aims?\s+to\s+|evaluates?\s+|investigates?\s+).{40,300}?\.",
        text,
        re.IGNORECASE,
    )
    if broad:
        return " ".join(broad[:2]).strip()
    return None


def _find_version_and_date(text: str) -> Tuple[Optional[str], Optional[str]]:
    version: Optional[str] = None
    date: Optional[str] = None
    for line in text.split("\n"):
        line_lower = line.lower()
        if "version" in line_lower or "amendment" in line_lower:
            for vp in VERSION_PATTERNS:
                vm = re.search(vp, line, re.IGNORECASE)
                if vm and not version:
                    version = vm.group(1).strip()
            for dp in DATE_PATTERNS:
                dm = re.search(dp, line, re.IGNORECASE)
                if dm and not date:
                    date = dm.group(1).strip()
    if not version:
        for vp in VERSION_PATTERNS:
            vm = re.search(vp, text, re.IGNORECASE)
            if vm:
                version = vm.group(1).strip()
                break
    if not date:
        for dp in DATE_PATTERNS:
            dm = re.search(dp, text, re.IGNORECASE)
            if dm:
                date = dm.group(1).strip()
                break
    return version, date


def extract_metadata(pdf_path: str, max_pages: int = 5) -> Dict[str, Any]:
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    text = extract_text(pdf_path, max_pages=max_pages)
    if not text.strip():
        raise ValueError("No text could be extracted from PDF.")
    protocol_number = _clean_text(_find_protocol_number(text))
    study_title = _clean_text(_find_study_title(text))
    study_description = _clean_text(_find_study_description(text))
    version, date = _find_version_and_date(text)
    result: Dict[str, Any] = {
        "protocol_number": protocol_number,
        "study_title": study_title,
        "study_description": study_description,
        "version": _clean_text(version),
        "date": _clean_text(date),
    }
    result["_missing_fields"] = [k for k in ("protocol_number", "study_title", "study_description", "version", "date") if not result.get(k)]
    return result

