"""
JobIntel - Market Analytics Service
Computes real-time TWSMA market metrics: skill demand, co-occurrence, locations, and salaries.
"""

from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, distinct
from backend.app.models.job import Job
from backend.app.services.job_service import active_filter
from backend.app.models.skill import Skill, JobSkill
from backend.app.schemas.analytics import (
    SkillDemandItem,
    SkillCooccurrenceItem,
    LocationDemandItem,
    RoleDistributionItem,
    SalaryAnalyticsItem,
    MarketSummaryResponse,
)


class AnalyticsService:
    @staticmethod
    def get_market_summary(db: Session) -> MarketSummaryResponse:
        """
        Compute high-level market summary statistics across the collected job dataset.
        """
        total_jobs = db.query(func.count(Job.id)).filter(active_filter()).scalar() or 0
        total_companies = db.query(func.count(distinct(Job.company_name))).filter(active_filter()).scalar() or 0
        total_cities = db.query(func.count(distinct(Job.city))).filter(Job.city.isnot(None), active_filter()).scalar() or 0
        total_skills_tracked = db.query(func.count(Skill.id)).scalar() or 0

        # 1. Top Skills Demand
        top_skills = AnalyticsService.get_top_skills(db, limit=15)

        # 2. Role Categories Distribution
        role_dist = AnalyticsService.get_role_distribution(db)

        # 3. Location Demand
        location_demand = AnalyticsService.get_location_demand(db, limit=10)

        # 4. Skill Co-occurrence
        skill_cooccurrences = AnalyticsService.get_skill_cooccurrences(db, limit=10)

        # 5. Salary Analytics (by role category, strictly preserving missing values)
        salary_analytics = AnalyticsService.get_salary_analytics(db)

        return MarketSummaryResponse(
            total_jobs=total_jobs,
            total_companies=total_companies,
            total_cities=total_cities,
            total_skills_tracked=total_skills_tracked,
            top_skills=top_skills,
            role_distribution=role_dist,
            location_demand=location_demand,
            skill_cooccurrences=skill_cooccurrences,
            salary_analytics=salary_analytics,
        )

    @staticmethod
    def get_top_skills(db: Session, limit: int = 20) -> List[SkillDemandItem]:
        """Compute the frequency of extracted skills across all jobs."""
        total_jobs = db.query(func.count(Job.id)).filter(active_filter()).scalar() or 1
        results = (
            db.query(
                Skill.name,
                Skill.display_name,
                Skill.category,
                func.count(JobSkill.job_id).label("job_count"),
            )
            .join(JobSkill, Skill.id == JobSkill.skill_id)
            .join(Job, Job.id == JobSkill.job_id)
            .filter(active_filter())
            .group_by(Skill.id, Skill.name, Skill.display_name, Skill.category)
            .order_by(desc("job_count"))
            .limit(limit)
            .all()
        )

        items = []
        for r in results:
            pct = round((r.job_count / total_jobs) * 100, 2)
            items.append(
                SkillDemandItem(
                    skill_name=r.name,
                    display_name=r.display_name,
                    category=r.category or "General",
                    job_count=r.job_count,
                    demand_percentage=pct,
                )
            )
        return items

    @staticmethod
    def get_role_distribution(db: Session) -> List[RoleDistributionItem]:
        """Compute distribution of job roles and average salaries where available."""
        total_jobs = db.query(func.count(Job.id)).filter(active_filter()).scalar() or 1
        results = (
            db.query(
                Job.role_category,
                func.count(Job.id).label("job_count"),
                func.avg(Job.salary_min).label("avg_min_salary"),
                func.avg(Job.salary_max).label("avg_max_salary"),
            )
            .filter(Job.role_category.isnot(None), active_filter())
            .group_by(Job.role_category)
            .order_by(desc("job_count"))
            .all()
        )

        items = []
        for r in results:
            pct = round((r.job_count / total_jobs) * 100, 2)
            items.append(
                RoleDistributionItem(
                    role_category=r.role_category,
                    job_count=r.job_count,
                    percentage=pct,
                    avg_min_salary=round(r.avg_min_salary, 2) if r.avg_min_salary else None,
                    avg_max_salary=round(r.avg_max_salary, 2) if r.avg_max_salary else None,
                )
            )
        return items

    @staticmethod
    def get_location_demand(db: Session, limit: int = 10) -> List[LocationDemandItem]:
        """Analyze job postings volume across Indian cities."""
        results = (
            db.query(
                Job.city,
                func.count(Job.id).label("job_count"),
            )
            .filter(Job.city.isnot(None), active_filter())
            .group_by(Job.city)
            .order_by(desc("job_count"))
            .limit(limit)
            .all()
        )

        items = []
        for r in results:
            items.append(
                LocationDemandItem(
                    city=r.city,
                    job_count=r.job_count,
                )
            )
        return items

    @staticmethod
    def get_skill_cooccurrences(db: Session, limit: int = 15) -> List[SkillCooccurrenceItem]:
        """
        Find top pairs of skills frequently appearing together in the same job postings.
        """
        from backend.app.services import twsma_service

        pairs = twsma_service.skill_cooccurrence(
            twsma_service.load_records_from_db(db), min_count=1, limit=limit
        )
        return [
            SkillCooccurrenceItem(
                skill_a=p["skill_a"],
                skill_b=p["skill_b"],
                cooccurrence_count=p["job_count"],
                cooccurrence_strength=p["lift"],
            )
            for p in pairs
        ]

    @staticmethod
    def get_salary_analytics(db: Session) -> List[SalaryAnalyticsItem]:
        """
        Calculate salary benchmarks only for postings with explicitly provided salary data.
        Missing salary fields are never imputed.
        """
        results = (
            db.query(
                Job.role_category,
                func.count(Job.id).label("sample_size"),
                func.min(Job.salary_min).label("min_sal"),
                func.avg(Job.salary_min).label("avg_min_sal"),
                func.max(Job.salary_max).label("max_sal"),
            )
            .filter(Job.salary_min.isnot(None), Job.role_category.isnot(None), active_filter())
            .group_by(Job.role_category)
            .all()
        )

        items = []
        for r in results:
            items.append(
                SalaryAnalyticsItem(
                    role_category=r.role_category,
                    sample_size=r.sample_size,
                    min_salary=r.min_sal,
                    median_salary=r.avg_min_sal,
                    max_salary=r.max_sal,
                    currency="INR",
                )
            )
        return items
