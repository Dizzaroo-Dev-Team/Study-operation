"""
Email mention extraction utility.
Extracts email addresses from text using @emailaddress pattern.
"""
import re
from typing import List


def extract_mention_emails(text: str) -> List[str]:
    """
    Extract email addresses mentioned in text using @emailaddress pattern.
    
    Pattern: @ followed by valid email pattern
    Example: @john@gmail.com
    
    Returns list of emails without "@" prefix.
    
    Args:
        text: The text to search for email mentions
        
    Returns:
        List of email addresses (without @ prefix)
    """
    if not text:
        return []
    
    # Strict pattern required by product spec.
    pattern = r'@([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    
    matches = re.findall(pattern, text)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_emails = []
    for email in matches:
        email_lower = email.strip().lower()
        if email_lower not in seen:
            seen.add(email_lower)
            unique_emails.append(email_lower)
    
    return unique_emails


def extractMentionEmails(text: str) -> List[str]:
    """CamelCase alias required by product spec."""
    return extract_mention_emails(text)
