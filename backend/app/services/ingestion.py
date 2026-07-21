"""Ingestion orchestration: load -> parse -> chunk -> embed -> index, then
atomic swap on success (docs/plan.md Decision #9).

run_ingestion() is a plain, synchronous function so it can be scheduled via
FastAPI BackgroundTasks (Decision #8) once Phase 4 adds the
`POST /ingestion-runs` route; it opens its own DB session rather than
reusing the request-scoped one, since that session may already be closed
by the time a background task runs and SQLAlchemy Sessions aren't safe to
share across threads.

Crash-safety argument (see docs/phase-2.md for the test that proves this):
while a new run is being loaded/parsed/chunked/embedded/indexed, the
previously-current run's rows in Postgres and documents in Azure AI Search
are never touched -- retrieval only ever queries chunks filtered to
whichever run is_current, and that pointer hasn't moved yet. If anything
in that phase raises, the run is marked 'failed' and we return: the
previous run is still current and still fully intact. Only after the new
run finishes completely does the atomic swap run, and only after the swap
has committed does cleanup of the old run begin.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Chunk, Document, IngestionRun
from app.db.session import SessionLocal
from app.services import chunking, parsing
from app.services.embedding import EmbeddingClient
from app.search import search_repo as _real_search_repo

logger = get_logger("ingestion")

# Per-document work (parse -> chunk -> embed -> upload) is dominated by
# network round-trips to Azure OpenAI/Azure AI Search, not CPU, so running
# several documents concurrently overlaps that wait time instead of paying
# for it once per document. Bounded rather than unbounded to stay polite to
# the embedding/search services' own rate limits.
INGESTION_CONCURRENCY = 4

def _resolve_default_corpus_dir() -> Path:
    # Azure App Service deploys only the `backend/` folder as the app root, so
    # production needs the corpus colocated at backend/corpus (see the deploy
    # workflow's "Stage corpus for deploy" step). Local dev keeps the corpus at
    # the repo root, one level above backend/, so prefer the colocated copy
    # when present and fall back to the repo-root copy otherwise.
    backend_local = Path(__file__).resolve().parents[2] / "corpus"
    if backend_local.is_dir():
        return backend_local
    return Path(__file__).resolve().parents[3] / "corpus"


DEFAULT_CORPUS_DIR = _resolve_default_corpus_dir()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def start_ingestion_run(db: Session, *, embedding_model: str | None = None) -> IngestionRun:
    """Creates a new ingestion_run row (status='pending') and returns it.
    Called synchronously so the caller gets an id back immediately; the
    actual work happens in run_ingestion(), meant to be scheduled via
    BackgroundTasks."""
    from app.core.config import get_settings

    run = IngestionRun(
        status="pending",
        embedding_model=embedding_model or get_settings().azure_openai_embedding_deployment,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _load_manifest(corpus_dir: Path) -> dict:
    return json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))


def _upsert_document(db: Session, corpus_dir: Path, entry: dict) -> Document:
    """Identifies documents by content hash (matches the sha256 unique
    constraint from Phase 0): byte-identical content across ingestion runs
    reuses the same Document row, so citations/history tied to an
    unchanged document stay meaningfully linked across re-indexes."""
    path = corpus_dir / entry["filename"]
    content_bytes = path.read_bytes()
    sha256 = hashlib.sha256(content_bytes).hexdigest()

    existing = db.execute(select(Document).where(Document.sha256 == sha256)).scalar_one_or_none()
    if existing is not None:
        return existing

    document = Document(
        source_filename=entry["filename"],
        title=entry["title"],
        doc_type=entry["type"],
        source_uri=str(path),
        sha256=sha256,
        byte_size=len(content_bytes),
    )
    db.add(document)
    db.flush()
    return document


def _process_document(
    corpus_dir: Path,
    entry: dict,
    document_id: uuid.UUID,
    document_title: str,
    run_id: uuid.UUID,
    embedding_client: EmbeddingClient,
    search_repo_module,
) -> list[Chunk]:
    """Parse -> chunk -> embed -> upload for one document. Runs in a worker
    thread, so it deliberately takes no DB session -- Document rows are
    upserted up front on the main thread instead, since SQLAlchemy Sessions
    aren't safe to share across threads."""
    sections = parsing.parse_document(corpus_dir / entry["filename"], entry["type"])
    doc_chunks = chunking.chunk_sections(sections)
    if not doc_chunks:
        return []

    vectors = embedding_client.embed_batch([c.content for c in doc_chunks])

    chunk_rows: list[Chunk] = []
    search_docs: list[search_repo_module.ChunkSearchDocument] = []
    for chunk, vector in zip(doc_chunks, vectors, strict=True):
        azure_doc_key = f"{run_id}_{document_id}_{chunk.chunk_index}"
        chunk_rows.append(
            Chunk(
                document_id=document_id,
                ingestion_run_id=run_id,
                chunk_index=chunk.chunk_index,
                section_path=chunk.section_path,
                content=chunk.content,
                token_count=chunk.token_count,
                page_no=chunk.page_no,
                azure_doc_key=azure_doc_key,
            )
        )
        search_docs.append(
            search_repo_module.ChunkSearchDocument(
                id=azure_doc_key,
                content=chunk.content,
                section_path=chunk.section_path,
                document_id=str(document_id),
                document_title=document_title,
                ingestion_run_id=str(run_id),
                chunk_index=chunk.chunk_index,
                content_vector=vector,
            )
        )

    search_repo_module.upload_chunks(search_docs)
    return chunk_rows


