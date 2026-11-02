import html
import re

def sanitize_user_input(raw_text: str) -> str:
    """Production-grade text sanitizer for user chat inputs."""
    if not raw_text:
        return ""
    
    # 1. Strip HTML/XML tags to prevent XSS or injection rendering on frontends
    clean_text = re.sub(r'<[^>]*?>', '', raw_text)
    
    # 2. Escape special HTML characters
    clean_text = html.escape(clean_text)
    
    # 3. Remove weird control characters or null bytes that can break databases or logging
    clean_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean_text)
    
    # 4. Collapse excessive whitespace/newlines
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return clean_text