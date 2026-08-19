"""Minimal stdlib-only sanitizer for inbound webhook content.

This is *defense in depth*. The frontend is the authoritative sanitizer
(DOMPurify) at render time. This module exists so that even if a render
site forgets DOMPurify, the worst-cased payload stored in Mongo is
already neutered.

Two helpers:
- `escape_plaintext(s)`  : for fields that should NEVER contain HTML
                          (subject, sender, recipient, body_plain).
- `strip_dangerous_html(s)`: for fields that ARE HTML (stripped_html).
                            Removes <script>/<style>/<iframe>/<object>/<embed>
                            blocks, `javascript:` URLs, and `on*=` attributes.
"""
from __future__ import annotations

import html
import re
from typing import Optional

# Block-level tags whose content we strip entirely (tag + body).
_BLOCK_STRIP = re.compile(
    r"<\s*(script|style|iframe|object|embed|noscript|frame|frameset)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Self-closing dangerous tags.
_VOID_STRIP = re.compile(
    r"<\s*(script|style|iframe|object|embed|noscript|frame|link|meta)\b[^>]*/?>",
    re.IGNORECASE,
)
# `on*=` event handler attributes.
_EVENT_ATTR = re.compile(r"\son\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]*)", re.IGNORECASE)
# `javascript:` / `vbscript:` / `data:text/html` URLs in href/src/etc.
# The data: URL form is `data:text/html,...`, no second colon — so it gets
# its own branch separate from javascript:/vbscript: which DO take a colon.
_JS_URL_IN_ATTR = re.compile(
    r"(\s(?:href|src|action|formaction|xlink:href)\s*=\s*[\"'])\s*"
    r"(?:(?:javascript|vbscript)\s*:|data\s*:\s*text/html\b)"
    r"[^\"']*([\"'])",
    re.IGNORECASE,
)


def escape_plaintext(value: Optional[str]) -> str:
    """Escape HTML special chars and normalize None to empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def strip_dangerous_html(value: Optional[str]) -> str:
    """Remove script/style/iframe/object/embed blocks, on*= attrs, and
    javascript:/vbscript:/data:text/html URLs. Returns the result.

    This is NOT a full HTML sanitizer — DOMPurify on the frontend is the
    authoritative pass. Treat this as a coarse safety net.
    """
    if not value:
        return ""
    out = _BLOCK_STRIP.sub("", value)
    out = _VOID_STRIP.sub("", out)
    out = _EVENT_ATTR.sub("", out)
    out = _JS_URL_IN_ATTR.sub(r"\1#blocked\2", out)
    return out
