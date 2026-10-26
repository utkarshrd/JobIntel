"""
JobIntel - Job Data Normalization Pipeline
Normalizes varying external API schema records into structured JobCreate models.
"""
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from backend.app.schemas.job import JobCreate
from ingestion.cleaner import TextCleaner
from ingestion.deduplicator import Deduplicator
from nlp.classifier import JobRoleClassifier


class JobNormalizer:
    @staticmethod
    def extract_city_state(location_str: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Extract city and state from typical Indian location strings."""
        if not location_str:
            return None, None

        loc = location_str.strip()
        parts = [p.strip() for p in loc.split(",") if p.strip()]

        known_indian_cities = {
            "mumbai": "Maharashtra",
            "pune": "Maharashtra",
            "bengaluru": "Karnataka",
            "bangalore": "Karnataka",
            "hyderabad": "Telangana",
            "delhi": "Delhi",
            "new delhi": "Delhi",
            "gurugram": "Haryana",
            "gurgaon": "Haryana",
            "noida": "Uttar Pradesh",
            "chennai": "Tamil Nadu",
            "kolkata": "West Bengal",
            "ahmedabad": "Gujarat",
            "jaipur": "Rajasthan",
            "kochi": "Kerala",
            "coimbatore": "Tamil Nadu",
            "indore": "Madhya Pradesh",
            "chandigarh": "Punjab/Haryana",
        }

        city = None
        state = None

        canonical = {"bangalore": "Bengaluru", "gurgaon": "Gurugram", "new delhi": "Delhi"}
        # Earliest known city mentioned anywhere in the string, so "Bengaluru-vtp" / "Mumbai / bangalore" resolve.
        low = loc.lower()
        hits = [(m.start(), name) for name in known_indian_cities
                for m in [re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low)] if m]
        if hits:
            name = min(hits, key=lambda h: (h[0], -len(h[1])))[1]
            city, state = canonical.get(name, name.title()), known_indian_cities[name]

        if not city and parts:
            city = parts[0].capitalize()
            if len(parts) > 1:
                state = parts[1].capitalize()

        # A country name or a "Remote ..." label is not a city: keep it missing rather than invent a location.
        if city and (city.lower() == "india" or city.lower().startswith("remote")):
            return None, None
        return city, state

    @staticmethod
    def infer_role_category(title: str) -> str:
        """Infer role domain from title. Delegates to the single classifier in nlp.classifier."""
        return JobRoleClassifier.classify(title or "")[0]

    @staticmethod
    def normalize_jobvetta_record(raw: Dict[str, Any]) -> Optional[JobCreate]:
        """Convert a raw Jobvetta API record to a normalized JobCreate model."""
        if not raw:
            return None

        # Title & Company
        title = raw.get("title") or raw.get("job_title") or "Untitled Position"
        company_name = raw.get("company") or raw.get("company_name") or "Confidential"

        # Unique external ID or deterministic hash
        job_id = str(raw.get("id") or raw.get("job_id") or "")
        location_raw = raw.get("location") or raw.get("city") or "India"

        # Assemble rich description from API fields (description, responsibilities, qualifications, skills)
        desc_parts = []
        if raw.get("description"):
            desc_parts.append(str(raw["description"]))
        if raw.get("responsibilities") and isinstance(raw["responsibilities"], list):
            desc_parts.append("Responsibilities:\n" + "\n".join([f"- {r}" for r in raw["responsibilities"]]))
        if raw.get("minimum_qualifications") and isinstance(raw["minimum_qualifications"], list):
            desc_parts.append("Minimum Qualifications:\n" + "\n".join([f"- {q}" for q in raw["minimum_qualifications"]]))
        if raw.get("skills_required") and isinstance(raw["skills_required"], list):
            desc_parts.append("Required Skills:\n" + ", ".join(raw["skills_required"]))

        description_raw = "\n\n".join(desc_parts) if desc_parts else (raw.get("snippet") or raw.get("summary") or title)

        if not job_id:
            job_id = Deduplicator.generate_job_hash(
                title=title,
                company_name=company_name,
                location=location_raw,
                description=description_raw,
            )

        # Cleaning
        description_cleaned = TextCleaner.clean_html(description_raw)
        city, state = JobNormalizer.extract_city_state(location_raw)
        role_category = JobNormalizer.infer_role_category(title)

        # Work Model
        work_model = raw.get("work_model") or raw.get("workplace_type")
        if not work_model:
            wm_low = f"{title} {location_raw} {description_cleaned}".lower()
            if "remote" in wm_low or "work from home" in wm_low:
                work_model = "Remote"
            elif "hybrid" in wm_low:
                work_model = "Hybrid"
            else:
                work_model = None  # not stated: stays missing (no placeholder)

        # Employment Type
        employment_type = raw.get("employment_type") or raw.get("job_type")
        if not employment_type:
            et_low = f"{title} {description_cleaned}".lower()
            if "intern" in et_low or "internship" in et_low:
                employment_type = "Internship"
            elif "contract" in et_low:
                employment_type = "Contract"
            elif "part time" in et_low or "part-time" in et_low:
                employment_type = "Part-time"
            else:
                employment_type = None  # not stated: stays missing

        # Experience Level
        exp_level = raw.get("experience_level")
        if not exp_level:
            exp_low = f"{title} {description_cleaned}".lower()
            if "senior" in exp_low or "lead" in exp_low or "principal" in exp_low:
                exp_level = "Senior"
            elif "junior" in exp_low or "entry" in exp_low or "graduate" in exp_low or "fresher" in exp_low:
                exp_level = "Entry-level"
            else:
                exp_level = None  # no explicit signal: stays missing (no "Mid-level" placeholder)

        # Salary fields (Preserve missing values as None - No fake imputation)
        salary_min = raw.get("salary_min") or raw.get("min_salary")
        salary_max = raw.get("salary_max") or raw.get("max_salary")
        try:
            salary_min = float(salary_min) if salary_min is not None else None
            salary_max = float(salary_max) if salary_max is not None else None
        except (ValueError, TypeError):
            salary_min, salary_max = None, None

        # Posted timestamp (Jobvetta returns unix timestamp in seconds for created_at / last_seen_date)
        posted_at = None
        raw_posted = raw.get("created_at") or raw.get("posted_at") or raw.get("date_posted")
        if raw_posted:
            try:
                if isinstance(raw_posted, (int, float)):
                    posted_at = datetime.fromtimestamp(raw_posted, timezone.utc)
                elif isinstance(raw_posted, str):
                    posted_at = datetime.fromisoformat(raw_posted.replace("Z", "+00:00"))
            except Exception:
                posted_at = datetime.now(timezone.utc)
        else:
            posted_at = datetime.now(timezone.utc)

        return JobCreate(
            job_id=str(job_id),
            source="jobvetta",
            source_url=raw.get("url") or raw.get("link") or raw.get("job_url"),
            title=title.strip(),
            normalized_title=title.strip().title(),
            role_category=role_category,
            company_name=company_name.strip(),
            location_raw=location_raw,
            city=city,
            state=state,
            country="India",
            description=description_raw,
            description_cleaned=description_cleaned,
            employment_type=employment_type,
            work_model=work_model,
            experience_level=exp_level,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=raw.get("salary_currency", "INR"),
            salary_period=raw.get("salary_period", "yearly"),
            posted_at=posted_at,
            raw_payload=raw,
        )

    @staticmethod
    def normalize_indianapi_record(raw: Dict[str, Any]) -> Optional[JobCreate]:
        """Convert a raw IndianAPI record to a normalized JobCreate model."""
        if not raw:
            return None

        title = raw.get("title") or raw.get("job_title") or "Untitled Position"
        company_name = raw.get("company") or raw.get("company_name") or "Confidential"
        location_raw = raw.get("location") or raw.get("city") or "India"

        # Assemble rich description from IndianAPI fields
        desc_parts = []
        if raw.get("job_description") or raw.get("description"):
            desc_parts.append(str(raw.get("job_description") or raw.get("description")))
        if raw.get("skills") and isinstance(raw["skills"], list):
            desc_parts.append("Skills: " + ", ".join(raw["skills"]))
        elif raw.get("skills") and isinstance(raw["skills"], str):
            desc_parts.append("Skills: " + raw["skills"])
        if raw.get("experience"):
            desc_parts.append("Experience: " + str(raw["experience"]))

        description_raw = "\n\n".join(desc_parts) if desc_parts else title

        job_id = str(raw.get("job_id") or raw.get("id") or "")
        if not job_id:
            job_id = Deduplicator.generate_job_hash(
                title=title,
                company_name=company_name,
                location=location_raw,
                description=description_raw,
            )

        description_cleaned = TextCleaner.clean_html(description_raw)
        city, state = JobNormalizer.extract_city_state(location_raw)
        role_category = JobNormalizer.infer_role_category(title)

        work_model = raw.get("work_model") or raw.get("workplace_type")
        if not work_model:
            wm_low = f"{title} {location_raw} {description_cleaned}".lower()
            if "remote" in wm_low or "work from home" in wm_low:
                work_model = "Remote"
            elif "hybrid" in wm_low:
                work_model = "Hybrid"
            else:
                work_model = None  # not stated: stays missing (no placeholder)

        employment_type = raw.get("job_type") or raw.get("employment_type")
        exp_level = raw.get("experience_level")  # missing stays missing

        salary_min, salary_max = None, None
        if raw.get("salary_min"):
            try:
                salary_min = float(raw["salary_min"])
            except (ValueError, TypeError):
                pass
        if raw.get("salary_max"):
            try:
                salary_max = float(raw["salary_max"])
            except (ValueError, TypeError):
                pass

        posted_at = datetime.now(timezone.utc)
        if raw.get("posted_date"):
            try:
                posted_at = datetime.fromisoformat(str(raw["posted_date"]).replace("Z", "+00:00"))
            except Exception:
                pass

        return JobCreate(
            job_id=str(job_id),
            source="indianapi",
            source_url=raw.get("apply_link") or raw.get("url") or raw.get("link"),
            title=title.strip(),
            normalized_title=title.strip().title(),
            role_category=role_category,
            company_name=company_name.strip(),
            location_raw=location_raw,
            city=city,
            state=state,
            country="India",
            description=description_raw,
            description_cleaned=description_cleaned,
            employment_type=employment_type,
            work_model=work_model,
            experience_level=exp_level,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="INR",
            salary_period="yearly",
            posted_at=posted_at,
            raw_payload=raw,
        )

    @staticmethod
    def normalize_adzuna_record(raw: Dict[str, Any]) -> Optional[JobCreate]:
        """Convert a raw Adzuna record to a normalized JobCreate model."""
        if not raw or not raw.get("title"):
            return None

        title = raw["title"].strip()
        company_name = ((raw.get("company") or {}).get("display_name") or "Confidential").strip()
        location_raw = (raw.get("location") or {}).get("display_name") or "India"
        description_raw = raw.get("description") or title
        description_cleaned = TextCleaner.clean_html(description_raw)
        city, state = JobNormalizer.extract_city_state(location_raw)

        wm_low = f"{title} {location_raw} {description_cleaned}".lower()
        if "remote" in wm_low or "work from home" in wm_low:
            work_model = "Remote"
        elif "hybrid" in wm_low:
            work_model = "Hybrid"
        else:
            work_model = None  # not stated: stays missing (no placeholder)

        contract = (raw.get("contract_time") or "").replace("_", "-")
        employment_type = contract.title() if contract else None

        # Adzuna reports 0 for undisclosed salary; keep those as null
        salary_min = float(raw["salary_min"]) if raw.get("salary_min") else None
        salary_max = float(raw["salary_max"]) if raw.get("salary_max") else None

        posted_at = datetime.now(timezone.utc)
        if raw.get("created"):
            try:
                posted_at = datetime.fromisoformat(str(raw["created"]).replace("Z", "+00:00"))
            except ValueError:
                pass

        return JobCreate(
            job_id=str(raw.get("id") or Deduplicator.generate_job_hash(
                title=title, company_name=company_name, location=location_raw, description=description_raw
            )),
            source="adzuna",
            source_url=raw.get("redirect_url"),
            title=title,
            normalized_title=title.title(),
            role_category=JobNormalizer.infer_role_category(title),
            company_name=company_name,
            location_raw=location_raw,
            city=city,
            state=state,
            country="India",
            description=description_raw,
            description_cleaned=description_cleaned,
            employment_type=employment_type,
            work_model=work_model,
            experience_level=None,  # Adzuna supplies no experience level
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="INR",
            salary_period="yearly",
            posted_at=posted_at,
            raw_payload=raw,
        )

    # ------------------------------------------------------------------ public ATS boards (full descriptions)

    @staticmethod
    def _work_model_from_text(text: str) -> Optional[str]:
        low = text.lower()
        if "remote" in low or "work from home" in low:
            return "Remote"
        if "hybrid" in low:
            return "Hybrid"
        return None

    @staticmethod
    def normalize_greenhouse_record(raw: Dict[str, Any], token: str) -> Optional[JobCreate]:
        """Greenhouse board posting -> JobCreate. Salary / experience level are not supplied (stay missing)."""
        if not raw or not raw.get("title") or not raw.get("id"):
            return None
        title = raw["title"].strip()
        location_raw = ((raw.get("location") or {}).get("name") or "India").strip()
        description_raw = raw.get("content") or title
        city, state = JobNormalizer.extract_city_state(location_raw.split(";")[0])
        posted = None
        for key in ("first_published", "updated_at"):
            if raw.get(key):
                try:
                    posted = datetime.fromisoformat(str(raw[key]).replace("Z", "+00:00"))
                    break
                except ValueError:
                    pass
        return JobCreate(
            job_id=f"gh:{token}:{raw['id']}", source="greenhouse", source_url=raw.get("absolute_url"),
            title=title, normalized_title=title.title(), role_category=JobNormalizer.infer_role_category(title),
            company_name=(raw.get("company_name") or token).strip(), location_raw=location_raw, city=city,
            state=state, country="India", description=description_raw,
            description_cleaned=TextCleaner.clean_html(description_raw),
            employment_type=None, work_model=JobNormalizer._work_model_from_text(f"{title} {location_raw}"),
            experience_level=None, salary_min=None, salary_max=None, salary_currency=None, salary_period=None,
            posted_at=posted,
            raw_payload={k: raw.get(k) for k in ("id", "internal_job_id", "requisition_id", "departments",
                                                 "offices", "updated_at", "first_published")},
        )

    @staticmethod
    def normalize_lever_record(raw: Dict[str, Any], token: str) -> Optional[JobCreate]:
        """Lever posting -> JobCreate. Uses the first India location of the posting when it has several."""
        if not raw or not raw.get("text") or not raw.get("id"):
            return None
        from ingestion.ats_clients import is_india_location
        cats = raw.get("categories") or {}
        locs = [l for l in ([cats.get("location")] + list(cats.get("allLocations") or [])) if l]
        location_raw = next((l for l in locs if is_india_location(l)), locs[0] if locs else "India")
        city, state = JobNormalizer.extract_city_state(location_raw)
        desc = raw.get("description") or ""
        for item in raw.get("lists") or []:
            desc += f"<p>{item.get('text', '')}</p>{item.get('content', '')}"
        desc += raw.get("additional") or ""
        description_raw = desc or raw["text"]
        posted = None
        if raw.get("createdAt"):
            try:
                posted = datetime.fromtimestamp(int(raw["createdAt"]) / 1000, tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                pass
        work_model = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite"}.get((raw.get("workplaceType") or "").lower())
        title = raw["text"].strip()
        return JobCreate(
            job_id=f"lv:{token}:{raw['id']}", source="lever", source_url=raw.get("hostedUrl"),
            title=title, normalized_title=title.title(), role_category=JobNormalizer.infer_role_category(title),
            company_name=token.title(), location_raw=location_raw, city=city, state=state, country="India",
            description=description_raw, description_cleaned=TextCleaner.clean_html(description_raw),
            employment_type=cats.get("commitment") or None, work_model=work_model, experience_level=None,
            salary_min=None, salary_max=None, salary_currency=None, salary_period=None, posted_at=posted,
            raw_payload={"id": raw.get("id"), "categories": cats, "workplaceType": raw.get("workplaceType")},
        )
