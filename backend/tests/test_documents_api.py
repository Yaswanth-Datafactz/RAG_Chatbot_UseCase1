"""Route-level tests for /api/v1/documents. Uses an explicit fixture
(Document + a current IngestionRun + Chunks) rather than relying on
ambient corpus state, so these tests are isolated from whatever the real
20-document corpus's ingestion state happens to be at run time.
"""

import uuid

from app.core.config import get_settings
from app.db.models import Chunk, Document, IngestionRun
from app.db.session import SessionLocal

API_KEY_HEADER = {"X-API-Key": get_settings().api_key}


def _make_fixture():
    db = SessionLocal()
    try:
        run = IngestionRun(status="succeeded", embedding_model="fake", is_current=True, doc_count=1, chunk_count=2)
        document = Document(
            source_filename="fixture.md",
            title="Fixture Policy Documents",
            doc_type="markdown",
            sha256=f"sha-{uuid.uuid4()}",
            byte_size=20,
        )
        db.add_all([run, document])
        db.flush()
        chunks = [
            Chunk(
                document_id=document.id,
                ingestion_run_id=run.id,
                chunk_index=i,
                section_path=f"Fixture Policy Documents > Section {i}",
                content=f"Fixture chunk content {i}.",
                token_count=5,
                azure_doc_key=f"{run.id}_{document.id}_{i}",
            )
            for i in range(2)
        ]
        db.add_all(chunks)
        db.commit()
        return {"run_id": run.id, "document_id": document.id}
    finally:
        db.close()


def _cleanup(ids: dict) -> None:
    db = SessionLocal()
    try:
        run = db.get(IngestionRun, ids["run_id"])
        if run is not None:
            db.delete(run)  # cascades chunks
        document = db.get(Document, ids["document_id"])
        if document is not None:
            db.delete(document)
        db.commit()
    finally:
        db.close()


def test_list_documents_requires_api_key(client):
    response = client.get("/api/v1/documents")

    assert response.status_code == 401


def test_list_documents_includes_current_chunk_count(client):
    ids = _make_fixture()
    try:
        response = client.get("/api/v1/documents", headers=API_KEY_HEADER)
        assert response.status_code == 200

        entry = next(d for d in response.json() if d["id"] == str(ids["document_id"]))
        assert entry["title"] == "Fixture Policy Documents"
        assert entry["current_chunk_count"] == 2
    finally:
        _cleanup(ids)


def test_get_document_chunk_returns_the_chunk(client):
    ids = _make_fixture()
    try:
        response = client.get(f"/api/v1/documents/{ids['document_id']}/chunks/0", headers=API_KEY_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["chunk_index"] == 0
        assert body["content"] == "Fixture chunk content 0."
        assert body["section_path"] == "Fixture Policy Documents > Section 0"
        assert body["document_title"] == "Fixture Policy Documents"
    finally:
        _cleanup(ids)


def test_get_document_chunk_404_for_unknown_chunk_index(client):
    ids = _make_fixture()
    try:
        response = client.get(f"/api/v1/documents/{ids['document_id']}/chunks/99", headers=API_KEY_HEADER)

        assert response.status_code == 404
        assert response.json()["error"]["type"] == "not_found"
    finally:
        _cleanup(ids)


def test_get_document_chunk_404_for_unknown_document(client):
    response = client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks/0", headers=API_KEY_HEADER)

    assert response.status_code == 404
