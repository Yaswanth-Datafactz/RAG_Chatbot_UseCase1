"""Query-time retrieval pipeline (docs/plan.md Decisions #5, #6, #10):
embed the standalone query -> hybrid_search, filtered to the CURRENT
ingestion_run_id, top `retrieval_candidate_count` -> dedupe by
(document_id, section_path) -> top `retrieval_top_k` -> refusal gate on
the top result's reranker score.

search_repo.hybrid_search() already runs Azure's semantic ranker as part
of its single search call (query_type="semantic", see
search/search_repo.py) and returns results carrying `reranker_score`,
already ordered by relevance -- confirmed by reading that code, not
assumed. So there is no separate "rerank" call to make here: this module
dedupes and slices the results hybrid_search() already ranked.

The ingestion_run_id filter is what prevents mid-reindex contamination
(Decision #9): while a new ingestion run is being built, its chunks sit
in the same Azure index as the current run's, but are tagged with a
different ingestion_run_id. Filtering on the run Postgres currently marks
`is_current` means a query never sees a mix of old and half-built new
data, and never sees the new run's data at all until the atomic swap
flips which run is current.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import IngestionRun
from app.search.search_repo import SearchResultChunk
from app.search.search_repo import hybrid_search as _real_hybrid_search
from app.services.embedding import EmbeddingClient

HybridSearchFn = Callable[..., list[SearchResultChunk]]


@dataclass
class RetrievalResult:
    chunks: list[SearchResultChunk]
    refused: bool
    top_reranker_score: float | None


def get_current_run_id(db: Session) -> str | None:
    """Returns the id of whichever ingestion_run is currently marked
    `is_current`, or None if no run has ever succeeded (e.g. before the
    first ingestion, or -- defensively -- mid-crash between a failed run
    and any prior successful one, though Decision #9's swap ordering
    means that case shouldn't arise once at least one run has ever
    succeeded)."""
    run = db.execute(select(IngestionRun).where(IngestionRun.is_current.is_(True))).scalar_one_or_none()
    return str(run.id) if run is not None else None


def _dedupe_by_section(results: list[SearchResultChunk]) -> list[SearchResultChunk]:
    """Keeps the first hit per (document_id, section_path) and drops the
    rest. hybrid_search() results already arrive ordered by relevance
    (Azure's semantic reranker score when semantic ranking is active), so
    "first" means "highest-ranked" -- this never re-sorts, only filters."""
    seen: set[tuple[str, str | None]] = set()
    deduped: list[SearchResultChunk] = []
    for result in results:
        key = (result.document_id, result.section_path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def retrieve(
    db: Session,
    query: str,
    *,
    embedding_client: EmbeddingClient | None = None,
    search_fn: HybridSearchFn = _real_hybrid_search,
) -> RetrievalResult:
    settings = get_settings()

    run_id = get_current_run_id(db)
    if run_id is None:
        # Nothing has ever been ingested (or is currently servable) --
        # there is no corpus to answer from, so refuse rather than search.
        return RetrievalResult(chunks=[], refused=True, top_reranker_score=None)

    embedding_client = embedding_client or EmbeddingClient()
    vector = embedding_client.embed_one(query)

    candidates = search_fn(query, vector, run_id=run_id, top=settings.retrieval_candidate_count)
    deduped = _dedupe_by_section(candidates)
    top = deduped[: settings.retrieval_top_k]

    top_score = top[0].reranker_score if top else None
    refused = top_score is None or top_score < settings.refusal_reranker_threshold

    if refused:
        return RetrievalResult(chunks=[], refused=True, top_reranker_score=top_score)
    return RetrievalResult(chunks=top, refused=False, top_reranker_score=top_score)
