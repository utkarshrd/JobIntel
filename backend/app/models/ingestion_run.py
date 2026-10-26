"""
JobIntel - Ingestion Run Audit Model
Tracks data acquisition batches, API consumption, deduplication counts, and data quality metrics.
"""

from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from backend.app.core.database import Base


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), default="jobvetta", nullable=False, index=True)
    status = Column(String(20), default=IngestionStatus.PENDING.value, nullable=False, index=True)
    
    # Query parameters executed (e.g. queries, locations, limit)
    query_parameters = Column(JSON, default=dict, nullable=False)
    
    # Ingestion metrics
    total_fetched = Column(Integer, default=0, nullable=False)
    new_inserted = Column(Integer, default=0, nullable=False)
    duplicates_skipped = Column(Integer, default=0, nullable=False)
    errors_count = Column(Integer, default=0, nullable=False)
    
    # Timing
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Logs & Error detail
    error_log = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<IngestionRun(id={self.id}, source='{self.source}', status='{self.status}', inserted={self.new_inserted})>"
