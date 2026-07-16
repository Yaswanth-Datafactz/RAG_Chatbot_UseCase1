"""Integration smoke test: runs the real ingestion pipeline over the real
20-document Phase 1 corpus (not the mini fixture), with a fake search repo
and a deterministic fake embedding client standing in for Azure/OpenAI
(no credentials are provisioned yet -- see docs/plan.md Risks). Proves
Phase 2's code actually processes Phase 1's corpus end to end, not just
synthetic fixtures.
"""

from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import IngestionRun
from app.services.ingestion import run_ingestion, start_ingestion_run
from tests.test_ingestion import FailAfterNCallsEmbeddingClient, FakeSearchRepo

REAL_CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"


def test_real_corpus_ingests_successfully_with_sane_section_paths():
    fake_repo = FakeSearchRepo()
    db = SessionLocal()
    try:
        run = start_ingestion_run(db)
        run_id = run.id
    finally:
        db.close()

    try:
        run_ingestion(
            run_id,
            corpus_dir=REAL_CORPUS_DIR,
            search_repo_module=fake_repo,
            embedding_client=FailAfterNCallsEmbeddingClient(),
        )

        db = SessionLocal()
        try:
            refreshed = db.get(IngestionRun, run_id)
            assert refreshed.status == "succeeded", refreshed.error
            assert refreshed.is_current is True
            assert refreshed.doc_count == 20
            assert refreshed.chunk_count > 0
        finally:
            db.close()

        docs = list(fake_repo.documents.values())
        assert len(docs) == refreshed.chunk_count
        # Every chunk's section_path should start with its document's title
        # (docs/phase-1.md's "Title > Section > Subsection" convention).
        for doc in docs:
            assert doc.section_path.startswith(doc.document_title)
            assert doc.content.strip() != ""
    finally:
        db = SessionLocal()
        try:
            run = db.get(IngestionRun, run_id)
            if run is not None:
                db.delete(run)
                db.commit()
        finally:
            db.close()
