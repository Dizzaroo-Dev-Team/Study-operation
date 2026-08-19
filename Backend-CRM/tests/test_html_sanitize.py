"""Tests for app/utils/html_sanitize.py - inbound-webhook sanitizer.

Defense-in-depth pass: the frontend's DOMPurify is the authoritative
sanitizer, but anything stored in Mongo from a webhook MUST already be
neutered for the worst cases.
"""
from __future__ import annotations

from app.utils.html_sanitize import escape_plaintext, strip_dangerous_html


# ── escape_plaintext ─────────────────────────────────────────────────────────

def test_escape_plaintext_basic():
    assert escape_plaintext("<b>hi</b>") == "&lt;b&gt;hi&lt;/b&gt;"


def test_escape_plaintext_quotes():
    assert escape_plaintext('Hello "world" & friends') == "Hello &quot;world&quot; &amp; friends"


def test_escape_plaintext_none_to_empty():
    assert escape_plaintext(None) == ""


def test_escape_plaintext_neutralizes_script_tag():
    out = escape_plaintext("<script>alert('xss')</script>")
    assert "<script" not in out
    assert "&lt;script" in out


# ── strip_dangerous_html ─────────────────────────────────────────────────────

def test_strip_removes_script_block():
    html = "<p>hello</p><script>steal()</script><p>bye</p>"
    out = strip_dangerous_html(html)
    assert "<script" not in out.lower()
    assert "steal" not in out  # body is gone too
    assert "<p>hello</p>" in out
    assert "<p>bye</p>" in out


def test_strip_removes_style_block():
    html = "<style>body{display:none}</style><p>ok</p>"
    out = strip_dangerous_html(html)
    assert "<style" not in out.lower()
    assert "<p>ok</p>" in out


def test_strip_removes_iframe():
    html = '<iframe src="https://evil"></iframe><p>ok</p>'
    out = strip_dangerous_html(html)
    assert "<iframe" not in out.lower()
    assert "<p>ok</p>" in out


def test_strip_removes_onclick_attr():
    html = '<a href="https://x.test" onclick="steal()">click</a>'
    out = strip_dangerous_html(html)
    assert "onclick" not in out.lower()
    assert 'href="https://x.test"' in out


def test_strip_removes_onerror_attr():
    html = '<img src="x" onerror="alert(1)">'
    out = strip_dangerous_html(html)
    assert "onerror" not in out.lower()


def test_strip_blocks_javascript_url():
    html = '<a href="javascript:alert(1)">go</a>'
    out = strip_dangerous_html(html)
    assert "javascript:" not in out.lower()
    assert "#blocked" in out


def test_strip_blocks_vbscript_url():
    html = '<a href="VBscript:foo">go</a>'
    out = strip_dangerous_html(html)
    assert "vbscript:" not in out.lower()


def test_strip_blocks_data_text_html_url():
    html = '<a href="data:text/html,<script>x</script>">go</a>'
    out = strip_dangerous_html(html)
    assert "data:text/html" not in out.lower()


def test_strip_handles_none_or_empty():
    assert strip_dangerous_html(None) == ""
    assert strip_dangerous_html("") == ""


def test_strip_preserves_safe_html():
    html = "<p>hello <b>world</b></p>"
    assert strip_dangerous_html(html) == html


def test_strip_removes_meta_refresh():
    html = '<meta http-equiv="refresh" content="0;url=https://evil"><p>ok</p>'
    out = strip_dangerous_html(html)
    assert "<meta" not in out.lower()
