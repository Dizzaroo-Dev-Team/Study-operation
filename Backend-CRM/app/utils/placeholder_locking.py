"""
Placeholder Locking Utility

Applies locking to merged placeholder content based on template configuration.
Marks locked placeholders in the TipTap JSON structure.
"""

from typing import Any, Dict, Optional, Set
import re
import copy


def apply_locking_to_text(
    text: str,
    placeholder_name: str,
    is_locked: bool
) -> tuple[str, bool]:
    """
    Apply locking to text that contains a specific placeholder.
    
    Args:
        text: The text string
        placeholder_name: The placeholder name (e.g., "PI_NAME")
        is_locked: Whether this placeholder should be locked
        
    Returns:
        Tuple of (text, should_wrap_in_locked_node)
        If the text contains the placeholder and is_locked, returns (text, True)
    """
    if not text or not isinstance(text, str):
        return text, False
    
    # Check if text contains this specific placeholder
    pattern = r'\{\{' + re.escape(placeholder_name) + r'\}\}'
    if re.search(pattern, text):
        # After merge, placeholder is replaced, but we need to mark the text node
        return text, is_locked
    
    return text, False


def apply_locking_to_json(
    content: Any,
    placeholder_config: Optional[Dict[str, Dict[str, bool]]],
    placeholder_locations: Dict[str, list]
) -> Any:
    """
    Recursively apply locking to JSON structure based on placeholder configuration.
    
    This function:
    1. Finds text nodes that contain merged placeholder values
    2. Adds a "locked" mark to them if the placeholder is marked as non-editable
    
    Args:
        content: The JSON content (dict, list, or primitive)
        placeholder_config: Configuration dict: {"PLACEHOLDER_NAME": {"editable": true/false}}
        placeholder_locations: Dict mapping placeholder names to lists of text values that contain them
        
    Returns:
        JSON structure with locked nodes marked
    """
    if not placeholder_config:
        return content
    
    if isinstance(content, dict):
        result = {}
        for key, value in content.items():
            if key == "text" and isinstance(value, str):
                # This is a text node - check if it contains any locked placeholder values
                text_value = value
                is_locked = False
                
                # Check if this text value is in the list for any locked placeholder
                for placeholder_name, text_values in placeholder_locations.items():
                    if text_value in text_values:
                        # Check if this placeholder is locked
                        config = placeholder_config.get(placeholder_name, {})
                        if not config.get("editable", True):
                            is_locked = True
                            break
                
                result[key] = text_value
                if is_locked:
                    # Add locked mark to the text node
                    existing_marks = content.get("marks", [])
                    if not any(mark.get("type") == "locked" for mark in existing_marks):
                        result["marks"] = existing_marks + [{"type": "locked", "attrs": {"locked": True}}]
                elif "marks" in content:
                    # Preserve existing marks if any
                    result["marks"] = content.get("marks", [])
            elif isinstance(value, (dict, list)):
                # Recursively process nested structures
                result[key] = apply_locking_to_json(value, placeholder_config, placeholder_locations)
            else:
                result[key] = value
        return result
    elif isinstance(content, list):
        return [apply_locking_to_json(item, placeholder_config, placeholder_locations) for item in content]
    else:
        return content


def apply_placeholder_locking(
    merged_content: Dict[str, Any],
    placeholder_config: Optional[Dict[str, Dict[str, bool]]],
    placeholder_locations: Dict[str, list]
) -> Dict[str, Any]:
    """
    Apply locking to merged content based on placeholder configuration.
    
    Args:
        merged_content: The merged template content (after placeholder replacement)
        placeholder_config: Configuration dict: {"PLACEHOLDER_NAME": {"editable": true/false}}
        placeholder_locations: Dict mapping placeholder names to lists of text values that contain them
        
    Returns:
        Content with locked nodes marked
    """
    if not placeholder_config:
        return merged_content
    
    # Deep copy to avoid modifying original
    locked_content = copy.deepcopy(merged_content)
    
    # Apply locking
    return apply_locking_to_json(locked_content, placeholder_config, placeholder_locations)
