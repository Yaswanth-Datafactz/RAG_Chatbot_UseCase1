"""Route-level tests for /api/v1/ingestion-runs. run_ingestion is patched
to a no-op: Phase 2 already proved the ingestion pipeline itself works
(test_ingestion.py); this phase only adds the HTTP surface, and no live
Azure credentials are provisioned to run it for real (see docs/plan.md
Risks). BackgroundTasks may execute synchronously within TestClient's
request/response cycle, so the patch guards against that triggering a
real (credential-less) ingestion run as a side effect of an HTTP test.
"""

import uuid
from unittest.mock import patch

from app.core.config import get_settings
from app.db.models import IngestionRun
from app.db.session import SessionLocal

API_KEY_HEADER = {"X-API-Key": get_settings().api_key}


def _cleanup(run_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        run = db.get(IngestionRun, run_id)
        if run is not None:
            db.delete(run)
            db.commit()
    finally:
        db.close()


def test_trigger_ingestion_run_requires_api_key(client):
    response = client.post("/api/v1/ingestion-runs")

    assert response.status_code == 401


def test_trigger_ingestion_run_returns_202_with_pending_run(client):
    with patch("app.api.v1.ingestion.run_ingestion") as fake_run_ingestion:
        response = client.post("/api/v1/ingestion-runs", headers=API_KEY_HEADER)

    assert response.status_code == 202
    body = response.json()
    run_id = uuid.UUID(body["id"])
    try:
        assert body["status"] == "pending"
        assert body["is_current"] is False
        fake_run_ingestion.assert_called_once_with(run_id)

        get_response = client.get(f"/api/v1/ingestion-runs/{run_id}", headers=API_KEY_HEADER)
        assert get_response.status_code == 200
        assert get_response.json()["id"] == str(run_id)
    finally:
        _cleanup(run_id)


def test_get_ingestion_run_requires_api_key(client):
    response = client.get(f"/api/v1/ingestion-runs/{uuid.uuid4()}")

    assert response.status_code == 401


def test_get_ingestion_run_404_for_unknown_id(client):
    response = client.get(f"/api/v1/ingestion-runs/{uuid.uuid4()}", headers=API_KEY_HEADER)

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found"
