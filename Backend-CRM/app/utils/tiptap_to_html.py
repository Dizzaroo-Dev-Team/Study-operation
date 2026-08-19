"""
Utility to convert TipTap JSON to HTML for PDF generation.
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def tiptap_json_to_html(json_content: Dict[str, Any]) -> str:
    """
    Convert TipTap JSON content to HTML string.
    
    Args:
        json_content: TipTap JSON document (e.g., {"type": "doc", "content": [...]})
        
    Returns:
        HTML string
    """
    if not json_content or not isinstance(json_content, dict):
        return "<p>Empty document</p>"
    
    content = json_content.get("content", [])
    if not content:
        return "<p>Empty document</p>"
    
    html_parts = []
    
    for node in content:
        html_parts.append(_render_node(node))
    
    # Wrap in basic HTML structure
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 40px;
            color: #333;
        }}
        h1 {{ font-size: 24px; margin-top: 20px; margin-bottom: 10px; }}
        h2 {{ font-size: 20px; margin-top: 18px; margin-bottom: 8px; }}
        h3 {{ font-size: 18px; margin-top: 16px; margin-bottom: 6px; }}
        p {{ margin: 10px 0; }}
        ul, ol {{ margin: 10px 0; padding-left: 30px; }}
        li {{ margin: 5px 0; }}
        strong {{ font-weight: bold; }}
        em {{ font-style: italic; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        img {{ max-width: 100%; height: auto; margin: 10px 0; }}
    </style>
</head>
<body>
{''.join(html_parts)}
</body>
</html>"""
    
    return html


def _render_node(node: Dict[str, Any]) -> str:
    """Render a single TipTap node to HTML."""
    node_type = node.get("type", "")
    content = node.get("content", [])
    
    if node_type == "paragraph":
        inner_html = "".join(_render_node(child) for child in content) if content else ""
        return f"<p>{inner_html}</p>\n"
    
    elif node_type == "heading":
        level = node.get("attrs", {}).get("level", 1)
        inner_html = "".join(_render_node(child) for child in content) if content else ""
        return f"<h{level}>{inner_html}</h{level}>\n"
    
    elif node_type == "bulletList":
        items = "".join(_render_node(child) for child in content) if content else ""
        return f"<ul>{items}</ul>\n"
    
    elif node_type == "orderedList":
        items = "".join(_render_node(child) for child in content) if content else ""
        return f"<ol>{items}</ol>\n"
    
    elif node_type == "listItem":
        inner_html = "".join(_render_node(child) for child in content) if content else ""
        return f"<li>{inner_html}</li>\n"
    
    elif node_type == "text":
        text = node.get("text", "")
        marks = node.get("marks", [])
        
        # Apply marks (bold, italic, etc.)
        for mark in marks:
            mark_type = mark.get("type", "")
            if mark_type == "bold":
                text = f"<strong>{text}</strong>"
            elif mark_type == "italic":
                text = f"<em>{text}</em>"
            elif mark_type == "underline":
                text = f"<u>{text}</u>"
        
        return text
    
    elif node_type == "hardBreak":
        return "<br>\n"
    
    elif node_type == "table":
        inner_html = "".join(_render_node(child) for child in content) if content else ""
        return f"<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; width: 100%; margin: 10px 0;'>{inner_html}</table>\n"
    
    elif node_type == "tableRow":
        inner_html = "".join(_render_node(child) for child in content) if content else ""
        return f"<tr>{inner_html}</tr>\n"
    
    elif node_type == "tableCell" or node_type == "tableHeader":
        inner_html = "".join(_render_node(child) for child in content) if content else ""
        tag = "th" if node_type == "tableHeader" else "td"
        return f"<{tag} style='border: 1px solid #ddd; padding: 8px;'>{inner_html}</{tag}>\n"
    
    elif node_type == "image":
        attrs = node.get("attrs", {})
        src = attrs.get("src", "")
        alt = attrs.get("alt", "")
        return f"<img src='{src}' alt='{alt}' style='max-width: 100%; height: auto; margin: 10px 0;' />\n"
    
    else:
        # Unknown node type - try to render content recursively
        if content:
            return "".join(_render_node(child) for child in content)
        return ""
