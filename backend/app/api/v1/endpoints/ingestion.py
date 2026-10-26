"""
JobIntel - Ingestion Management API Endpoints
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.api.deps import get_db
from backend.app.models.ingestion_run import IngestionRun
from backend.app.schemas.ingestion import IngestionRunResponse

router = APIRouter()


@router.get("/runs", response_model=List[IngestionRunResponse])
def get_ingestion_runs(limit: int = 10, db: Session = Depends(get_db)):
    """
    List past ingestion batches and audit status.
    """
    runs = db.query(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit).all()
    return [IngestionRunResponse.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
def get_ingestion_run(run_id: int, db: Session = Depends(get_db)):
    """
    Get audit status of a specific ingestion batch.
    """
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion run with ID {run_id} not found."
        )
    return IngestionRunResponse.model_validate(run)
