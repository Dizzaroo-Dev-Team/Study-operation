"""
DOCX Comment Extractor
======================
Extracts comments (and comment replies) from a DOCX file by reading the
underlying XML directly.  Used during the OnlyOffice callback to persist
site-user comments into the agreement_document_comments table.

OnlyOffice embeds comments in the standard OOXML format:
  word/comments.xml        – comment bodies (id, author, date, text)
  word/commentsExtended.xml – reply relationships (paraIdParent)
  word/document.xml        – commentRangeStart/End anchors + quoted text

No third-party library is required beyond the Python standard library.
"""

import posixpath
import zipfile
import logging
import re
import shutil
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# ── XML namespace constants used by OOXML ────────────────────────────────────
_NS_W  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"

# Helper to qualify a tag name with a namespace
_w  = lambda tag: f"{{{_NS_W}}}{tag}"
_w14 = lambda tag: f"{{{_NS_W14}}}{tag}"


def _get_attr(elem: ET.Element, local_name: str, ns: str = _NS_W) -> Optional[str]:
    """Return the value of a namespaced attribute, or None if absent."""
    return elem.get(f"{{{ns}}}{local_name}")


def _extract_text(elem: ET.Element) -> str:
    """Recursively collect all w:t text nodes beneath *elem*."""
    parts: List[str] = []
    for t_node in elem.iter(_w("t")):
        if t_node.text:
            parts.append(t_node.text)
    return "".join(parts).strip()


