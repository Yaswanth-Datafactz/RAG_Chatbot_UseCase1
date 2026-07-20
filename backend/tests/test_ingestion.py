"""Orchestration tests for services/ingestion.py, run against the real
local Postgres (matching the rest of this test suite's philosophy of
faking external network dependencies but exercising real DB behavior).

These tests do NOT use the `db_session` fixture (rollback-on-teardown):
run_ingestion() opens its own sessions and commits for real as it
progresses, so there is no single outer transaction to roll back. Each
test uses plain sessions and cleans up explicitly in a `finally` block.

The crash-mid-run test is the one docs/plan.md called out as the
highest-risk logic in the system: it proves, rather than assumes, that a
failure partway through a new ingestion run leaves the previously-current
run's chunks fully intact in both Postgres and the search index.
"""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Chunk, Document, IngestionRun
from app.db.session import SessionLocal
from app.search.search_repo import ChunkSearchDocument
from app.services.ingestion import run_ingestion, start_ingestion_run

MINI_CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "mini_corpus"


@pytest.fixture(autouse=True)
def _cleanup_fixture_documents():
    """Document rows are content-addressed (sha256) and meant to persist
    across ingestion runs by design (Phase 0), so per-test IngestionRun
    cleanup deliberately doesn't touch them. But that means the mini
    fixture's "Fixture Policy ..." documents would otherwise accumulate in
    the dev database across test runs -- clean those up specifically,
    without touching real corpus documents a manual demo might rely on."""
    yield
    db = SessionLocal()
    try:
        fixture_docs = db.execute(select(Document).where(Document.title.like("Fixture Policy%"))).scalars().all()
        for doc in fixture_docs:
            db.delete(doc)
        db.commit()
    finally:
        db.close()


class FakeSearchRepo:
    """In-memory stand-in for Azure AI Search, keyed the same way the real
    index is: one shared store, documents tagged with ingestion_run_id,
    queries/deletes filtered by it."""

    ChunkSearchDocument = ChunkSearchDocument

    def __init__(self):
        self.documents: dict[str, ChunkSearchDocument] = {}
        self.index_created = False

    def create_index(self):
        self.index_created = True

    def upload_chunks(self, chunks):
        for c in chunks:
            self.documents[c.id] = c

    def hybrid_search(self, query, vector, run_id, top):
        matches = [d for d in self.documents.values() if d.ingestion_run_id == run_id]
        return matches[:top]

    def delete_old_run(self, run_id):
        for key in [k for k, d in self.documents.items() if d.ingestion_run_id == run_id]:
            del self.documents[key]


class FailAfterNCallsEmbeddingClient:
    """Simulates an embedding API that works fine for the first N calls,
    then fails -- e.g. a transient network/API error partway through a
    long-running ingestion job. One call = one document's chunk batch."""

    deployment_name = "fake-embedding-model"

    def __init__(self, fail_after: int | None = None, dimensions: int = 1536):
        self.calls = 0
        self.fail_after = fail_after
        self.dimensions = dimensions

    def embed_batch(self, texts):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("Simulated embedding API failure mid-run")
        return [[0.01] * self.dimensions for _ in texts]


def _new_run():
    db = SessionLocal()
    try:
        run = start_ingestion_run(db)
        return run.id
    finally:
        db.close()


def _get_run(run_id) -> IngestionRun | None:
    db = SessionLocal()
    try:
        return db.get(IngestionRun, run_id)
    finally:
        db.close()


def _chunk_count(run_id) -> int:
    db = SessionLocal()
    try:
        return len(db.execute(select(Chunk).where(Chunk.ingestion_run_id == run_id)).scalars().all())
    finally:
        db.close()


def _cleanup_run(run_id) -> None:
    db = SessionLocal()
    try:
        run = db.get(IngestionRun, run_id)
        if run is not None:
            db.delete(run)  # cascades to this run's chunks
            db.commit()
    finally:
        db.close()


def test_first_ever_run_becomes_current_with_no_previous_to_swap():
    fake_repo = FakeSearchRepo()
    run_id = _new_run()

    try:
        run_ingestion(
            run_id,
            corpus_dir=MINI_CORPUS_DIR,
            search_repo_module=fake_repo,
            embedding_client=FailAfterNCallsEmbeddingClient(),
        )

        run = _get_run(run_id)
        assert run.status == "succeeded"
        assert run.is_current is True
        assert run.doc_count == 3
        assert run.chunk_count > 0
        assert _chunk_count(run_id) == run.chunk_count

        assert fake_repo.index_created is True
        assert len(fake_repo.hybrid_search("anything", [0.0], run_id=str(run_id), top=100)) == run.chunk_count
    finally:
        _cleanup_run(run_id)


def test_successful_reindex_swaps_current_and_cleans_up_previous_run():
    fake_repo = FakeSearchRepo()

    old_run_id = _new_run()
    run_ingestion(
        old_run_id,
        corpus_dir=MINI_CORPUS_DIR,
        search_repo_module=fake_repo,
        embedding_client=FailAfterNCallsEmbeddingClient(),
    )

    new_run_id = _new_run()

    try:
        run_ingestion(
            new_run_id,
            corpus_dir=MINI_CORPUS_DIR,
            search_repo_module=fake_repo,
            embedding_client=FailAfterNCallsEmbeddingClient(),
        )

        new_run = _get_run(new_run_id)
        assert new_run.status == "succeeded"
        assert new_run.is_current is True

        # Old run was fully cleaned up: row deleted (cascades chunks).
        assert _get_run(old_run_id) is None
        assert _chunk_count(old_run_id) == 0

        # Old run's documents purged from the shared search store; new
        # run's documents present.
        assert fake_repo.hybrid_search("x", [0.0], run_id=str(old_run_id), top=100) == []
        assert len(fake_repo.hybrid_search("x", [0.0], run_id=str(new_run_id), top=100)) > 0
    finally:
        _cleanup_run(old_run_id)
        _cleanup_run(new_run_id)


