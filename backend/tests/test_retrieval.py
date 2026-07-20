from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.db.models import IngestionRun
from app.search.search_repo import SearchResultChunk
from app.services.embedding import EmbeddingClient
from app.services.retrieval import get_current_run_id, retrieve

SETTINGS = get_settings()


def _fake_embedding_client() -> EmbeddingClient:
    fake_openai = MagicMock()
    fake_openai.embeddings.create.side_effect = lambda model, input, dimensions: MagicMock(
        data=[MagicMock(embedding=[0.1] * dimensions) for _ in input]
    )
    return EmbeddingClient(deployment="text-embedding-3-large", client=fake_openai)


def _chunk(
    *,
    id: str,
    document_id: str = "doc-1",
    section_path: str = "Doc > Section A",
    reranker_score: float | None = 3.0,
    score: float = 1.0,
) -> SearchResultChunk:
    return SearchResultChunk(
        id=id,
        content=f"content for {id}",
        section_path=section_path,
        document_id=document_id,
        document_title="Doc",
        ingestion_run_id="run-1",
        chunk_index=0,
        score=score,
        reranker_score=reranker_score,
    )


def _suppress_real_current_run(db_session) -> None:
    """The dev database can now hold a real, committed current run (live
    Azure credentials configured after Phase 6/7) -- Phase 0's partial
    unique index allows only one is_current=true row at a time, so tests
    that need "no current run" or "this fixture's run is current" must
    temporarily un-mark it. Since db_session never commits (conftest.py
    rolls its transaction back at teardown), this reverts automatically --
    no manual restore needed, unlike the SessionLocal()-based fixtures in
    test_chat_service.py/test_documents_api.py/test_chat_api.py, which
    commit for real and must restore explicitly in `finally`."""
    existing = db_session.query(IngestionRun).filter(IngestionRun.is_current.is_(True)).one_or_none()
    if existing is not None:
        existing.is_current = False
        db_session.flush()


def _make_current_run(db_session) -> str:
    _suppress_real_current_run(db_session)
    run = IngestionRun(status="succeeded", embedding_model="text-embedding-3-large", is_current=True)
    db_session.add(run)
    db_session.flush()
    return str(run.id)


def test_get_current_run_id_returns_none_when_no_run_is_current(db_session):
    _suppress_real_current_run(db_session)

    assert get_current_run_id(db_session) is None


def test_get_current_run_id_returns_the_current_runs_id(db_session):
    run_id = _make_current_run(db_session)

    assert get_current_run_id(db_session) == run_id


def test_refuses_when_no_current_run_exists_and_never_calls_search(db_session):
    _suppress_real_current_run(db_session)

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("search_fn must not be called when there is no current ingestion run")

    result = retrieve(db_session, "some question", embedding_client=_fake_embedding_client(), search_fn=_should_not_be_called)

    assert result.refused is True
    assert result.chunks == []
    assert result.top_reranker_score is None


def test_search_is_called_with_the_current_run_id_and_candidate_count(db_session):
    run_id = _make_current_run(db_session)
    captured = {}

    def _search_fn(query, vector, run_id, top):
        captured["query"] = query
        captured["vector"] = vector
        captured["run_id"] = run_id
        captured["top"] = top
        return [_chunk(id="c1")]

    retrieve(db_session, "what is the PTO policy?", embedding_client=_fake_embedding_client(), search_fn=_search_fn)

    assert captured["run_id"] == run_id
    assert captured["top"] == SETTINGS.retrieval_candidate_count
    assert captured["query"] == "what is the PTO policy?"
    assert len(captured["vector"]) > 0


def test_dedupe_keeps_only_the_first_hit_per_document_and_section(db_session):
    _make_current_run(db_session)
    candidates = [
        _chunk(id="c1", document_id="doc-1", section_path="Doc > Section A", reranker_score=3.9),
        _chunk(id="c2", document_id="doc-1", section_path="Doc > Section A", reranker_score=3.5),  # duplicate section
        _chunk(id="c3", document_id="doc-1", section_path="Doc > Section B", reranker_score=3.2),
        _chunk(id="c4", document_id="doc-2", section_path="Doc > Section A", reranker_score=3.0),  # diff doc, same path
    ]

    result = retrieve(db_session, "q", embedding_client=_fake_embedding_client(), search_fn=lambda *a, **k: candidates)

    assert [c.id for c in result.chunks] == ["c1", "c3", "c4"]


def test_retrieve_returns_at_most_top_k_after_dedupe(db_session):
    _make_current_run(db_session)
    candidates = [
        _chunk(id=f"c{i}", document_id=f"doc-{i}", section_path=f"Section {i}", reranker_score=3.0)
        for i in range(SETTINGS.retrieval_candidate_count)
    ]

    result = retrieve(db_session, "q", embedding_client=_fake_embedding_client(), search_fn=lambda *a, **k: candidates)

    assert len(result.chunks) == SETTINGS.retrieval_top_k
    assert [c.id for c in result.chunks] == [f"c{i}" for i in range(SETTINGS.retrieval_top_k)]


def test_refused_when_top_score_is_no_results(db_session):
    _make_current_run(db_session)

    result = retrieve(db_session, "q", embedding_client=_fake_embedding_client(), search_fn=lambda *a, **k: [])

    assert result.refused is True
    assert result.chunks == []
    assert result.top_reranker_score is None


def test_refused_when_top_score_is_below_threshold(db_session):
    _make_current_run(db_session)
    below = SETTINGS.refusal_reranker_threshold - 0.01
    candidates = [_chunk(id="c1", reranker_score=below)]

    result = retrieve(db_session, "q", embedding_client=_fake_embedding_client(), search_fn=lambda *a, **k: candidates)

    assert result.refused is True
    assert result.chunks == []
    assert result.top_reranker_score == pytest.approx(below)


def test_not_refused_when_top_score_is_exactly_at_threshold(db_session):
    _make_current_run(db_session)
    at_threshold = SETTINGS.refusal_reranker_threshold
    candidates = [_chunk(id="c1", reranker_score=at_threshold)]

    result = retrieve(db_session, "q", embedding_client=_fake_embedding_client(), search_fn=lambda *a, **k: candidates)

    assert result.refused is False
    assert len(result.chunks) == 1
    assert result.top_reranker_score == pytest.approx(at_threshold)


def test_not_refused_when_top_score_is_above_threshold(db_session):
    _make_current_run(db_session)
    above = SETTINGS.refusal_reranker_threshold + 1.0
    candidates = [_chunk(id="c1", reranker_score=above)]

    result = retrieve(db_session, "q", embedding_client=_fake_embedding_client(), search_fn=lambda *a, **k: candidates)

    assert result.refused is False
    assert result.top_reranker_score == pytest.approx(above)
