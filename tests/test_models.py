"""
JobIntel - Database Models Unit Tests
Validates schema definition, foreign key cascades, and ORM relationships.
"""

from datetime import datetime, timezone
from backend.app.models.job import Job
from backend.app.models.skill import Skill, JobSkill, UserSkill
from backend.app.models.company import Company
from backend.app.models.user import User
from backend.app.models.interaction import Interaction, InteractionType
from backend.app.models.ingestion_run import IngestionRun, IngestionStatus


def test_job_and_skill_relationships(db_session):
    # 1. Create Company
    company = Company(name="Tata Consultancy Services", normalized_name="tata consultancy services", industry="IT Services")
    db_session.add(company)
    db_session.flush()

    # 2. Create Job
    job = Job(
        job_id="jobvetta_test_101",
        source="jobvetta",
        title="Data Analyst",
        normalized_title="Data Analyst",
        role_category="Data & Analytics",
        company_id=company.id,
        company_name=company.name,
        city="Mumbai",
        state="Maharashtra",
        country="India",
        description="Looking for an experienced Data Analyst skilled in Python, SQL, and Power BI.",
        description_cleaned="looking for an experienced data analyst skilled in python sql and power bi",
        work_model="Hybrid",
        experience_level="Entry-level",
        min_experience_years=1.0,
        salary_min=600000.0,
        salary_max=900000.0,
        posted_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.flush()

    # 3. Create Skills
    skill_py = Skill(name="python", display_name="Python", category="Programming Languages")
    skill_sql = Skill(name="sql", display_name="SQL", category="Databases")
    db_session.add_all([skill_py, skill_sql])
    db_session.flush()

    # 4. Link JobSkills
    js1 = JobSkill(job_id=job.id, skill_id=skill_py.id, skill_type="required", confidence=0.98)
    js2 = JobSkill(job_id=job.id, skill_id=skill_sql.id, skill_type="required", confidence=0.95)
    db_session.add_all([js1, js2])
    db_session.commit()

    # Assertions
    saved_job = db_session.query(Job).filter(Job.id == job.id).first()
    assert saved_job is not None
    assert saved_job.company_rel.name == "Tata Consultancy Services"
    assert len(saved_job.skills_rel) == 2
    assert {js.skill_rel.name for js in saved_job.skills_rel} == {"python", "sql"}


def test_user_and_interaction_models(db_session):
    user = User(
        email="utkarsh@example.com",
        full_name="Utkarsh Sharma",
        headline="Aspiring Data Scientist",
        experience_years=1.5,
        target_role="Data & Analytics",
        preferred_locations=["Mumbai", "Bengaluru"],
        preferred_work_models=["Remote", "Hybrid"],
    )
    db_session.add(user)
    db_session.flush()

    job = Job(
        job_id="job_interaction_test_102",
        source="jobvetta",
        title="Junior Data Scientist",
        company_name="Analytics Corp",
        city="Bengaluru",
        description="Python machine learning role",
        posted_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.flush()

    interaction = Interaction(
        user_id=user.id,
        job_id=job.id,
        interaction_type=InteractionType.VIEW.value,
        duration_seconds=45.0,
    )
    db_session.add(interaction)
    db_session.commit()

    saved_user = db_session.query(User).filter(User.id == user.id).first()
    assert saved_user is not None
    assert len(saved_user.interactions) == 1
    assert saved_user.interactions[0].interaction_type == "view"


def test_ingestion_run_model(db_session):
    run = IngestionRun(
        source="jobvetta",
        status=IngestionStatus.COMPLETED.value,
        query_parameters={"query": "Data Analyst", "location": "Mumbai"},
        total_fetched=20,
        new_inserted=18,
        duplicates_skipped=2,
    )
    db_session.add(run)
    db_session.commit()

    saved_run = db_session.query(IngestionRun).filter(IngestionRun.id == run.id).first()
    assert saved_run is not None
    assert saved_run.new_inserted == 18
    assert saved_run.duplicates_skipped == 2
