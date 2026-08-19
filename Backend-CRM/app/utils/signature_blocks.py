"""
Signature Block Generation Utility

Generates formatted signature blocks for agreements from templates.
Replaces {{SITE_SIGNATURE_BLOCK}} and {{SPONSOR_SIGNATURE_BLOCK}} placeholders.
"""

from typing import Dict, Any, Optional
from app.models import SiteProfile
from app.config import settings


def generate_site_signature_block(profile: SiteProfile) -> Dict[str, Any]:
    """
    Generate TipTap JSON structure for site signature block.
    
    Args:
        profile: The SiteProfile instance
        
    Returns:
        TipTap JSON structure representing the signature block
    """
    hospital_name = profile.hospital_name or ""
    signatory_name = profile.authorized_signatory_name or ""
    signatory_title = profile.authorized_signatory_title or ""
    
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Signed for and on behalf of:", "marks": [{"type": "bold"}]}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": hospital_name}
                ]
            },
            {
                "type": "paragraph",
                "content": []
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Name: "},
                    {"type": "text", "text": signatory_name}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Title: "},
                    {"type": "text", "text": signatory_title}
                ]
            },
            {
                "type": "paragraph",
                "content": []
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Signature: {{Signature:Recipient1}}"}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Date: {{Date:Recipient1}}"}
                ]
            }
        ]
    }


def generate_sponsor_signature_block(
    profile: SiteProfile,
    sponsor_signatory_name: Optional[str] = None,
    sponsor_signatory_email: Optional[str] = None,
    current_user_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate TipTap JSON structure for sponsor signature block.
    
    Args:
        profile: The SiteProfile instance (for primary_contracting_entity)
        sponsor_signatory_name: Sponsor signatory name from config
        sponsor_signatory_email: Sponsor signatory email from config
        current_user_email: Fallback to current logged-in user email
        
    Returns:
        TipTap JSON structure representing the signature block
    """
    contracting_entity = profile.primary_contracting_entity or ""
    
    # Get sponsor signatory name (from config, or fallback to current user)
    signatory_name = sponsor_signatory_name
    if not signatory_name:
        # Fallback to current user email if available
        if current_user_email:
            signatory_name = current_user_email.split("@")[0]  # Use email prefix as name
        else:
            signatory_name = ""
    
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Signed for and on behalf of:", "marks": [{"type": "bold"}]}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": contracting_entity}
                ]
            },
            {
                "type": "paragraph",
                "content": []
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Name: "},
                    {"type": "text", "text": signatory_name}
                ]
            },
            {
                "type": "paragraph",
                "content": []
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Signature: {{Signature:Recipient2}}"}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Date: {{Date:Recipient2}}"}
                ]
            }
        ]
    }


def replace_signature_block_placeholder(
    content: Any,
    placeholder_name: str,
    signature_block: Dict[str, Any]
) -> Any:
    """
    Replace a signature block placeholder in TipTap JSON content.
    
    Args:
        content: The TipTap JSON content (dict, list, or primitive)
        placeholder_name: The placeholder name (e.g., "SITE_SIGNATURE_BLOCK")
        signature_block: The signature block TipTap JSON structure to insert
        
    Returns:
        Content with placeholder replaced by signature block
    """
    import re
    
    # Pre-compute escaped placeholder name and construct pattern
    # Can't use backslashes in f-string expressions, so use string concatenation
    escaped_name = re.escape(placeholder_name)
    pattern = r'\{\{' + escaped_name + r'\}\}'
    
    if isinstance(content, dict):
        result = {}
        for key, value in content.items():
            if key == "text" and isinstance(value, str):
                # Check if this text node contains the signature block placeholder
                if re.search(pattern, value):
                    # Replace the placeholder with the signature block content
                    # We need to split the content and insert the signature block
                    # For simplicity, we'll replace the entire text node's parent paragraph
                    # with the signature block content
                    result[key] = value  # Keep original for now, will be handled at paragraph level
                else:
                    result[key] = value
            elif isinstance(value, (dict, list)):
                # Recursively process nested structures
                result[key] = replace_signature_block_placeholder(value, placeholder_name, signature_block)
            else:
                result[key] = value
        
        # Check if this is a paragraph containing the placeholder
        if content.get("type") == "paragraph" and "content" in content:
            paragraph_content = content.get("content", [])
            # Look for text nodes with the placeholder
            for i, item in enumerate(paragraph_content):
                if isinstance(item, dict) and item.get("type") == "text":
                    text_value = item.get("text", "")
                    if re.search(pattern, text_value):
                        # Replace this paragraph's content with the signature block
                        # Extract the signature block's content (skip the outer "doc" wrapper)
                        sig_content = signature_block.get("content", [])
                        return sig_content  # Return the content array to replace the paragraph
        return result
    elif isinstance(content, list):
        result = []
        i = 0
        while i < len(content):
            item = content[i]
            if isinstance(item, dict):
                # Check if this paragraph contains the signature block placeholder
                if item.get("type") == "paragraph" and "content" in item:
                    paragraph_content = item.get("content", [])
                    found_placeholder = False
                    for text_item in paragraph_content:
                        if isinstance(text_item, dict) and text_item.get("type") == "text":
                            text_value = text_item.get("text", "")
                            if re.search(pattern, text_value):
                                found_placeholder = True
                                break
                    
                    if found_placeholder:
                        # Replace this paragraph with the signature block content
                        sig_content = signature_block.get("content", [])
                        result.extend(sig_content)
                        i += 1
                        continue
                
                # Recursively process
                replaced = replace_signature_block_placeholder(item, placeholder_name, signature_block)
                if isinstance(replaced, list):
                    result.extend(replaced)
                else:
                    result.append(replaced)
            else:
                result.append(item)
            i += 1
        return result
    else:
        return content


def apply_signature_blocks(
    content: Dict[str, Any],
    profile: SiteProfile,
    sponsor_signatory_name: Optional[str] = None,
    sponsor_signatory_email: Optional[str] = None,
    current_user_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply signature block replacements to TipTap JSON content.
    
    Args:
        content: The TipTap JSON content
        profile: The SiteProfile instance
        sponsor_signatory_name: Sponsor signatory name from config
        sponsor_signatory_email: Sponsor signatory email from config
        current_user_email: Fallback to current logged-in user email
        
    Returns:
        Content with signature block placeholders replaced
    """
    import copy
    
    # Deep copy to avoid modifying original
    result = copy.deepcopy(content)
    
    # Generate signature blocks
    site_sig_block = generate_site_signature_block(profile)
    sponsor_sig_block = generate_sponsor_signature_block(
        profile,
        sponsor_signatory_name,
        sponsor_signatory_email,
        current_user_email
    )
    
    # Replace placeholders
    result = replace_signature_block_placeholder(result, "SITE_SIGNATURE_BLOCK", site_sig_block)
    result = replace_signature_block_placeholder(result, "SPONSOR_SIGNATURE_BLOCK", sponsor_sig_block)
    
    return result