def _mark_failed(db: Session, run_id: uuid.UUID, error: Exception) -> None:
    db.rollback()
    run = db.get(IngestionRun, run_id)
    run.status = "failed"
    run.error = str(error)
    run.finished_at = _utcnow()
    db.commit()
    logger.error("ingestion_run_failed", run_id=str(run_id), error=str(error))


def run_ingestion(
    run_id: uuid.UUID,
    *,
    corpus_dir: Path | None = None,
    session_factory: Callable[[], Session] | None = None,
    search_repo_module=None,
    embedding_client: EmbeddingClient | None = None,
) -> None:
    session_factory = session_factory or SessionLocal
    search_repo_module = search_repo_module or _real_search_repo
    corpus_dir = corpus_dir or DEFAULT_CORPUS_DIR
    embedding_client = embedding_client or EmbeddingClient()

    db = session_factory()
    try:
        run = db.get(IngestionRun, run_id)
        run.status = "running"
        run.embedding_model = embedding_client.deployment_name
        run.started_at = _utcnow()
        db.commit()

        search_repo_module.create_index()

        manifest = _load_manifest(corpus_dir)

        # Upsert every Document row up front, sequentially, on this thread's
        # session -- cheap (one insert-or-lookup per doc) and keeps all DB
        # access off the worker threads below.
        documents = {entry["filename"]: _upsert_document(db, corpus_dir, entry) for entry in manifest["documents"]}

        doc_count = 0
        chunk_count = 0

        executor = ThreadPoolExecutor(max_workers=INGESTION_CONCURRENCY)
        try:
            future_to_entry = {
                executor.submit(
                    _process_document,
                    corpus_dir,
                    entry,
                    documents[entry["filename"]].id,
                    documents[entry["filename"]].title,
                    run_id,
                    embedding_client,
                    search_repo_module,
                ): entry
                for entry in manifest["documents"]
            }

            for future in as_completed(future_to_entry):
                chunk_rows = future.result()  # re-raises the worker's exception here, on the main thread
                if not chunk_rows:
                    continue
                db.add_all(chunk_rows)
                db.commit()
                doc_count += 1
                chunk_count += len(chunk_rows)
        finally:
            # cancel_futures drops any not-yet-started documents immediately
            # on failure, rather than burning time processing work that will
            # just be discarded; already-running ones finish naturally since
            # threads can't be forcibly killed.
            executor.shutdown(wait=True, cancel_futures=True)

        _swap_to_current(db, run_id, doc_count, chunk_count, search_repo_module)

    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure must land the run in 'failed'
        _mark_failed(db, run_id, exc)
    finally:
        db.close()


def _swap_to_current(
    db: Session,
    run_id: uuid.UUID,
    doc_count: int,
    chunk_count: int,
    search_repo_module,
) -> None:
    """The atomic swap (Decision #9). The two UPDATEs are issued as
    separate, immediately-executed statements -- old run's is_current is
    cleared BEFORE the new run's is_current is set -- so at no point do
    two rows have is_current=true at once, which the partial unique index
    `uq_ingestion_runs_is_current` would otherwise reject. Relying on the
    ORM's implicit flush ordering for two unrelated row updates does not
    guarantee this order; issuing them explicitly does."""
    from sqlalchemy import update

    previous_run = db.execute(select(IngestionRun).where(IngestionRun.is_current.is_(True))).scalar_one_or_none()

    if previous_run is not None:
        db.execute(update(IngestionRun).where(IngestionRun.id == previous_run.id).values(is_current=False))

    db.execute(
        update(IngestionRun)
        .where(IngestionRun.id == run_id)
        .values(
            is_current=True,
            status="succeeded",
            doc_count=doc_count,
            chunk_count=chunk_count,
            finished_at=_utcnow(),
        )
    )
    db.commit()
    logger.info("ingestion_run_swapped", run_id=str(run_id), previous_run_id=str(previous_run.id) if previous_run else None)

    if previous_run is not None:
        _cleanup_previous_run(db, previous_run, search_repo_module)


def _cleanup_previous_run(db: Session, previous_run: IngestionRun, search_repo_module) -> None:
    """Best-effort: the new run is already live by this point, so a
    failure here just leaves stale data to clean up on a future run
    rather than affecting correctness."""
    try:
        search_repo_module.delete_old_run(str(previous_run.id))
        db.delete(previous_run)  # cascades to previous_run's chunks (ON DELETE CASCADE)
        db.commit()
        _delete_orphaned_documents(db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("ingestion_run_cleanup_failed", old_run_id=str(previous_run.id), error=str(exc))


def _delete_orphaned_documents(db: Session) -> None:
    """_upsert_document() reuses a Document row across runs when a file's
    bytes are unchanged (matching sha256), so most Document rows survive
    the swap above untouched -- they still have chunks in the new current
    run. But when a file's content *changes*, upsert can't match the old
    sha256 and inserts a fresh Document row for the new content; the old
    row's chunks just got cascade-deleted with the previous run above,
    leaving that old row referencing zero chunks anywhere. Delete any such
    orphan so the admin documents list doesn't accumulate stale rows for
    superseded content, which is genuinely confusing (same title/filename
    appearing multiple times) rather than a display quirk to filter around."""
    orphaned = db.execute(select(Document).where(~Document.chunks.any())).scalars().all()
    if not orphaned:
        return
    for document in orphaned:
        db.delete(document)
    db.commit()
    logger.info("orphaned_documents_deleted", count=len(orphaned), document_ids=[str(d.id) for d in orphaned])
