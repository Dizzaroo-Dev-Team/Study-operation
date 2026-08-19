import logging
import re
from typing import Dict, Any

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    try:
        import PyPDF2
        import io
        PDF_AVAILABLE = True
    except ImportError:
        PDF_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import pandas as pd
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

logger = logging.getLogger(__name__)

async def extract_document_text(content: bytes, mime_type: str) -> str:
    """Extract text from document based on mime type (Node.js equivalent)"""
    try:
        if mime_type == 'application/pdf':
            return extract_pdf_text(content)
        elif mime_type and ('word' in mime_type or 'docx' in mime_type):
            return extract_docx_text(content)
        elif mime_type and ('excel' in mime_type or 'xlsx' in mime_type):
            return extract_excel_text(content)
        elif mime_type and ('text' in mime_type or mime_type == 'text/plain'):
            return content.decode('utf-8', errors='ignore')
        else:
            # Default: try to decode as text
            try:
                return content.decode('utf-8', errors='ignore')
            except:
                return str(content)
    except Exception as e:
        logger.exception(f"Error extracting document text: {e}")
        return ""

def extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF (Node.js equivalent)"""
    try:
        if PDF_AVAILABLE:
            # Try pdfplumber first (better text extraction)
            if 'pdfplumber' in globals():
                import io
                with io.BytesIO(content) as pdf_file:
                    with pdfplumber.open(pdf_file) as pdf:
                        text = ""
                        for page in pdf.pages:
                            page_text = page.extract_text() or ""
                            text += page_text + "\n"
                        return text
            
            # Fallback to PyPDF2
            if 'PyPDF2' in globals():
                import io
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        
        logger.warning("PDF processing not available")
        return ""
    except Exception as e:
        logger.exception(f"Error extracting PDF text: {e}")
        return ""

def extract_docx_text(content: bytes) -> str:
    """Extract text from DOCX (Node.js equivalent)"""
    try:
        if DOCX_AVAILABLE:
            import io
            doc = docx.Document(io.BytesIO(content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        
        logger.warning("DOCX processing not available")
        return ""
    except Exception as e:
        logger.exception(f"Error extracting DOCX text: {e}")
        return ""

def extract_excel_text(content: bytes) -> str:
    """Extract text from Excel (Node.js equivalent)"""
    try:
        if EXCEL_AVAILABLE:
            import io
            df = pd.read_excel(io.BytesIO(content))
            text = ""
            for sheet_name in df.sheet_names:
                if isinstance(df, dict):
                    sheet_df = df[sheet_name]
                else:
                    sheet_df = df
                # Convert to rows and join
                rows = sheet_df.values.tolist()
                for row in rows:
                    row_text = " ".join(str(cell) for cell in row if pd.notna(cell))
                    text += row_text + "\n"
            return text
        
        logger.warning("Excel processing not available")
        return ""
    except Exception as e:
        logger.exception(f"Error extracting Excel text: {e}")
        return ""


def get_page_count(content: bytes, mime_type: str) -> int | None:
    """Extract page count from document (Node.js equivalent for pageCount). Returns None if unavailable."""
    if not content or not mime_type:
        return None
    try:
        if "pdf" in mime_type.lower() and PDF_AVAILABLE:
            import io
            try:
                with io.BytesIO(content) as f:
                    with pdfplumber.open(f) as pdf:
                        return len(pdf.pages)
            except Exception:
                try:
                    import PyPDF2
                    with io.BytesIO(content) as f:
                        reader = PyPDF2.PdfReader(f)
                        return len(reader.pages)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Page count extraction failed: {e}")
    return None
