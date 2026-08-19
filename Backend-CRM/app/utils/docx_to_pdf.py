"""
DOCX to PDF Conversion Utility

Converts DOCX files to PDF using LibreOffice headless mode or ONLYOFFICE.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _resolve_soffice_executable() -> str:
    """Resolve soffice executable name/path across environments."""
    env_override = (os.getenv("LIBREOFFICE_PATH") or "").strip()
    if env_override:
        override_path = Path(env_override)
        if override_path.exists():
            return str(override_path)

    if os.name == "nt":
        candidates = [
            Path(os.getenv("PROGRAMFILES", "")) / "LibreOffice" / "program" / "soffice.exe",
            Path(os.getenv("PROGRAMFILES(X86)", "")) / "LibreOffice" / "program" / "soffice.exe",
            Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "LibreOffice" / "program" / "soffice.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

    return "soffice"


def docx_to_pdf_libreoffice(docx_path: Path, pdf_path: Path) -> None:
    """
    Convert DOCX to PDF using LibreOffice headless mode.
    
    Args:
        docx_path: Path to source DOCX file
        pdf_path: Path to save output PDF
        
    Raises:
        Exception: If conversion fails
    """
    try:
        # Use LibreOffice headless mode to convert DOCX to PDF
        # soffice is the LibreOffice command-line interface
        # --headless: Run without GUI
        # --convert-to pdf: Convert to PDF format
        # --outdir: Output directory
        cmd = [
            _resolve_soffice_executable(),
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(pdf_path.parent),
            str(docx_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            raise Exception(f"LibreOffice conversion failed: {result.stderr}")
        
        # LibreOffice creates the PDF in the specified --outdir with the
        # same base name as the DOCX (e.g. version_1_xxx.docx -> version_1_xxx.pdf)
        #
        # Since we passed pdf_path.parent as --outdir, the generated file
        # should live in that directory with the DOCX base name.
        generated_pdf = pdf_path.parent / docx_path.with_suffix('.pdf').name

        if generated_pdf.exists():
            # Use replace() instead of rename() so Windows can overwrite an
            # existing destination temp file created by the caller.
            if generated_pdf.resolve() != pdf_path.resolve():
                generated_pdf.replace(pdf_path)
            logger.info(f"Successfully converted DOCX to PDF: {pdf_path}")
        elif pdf_path.exists():
            # In some environments LibreOffice may already create the file
            # with the desired name; in that case just log success.
            logger.info(f"Successfully converted DOCX to PDF (already at target path): {pdf_path}")
        else:
            raise Exception(
                f"PDF file not created at expected locations: "
                f"{generated_pdf} or {pdf_path}"
            )
            
    except FileNotFoundError:
        raise Exception(
            "LibreOffice (soffice) not found. Install LibreOffice and ensure soffice is in PATH, "
            "or set LIBREOFFICE_PATH to the full soffice executable path."
        )
    except subprocess.TimeoutExpired:
        raise Exception("DOCX to PDF conversion timed out")
    except Exception as e:
        logger.exception(f"Failed to convert DOCX to PDF: {str(e)}")
        raise


def docx_to_pdf(docx_path: Path, pdf_path: Path, method: str = "libreoffice") -> None:
    """
    Convert DOCX to PDF using specified method.
    
    Args:
        docx_path: Path to source DOCX file
        pdf_path: Path to save output PDF
        method: Conversion method ("libreoffice" or "onlyoffice")
        
    Raises:
        Exception: If conversion fails
    """
    if method == "libreoffice":
        docx_to_pdf_libreoffice(docx_path, pdf_path)
    elif method == "onlyoffice":
        # TODO: Implement ONLYOFFICE conversion API call if needed
        raise NotImplementedError("ONLYOFFICE conversion method not yet implemented")
    else:
        raise ValueError(f"Unknown conversion method: {method}")
