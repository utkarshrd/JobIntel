"""
JobIntel - Entity Extraction Engine
Extracts structured entities such as qualifications, experience range, and organizations from job descriptions.
"""

import re
from typing import List, Optional


class EntityExtractor:
    @staticmethod
    def extract_experience_years(text: str) -> tuple[Optional[float], Optional[float]]:
        """
        Extract minimum and maximum required years of experience using regex patterns.
        Examples: '3-5 years', '2+ years', 'minimum 4 years', '0 to 2 yrs'.
        """
        if not text:
            return None, None

        cleaned = text.lower()

        # Pattern: "3 - 5 years" or "3 to 5 yrs"
        range_match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?)", cleaned)
        if range_match:
            try:
                min_yr = float(range_match.group(1))
                max_yr = float(range_match.group(2))
                return min_yr, max_yr
            except ValueError:
                pass

        # Pattern: "3+ years" or "3 + yrs"
        plus_match = re.search(r"(\d+)\s*\+\s*(?:years?|yrs?)", cleaned)
        if plus_match:
            try:
                # "3+ years" states only a minimum; never invent an upper bound.
                return float(plus_match.group(1)), None
            except ValueError:
                pass

        # Pattern: "minimum 2 years" or "at least 2 years"
        min_match = re.search(r"(?:minimum|at least|min\.?)\s*(\d+)\s*(?:years?|yrs?)", cleaned)
        if min_match:
            try:
                min_yr = float(min_match.group(1))
                return min_yr, None
            except ValueError:
                pass

        return None, None

    @staticmethod
    def extract_qualifications(text: str) -> List[str]:
        """
        Extract degree and educational requirements (B.Tech, BE, MBA, MCA, Bachelor's, Master's).
        """
        if not text:
            return []

        # (label, case-insensitive pattern, case-sensitive pattern). Bare "be"/"me" are ordinary
        # English words, so B.E./M.E. are only accepted in the dotted, capitalised form.
        qual_patterns = [
            ("B.Tech / B.E.", r"\b(b\.?tech|bachelor of engineering|bachelor of technology)\b", r"\bB\.E\b"),
            ("M.Tech / M.E.", r"\b(m\.?tech|master of engineering|master of technology)\b", r"\bM\.E\b"),
            ("MBA", r"\b(mba|master of business administration)\b", None),
            ("MCA", r"\b(mca|master of computer applications)\b", None),
            ("BCA / B.Sc", r"\b(bca|b\.?sc|bachelor of science|bachelor of computer applications)\b", None),
            ("Master's Degree", r"\b(master'?s|post-?graduate)\b", None),
            ("Bachelor's Degree", r"\b(bachelor'?s|undergraduate)\b", None),
            ("Degree (level unspecified)", r"\bdegree\b", None),
            ("PhD", r"\b(phd|doctorate)\b", None),
        ]

        found = []
        for name, pat_ci, pat_cs in qual_patterns:
            if re.search(pat_ci, text, flags=re.IGNORECASE) or (pat_cs and re.search(pat_cs, text)):
                found.append(name)

        return found
