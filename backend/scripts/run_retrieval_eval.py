"""Phase 8 evaluation script (docs/plan.md, docs/phase-8.md): runs the
real retrieval pipeline -- real Azure OpenAI embeddings, real Azure AI
Search hybrid+semantic search -- against every question in
backend/eval/questions.json and records what actually came back.

Deliberately NOT a pytest test: docs/phase-7.md Deviation 2 documents that
running the full test suite deletes the live current ingestion run
(Phase 2/3's ingestion tests exercise the real atomic-swap-and-cleanup
against the shared dev Postgres). This script only ever reads -- it never
starts an ingestion run or touches ingestion_runs -- so it's safe to run
any number of times without disturbing the live index. Run directly:

    ./.venv/bin/python scripts/run_retrieval_eval.py

Mirrors app/services/retrieval.py's real retrieve() function exactly
(same embedding client construction, same hybrid_search call, same
_dedupe_by_section), rather than reimplementing the pipeline, so results
are faithful to what a real chat request would actually retrieve. It
additionally keeps the *full* deduped candidate list (up to
retrieval_candidate_count, before slicing to retrieval_top_k) so an
in-corpus question whose correct source lands just outside the top-k can
be reported as "close" rather than a flat miss -- retrieve() itself
only ever returns the top-k slice.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.search.search_repo import hybrid_search
from app.services.embedding import EmbeddingClient
from app.services.retrieval import _dedupe_by_section, get_current_run_id

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "eval" / "questions.json"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "eval" / "results.json"


def run_one_query(embedding_client: EmbeddingClient, db, run_id: str, question: str, settings) -> dict:
    embed_start = time.perf_counter()
    vector = embedding_client.embed_one(question)
    embed_ms = (time.perf_counter() - embed_start) * 1000

    search_start = time.perf_counter()
    candidates = hybrid_search(question, vector, run_id=run_id, top=settings.retrieval_candidate_count)
    search_ms = (time.perf_counter() - search_start) * 1000

    deduped = _dedupe_by_section(candidates)
    top_k = deduped[: settings.retrieval_top_k]
    top_score = top_k[0].reranker_score if top_k else None
    refused_at_current_threshold = top_score is None or top_score < settings.refusal_reranker_threshold

    return {
        "embed_ms": round(embed_ms, 1),
        "search_ms": round(search_ms, 1),
        "top_reranker_score": top_score,
        "refused_at_current_threshold": refused_at_current_threshold,
        "deduped_candidates": [
            {
                "rank": i + 1,
                "document_title": c.document_title,
                "section_path": c.section_path,
                "reranker_score": c.reranker_score,
            }
            for i, c in enumerate(deduped)
        ],
        "top_k_served": [
            {
                "rank": i + 1,
                "document_title": c.document_title,
                "section_path": c.section_path,
                "reranker_score": c.reranker_score,
            }
            for i, c in enumerate(top_k)
        ],
    }


def find_expected_rank(deduped_candidates: list[dict], expected_document_title: str, expected_section_path: str) -> dict:
    for candidate in deduped_candidates:
        if candidate["document_title"] == expected_document_title and candidate["section_path"] == expected_section_path:
            return {"found": True, "rank": candidate["rank"], "matched_on": "document+section"}
    for candidate in deduped_candidates:
        if candidate["document_title"] == expected_document_title:
            return {"found": True, "rank": candidate["rank"], "matched_on": "document only (different section)"}
    return {"found": False, "rank": None, "matched_on": None}


def main() -> None:
    settings = get_settings()
    questions = json.loads(QUESTIONS_PATH.read_text())

    db = SessionLocal()
    try:
        run_id = get_current_run_id(db)
        if run_id is None:
            print("FATAL: no current ingestion run exists. Re-index before running this eval.", file=sys.stderr)
            sys.exit(1)
        print(f"Current ingestion run: {run_id}")
        print(f"Embedding deployment in use: {settings.azure_openai_embedding_deployment}")
        print(f"Refusal threshold in use: {settings.refusal_reranker_threshold}")
        print()

        embedding_client = EmbeddingClient()  # real Azure OpenAI client, default (prod) deployment

        results = {"embedding_deployment": settings.azure_openai_embedding_deployment, "in_corpus": [], "out_of_corpus": []}

        print("=== In-corpus questions ===")
        for q in questions["in_corpus_questions"]:
            outcome = run_one_query(embedding_client, db, run_id, q["question"], settings)
            expected = find_expected_rank(outcome["deduped_candidates"], q["expected_document_title"], q["expected_section_path"])
            in_top_k = expected["found"] and expected["rank"] is not None and expected["rank"] <= settings.retrieval_top_k
            print(
                f"[{q['id']}] {q['question']!r}\n"
                f"    expected: {q['expected_document_title']} > ...\n"
                f"    top score: {outcome['top_reranker_score']}  refused_at_current_threshold: {outcome['refused_at_current_threshold']}\n"
                f"    expected source found at rank: {expected['rank']} (matched_on={expected['matched_on']})  in_top_{settings.retrieval_top_k}: {in_top_k}\n"
            )
            results["in_corpus"].append({"question": q, "outcome": outcome, "expected_match": expected, "in_top_k": in_top_k})

        print("=== Out-of-corpus questions (should refuse) ===")
        for q in questions["out_of_corpus_questions"]:
            outcome = run_one_query(embedding_client, db, run_id, q["question"], settings)
            print(
                f"[{q['id']}] {q['question']!r}\n"
                f"    gap topic: {q['gap_topic']}\n"
                f"    top score: {outcome['top_reranker_score']}  refused_at_current_threshold: {outcome['refused_at_current_threshold']}\n"
                f"    top candidate: {outcome['deduped_candidates'][0] if outcome['deduped_candidates'] else None}\n"
            )
            results["out_of_corpus"].append({"question": q, "outcome": outcome})

        RESULTS_PATH.write_text(json.dumps(results, indent=2))
        print(f"Full results written to {RESULTS_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
