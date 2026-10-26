"""
JobIntel - Skill Extraction Engine
Hybrid skill extractor combining curated ontology dictionaries, regex patterns, and context analysis.
"""

import json
import os
import re
from typing import List, Dict, Any, Set
from backend.app.core.config import settings
from backend.app.core.logging import logger
from nlp.preprocessor import TextPreprocessor


class ExtractedSkill:
    def __init__(
        self,
        name: str,
        display_name: str,
        category: str,
        confidence: float = 1.0,
        skill_type: str = "required",
        extraction_method: str = "dictionary"
    ):
        self.name = name
        self.display_name = display_name
        self.category = category
        self.confidence = confidence
        self.skill_type = skill_type
        self.extraction_method = extraction_method

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "confidence": self.confidence,
            "skill_type": self.skill_type,
            "extraction_method": self.extraction_method,
        }


class SkillExtractor:
    def __init__(self, taxonomy_path: str = settings.SKILLS_TAXONOMY_PATH):
        self.taxonomy_path = taxonomy_path
        self.skills_lookup: Dict[str, Dict[str, Any]] = {}
        self._load_taxonomy()

    def _load_taxonomy(self):
        """Load skills taxonomy dictionary from JSON file."""
        if not os.path.exists(self.taxonomy_path):
            logger.warning(f"Taxonomy path {self.taxonomy_path} not found. Using fallback taxonomy.")
            self._load_fallback_taxonomy()
            return

        try:
            with open(self.taxonomy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                skills = data.get("skills", [])
                for s in skills:
                    canonical = s["name"].lower()
                    entry = {
                        "name": canonical,
                        "display_name": s.get("display_name", canonical.title()),
                        "category": s.get("category", "General"),
                    }
                    self.skills_lookup[canonical] = entry
                    # Index aliases
                    for alias in s.get("aliases", []):
                        self.skills_lookup[alias.lower()] = entry
        except Exception as e:
            logger.error(f"Error loading skills taxonomy: {e}")
            self._load_fallback_taxonomy()

    def _load_fallback_taxonomy(self):
        default_skills = [
            ("python", "Python", "Programming Languages"),
            ("sql", "SQL", "Databases & Query"),
            ("power bi", "Power BI", "Business Intelligence"),
            ("tableau", "Tableau", "Business Intelligence"),
            ("excel", "Excel", "Business Intelligence"),
            ("r", "R", "Data Science"),
            ("machine learning", "Machine Learning", "AI & Machine Learning"),
            ("aws", "AWS", "Cloud & DevOps"),
            ("docker", "Docker", "Cloud & DevOps"),
            ("fastapi", "FastAPI", "Web Frameworks"),
            ("financial modeling", "Financial Modeling", "Finance"),
        ]
        for name, disp, cat in default_skills:
            self.skills_lookup[name] = {"name": name, "display_name": disp, "category": cat}

    def extract_skills(self, text: str, exclude_company: str = "") -> List[ExtractedSkill]:
        """
        Extract skills from job description text.
        Matches exact phrases and word-boundaries to avoid false positives. `exclude_company` drops a skill that
        is just the employer's own name (e.g. "MongoDB" in every MongoDB posting): that is boilerplate, not a
        requirement. Only whole-name matches are dropped; other company boilerplate is NOT filtered.
        """
        if not text:
            return []

        cleaned_text = TextPreprocessor.preprocess(text)
        found_canonical: Set[str] = set()
        results: List[ExtractedSkill] = []

        # Sort search terms by length descending to match longer phrases first (e.g. "power bi" before "bi")
        sorted_terms = sorted(self.skills_lookup.keys(), key=len, reverse=True)

        for term in sorted_terms:
            pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
            if re.search(pattern, cleaned_text, flags=re.IGNORECASE):
                entry = self.skills_lookup[term]
                canonical = entry["name"]
                if exclude_company and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", exclude_company.lower()):
                    continue
                if canonical not in found_canonical:
                    found_canonical.add(canonical)
                    
                    # Infer skill_type (required vs preferred) based on sentence context
                    skill_type = "required"
                    if "preferred" in cleaned_text or "nice to have" in cleaned_text or "plus" in cleaned_text:
                        # Simple context check
                        skill_type = "preferred" if term in ["docker", "kubernetes", "aws"] else "required"

                    results.append(
                        ExtractedSkill(
                            name=canonical,
                            display_name=entry["display_name"],
                            category=entry["category"],
                            confidence=0.95,
                            skill_type=skill_type,
                            extraction_method="dictionary",
                        )
                    )

        return results
