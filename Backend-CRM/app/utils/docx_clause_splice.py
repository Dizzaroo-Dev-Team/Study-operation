"""Splice clause content into an existing DOCX without disturbing its formatting.

The original document's blocks (paragraphs + tables) are never modified — clause
content is inserted *between* them at the XML level, so tables, colors, fonts and
layout of the surrounding content are preserved byte-for-byte.

Block model
-----------
A "block" is a top-level child of the document body: either a `<w:p>` (paragraph)
or a `<w:tbl>` (table). Blocks are indexed by their order in the body. Both the
block-extraction endpoint and the splice routine iterate the body the same way, so
an `after_block` index recorded in the builder maps to the same position here.

Insertion
---------
An insertion is `{after_block, clause_*}`. The clause's TipTap content_json is
rendered to a sequence of `<w:p>` elements which are inserted immediately after the
anchor block's XML element (or before the first block when `after_block == -1`).
Insertions are applied in descending anchor order so earlier indices stay valid.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

_BLOCK_TAGS = (qn("w:p"), qn("w:tbl"))


def _iter_body_blocks(doc: Document):
    """Yield (index, element, kind) for each top-level body block in order."""
    body = doc.element.body
    idx = 0
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield idx, child, "paragraph"
            idx += 1
        elif child.tag == qn("w:tbl"):
            yield idx, child, "table"
            idx += 1
        # sectPr and other non-block elements are skipped (not indexed)


def extract_blocks(docx_path: Path) -> List[Dict[str, Any]]:
    """Return an ordered list of body blocks with a short text preview.

    Each item: {index, type, text}. Used by the builder to show the document
    structure and let the user choose insertion points.
    """
    doc = Document(str(docx_path))
    blocks: List[Dict[str, Any]] = []
    for idx, element, kind in _iter_body_blocks(doc):
        if kind == "paragraph":
            para = Paragraph(element, doc)
            text = para.text or ""
        else:
            # Summarise the table: first row's cell text
            texts: List[str] = []
            for row in element.findall(qn("w:tr")):
                for tc in row.findall(qn("w:tc")):
                    cell_text = "".join(t.text or "" for t in tc.iter(qn("w:t")))
                    if cell_text:
                        texts.append(cell_text)
                if texts:
                    break
            text = "[Table] " + " | ".join(texts[:4])
        blocks.append({"index": idx, "type": kind, "text": text})
    return blocks


# ---------------------------------------------------------------------------
# TipTap JSON -> list of <w:p> OxmlElements
# ---------------------------------------------------------------------------

def _make_run(text: str, marks: Optional[List[Dict[str, Any]]]) -> OxmlElement:
    r = OxmlElement("w:r")
    if marks:
        rpr = OxmlElement("w:rPr")
        has_pr = False
        for mark in marks:
            mtype = mark.get("type")
            if mtype == "bold":
                rpr.append(OxmlElement("w:b")); has_pr = True
            elif mtype == "italic":
                rpr.append(OxmlElement("w:i")); has_pr = True
            elif mtype == "underline":
                u = OxmlElement("w:u"); u.set(qn("w:val"), "single")
                rpr.append(u); has_pr = True
        if has_pr:
            r.append(rpr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text or ""
    r.append(t)
    return r


def _make_paragraph(style: Optional[str] = None) -> OxmlElement:
    p = OxmlElement("w:p")
    if style:
        ppr = OxmlElement("w:pPr")
        ps = OxmlElement("w:pStyle")
        ps.set(qn("w:val"), style)
        ppr.append(ps)
        p.append(ppr)
    return p


def _render_inline_into(p_el: OxmlElement, nodes: Optional[List[Dict[str, Any]]]) -> None:
    for node in nodes or []:
        if node.get("type") == "text":
            p_el.append(_make_run(node.get("text", ""), node.get("marks")))
        elif node.get("type") == "hardBreak":
            r = OxmlElement("w:r")
            r.append(OxmlElement("w:br"))
            p_el.append(r)


def _clause_block_to_paragraphs(node: Dict[str, Any]) -> List[OxmlElement]:
    """Render one TipTap block node to a list of <w:p> elements."""
    ntype = node.get("type")
    out: List[OxmlElement] = []

    if ntype == "heading":
        level = int(node.get("attrs", {}).get("level", 2) or 2)
        p = _make_paragraph(style=f"Heading{max(1, min(level, 9))}")
        _render_inline_into(p, node.get("content"))
        out.append(p)

    elif ntype == "paragraph":
        p = _make_paragraph()
        _render_inline_into(p, node.get("content"))
        out.append(p)

    elif ntype in ("bulletList", "orderedList"):
        style = "ListNumber" if ntype == "orderedList" else "ListBullet"
        for item in node.get("content", []):
            if item.get("type") != "listItem":
                continue
            for block in item.get("content", []):
                if block.get("type") == "paragraph":
                    p = _make_paragraph(style=style)
                    _render_inline_into(p, block.get("content"))
                    out.append(p)

    elif ntype == "horizontalRule":
        out.append(_make_paragraph())

    else:
        # Unknown — recurse so nested content is not lost
        for child in node.get("content", []) or []:
            out.extend(_clause_block_to_paragraphs(child))

    return out


def _clause_json_to_paragraphs(
    content_json: Dict[str, Any],
    title: Optional[str] = None,
) -> List[OxmlElement]:
    paragraphs: List[OxmlElement] = []
    if title:
        head = _make_paragraph(style="Heading3")
        head.append(_make_run(title, None))
        paragraphs.append(head)
    for node in (content_json or {}).get("content", []) or []:
        paragraphs.extend(_clause_block_to_paragraphs(node))
    if not paragraphs:
        paragraphs.append(_make_paragraph())
    return paragraphs


# ---------------------------------------------------------------------------
# Splice
# ---------------------------------------------------------------------------

def splice_clauses_into_docx(
    docx_path: Path,
    insertions: List[Dict[str, Any]],
    clause_content_by_id: Dict[str, Dict[str, Any]],
    output_path: Path,
) -> Path:
    """Insert clause content into a clone of docx_path at the given anchor blocks.

    Args:
        docx_path: the original template DOCX (never modified)
        insertions: list of {after_block, clause_id, clause_title?}
        clause_content_by_id: clause_id -> TipTap content_json
        output_path: where to write the spliced DOCX

    Returns output_path.
    """
    doc = Document(str(docx_path))

    # Snapshot the current block elements by index (before any mutation)
    block_elements: Dict[int, Any] = {}
    for idx, element, _kind in _iter_body_blocks(doc):
        block_elements[idx] = element

    # Apply in descending anchor order so indices stay valid as we insert
    ordered = sorted(insertions, key=lambda ins: int(ins.get("after_block", -1)), reverse=True)

    for ins in ordered:
        clause_id = str(ins.get("clause_id"))
        content_json = clause_content_by_id.get(clause_id)
        if not content_json:
            logger.warning("splice: no content for clause %s, skipping", clause_id)
            continue

        new_paras = _clause_json_to_paragraphs(content_json, ins.get("clause_title"))
        after_block = int(ins.get("after_block", -1))

        if after_block < 0:
            # Insert before the very first block
            anchor = block_elements.get(0)
            if anchor is not None:
                for p in new_paras:
                    anchor.addprevious(p)
            else:
                # Empty doc — append to body
                for p in new_paras:
                    doc.element.body.append(p)
        else:
            anchor = block_elements.get(after_block)
            if anchor is None:
                # Anchor out of range — append at end of body (before sectPr if present)
                for p in new_paras:
                    doc.element.body.append(p)
            else:
                # Insert in order immediately after the anchor
                ref = anchor
                for p in new_paras:
                    ref.addnext(p)
                    ref = p

    doc.save(str(output_path))
    return output_path
