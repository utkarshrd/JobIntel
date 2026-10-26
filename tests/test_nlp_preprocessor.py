"""
JobIntel - NLP & Text Processing Unit Tests
"""

from nlp.preprocessor import TextPreprocessor
from nlp.skill_extractor import SkillExtractor
from nlp.entity_extractor import EntityExtractor
from nlp.classifier import JobRoleClassifier


def test_text_cleaning_and_tokenization():
    raw_html = "<p>We are hiring a <b>Senior Data Analyst</b> with 3+ years experience in Python &amp; SQL.</p>"
    cleaned = TextPreprocessor.preprocess(raw_html)
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned
    assert "&amp;" not in cleaned
    assert "senior data analyst" in cleaned

    tokens = TextPreprocessor.tokenize(cleaned, remove_stopwords=True)
    assert "senior" in tokens
    assert "analyst" in tokens
    assert "python" in tokens
    assert "sql" in tokens


def test_skill_extraction():
    extractor = SkillExtractor()
    sample_text = (
        "Candidate must have deep expertise in Python, SQL, Power BI, and Docker. "
        "Experience in Machine Learning and AWS is preferred."
    )
    extracted = extractor.extract_skills(sample_text)
    names = {s.name for s in extracted}
    assert "python" in names
    assert "sql" in names
    assert "power bi" in names
    assert "docker" in names
    assert "machine learning" in names
    assert "aws" in names


def test_entity_extraction_experience_and_degree():
    text = "Requires B.Tech / B.E. in Computer Science with 3-5 years of industry experience."
    min_exp, max_exp = EntityExtractor.extract_experience_years(text)
    assert min_exp == 3.0
    assert max_exp == 5.0

    quals = EntityExtractor.extract_qualifications(text)
    assert any("B.Tech" in q for q in quals)


def test_job_role_classification():
    cat, conf = JobRoleClassifier.classify(
        title="Senior Financial Risk Analyst",
        description="Responsible for financial modeling, DCF valuation, and portfolio risk management."
    )
    assert cat == "Finance & Banking"
    assert conf > 0.60


def test_qualification_no_false_positive_on_word_be():
    assert EntityExtractor.extract_qualifications("You will be able to be part of the team") == []
    assert "B.Tech / B.E." in EntityExtractor.extract_qualifications("B.E. in Computer Science")


def test_plus_experience_has_no_invented_upper_bound():
    assert EntityExtractor.extract_experience_years("Needs 3+ years of Python") == (3.0, None)


def test_skill_taxonomy_audit_additions():
    from nlp.skill_extractor import SkillExtractor
    names = {s.name for s in SkillExtractor().extract_skills(
        "Build data pipelines and dashboards with statistical analysis, A/B testing and data warehouse design")}
    assert {"etl", "data visualization", "statistics", "a/b testing", "data warehousing"} <= names
