"""Shared upload validation: size cap, mime whitelist, magic-byte sniff.

Use `stream_to_disk_safely()` from any FastAPI upload route. It enforces
the size cap during streaming (so the server never buffers more than
MAX_UPLOAD_BYTES even if the client lies about Content-Length), then
sniffs the first 32 bytes of the saved file against a static signature
table to defeat content-type spoofing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Set, Tuple

from fastapi import HTTPException, UploadFile

# 25 MB cap per upload (matches FE chunk expectations + nginx default).
MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

# Whitelist of acceptable MIME types as advertised by the client. The
# magic-byte sniff is the real authority; this just rejects obviously
# wrong headers early.
ALLOWED_MIME_TYPES: Set[str] = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
}

# Whitelisted extensions. Any uploaded filename must match (case-insensitive).
ALLOWED_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf",
    ".doc", ".docx",
    ".xls", ".xlsx",
    ".ppt", ".pptx",
    ".txt", ".csv",
}

# Magic-byte signatures. Multiple entries per family because office docs and
# images have several legit prefixes.
_MAGIC_SIGNATURES: Tuple[Tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff",                 "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n",            "image/png"),
    (b"GIF87a",                       "image/gif"),
    (b"GIF89a",                       "image/gif"),
    (b"RIFF",                         "image/webp"),   # also AVI / WAV; extra check below
    (b"%PDF-",                        "application/pdf"),
    (b"PK\x03\x04",                   "zip-family"),   # docx/xlsx/pptx
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole-family"),  # legacy doc/xls/ppt
)

_ZIP_FAMILY_MIMES: Set[str] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Plain zip extensions aren't whitelisted; office formats are.
}

_OLE_FAMILY_MIMES: Set[str] = {
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
}


def _sniff(head: bytes) -> Optional[str]:
    """Return a coarse family label for the magic bytes, or None."""
    for sig, label in _MAGIC_SIGNATURES:
        if head.startswith(sig):
            # WebP: RIFF....WEBP at offset 8
            if label == "image/webp" and not (len(head) >= 12 and head[8:12] == b"WEBP"):
                continue
            return label
    return None


def _ext_for(filename: Optional[str]) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def safe_extension(filename: Optional[str]) -> str:
    """Return the upload's extension as a TRUSTED literal from ALLOWED_EXTENSIONS.

    Returning the whitelist's own string (not the user-supplied one) breaks the
    CWE-22 taint chain when the extension is used to build a disk path.
    Raises 400 when the extension is not whitelisted.
    """
    ext = _ext_for(filename)
    for allowed in ALLOWED_EXTENSIONS:
        if ext == allowed:
            return allowed
    raise HTTPException(
        status_code=400,
        detail=f"File extension not allowed: {ext or '(none)'}",
    )


def _contained_upload_path(p: Path) -> Path:
    """CWE-22 guard: resolve `p` and refuse anything outside the configured
    upload root. Callers build paths as `upload_dir / <uuid><whitelisted-ext>`,
    so this never fires in legitimate use — it is defense in depth."""
    from app.config import settings

    base = Path(settings.upload_dir).resolve()
    resolved = p.resolve()
    if not resolved.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Invalid upload path")
    return resolved


def validate_upload_metadata(file: UploadFile) -> None:
    """Reject obviously bad uploads before touching the disk."""
    ext = _ext_for(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension not allowed: {ext or '(none)'}",
        )
    client_mime = (file.content_type or "").lower()
    # text/plain is sometimes sent as application/octet-stream; allow that pairing only when extension is whitelisted.
    if client_mime and client_mime not in ALLOWED_MIME_TYPES and client_mime != "application/octet-stream":
        raise HTTPException(
            status_code=400,
            detail=f"Content-Type not allowed: {client_mime}",
        )


def stream_to_disk_safely(file: UploadFile, dest: Path) -> int:
    """Stream the upload to `dest`, enforcing MAX_UPLOAD_BYTES.

    Returns the byte count written. Raises HTTPException(413) if the cap is
    exceeded, deleting the partial file before returning so the disk doesn't
    leak data on rejection.
    """
    dest = _contained_upload_path(dest)
    written = 0
    chunk_size = 1024 * 1024  # 1 MiB
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    out.close()
                    try:
                        dest.unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to write upload: {exc}")
    return written


def verify_magic_bytes(path: Path, client_mime: str, filename: Optional[str]) -> None:
    """Read the first 32 bytes from `path` and reject if they don't match an
    allowed family or if the family is inconsistent with the declared mime.
    Deletes the file on failure.
    """
    path = _contained_upload_path(path)
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}")

    family = _sniff(head)
    if family is None:
        # text/csv & text/plain have no magic; allow only by extension+content-type
        ext = _ext_for(filename)
        if ext in {".txt", ".csv"} and (client_mime or "").startswith("text/"):
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail="File content does not match any allowed file type",
        )

    # Cross-check: declared mime must be consistent with the sniffed family.
    cm = (client_mime or "").lower()
    if family == "zip-family":
        if cm and cm not in _ZIP_FAMILY_MIMES and cm != "application/octet-stream":
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(
                status_code=400,
                detail="File contents (zip-family) do not match declared type",
            )
    elif family == "ole-family":
        if cm and cm not in _OLE_FAMILY_MIMES and cm != "application/octet-stream":
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(
                status_code=400,
                detail="File contents (ole-family) do not match declared type",
            )
    else:
        # family is an exact mime like image/png. Allow if declared mime
        # matches OR if client sent octet-stream (some clients do that).
        if cm and cm != family and cm != "application/octet-stream":
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(
                status_code=400,
                detail=f"Declared type {cm} does not match file contents",
            )