def _parse_comments_xml(xml_bytes: bytes) -> Dict[str, Dict[str, Any]]:
    """
    Parse word/comments.xml and return a mapping of
      comment_id (str) → {author, date, text, para_id}
    """
    comments: Dict[str, Dict[str, Any]] = {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("Failed to parse comments.xml: %s", exc)
        return comments

    for comment_elem in root.iter(_w("comment")):
        cid    = _get_attr(comment_elem, "id")
        author = _get_attr(comment_elem, "author") or ""
        date   = _get_attr(comment_elem, "date")   or ""
        text   = _extract_text(comment_elem)
        # w14:paraId is used to link replies (commentsExtended.xml)
        para_id = _get_attr(comment_elem, "paraId", _NS_W14)

        if cid is not None:
            comments[cid] = {
                "comment_id":     cid,
                "author":         author,
                "date":           date,
                "text":           text,
                "para_id":        para_id,      # None for plain OnlyOffice comments
                "parent_comment_id": None,      # filled in below
            }

    return comments


def _apply_extended_comments(
    comments: Dict[str, Dict[str, Any]],
    ext_xml_bytes: bytes,
) -> None:
    """
    Parse word/commentsExtended.xml to find reply relationships and inject
    parent_comment_id into the comments dict (mutates in-place).

    In commentsExtended, a reply element looks like:
      <w15:commentEx w15:paraId="..." w15:paraIdParent="..." />
    where paraIdParent references the parent comment's paraId.
    """
    NS_W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
    _w15 = lambda tag: f"{{{NS_W15}}}{tag}"

    # Build reverse mapping:  para_id → comment_id
    para_id_to_comment = {
        v["para_id"]: k
        for k, v in comments.items()
        if v.get("para_id")
    }

    try:
        root = ET.fromstring(ext_xml_bytes)
    except ET.ParseError as exc:
        logger.warning("Failed to parse commentsExtended.xml: %s", exc)
        return

    for ex_elem in root.iter(_w15("commentEx")):
        para_id        = ex_elem.get(f"{{{NS_W15}}}paraId")
        para_id_parent = ex_elem.get(f"{{{NS_W15}}}paraIdParent")

        if para_id and para_id_parent:
            child_cid  = para_id_to_comment.get(para_id)
            parent_cid = para_id_to_comment.get(para_id_parent)
            if child_cid and parent_cid:
                comments[child_cid]["parent_comment_id"] = parent_cid


def _extract_referenced_texts(document_xml_bytes: bytes) -> Dict[str, str]:
    """
    Parse word/document.xml and build a mapping of
      comment_id → quoted (referenced) text
    by collecting the text between commentRangeStart and commentRangeEnd.

    Implementation notes
    --------------------
    The previous version walked only direct children of each <w:p> element
    and only collected text from <w:r> runs.  This missed selected text when
    it was wrapped in any other element — <w:hyperlink>, <w:ins> (tracked
    change), <w:del>, formatting wrappers, etc. — causing referenced_text to
    be empty even when the reviewer had selected text.

    The fix: iterate the ENTIRE document element tree in document order with
    root.iter().  This is a flat, depth-first walk so:
    •  commentRangeStart / commentRangeEnd are detected wherever they sit.
    •  <w:t> text nodes inside ANY parent are captured.
    •  Multi-paragraph selections work because we never reset active_ids at
       paragraph boundaries.
    """
    quoted: Dict[str, str] = {}
    try:
        root = ET.fromstring(document_xml_bytes)
    except ET.ParseError as exc:
        logger.warning("Failed to parse document.xml: %s", exc)
        return quoted

    # comment_id (str) → list of text fragments collected so far
    active_ids: Dict[str, List[str]] = {}

    for elem in root.iter():
        tag = elem.tag

        if tag == _w("commentRangeStart"):
            cid = _get_attr(elem, "id")
            if cid is not None:
                active_ids[cid] = []

        elif tag == _w("commentRangeEnd"):
            cid = _get_attr(elem, "id")
            if cid is not None and cid in active_ids:
                text = "".join(active_ids.pop(cid)).strip()
                if text:
                    quoted[cid] = text

        elif tag == _w("t") and active_ids:
            # Plain text node — append to every currently-open range.
            # xml:space="preserve" means leading/trailing spaces must be kept.
            fragment = elem.text or ""
            if fragment:
                for cid in list(active_ids):
                    active_ids[cid].append(fragment)

    # Any active_ids still open means commentRangeEnd was never found
    # (malformed OOXML); add whatever text was collected as a best-effort.
    for cid, parts in active_ids.items():
        text = "".join(parts).strip()
        if text and cid not in quoted:
            quoted[cid] = text
            logger.debug(
                "comment %s: commentRangeEnd not found; using collected text as fallback",
                cid,
            )

    return quoted


# ── Public API ────────────────────────────────────────────────────────────────

def extract_comments_from_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract all comments from a DOCX file at *file_path*.

    Returns a list of dicts, each with keys:
        comment_id        – OOXML comment id (str)
        author            – author name as stored in the DOCX
        date              – ISO date/time string from DOCX metadata
        text              – comment body text
        referenced_text   – the document text the comment is attached to
        parent_comment_id – id of the parent comment (None for top-level)

    Returns an empty list if the DOCX has no comments or cannot be read.
    """
    result: List[Dict[str, Any]] = []

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()

            # ── comments.xml is mandatory ────────────────────────────────────
            if "word/comments.xml" not in names:
                logger.debug("No word/comments.xml in %s – no comments", file_path)
                return []

            with zf.open("word/comments.xml") as fh:
                comments = _parse_comments_xml(fh.read())

            if not comments:
                return []

            # ── commentsExtended.xml (optional – for reply threading) ────────
            if "word/commentsExtended.xml" in names:
                with zf.open("word/commentsExtended.xml") as fh:
                    _apply_extended_comments(comments, fh.read())

            # ── document.xml (for quoted / referenced text) ──────────────────
            if "word/document.xml" in names:
                with zf.open("word/document.xml") as fh:
                    quoted_map = _extract_referenced_texts(fh.read())
            else:
                quoted_map = {}

    except (zipfile.BadZipFile, KeyError) as exc:
        logger.exception("Cannot open DOCX %s for comment extraction: %s", file_path, exc)
        return []
    except Exception as exc:
        logger.error("Unexpected error extracting comments from %s: %s", file_path, exc, exc_info=True)
        return []

    # ── Assemble final list ───────────────────────────────────────────────────
    for cid, meta in comments.items():
        result.append({
            "comment_id":        meta["comment_id"],
            "author":            meta["author"],
            "date":              meta["date"],
            "text":              meta["text"],
            "referenced_text":   quoted_map.get(cid, ""),
            "parent_comment_id": meta.get("parent_comment_id"),
        })

    logger.info(
        "Extracted %d comment(s) from %s (%d with parent)",
        len(result),
        file_path,
        sum(1 for c in result if c["parent_comment_id"]),
    )
    return result


def _strip_comment_markup_from_xml_bytes(data: bytes) -> bytes:
    """
    Remove comment anchor elements from XML without parsing/re-serializing the
    full tree. Full ElementTree round-trips can break `w:sdt` content controls
    (placeholders visible only as blank in OnlyOffice for reviewers).
    """
    try:
        s = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    s = re.sub(r"<w:commentRangeStart\b[^>]*/>", "", s)
    s = re.sub(r"<w:commentRangeEnd\b[^>]*/>", "", s)
    s = re.sub(r"<w:commentReference\b[^>]*/>", "", s)
    return s.encode("utf-8")


def _content_types_drop_comments(data: bytes) -> bytes:
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data
    # Remove Override entries for comments parts
    ns = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
    to_drop = []
    for ov in root.findall(".//{http://schemas.openxmlformats.org/package/2006/content-types}Override"):
        pn = ov.get("PartName") or ""
        if "comments.xml" in pn.lower() or "commentsextended.xml" in pn.lower():
            to_drop.append(ov)
    for el in to_drop:
        root.remove(el)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _document_rels_drop_comments(data: bytes) -> bytes:
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    to_drop = []
    for rel in root.findall(f".//{{{rel_ns}}}Relationship"):
        tgt = (rel.get("Target") or "").lower()
        if "comments.xml" in tgt or "commentsextended.xml" in tgt:
            to_drop.append(rel)
    for el in to_drop:
        root.remove(el)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def strip_comments_from_docx(src_path: str, dst_path: str) -> None:
    """
    Copy *src_path* DOCX to *dst_path* with Word comments removed from the package.

    Used before starting a new external review round so previous-cycle comments
    are not embedded in the file sent to reviewers.
    """
    from io import BytesIO

    with zipfile.ZipFile(src_path, "r") as zin:
        names = zin.namelist()
        if "word/comments.xml" not in names:
            shutil.copy2(src_path, dst_path)
            logger.info(
                "strip_comments_from_docx: no comments part in package; copied unchanged to %s",
                dst_path,
            )
            return
        out_buf = BytesIO()
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                if name in ("word/comments.xml", "word/commentsExtended.xml"):
                    continue
                data = zin.read(name)
                if name == "word/document.xml" or name.startswith("word/header") or name.startswith(
                    "word/footer"
                ):
                    data = _strip_comment_markup_from_xml_bytes(data)
                elif name == "[Content_Types].xml":
                    data = _content_types_drop_comments(data)
                elif name.endswith("document.xml.rels") and "word/_rels" in name:
                    data = _document_rels_drop_comments(data)
                zout.writestr(name, data)
        out_buf.seek(0)
        with open(dst_path, "wb") as fh:
            shutil.copyfileobj(out_buf, fh)

    logger.info("strip_comments_from_docx: wrote clean copy to %s", dst_path)


_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _partname_to_member(partname: str) -> str:
    return (partname or "").lstrip("/")


def _resolve_rel_target(rels_member: str, target: str) -> Optional[str]:
    """Resolve a relationship Target to a zip member path."""
    if not target:
        return None
    lower = target.lower()
    if lower.startswith(("http://", "https://", "mailto:")):
        return None
    if target.startswith("/"):
        return _partname_to_member(target)
    base_dir = rels_member.split("_rels/", 1)[0]
    return posixpath.normpath(posixpath.join(base_dir, target))


def _content_types_drop_missing_parts(data: bytes, present: set[str]) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data
    to_drop = []
    for ov in root.findall(f".//{{{_CT_NS}}}Override"):
        member = _partname_to_member(ov.get("PartName") or "")
        if member and member not in present:
            to_drop.append(ov)
    for el in to_drop:
        root.remove(el)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rels_drop_missing_targets(data: bytes, rels_member: str, present: set[str]) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data
    to_drop = []
    for rel in root.findall(f".//{{{_REL_NS}}}Relationship"):
        target = rel.get("Target") or ""
        resolved = _resolve_rel_target(rels_member, target)
        if resolved and resolved not in present:
            to_drop.append(rel)
    for el in to_drop:
        root.remove(el)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def repair_docx_package(src_path: str, dst_path: str) -> None:
    """
    Remove [Content_Types].xml and .rels entries that point at parts missing
    from the DOCX zip.

    OnlyOffice sometimes declares word/commentsExtended.xml (and similar) in
    content types without writing the part, which makes python-docx fail to open
    the file when appending a visible signature block.
    """
    from io import BytesIO

    with zipfile.ZipFile(src_path, "r") as zin:
        present = set(zin.namelist())
        out_buf = BytesIO()
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "[Content_Types].xml":
                    data = _content_types_drop_missing_parts(data, present)
                elif name.endswith(".rels"):
                    data = _rels_drop_missing_targets(data, name, present)
                zout.writestr(name, data)
        out_buf.seek(0)
        with open(dst_path, "wb") as fh:
            shutil.copyfileobj(out_buf, fh)

    logger.info("repair_docx_package: wrote repaired copy to %s", dst_path)
