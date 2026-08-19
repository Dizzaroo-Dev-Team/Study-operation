"""
PDF to TipTap JSON Converter Utility

Converts PDF files to TipTap JSON format for use in agreement templates.
"""

import logging
from pathlib import Path
from typing import Dict, Any
import pdfplumber

logger = logging.getLogger(__name__)


def sanitize_text(text: str) -> str:
    """
    Remove null characters (\u0000) that PostgreSQL JSONB cannot store.
    
    PostgreSQL's JSONB type cannot store null characters in text strings.
    This function removes them while preserving all other characters.
    
    Args:
        text: Input text string
        
    Returns:
        Sanitized text string with null characters removed
    """
    if not text:
        return text
    
    # Remove null characters (\u0000 or \x00)
    # Replace with empty string (remove) rather than space to preserve formatting
    sanitized = text.replace('\x00', '').replace('\u0000', '')
    
    return sanitized


def pdf_to_tiptap_json(pdf_path: Path) -> Dict[str, Any]:
    """
    Convert a PDF file to TipTap JSON format.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        TipTap JSON structure as a dictionary
        
    Raises:
        Exception: If PDF cannot be read or converted
    """
    try:
        # Extract text from PDF
        text_content = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    # Sanitize text to remove null characters and other problematic characters
                    page_text = sanitize_text(page_text)
                    
                    # Split text into paragraphs (by double newlines)
                    paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
                    
                    for para in paragraphs:
                        # Split into lines for better structure
                        lines = [line.strip() for line in para.split('\n') if line.strip()]
                        
                        for line in lines:
                            # Sanitize each line again to be safe
                            sanitized_line = sanitize_text(line)
                            if sanitized_line:  # Only add non-empty lines
                                text_content.append({
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": sanitized_line
                                        }
                                    ]
                                })
                        
                        # Add spacing between paragraphs
                        if para != paragraphs[-1]:
                            text_content.append({
                                "type": "paragraph",
                                "content": []
                            })
        
        # If no text was extracted, create a placeholder
        if not text_content:
            text_content = [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "PDF content extracted. Please review and format as needed."
                        }
                    ]
                }
            ]
        
        # Build TipTap document structure
        tiptap_json = {
            "type": "doc",
            "content": text_content
        }
        
        logger.info(f"Successfully converted PDF to TipTap JSON: {len(text_content)} paragraphs")
        return tiptap_json
        
    except Exception as e:
        logger.exception(f"Failed to convert PDF to TipTap JSON: {str(e)}")
        raise Exception(f"Failed to process PDF: {str(e)}")
