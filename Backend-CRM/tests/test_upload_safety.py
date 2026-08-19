"""Tests for app/utils/upload_safety.py - the shared upload validator.

Covers:
- Extension allow/deny
- Declared mime-type allow/deny
- 25 MB hard streaming cap with partial-file cleanup
- Magic-byte sniffing for image/pdf/office/zip/ole families
- Mismatch between declared mime and actual file bytes
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import HTTPException

from app.utils.upload_safety import (
    MAX_UPLOAD_BYTES,
    stream_to_disk_safely,
    validate_upload_metadata,
    verify_magic_bytes,
)


@pytest.fixture(autouse=True)
def _upload_root_is_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """stream_to_disk_safely / verify_magic_bytes refuse paths outside
    settings.upload_dir (CWE-22 containment guard) — point the root at this
    test's tmp dir so the doubles below stay contained."""
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


# ── Test doubles ─────────────────────────────────────────────────────────────

class _FakeUploadFile:
    """Minimal stand-in for fastapi.UploadFile that exposes `.file`, `.filename`,
    and `.content_type`. Real UploadFile pulls from `starlette.datastructures`
    which is overkill for these unit tests."""

    def __init__(self, *, data: bytes, filename: Optional[str], content_type: Optional[str]):
        self.file = io.BytesIO(data)
        self.filename = filename
        self.content_type = content_type


# ── validate_upload_metadata ─────────────────────────────────────────────────

def test_validate_accepts_pdf():
    f = _FakeUploadFile(data=b"%PDF-1.4\n", filename="report.pdf", content_type="application/pdf")
    validate_upload_metadata(f)  # should not raise


def test_validate_accepts_docx_with_octet_stream():
    """Browsers sometimes send octet-stream for office docs; we allow that
    pairing and rely on magic-byte sniff downstream."""
    f = _FakeUploadFile(data=b"PK\x03\x04", filename="contract.docx", content_type="application/octet-stream")
    validate_upload_metadata(f)


def test_validate_rejects_unknown_extension():
    f = _FakeUploadFile(data=b"#!/bin/sh\n", filename="malware.sh", content_type="application/x-sh")
    with pytest.raises(HTTPException) as exc:
        validate_upload_metadata(f)
    assert exc.value.status_code == 400


def test_validate_rejects_no_extension():
    f = _FakeUploadFile(data=b"abc", filename="noextension", content_type="application/pdf")
    with pytest.raises(HTTPException) as exc:
        validate_upload_metadata(f)
    assert exc.value.status_code == 400


def test_validate_rejects_disallowed_mime():
    f = _FakeUploadFile(data=b"abc", filename="ok.pdf", content_type="application/x-msdownload")
    with pytest.raises(HTTPException) as exc:
        validate_upload_metadata(f)
    assert exc.value.status_code == 400


# ── stream_to_disk_safely ────────────────────────────────────────────────────

def test_stream_writes_small_file(tmp_path: Path):
    f = _FakeUploadFile(data=b"hello-world", filename="a.txt", content_type="text/plain")
    dest = tmp_path / "out.bin"
    written = stream_to_disk_safely(f, dest)
    assert written == len(b"hello-world")
    assert dest.read_bytes() == b"hello-world"


def test_stream_rejects_oversize(tmp_path: Path):
    # Build a payload one byte over the cap. We don't actually allocate
    # MAX_UPLOAD_BYTES + 1 in memory; we use a streaming source.
    class _BigStream(io.RawIOBase):
        def __init__(self, total: int):
            self.remaining = total
            self.readable_flag = True

        def readable(self):
            return True

        def read(self, n=-1):
            if self.remaining <= 0:
                return b""
            chunk = b"\x00" * min(n if n > 0 else 65536, self.remaining, 65536)
            self.remaining -= len(chunk)
            return chunk

    big = _BigStream(total=MAX_UPLOAD_BYTES + 1)
    f = SimpleNamespace(file=big)  # only `.file` is read by stream_to_disk_safely
    dest = tmp_path / "out.bin"
    with pytest.raises(HTTPException) as exc:
        stream_to_disk_safely(f, dest)  # type: ignore[arg-type]
    assert exc.value.status_code == 413
    # Partial file MUST be cleaned up on rejection.
    assert not dest.exists()


# ── verify_magic_bytes ───────────────────────────────────────────────────────

def _write(tmp_path: Path, data: bytes) -> Path:
    p = tmp_path / "f"
    p.write_bytes(data)
    return p


def test_magic_pdf_matches_declared_pdf(tmp_path: Path):
    p = _write(tmp_path, b"%PDF-1.7\n%...\n")
    verify_magic_bytes(p, "application/pdf", "doc.pdf")  # should not raise


def test_magic_pdf_with_octet_stream_allowed(tmp_path: Path):
    p = _write(tmp_path, b"%PDF-1.7\n")
    verify_magic_bytes(p, "application/octet-stream", "doc.pdf")


def test_magic_png_matches(tmp_path: Path):
    p = _write(tmp_path, b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    verify_magic_bytes(p, "image/png", "logo.png")


def test_magic_mismatch_rejects(tmp_path: Path):
    """Declared PDF but bytes are PNG → rejected; file deleted."""
    p = _write(tmp_path, b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    with pytest.raises(HTTPException) as exc:
        verify_magic_bytes(p, "application/pdf", "trojan.pdf")
    assert exc.value.status_code == 400
    assert not p.exists()


def test_magic_unknown_bytes_rejects_unless_text(tmp_path: Path):
    """Random binary blob with no recognizable signature → rejected."""
    p = _write(tmp_path, b"\xde\xad\xbe\xef" * 8)
    with pytest.raises(HTTPException) as exc:
        verify_magic_bytes(p, "application/pdf", "blob.pdf")
    assert exc.value.status_code == 400


def test_magic_text_csv_allowed_without_signature(tmp_path: Path):
    """text/csv has no magic bytes; we accept by extension+content-type."""
    p = _write(tmp_path, b"a,b,c\n1,2,3\n")
    verify_magic_bytes(p, "text/csv", "data.csv")


def test_magic_docx_accepts_zip_family_with_office_mime(tmp_path: Path):
    p = _write(tmp_path, b"PK\x03\x04" + b"\x00" * 16)
    verify_magic_bytes(
        p,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "contract.docx",
    )


def test_magic_zip_family_with_wrong_office_mime_rejects(tmp_path: Path):
    """An executable claiming to be an office doc but is in fact a bare ZIP
    with a disallowed mime → reject."""
    p = _write(tmp_path, b"PK\x03\x04" + b"\x00" * 16)
    with pytest.raises(HTTPException) as exc:
        verify_magic_bytes(p, "application/zip", "thing.docx")
    assert exc.value.status_code == 400
    assert not p.exists()
