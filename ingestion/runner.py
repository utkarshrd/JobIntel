"""
JobIntel - Ingestion Execution Runner
Coordinates data fetching from Jobvetta API, deduplication, normalization, and persistence.
"""

from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.core.logging import logger
from backend.app.models.ingestion_run import IngestionRun, IngestionStatus
from backend.app.services.job_service import JobService
from ingestion.jobvetta_client import JobvettaClient
from ingestion.normalizer import JobNormalizer


class IngestionRunner:
    @staticmethod
    def run_jobvetta_ingestion(
        query_roles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        max_requests_per_query: int = 2
    ) -> IngestionRun:
        """
        Execute an ingestion run across target roles and Indian locations.
        """
        db: Session = SessionLocal()
        roles = query_roles or ["Data Analyst", "Data Scientist", "Financial Analyst", "Software Engineer"]
        target_locations = locations or ["Mumbai", "Bengaluru", "Pune", "Hyderabad", "Delhi NCR"]

        # 1. Initialize IngestionRun record
        run_record = IngestionRun(
            source="jobvetta",
            status=IngestionStatus.RUNNING.value,
            query_parameters={
                "roles": roles,
                "locations": target_locations,
                "max_requests_per_query": max_requests_per_query,
            },
            started_at=datetime.now(timezone.utc),
        )
        db.add(run_record)
        db.commit()
        db.refresh(run_record)

        client = JobvettaClient()
        total_fetched = 0
        new_inserted = 0
        duplicates_skipped = 0
        errors = 0

        logger.info(f"Starting Jobvetta Ingestion Run #{run_record.id}")

        try:
            for role in roles:
                for loc in target_locations:
                    for page in range(1, max_requests_per_query + 1):
                        logger.info(f"Fetching: role='{role}', location='{loc}', page={page}")
                        raw_jobs = client.fetch_jobs(query=role, location=loc, limit=10, page=page)
                        if not raw_jobs:
                            break

                        total_fetched += len(raw_jobs)
                        for raw in raw_jobs:
                            try:
                                normalized = JobNormalizer.normalize_jobvetta_record(raw)
                                if normalized:
                                    _, created = JobService.create_or_update_job(db, normalized)
                                    if created:
                                        new_inserted += 1
                                    else:
                                        duplicates_skipped += 1
                            except Exception as e:
                                errors += 1
                                logger.error(f"Error normalizing/persisting job: {e}")

            run_record.status = IngestionStatus.COMPLETED.value
            run_record.total_fetched = total_fetched
            run_record.new_inserted = new_inserted
            run_record.duplicates_skipped = duplicates_skipped
            run_record.errors_count = errors
            run_record.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Ingestion run failed: {e}")
            run_record.status = IngestionStatus.FAILED.value
            run_record.error_log = str(e)
            run_record.completed_at = datetime.now(timezone.utc)
        finally:
            db.commit()
            db.close()

        logger.info(
            f"Ingestion Run #{run_record.id} finished: "
            f"Fetched={total_fetched}, Inserted={new_inserted}, Dups={duplicates_skipped}, Errors={errors}"
        )
        return run_record


if __name__ == "__main__":
    runner = IngestionRunner()
    runner.run_jobvetta_ingestion()
