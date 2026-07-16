"""POST /ingestion-runs (trigger a re-index in the background) and
GET /ingestion-runs/{id} (poll status). Both call the exact same
start_ingestion_run()/run_ingestion() functions Phase 2 already built and
tested; this phase only adds the HTTP surface Phase 2 deferred."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import require_api_key
from app.db.models import IngestionRun
from app.db.session import get_db
from app.schemas.ingestion import IngestionRunOut
from app.services.ingestion import run_ingestion, start_ingestion_run

router = APIRouter(
    prefix="/ingestion-runs",
    tags=["ingestion"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)


@router.post("", response_model=IngestionRunOut, status_code=status.HTTP_202_ACCEPTED)
def trigger_ingestion_run(
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> IngestionRun:
    run = start_ingestion_run(db)
    background_tasks.add_task(run_ingestion, run.id)
    return run


@router.get("/{run_id}", response_model=IngestionRunOut, responses={404: {"description": "Ingestion run not found"}})
def get_ingestion_run(run_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> IngestionRun:
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise NotFoundError(f"Ingestion run {run_id} not found")
    return run
