"""
Text extraction utilities for various document types
"""

import PyPDF2
import docx
from typing import Union
import logging

from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)

async def extract_document_text(file_buffer: bytes, mime_type: str) -> str:
    """Extract text from various document types"""
    try:
        if not file_buffer:
            raise ValueError("No file content provided")
        
        if mime_type == 'application/pdf':
            return _extract_pdf_text(file_buffer)
        elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
            return _extract_docx_text(file_buffer)
        elif mime_type == 'text/plain':
            return file_buffer.decode('utf-8')
        else:
            raise ValueError(f"Unsupported file type for text extraction: {mime_type}")
    
    except Exception as e:
        logger.exception(f"Failed to extract text from {sfmt(mime_type)}: {sfmt(str(e))}")
        raise Exception(f"Failed to extract text from document: {str(e)}")

def _extract_pdf_text(file_buffer: bytes) -> str:
    """Extract text from PDF using PyPDF2 with error handling"""
    try:
        import io
        
        # Create a file-like object from buffer
        pdf_file = io.BytesIO(file_buffer)
        
        # Create PDF reader with strict mode to handle encrypted PDFs
        pdf_reader = PyPDF2.PdfReader(pdf_file, strict=False)
        
        # Extract text from all pages
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            try:
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n"
            except Exception as page_error:
                logger.warning(f"Failed to extract text from page {page_num}: {str(page_error)}")
                continue
        
        return text.strip()
    
    except Exception as e:
        logger.exception(f"PDF text extraction failed: {str(e)}")
        raise Exception(f"Failed to extract text from PDF: {str(e)}")

def _extract_docx_text(file_buffer: bytes) -> str:
    """Extract text from DOCX using python-docx"""
    try:
        import io
        
        # Create a file-like object from buffer
        docx_file = io.BytesIO(file_buffer)
        
        # Create document object
        doc = docx.Document(docx_file)
        
        # Extract text from all paragraphs
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        
        return text.strip()
    
    except Exception as e:
        logger.exception(f"DOCX text extraction failed: {str(e)}")
        raise Exception(f"Failed to extract text from DOCX: {str(e)}")
