"""
JobIntel - NLP Text Preprocessing Pipeline
Cleans, segments, tokenizes, and normalizes unstructured job descriptions.
"""

import re
from typing import List, Optional
from ingestion.cleaner import TextCleaner


class TextPreprocessor:
    """
    Text preprocessing engine for TWSMA pipeline.
    """

    STOPWORDS = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
        "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
        "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't",
        "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have",
        "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself",
        "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into",
        "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
        "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our",
        "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's",
        "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs",
        "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
        "they've", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't",
        "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's",
        "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't",
        "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
        "yourselves", "will", "shall", "job", "role", "candidate", "responsibilities", "requirements",
        "experience", "years", "work", "team", "looking", "must"
    }

    @classmethod
    def preprocess(cls, text: Optional[str]) -> str:
        """
        Complete text cleaning and normalization pipeline.
        """
        if not text:
            return ""

        # 1. Clean HTML and entities
        text = TextCleaner.clean_html(text)

        # 2. Lowercase
        text = text.lower()

        # 3. Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    @classmethod
    def tokenize(cls, text: str, remove_stopwords: bool = True) -> List[str]:
        """
        Tokenize string into words, preserving programming terms like c++, c#, .net, node.js.
        """
        # Protect special tokens
        text = text.replace("c++", "cpp_token").replace("c#", "csharp_token").replace(".net", "dotnet_token")
        
        # Remove punctuation except underscores
        text = re.sub(r"[^\w\s_]", " ", text)
        tokens = text.split()

        cleaned_tokens = []
        for t in tokens:
            t = t.replace("cpp_token", "c++").replace("csharp_token", "c#").replace("dotnet_token", ".net")
            if remove_stopwords and t.lower() in cls.STOPWORDS:
                continue
            if len(t) > 1:
                cleaned_tokens.append(t)

        return cleaned_tokens

    @classmethod
    def segment_sentences(cls, text: str) -> List[str]:
        """Split text into sentences based on punctuation and linebreaks."""
        if not text:
            return []
        cleaned = TextCleaner.clean_html(text)
        sentences = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
        return [s.strip() for s in sentences if s.strip()]