def test_reindex_with_changed_content_deletes_orphaned_document_row(tmp_path):
    """Real-world scenario this regression covers: a corpus file's bytes
    change between two ingestion runs (content edited, not just
    re-ingested unchanged). _upsert_document() can't match the old
    sha256, so it inserts a fresh Document row for doc1's new content;
    the old row's chunks get cascade-deleted with the previous run at
    swap time, leaving the old row referencing zero chunks anywhere.
    _cleanup_previous_run() must delete that orphan rather than leaving
    it to accumulate -- otherwise the admin documents list shows the same
    title multiple times with stale 0-chunk rows, which is genuinely
    confusing rather than a display quirk."""
    fake_repo = FakeSearchRepo()

    old_run_id = _new_run()
    run_ingestion(
        old_run_id,
        corpus_dir=MINI_CORPUS_DIR,
        search_repo_module=fake_repo,
        embedding_client=FailAfterNCallsEmbeddingClient(),
    )

    # Copy the fixture corpus to a temp dir and change doc1.md's content
    # (and only doc1.md's) so its sha256 no longer matches the old run's
    # Document row; doc2.md/doc3.md are byte-identical and should reuse
    # their existing rows exactly like the unchanged-content case already
    # covered by test_successful_reindex_swaps_current_and_cleans_up_previous_run.
    changed_corpus_dir = tmp_path / "changed_corpus"
    shutil.copytree(MINI_CORPUS_DIR, changed_corpus_dir)
    (changed_corpus_dir / "doc1.md").write_text(
        (changed_corpus_dir / "doc1.md").read_text() + "\n\nNewly added paragraph.\n"
    )

    new_run_id = _new_run()

    try:
        run_ingestion(
            new_run_id,
            corpus_dir=changed_corpus_dir,
            search_repo_module=fake_repo,
            embedding_client=FailAfterNCallsEmbeddingClient(),
        )

        new_run = _get_run(new_run_id)
        assert new_run.status == "succeeded"
        assert new_run.is_current is True

        db = SessionLocal()
        try:
            for title in ("Fixture Policy One", "Fixture Policy Two", "Fixture Policy Three"):
                rows = db.execute(select(Document).where(Document.title == title)).scalars().all()
                assert len(rows) == 1, f"expected exactly one Document row for {title!r}, found {len(rows)}"
        finally:
            db.close()
    finally:
        _cleanup_run(old_run_id)
        _cleanup_run(new_run_id)


def test_crash_mid_run_leaves_previous_current_run_fully_intact():
    """The highest-risk-logic test: a new run that fails partway through
    must not affect the previously-current run in any way -- not in
    Postgres, not in the search index, and it must never become current
    itself."""
    fake_repo = FakeSearchRepo()

    old_run_id = _new_run()
    run_ingestion(
        old_run_id,
        corpus_dir=MINI_CORPUS_DIR,
        search_repo_module=fake_repo,
        embedding_client=FailAfterNCallsEmbeddingClient(),
    )

    old_run_before = _get_run(old_run_id)
    assert old_run_before.status == "succeeded"
    assert old_run_before.is_current is True
    old_chunk_count_before = _chunk_count(old_run_id)
    assert old_chunk_count_before > 0
    old_search_docs_before = fake_repo.hybrid_search("x", [0.0], run_id=str(old_run_id), top=100)

    new_run_id = _new_run()

    try:
        # mini_corpus has 3 documents; failing after the 1st embed_batch
        # call means document #2's processing raises mid-run.
        run_ingestion(
            new_run_id,
            corpus_dir=MINI_CORPUS_DIR,
            search_repo_module=fake_repo,
            embedding_client=FailAfterNCallsEmbeddingClient(fail_after=1),
        )

        # --- The new run correctly recorded its own failure ---
        new_run_after = _get_run(new_run_id)
        assert new_run_after.status == "failed"
        assert new_run_after.error is not None
        assert "Simulated embedding API failure" in new_run_after.error
        assert new_run_after.is_current is False

        # --- Proof of partial progress: doc #1's chunks WERE written
        # under the new run_id before the crash, but that's harmless
        # because is_current never pointed at them ---
        new_run_chunk_count = _chunk_count(new_run_id)
        assert 0 < new_run_chunk_count < old_chunk_count_before * 2  # only ~1 of 3 docs got through

        # --- The old run is untouched: still current, same row, same chunks ---
        old_run_after = _get_run(old_run_id)
        assert old_run_after.is_current is True
        assert old_run_after.status == "succeeded"
        assert _chunk_count(old_run_id) == old_chunk_count_before

        # --- The old run is still fully "serving": hybrid_search against
        # it returns exactly what it did before the crashed run started ---
        old_search_docs_after = fake_repo.hybrid_search("x", [0.0], run_id=str(old_run_id), top=100)
        assert {d.id for d in old_search_docs_after} == {d.id for d in old_search_docs_before}
    finally:
        _cleanup_run(old_run_id)
        _cleanup_run(new_run_id)
