"""Manually trigger an ingestion run.

Phase 4 will add `POST /api/v1/ingestion-runs` (scheduled via
BackgroundTasks); until that route exists, this script is the supported
way to run ingestion. It calls the exact same start_ingestion_run() /
run_ingestion() functions that route will call.

Requires real Azure AI Search + Azure OpenAI credentials in backend/.env
-- none are provisioned yet (docs/plan.md Risks), so running this for
real will fail at the create_index()/embeddings.create() calls until
those are in place. Phase 2's correctness is proven by the test suite
(fakes standing in for both services), not by a live run of this script.

Usage:
    cd backend
    ./.venv/bin/python scripts/run_ingestion_manually.py
"""

from app.db.session import SessionLocal
from app.db.models import IngestionRun
from app.services.ingestion import run_ingestion, start_ingestion_run


def main() -> None:
    db = SessionLocal()
    try:
        run = start_ingestion_run(db)
        run_id = run.id
    finally:
        db.close()

    print(f"Started ingestion run {run_id}, processing corpus/ ...")
    run_ingestion(run_id)

    db = SessionLocal()
    try:
        run = db.get(IngestionRun, run_id)
        print(
            f"Run {run_id} finished: status={run.status}, "
            f"doc_count={run.doc_count}, chunk_count={run.chunk_count}, "
            f"is_current={run.is_current}, error={run.error}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
