"""
DOCX to HTML Converter Utility

Converts DOCX files to clean HTML using mammoth library.
Preserves formatting, tables, and images.
"""

import logging
from pathlib import Path
from typing import Tuple
import mammoth

logger = logging.getLogger(__name__)


def docx_to_html(docx_path: Path) -> Tuple[str, dict]:
    """
    Convert a DOCX file to HTML format.
    
    Args:
        docx_path: Path to the DOCX file
        
    Returns:
        Tuple of (HTML string, conversion warnings dict)
        
    Raises:
        Exception: If DOCX cannot be read or converted
    """
    try:
        with open(docx_path, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)
            html_content = result.value
            warnings = result.messages
            
            if warnings:
                logger.warning(f"DOCX conversion warnings: {warnings}")
            
            logger.info(f"Successfully converted DOCX to HTML: {len(html_content)} characters")
            return html_content, warnings
            
    except Exception as e:
        logger.exception(f"Failed to convert DOCX to HTML: {str(e)}")
        raise Exception(f"Failed to process DOCX file: {str(e)}")
