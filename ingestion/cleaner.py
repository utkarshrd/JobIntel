"""
JobIntel - Text & Data Cleaning Utilities
Cleans HTML tags, whitespace, unwanted unicode characters from raw job descriptions.
"""

import re
import html
from typing import Optional


class TextCleaner:
    @staticmethod
    def clean_html(text: Optional[str]) -> str:
        """
        Convert HTML formatting to clean plain text.
        Preserves bullet points, removes script/style tags, normalizes whitespace.
        """
        if not text:
            return ""

        # Decode HTML entities (&amp;, &nbsp;, etc.)
        cleaned = html.unescape(text)

        # Remove script and style elements
        cleaned = re.sub(r"<(script|style).*?>.*?</\1>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

        # Replace block tags with newline
        cleaned = re.sub(r"<(p|br|div|li|tr)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)

        # Strip all other HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # Normalize multiple spaces and multiple newlines
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)

        return cleaned.strip()

    @staticmethod
    def normalize_string(text: Optional[str]) -> Optional[str]:
        """Strip whitespace and lowercase text for exact string comparisons."""
        if not text:
            return None
        return text.strip().lower()
