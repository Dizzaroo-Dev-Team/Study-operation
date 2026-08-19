"""
HTML to TipTap JSON Converter Utility

Converts clean HTML to TipTap JSON format for use in agreement templates.
Handles paragraphs, headings, lists, tables, images, and formatting.
"""

import logging
from typing import Dict, Any, List
from html.parser import HTMLParser
import re

logger = logging.getLogger(__name__)


class HTMLToTipTapParser(HTMLParser):
    """Parser to convert HTML to TipTap JSON structure."""
    
    def __init__(self):
        super().__init__()
        self.stack = []
        self.current_node = None
        self.doc = {"type": "doc", "content": []}
        self.current_text = ""
        self.current_marks = []
        
    def handle_starttag(self, tag, attrs):
        """Handle opening HTML tags."""
        attrs_dict = dict(attrs)
        
        if tag == "p":
            # Start new paragraph
            self._flush_text()
            self.current_node = {"type": "paragraph", "content": []}
            self.stack.append(self.current_node)
            
        elif tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            # Start new heading
            self._flush_text()
            level = int(tag[1])
            self.current_node = {
                "type": "heading",
                "attrs": {"level": level},
                "content": []
            }
            self.stack.append(self.current_node)
            
        elif tag == "ul":
            # Start bullet list
            self._flush_text()
            self.current_node = {"type": "bulletList", "content": []}
            self.stack.append(self.current_node)
            
        elif tag == "ol":
            # Start ordered list
            self._flush_text()
            self.current_node = {"type": "orderedList", "content": []}
            self.stack.append(self.current_node)
            
        elif tag == "li":
            # List item
            self._flush_text()
            self.current_node = {"type": "listItem", "content": []}
            if self.stack:
                self.stack[-1].setdefault("content", []).append(self.current_node)
            self.stack.append(self.current_node)
            
        elif tag == "strong" or tag == "b":
            # Bold mark
            self._flush_text()
            self.current_marks.append({"type": "bold"})
            
        elif tag == "em" or tag == "i":
            # Italic mark
            self._flush_text()
            self.current_marks.append({"type": "italic"})
            
        elif tag == "u":
            # Underline mark
            self._flush_text()
            self.current_marks.append({"type": "underline"})
            
        elif tag == "br":
            # Hard break
            self._flush_text()
            if self.stack:
                self.stack[-1].setdefault("content", []).append({"type": "hardBreak"})
                
        elif tag == "table":
            # Table
            self._flush_text()
            self.current_node = {"type": "table", "content": []}
            self.stack.append(self.current_node)
            
        elif tag == "tr":
            # Table row
            self._flush_text()
            self.current_node = {"type": "tableRow", "content": []}
            if self.stack:
                self.stack[-1].setdefault("content", []).append(self.current_node)
            self.stack.append(self.current_node)
            
        elif tag == "td":
            # Table cell
            self._flush_text()
            cell_type = "tableCell"
            self.current_node = {"type": cell_type, "content": [{"type": "paragraph", "content": []}]}
            if self.stack:
                self.stack[-1].setdefault("content", []).append(self.current_node)
            self.stack.append(self.current_node)
            
        elif tag == "th":
            # Table header cell
            self._flush_text()
            self.current_node = {"type": "tableHeader", "content": [{"type": "paragraph", "content": []}]}
            if self.stack:
                self.stack[-1].setdefault("content", []).append(self.current_node)
            self.stack.append(self.current_node)
            
        elif tag == "img":
            # Image
            self._flush_text()
            src = attrs_dict.get("src", "")
            alt = attrs_dict.get("alt", "")
            image_node = {
                "type": "image",
                "attrs": {
                    "src": src,
                    "alt": alt
                }
            }
            if self.stack:
                self.stack[-1].setdefault("content", []).append(image_node)
    
    def handle_endtag(self, tag):
        """Handle closing HTML tags."""
        if tag in ["p", "h1", "h2", "h3", "h4", "h5", "h6"]:
            self._flush_text()
            if self.stack:
                node = self.stack.pop()
                if not self.stack:
                    # Top level - add to doc
                    self.doc["content"].append(node)
                elif self.stack:
                    # Add to parent
                    self.stack[-1].setdefault("content", []).append(node)
            self.current_node = None
            
        elif tag in ["ul", "ol"]:
            self._flush_text()
            if self.stack:
                node = self.stack.pop()
                if not self.stack:
                    self.doc["content"].append(node)
                elif self.stack:
                    self.stack[-1].setdefault("content", []).append(node)
            self.current_node = None
            
        elif tag == "li":
            self._flush_text()
            if self.stack:
                self.stack.pop()
            self.current_node = None
            
        elif tag in ["strong", "b", "em", "i", "u"]:
            self._flush_text()
            if self.current_marks:
                self.current_marks.pop()
                
        elif tag == "table":
            self._flush_text()
            if self.stack:
                node = self.stack.pop()
                if not self.stack:
                    self.doc["content"].append(node)
                elif self.stack:
                    self.stack[-1].setdefault("content", []).append(node)
            self.current_node = None
            
        elif tag in ["tr", "td", "th"]:
            self._flush_text()
            if self.stack:
                self.stack.pop()
            self.current_node = None
    
    def handle_data(self, data):
        """Handle text data."""
        # Clean up whitespace but preserve structure
        text = data.strip()
        if text:
            self.current_text += text + " "
    
    def _flush_text(self):
        """Flush accumulated text as a text node."""
        if self.current_text.strip():
            text_node = {
                "type": "text",
                "text": self.current_text.strip()
            }
            if self.current_marks:
                text_node["marks"] = self.current_marks.copy()
            
            if self.stack:
                # Find the appropriate container (paragraph or list item)
                # For table cells, ensure we're adding to the paragraph inside
                target = self.stack[-1]
                if target.get("type") in ["tableCell", "tableHeader"]:
                    # Add to the paragraph inside the cell
                    if target.get("content") and target["content"][0].get("type") == "paragraph":
                        target["content"][0].setdefault("content", []).append(text_node)
                    else:
                        # Create paragraph if it doesn't exist
                        para = {"type": "paragraph", "content": [text_node]}
                        target.setdefault("content", []).append(para)
                else:
                    target.setdefault("content", []).append(text_node)
            else:
                # No parent - create paragraph wrapper
                para = {"type": "paragraph", "content": [text_node]}
                self.doc["content"].append(para)
            
            self.current_text = ""
    
    def get_result(self) -> Dict[str, Any]:
        """Get the final TipTap JSON document."""
        self._flush_text()
        # Ensure we have at least one paragraph
        if not self.doc["content"]:
            self.doc["content"] = [{"type": "paragraph", "content": []}]
        return self.doc


def html_to_tiptap_json(html_content: str) -> Dict[str, Any]:
    """
    Convert HTML content to TipTap JSON format.
    
    Args:
        html_content: HTML string
        
    Returns:
        TipTap JSON structure as a dictionary
    """
    try:
        # Clean HTML - remove script and style tags
        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Parse HTML
        parser = HTMLToTipTapParser()
        parser.feed(html_content)
        result = parser.get_result()
        
        logger.info(f"Successfully converted HTML to TipTap JSON: {len(result.get('content', []))} top-level nodes")
        return result
        
    except Exception as e:
        logger.exception(f"Failed to convert HTML to TipTap JSON: {str(e)}")
        raise Exception(f"Failed to process HTML: {str(e)}")
