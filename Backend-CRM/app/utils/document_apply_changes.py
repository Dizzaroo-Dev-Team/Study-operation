"""
Document Apply Changes Utility

Applies accepted negotiation changes (ADDED, DELETED, MODIFIED) from AgreementChange records
back into the main agreement DOCX document. Called when an internal user accepts a change.

KEY DESIGN PRINCIPLE — preserve SDT (content control) structure
================================================================
Editable placeholder fields in the generated DOCX are wrapped in `w:sdt` elements:

    <w:sdt>
        <w:sdtPr>
            <w:tag w:val="SITE_NAME"/>
            <w:richText/>          ← marks field as editable in forms-protection mode
        </w:sdtPr>
        <w:sdtContent>
            <w:r><w:t>Mahindra Hospital</w:t></w:r>   ← the actual text
        </w:sdtContent>
    </w:sdt>

The document is saved with Word's "forms" protection (`w:documentProtection edit="forms"`).
In forms mode ONLY content controls (w:sdt elements) can be edited. Plain w:r runs are
read-only.

WRONG approach (old): clear the paragraph, write plain w:r.
  → Destroys w:sdt → field becomes plain text → read-only after merge.

CORRECT approach (this file): update text INSIDE w:sdtContent, never touch w:sdtPr.
  → SDT wrapper is preserved → field stays editable after merge.

Change types
-----------
  MODIFIED → locate paragraph by old_text, update text (SDT-aware).
  DELETED  → locate paragraph by old_text, remove whole w:p element.
  ADDED    → create a new w:p at paragraph_index (or end of body).
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# WordprocessingML namespace
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_T = f"{{{WORD_NS}}}t"
W_R = f"{{{WORD_NS}}}r"
W_P = f"{{{WORD_NS}}}p"
W_PPR = f"{{{WORD_NS}}}pPr"
W_SDT = f"{{{WORD_NS}}}sdt"
W_SDT_CONTENT = f"{{{WORD_NS}}}sdtContent"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


# ---------------------------------------------------------------------------
# Text extraction (full, including SDT content)
# ---------------------------------------------------------------------------

def _get_element_full_text(element) -> str:
    """
    Extract ALL text from an XML element including text inside content controls (w:sdt).
    python-docx's .text property misses text inside SDT wrappers — this does not.
    """
    parts = []
    for t_elem in element.iter(W_T):
        if t_elem.text:
            parts.append(t_elem.text)
    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Text replacement — SDT-aware (never destroys content control structure)
# ---------------------------------------------------------------------------

def _set_paragraph_text(para_element, new_text: str) -> None:
    """
    Update the visible text of a paragraph, preserving SDT content control structure.

    Priority:
    1. If the paragraph contains w:sdt elements → update text WITHIN w:sdtContent.
       w:sdtPr (which holds editability config, tag name, etc.) is left intact.
    2. Otherwise → clear the paragraph's children (keep w:pPr) and write a plain run.

    This ensures that editable placeholder fields remain editable after a change
    is accepted, because their w:sdt / w:sdtPr wrapper is never removed.
    """
    has_sdt = any(child.tag == W_SDT for child in para_element)

    if has_sdt:
        if _update_text_in_sdts(para_element, new_text):
            return
        # SDT update failed — fall through to destructive rewrite with a warning
        logger.warning(
            "SDT-aware text update failed for paragraph; "
            "falling back to plain-run rewrite (may affect field editability)"
        )

    _rewrite_paragraph_as_plain_text(para_element, new_text)


def _update_text_in_sdts(para_element, new_text: str) -> bool:
    """
    Update the text content of a paragraph that contains w:sdt (content control) elements,
    without touching w:sdtPr (which contains editability, tag name, lock flags, etc.).

    Two sub-cases:
    A. Paragraph is PURE SDT (all non-pPr children are w:sdt):
       Replace content of the first SDT with a single clean run carrying new_text.

    B. Paragraph is MIXED (SDT + plain runs):
       Set the first w:t element to new_text and clear all subsequent w:t elements.
       The SDT structure is left in place; we only change text node values.

    Returns True on success, False if no w:t elements were found to update.
    """
    from lxml import etree

    # Determine whether the paragraph is pure-SDT or mixed
    non_ppr_children = [c for c in para_element if c.tag != W_PPR]
    all_are_sdt = all(c.tag == W_SDT for c in non_ppr_children)

    if all_are_sdt and non_ppr_children:
        # ── Pure SDT paragraph ─────────────────────────────────────────────
        # Operate on the first SDT; replace its sdtContent with a fresh run.
        sdt = non_ppr_children[0]
        sdt_content = sdt.find(W_SDT_CONTENT)

        if sdt_content is None:
            # Create sdtContent if it's somehow missing
            sdt_content = etree.SubElement(sdt, W_SDT_CONTENT)
        else:
            # Remove existing runs / content inside sdtContent
            for child in list(sdt_content):
                sdt_content.remove(child)

        # Write a new single run with the new text
        new_run = etree.SubElement(sdt_content, W_R)
        new_t = etree.SubElement(new_run, W_T)
        new_t.text = new_text or ""
        if new_text and new_text != new_text.strip():
            new_t.set(XML_SPACE, "preserve")

        logger.debug(
            f"SDT update (pure): replaced sdtContent text → {new_text!r} "
            f"(w:sdtPr preserved)"
        )
        return True

    else:
        # ── Mixed paragraph: has SDTs AND plain runs ───────────────────────
        # Update w:t nodes in-place to avoid destroying any part of the structure.
        all_t = list(para_element.iter(W_T))
        if not all_t:
            return False

        all_t[0].text = new_text or ""
        if new_text and new_text != new_text.strip():
            all_t[0].set(XML_SPACE, "preserve")

        # Clear remaining text nodes (text was split across multiple runs)
        for t_elem in all_t[1:]:
            t_elem.text = ""

        logger.debug(
            f"SDT update (mixed): set first w:t → {new_text!r}, "
            f"cleared {len(all_t) - 1} subsequent w:t node(s)"
        )
        return True


def _rewrite_paragraph_as_plain_text(para_element, new_text: str) -> None:
    """
    Destructive fallback: clear all paragraph children except w:pPr and write new_text
    as a plain w:r run. This does NOT preserve SDT structure and should only be used
    when the paragraph has no content controls.
    """
    from lxml import etree

    # Remove everything except paragraph properties
    for child in list(para_element):
        if child.tag != W_PPR:
            para_element.remove(child)

    if not new_text:
        return

    run_elem = etree.SubElement(para_element, W_R)
    t_elem = etree.SubElement(run_elem, W_T)
    t_elem.text = new_text
    if new_text != new_text.strip():
        t_elem.set(XML_SPACE, "preserve")


def _make_paragraph_element(text: str):
    """Create a new bare w:p element containing a single text run (for ADDED changes)."""
    from lxml import etree
    p = etree.Element(W_P)
    r = etree.SubElement(p, W_R)
    t = etree.SubElement(r, W_T)
    t.text = text
    if text != text.strip():
        t.set(XML_SPACE, "preserve")
    return p


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_change_to_docx(
    source_path: Path,
    change_type: str,
    old_text: Optional[str],
    new_text: Optional[str],
    paragraph_index: Optional[int],
    output_path: Path,
) -> bool:
    """
    Apply a single negotiation change to a DOCX document and save the result.

    Field editability is preserved because:
    - For MODIFIED changes inside SDT elements, only w:sdtContent is modified;
      w:sdtPr (which holds <w:richText/> and other editability config) is never touched.
    - The document's forms-protection settings are also never modified.

    Args:
        source_path:     Path to the current main document DOCX.
        change_type:     'ADDED', 'DELETED', or 'MODIFIED'.
        old_text:        Text that was changed / removed (used to locate the paragraph).
        new_text:        Replacement or inserted text.
        paragraph_index: Positional index hint (only used for ADDED when no old_text).
        output_path:     Where to save the modified document.

    Returns:
        True  — change was applied and document saved.
        False — target paragraph could not be located; document NOT saved.
    """
    from docx import Document

    try:
        doc = Document(str(source_path))
    except Exception as exc:
        logger.exception(f"Failed to open document {source_path}: {exc}")
        return False

    paragraphs = doc.paragraphs
    applied = False

    # -----------------------------------------------------------------------
    # MODIFIED — locate paragraph by old_text, update text (SDT-aware)
    # -----------------------------------------------------------------------
    if change_type == "MODIFIED":
        if not old_text:
            logger.warning("MODIFIED change has no old_text — cannot locate paragraph")
            return False

        old_stripped = old_text.strip()

        # Pass 1: exact full-text match
        for para in paragraphs:
            full = _get_element_full_text(para._element)
            if full == old_stripped:
                _set_paragraph_text(para._element, new_text or "")
                applied = True
                logger.info(f"MODIFIED (exact match): {old_stripped!r} → {new_text!r}")
                break

        # Pass 2: old_text appears as a substring
        if not applied:
            for para in paragraphs:
                full = _get_element_full_text(para._element)
                if old_stripped in full:
                    merged = full.replace(old_stripped, new_text or "", 1)
                    _set_paragraph_text(para._element, merged)
                    applied = True
                    logger.info(f"MODIFIED (substring match): paragraph → {merged!r}")
                    break

        if not applied:
            logger.warning(
                f"MODIFIED: could not find paragraph containing old_text={old_text!r}"
            )

    # -----------------------------------------------------------------------
    # DELETED — locate paragraph by old_text, remove entire w:p
    # -----------------------------------------------------------------------
    elif change_type == "DELETED":
        if not old_text:
            logger.warning("DELETED change has no old_text — cannot locate paragraph")
            return False

        old_stripped = old_text.strip()

        for para in paragraphs:
            full = _get_element_full_text(para._element)
            if full == old_stripped:
                p_elem = para._element
                parent = p_elem.getparent()
                if parent is not None:
                    parent.remove(p_elem)
                    applied = True
                    logger.info(f"DELETED: removed paragraph with text={old_text!r}")
                break

        # Fallback: remove if old_text is contained and that's the full content
        if not applied:
            for para in paragraphs:
                full = _get_element_full_text(para._element)
                if full.strip() == old_stripped:
                    p_elem = para._element
                    parent = p_elem.getparent()
                    if parent is not None:
                        parent.remove(p_elem)
                        applied = True
                        logger.info(f"DELETED (fallback): removed paragraph text={old_text!r}")
                    break

        if not applied:
            logger.warning(
                f"DELETED: could not find paragraph containing old_text={old_text!r}"
            )

    # -----------------------------------------------------------------------
    # ADDED — insert a new plain paragraph at paragraph_index (or end)
    # -----------------------------------------------------------------------
    elif change_type == "ADDED":
        if not new_text:
            logger.warning("ADDED change has no new_text — nothing to insert")
            return False

        new_para_elem = _make_paragraph_element(new_text)
        body = doc.element.body

        # Direct w:p children of body (excludes nested content)
        body_paras = [child for child in body if child.tag == W_P]

        if paragraph_index is not None and 0 <= paragraph_index < len(body_paras):
            ref_para = body_paras[paragraph_index]
            body.insert(list(body).index(ref_para), new_para_elem)
            logger.info(f"ADDED: inserted paragraph at index {paragraph_index}: {new_text!r}")
        else:
            # Insert before w:sectPr (section properties) if present
            sect_pr_tag = f"{{{WORD_NS}}}sectPr"
            sect_pr = body.find(sect_pr_tag)
            if sect_pr is not None:
                body.insert(list(body).index(sect_pr), new_para_elem)
            else:
                body.append(new_para_elem)
            logger.info(f"ADDED: appended paragraph at end: {new_text!r}")

        applied = True

    else:
        logger.warning(f"Unknown change_type: {change_type!r}")
        return False

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------
    if applied:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(output_path))
            logger.info(f"Saved merged document to {output_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to save merged document: {exc}", exc_info=True)
            return False

    return False
