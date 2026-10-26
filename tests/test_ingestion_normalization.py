"""
JobIntel - Ingestion & Normalization Unit Tests
"""

from ingestion.cleaner import TextCleaner
from ingestion.deduplicator import Deduplicator
from ingestion.normalizer import JobNormalizer


def test_html_cleaner():
    html_sample = "<div><ul><li>Python developer</li><li>Work with SQL databases</li></ul></div>"
    cleaned = TextCleaner.clean_html(html_sample)
    assert "<div>" not in cleaned
    assert "Python developer" in cleaned
    assert "Work with SQL databases" in cleaned


def test_deduplicator_hash():
    h1 = Deduplicator.generate_job_hash(
        title="Data Scientist",
        company_name="Innovate Ltd",
        location="Bengaluru",
        description="Looking for ML engineers"
    )
    h2 = Deduplicator.generate_job_hash(
        title="Data Scientist",
        company_name="Innovate Ltd",
        location="Bengaluru",
        description="Looking for ML engineers"
    )
    assert h1 == h2
    assert len(h1) == 32


def test_jobvetta_record_normalization():
    raw_api_response = {
        "id": "jv_sample_987",
        "title": "Data Analyst (Power BI)",
        "company": "Infosys",
        "location": "Pune, Maharashtra, India",
        "description": "<p>Responsible for building <b>Power BI</b> dashboards and SQL reporting. Remote eligible.</p>",
        "salary_min": 750000,
        "salary_max": 1100000,
        "salary_currency": "INR",
        "workplace_type": "Remote",
    }

    normalized = JobNormalizer.normalize_jobvetta_record(raw_api_response)
    assert normalized is not None
    assert normalized.job_id == "jv_sample_987"
    assert normalized.company_name == "Infosys"
    assert normalized.city == "Pune"
    assert normalized.state == "Maharashtra"
    assert normalized.role_category == "Data & Analytics"
    assert normalized.work_model == "Remote"
    assert normalized.salary_min == 750000.0
    assert normalized.salary_max == 1100000.0


def test_data_science_manager_not_software_engineering():
    """Regression: manager-level data science titles fell through to Software Engineering."""
    for title in ["Data Science Manager", "Data Science Manager - Market Mix Modeling"]:
        assert JobNormalizer.infer_role_category(title) == "AI & Machine Learning"
    # 'ml' must match as a whole word only
    assert JobNormalizer.infer_role_category("HTML Developer") == "Software Engineering"


import pytest

from nlp.classifier import JobRoleClassifier


@pytest.mark.parametrize("title,expected", [
    ("Data Science Manager", "AI & Machine Learning"),
    ("Data Scientist", "AI & Machine Learning"),
    ("ML Engineer", "AI & Machine Learning"),
    ("HTML Developer", "Software Engineering"),
    ("Senior Data Analyst", "Data & Analytics"),
    ("Business Intelligence Developer", "Data & Analytics"),
    ("Financial Risk Analyst", "Finance & Banking"),
    ("Cloud Engineer", "Cloud & DevOps"),
    ("DevOps Engineer", "Cloud & DevOps"),
    ("Associate Product Manager", "Product Management"),
    ("UI/UX Designer", "Design & UX"),
    ("Cyber Security Analyst", "Cybersecurity"),
    ("Digital Marketing Executive", "Sales & Marketing"),
    ("HR Recruiter", "Operations & HR"),
    ("Sr Azure Data engineer", "Data & Analytics"),
    ("Principal GenAI Engineer", "AI & Machine Learning"),
    ("Associate Accountant", "Finance & Banking"),
    ("Java Backend Developer", "Software Engineering"),
])
def test_role_classification_single_source_of_truth(title, expected):
    assert JobRoleClassifier.classify(title)[0] == expected
    # ingestion must agree with the shared classifier
    assert JobNormalizer.infer_role_category(title) == expected


def test_unmatched_title_is_low_confidence_fallback():
    cat, conf = JobRoleClassifier.classify("Zebra Wrangler")
    assert (cat, conf) == ("Software Engineering", 0.5)
