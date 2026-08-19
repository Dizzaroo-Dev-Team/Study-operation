"""Render confirmation letter plain text as styled HTML (UI + email)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import List, Optional

_SEPARATOR_RE = re.compile(r"^[-=]{4,}\s*$")
_SECTION_RE = re.compile(r"^(\d++)\)\s++(.+)$")
_BULLET_RE = re.compile(r"^(\s*+)(?:•|-)\s++(.+)$")

_SECTION_ACCENTS = {
    "visit logistics": "#2563eb",
    "personnel availability": "#7c3aed",
    "visit agenda and objectives": "#0d9488",
    "pre-visit preparation": "#d97706",
}


@dataclass
class _HeaderField:
    label: str
    value: str


@dataclass
class _ListItem:
    text: str
    indent: int


@dataclass
class _Section:
    title: str
    intro: Optional[str] = None
    items: List[_ListItem] = field(default_factory=list)


@dataclass
class ParsedConfirmationLetter:
    header_fields: List[_HeaderField] = field(default_factory=list)
    salutation: str = ""
    intro_paragraphs: List[str] = field(default_factory=list)
    sections: List[_Section] = field(default_factory=list)
    acknowledgment_title: str = ""
    acknowledgment_body: str = ""
    signature_lines: List[str] = field(default_factory=list)


def _is_header_field_line(line: str) -> bool:
    t = line.strip()
    if not t or _SEPARATOR_RE.match(t):
        return False
    if re.match(r"^Dear\s", t, re.I):
        return False
    if _SECTION_RE.match(t):
        return False
    if _BULLET_RE.match(line):
        return False
    return bool(re.match(r"^[^:]++:\s*+.+$", t))


def _parse_header_field(line: str) -> _HeaderField:
    idx = line.find(":")
    if idx < 0:
        return _HeaderField(label="", value=line.strip())
    return _HeaderField(label=line[:idx].strip(), value=line[idx + 1 :].strip())


def parse_confirmation_letter(text: str) -> ParsedConfirmationLetter:
    lines = (text or "").replace("\r\n", "\n").split("\n")
    result = ParsedConfirmationLetter()
    phase = "header"
    paragraph_buf: List[str] = []
    current_section: Optional[_Section] = None

    def flush_paragraph() -> None:
        nonlocal paragraph_buf
        if not paragraph_buf:
            return
        p = " ".join(paragraph_buf).strip()
        paragraph_buf = []
        if not p:
            return
        if current_section is not None and not current_section.intro and not current_section.items:
            current_section.intro = p
        elif not result.salutation and phase == "body" and not current_section and not result.sections:
            result.intro_paragraphs.append(p)
        elif current_section is not None:
            current_section.items.append(_ListItem(text=p, indent=0))
        else:
            result.intro_paragraphs.append(p)

    def close_section() -> None:
        nonlocal current_section
        flush_paragraph()
        if current_section is not None:
            result.sections.append(current_section)
            current_section = None

    for raw in lines:
        line = raw.rstrip()
        trimmed = line.strip()
        if not trimmed:
            flush_paragraph()
            continue
        if _SEPARATOR_RE.match(trimmed):
            continue

        if phase == "signature":
            result.signature_lines.append(trimmed)
            continue

        if re.match(r"^Sincerely,?\s*$", trimmed, re.I):
            close_section()
            phase = "signature"
            result.signature_lines.append("Sincerely,")
            continue

        if phase == "header":
            if re.match(r"^Dear\s", trimmed, re.I):
                result.salutation = trimmed
                phase = "body"
                continue
            if _is_header_field_line(trimmed):
                result.header_fields.append(_parse_header_field(trimmed))
                continue
            phase = "body"

        if re.match(r"^Dear\s", trimmed, re.I):
            close_section()
            result.salutation = trimmed
            continue

        if re.match(r"^Acknowledgment\s*$", trimmed, re.I):
            close_section()
            result.acknowledgment_title = "Acknowledgment"
            continue

        sec_match = _SECTION_RE.match(trimmed)
        if sec_match:
            close_section()
            current_section = _Section(title=sec_match.group(2).strip())
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            flush_paragraph()
            indent = len(bullet_match.group(1)) // 2
            item = _ListItem(text=bullet_match.group(2).strip(), indent=indent)
            if current_section is not None:
                current_section.items.append(item)
            else:
                result.intro_paragraphs.append(f"• {item.text}")
            continue

        if result.acknowledgment_title and current_section is None:
            if result.acknowledgment_body:
                result.acknowledgment_body += f" {trimmed}"
            else:
                result.acknowledgment_body = trimmed
            continue

        paragraph_buf.append(trimmed)

    close_section()
    flush_paragraph()
    return result


def _section_accent(title: str) -> str:
    key = title.lower()
    for fragment, color in _SECTION_ACCENTS.items():
        if fragment in key:
            return color
    return "#475569"


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def build_confirmation_letter_html(text: str, *, compact: bool = False) -> str:
    """Turn rendered letter text into email-safe HTML."""
    parsed = parse_confirmation_letter(text)
    pad = "14px 16px" if compact else "16px 18px"

    header_html = ""
    if parsed.header_fields:
        rows = []
        fields = parsed.header_fields
        for i in range(0, len(fields), 2):
            left = (
                f'<td style="width:50%;vertical-align:top;padding:6px 8px;">'
                f'<div style="font-size:10px;font-weight:600;text-transform:uppercase;'
                f'letter-spacing:0.06em;color:#64748b;margin-bottom:4px;">{_esc(fields[i].label)}</div>'
                f'<div style="font-size:13px;color:#1e293b;font-weight:500;">{_esc(fields[i].value or "—")}</div></td>'
            )
            right = ""
            if i + 1 < len(fields):
                right = (
                    f'<td style="width:50%;vertical-align:top;padding:6px 8px;">'
                    f'<div style="font-size:10px;font-weight:600;text-transform:uppercase;'
                    f'letter-spacing:0.06em;color:#64748b;margin-bottom:4px;">{_esc(fields[i + 1].label)}</div>'
                    f'<div style="font-size:13px;color:#1e293b;font-weight:500;">{_esc(fields[i + 1].value or "—")}</div></td>'
                )
            else:
                right = '<td style="width:50%;"></td>'
            rows.append(f"<tr>{left}{right}</tr>")
        header_html = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin-bottom:24px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">'
            f'<tr><td style="padding:{pad};"><table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" border="0">{"".join(rows)}</table></td></tr></table>'
        )

    intro_html = "".join(
        f'<p style="margin:0 0 14px;font-size:13px;line-height:1.75;color:#475569;">{_esc(p)}</p>'
        for p in parsed.intro_paragraphs
    )

    sections_html = ""
    for sec in parsed.sections:
        accent = _section_accent(sec.title)
        items_html = "".join(
            f'<li style="margin:0 0 8px {it.indent * 12}px;color:#334155;font-size:13px;line-height:1.65;">'
            f"{_esc(it.text)}</li>"
            for it in sec.items
        )
        intro_block = (
            f'<p style="margin:0 0 12px;font-size:13px;line-height:1.7;color:#475569;">{_esc(sec.intro)}</p>'
            if sec.intro
            else ""
        )
        list_block = (
            f'<ul style="margin:0;padding-left:20px;">{items_html}</ul>' if items_html else ""
        )
        sections_html += (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin-bottom:18px;border-left:4px solid {accent};background:#ffffff;'
            f'border:1px solid #e2e8f0;border-radius:0 10px 10px 0;">'
            f'<tr><td style="padding:{pad};">'
            f'<h3 style="margin:0 0 10px;font-size:14px;font-weight:700;color:{accent};">{_esc(sec.title)}</h3>'
            f"{intro_block}{list_block}</td></tr></table>"
        )

    ack_html = ""
    if parsed.acknowledgment_title:
        ack_html = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin-bottom:18px;border-left:4px solid #059669;background:#f0fdf4;'
            f'border:1px solid #bbf7d0;border-radius:0 10px 10px 0;">'
            f'<tr><td style="padding:{pad};">'
            f'<h3 style="margin:0 0 8px;font-size:14px;font-weight:700;color:#059669;">'
            f"{_esc(parsed.acknowledgment_title)}</h3>"
            f'<p style="margin:0;font-size:13px;line-height:1.7;color:#475569;">'
            f"{_esc(parsed.acknowledgment_body)}</p></td></tr></table>"
        )

    sig_html = ""
    if parsed.signature_lines:
        sig_parts = []
        for i, line in enumerate(parsed.signature_lines):
            if i == 0:
                style = "margin:0 0 12px;font-size:13px;color:#64748b;"
            elif i == 1:
                style = "margin:0 0 4px;font-size:15px;font-weight:700;color:#1e293b;"
            else:
                style = "margin:0 0 4px;font-size:13px;color:#475569;"
            sig_parts.append(f'<p style="{style}">{_esc(line)}</p>')
        sig_html = (
            f'<div style="margin-top:28px;padding-top:18px;border-top:1px solid #e2e8f0;">'
            f"{''.join(sig_parts)}</div>"
        )

    salutation_html = (
        f'<p style="margin:0 0 16px;font-size:14px;font-weight:600;color:#1e293b;">'
        f"{_esc(parsed.salutation)}</p>"
        if parsed.salutation
        else ""
    )

    banner = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin-bottom:24px;border-bottom:2px solid #e2e8f0;">'
        '<tr><td style="padding-bottom:18px;">'
        '<div style="font-size:18px;font-weight:700;color:#0f172a;">Confirmation of Monitoring Visit</div>'
        '<div style="font-size:12px;color:#64748b;margin-top:6px;">Formal notice to the investigative site</div>'
        "</td></tr></table>"
    )

    return (
        f'<div style="font-family:Arial,Helvetica,sans-serif;color:#1e293b;max-width:720px;">'
        f"{banner}{header_html}{salutation_html}{intro_html}{sections_html}{ack_html}{sig_html}"
        f"</div>"
    )
