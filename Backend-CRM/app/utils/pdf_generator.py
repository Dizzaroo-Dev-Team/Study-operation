"""
PDF Generation Utility

Primary path: use WeasyPrint to render full CDA HTML (with styles) to PDF.
Fallback: minimal ReportLab-based text rendering if WeasyPrint isn't
available or fails at runtime.
"""
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import ReportLab (optional, used as fallback)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not available; PDF generation will require WeasyPrint")


# ---------------------------------------------------------------------------
# Try to enable WeasyPrint with a small compatibility shim for the pydyf
# version available in this environment.
# ---------------------------------------------------------------------------
WEASYPRINT_AVAILABLE = False

try:
    from weasyprint import HTML, CSS  # type: ignore
    import pydyf  # type: ignore

    try:
        # Patch PDF.__init__ to accept (version, identifier) as WeasyPrint 60.x
        # expects, while delegating to the existing no-arg __init__.
        pdf_init = pydyf.PDF.__init__  # type: ignore[attr-defined]
        if getattr(pdf_init, "__code__", None) and pdf_init.__code__.co_argcount == 1:

            def _patched_pdf_init(self, version="1.7", identifier=None):
                # Store attributes so WeasyPrint can read pdf.version later.
                self.version = version
                self.identifier = identifier
                pdf_init(self)  # call original implementation

            pydyf.PDF.__init__ = _patched_pdf_init  # type: ignore[assignment]
            logger.info("Patched pydyf.PDF.__init__ for WeasyPrint compatibility")

        # Patch Stream to add transform / text_matrix expected by WeasyPrint's
        # own Stream subclass.
        stream_cls = getattr(pydyf, "Stream", None)
        if stream_cls is not None:
            if not hasattr(stream_cls, "transform"):

                def _stream_transform(self, a=1, b=0, c=0, d=1, e=0, f=0):
                    # Delegate to existing set_matrix implementation.
                    return self.set_matrix(a, b, c, d, e, f)

                stream_cls.transform = _stream_transform  # type: ignore[assignment]
                logger.info("Patched pydyf.Stream.transform for WeasyPrint compatibility")

            if not hasattr(stream_cls, "text_matrix"):

                def _stream_text_matrix(self, a=1, b=0, c=0, d=1, e=0, f=0):
                    # Delegate to existing set_text_matrix implementation.
                    return self.set_text_matrix(a, b, c, d, e, f)

                stream_cls.text_matrix = _stream_text_matrix  # type: ignore[assignment]
                logger.info("Patched pydyf.Stream.text_matrix for WeasyPrint compatibility")

        WEASYPRINT_AVAILABLE = True
        logger.info("WeasyPrint is available; will use it for CDA PDF rendering")
    except Exception as patch_err:  # pragma: no cover - defensive
        WEASYPRINT_AVAILABLE = False
        logger.warning(
            "WeasyPrint import succeeded but pydyf compatibility patch failed: %s",
            patch_err,
        )
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.info("WeasyPrint not installed; falling back to ReportLab-only PDFs")


def _render_with_reportlab(html_content: str, output_path: Path) -> Path:
    """
    Fallback: very simple text-only rendering using ReportLab.
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("ReportLab is not installed. Install it with: pip install reportlab")
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove <style>...</style> and <head>...</head> blocks so CSS/metadata
    # doesn't appear as visible text in the PDF.
    cleaned = re.sub(r"(?is)<style.*?</style>", "", html_content)
    cleaned = re.sub(r"(?is)<head.*?</head>", "", cleaned)

    # Naive HTML -> plain text: drop '<'...'>' segments.
    text = []
    in_tag = False
    for ch in cleaned:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            text.append(ch)
    plain_text = "".join(text)

    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4
    margin = 40
    max_width = width - 2 * margin

    y = height - margin
    line_height = 14

    for paragraph in plain_text.splitlines():
        if not paragraph.strip():
            y -= line_height
            continue
        lines = simpleSplit(paragraph, "Helvetica", 11, max_width)
        for line in lines:
            if y < margin:
                c.showPage()
                y = height - margin
            c.setFont("Helvetica", 11)
            c.drawString(margin, y, line)
            y -= line_height

    c.showPage()
    c.save()

    logger.info(f"Generated PDF (ReportLab fallback) at {output_path}")
    return output_path


def html_to_pdf(html_content: str, output_path: Path, base_url: Optional[str] = None) -> Path:
    """
    Convert CDA HTML content to a PDF file.

    Preference order:
    1. Use WeasyPrint (full HTML/CSS rendering) when available and working.
    2. Fall back to a simple text-only ReportLab rendering as a last resort.
    """
    # 1) Try WeasyPrint first
    if WEASYPRINT_AVAILABLE:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            html_doc = HTML(string=html_content, base_url=base_url)
            html_doc.write_pdf(str(output_path))
            logger.info(f"Generated PDF with WeasyPrint at {output_path}")
            return output_path
        except Exception as e:
            logger.exception(f"WeasyPrint PDF generation failed, falling back to ReportLab: {e}")

    # 2) Fallback to ReportLab text-only rendering
    try:
        return _render_with_reportlab(html_content, output_path)
    except Exception as e:
        logger.exception(f"Failed to generate PDF with ReportLab: {e}")
        raise Exception(f"PDF generation failed: {e}")
