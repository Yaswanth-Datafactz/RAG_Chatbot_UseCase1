"""Verifies search_repo.py constructs correct Azure AI Search requests,
without hitting a live Azure Search resource (none is provisioned yet --
see docs/plan.md Risks). The Azure SDK clients are mocked; what's under
test is the shape of what we'd send them.
"""

from unittest.mock import MagicMock, patch

from app.search import search_repo
from app.search.search_repo import ChunkSearchDocument


def test_create_index_builds_expected_fields_and_vector_config():
    with patch.object(search_repo, "_index_client") as factory:
        mock_client = MagicMock()
        factory.return_value = mock_client

        search_repo.create_index()

        mock_client.create_or_update_index.assert_called_once()
        index_arg = mock_client.create_or_update_index.call_args[0][0]
        field_names = {f.name for f in index_arg.fields}
        assert {
            "id",
            "content",
            "section_path",
            "document_id",
            "document_title",
            "ingestion_run_id",
            "chunk_index",
            "content_vector",
        } <= field_names
        vector_field = next(f for f in index_arg.fields if f.name == "content_vector")
        assert vector_field.vector_search_dimensions == search_repo.VECTOR_DIMENSIONS
        assert index_arg.semantic_search is not None


def test_upload_chunks_sends_plain_dicts_with_all_fields():
    with patch.object(search_repo, "_search_client") as factory:
        mock_client = MagicMock()
        factory.return_value = mock_client

        chunk = ChunkSearchDocument(
            id="abc",
            content="text",
            section_path="A > B",
            document_id="doc1",
            document_title="Doc",
            ingestion_run_id="run1",
            chunk_index=0,
            content_vector=[0.1] * search_repo.VECTOR_DIMENSIONS,
        )
        search_repo.upload_chunks([chunk])

        mock_client.upload_documents.assert_called_once()
        docs_arg = mock_client.upload_documents.call_args.kwargs["documents"]
        assert docs_arg[0]["id"] == "abc"
        assert docs_arg[0]["ingestion_run_id"] == "run1"
        assert len(docs_arg[0]["content_vector"]) == search_repo.VECTOR_DIMENSIONS


def test_upload_chunks_noop_on_empty_list():
    with patch.object(search_repo, "_search_client") as factory:
        mock_client = MagicMock()
        factory.return_value = mock_client

        search_repo.upload_chunks([])

        mock_client.upload_documents.assert_not_called()


def test_hybrid_search_filters_by_run_id_and_uses_semantic_ranking():
    with patch.object(search_repo, "_search_client") as factory:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        factory.return_value = mock_client

        search_repo.hybrid_search("what is PTO", [0.1] * search_repo.VECTOR_DIMENSIONS, run_id="run-42", top=5)

        _, kwargs = mock_client.search.call_args
        assert kwargs["filter"] == "ingestion_run_id eq 'run-42'"
        assert kwargs["top"] == 5
        assert kwargs["query_type"] == "semantic"
        assert kwargs["semantic_configuration_name"] == search_repo.SEMANTIC_CONFIG_NAME


def test_hybrid_search_parses_results_into_dataclasses():
    with patch.object(search_repo, "_search_client") as factory:
        mock_client = MagicMock()
        mock_client.search.return_value = [
            {
                "id": "chunk-1",
                "content": "PTO accrues at 1.67 days per month.",
                "section_path": "PTO Policy > Accrual Rates",
                "document_id": "doc-1",
                "document_title": "PTO Policy",
                "ingestion_run_id": "run-42",
                "chunk_index": 0,
                "@search.score": 0.83,
                "@search.reranker_score": 2.9,
            }
        ]
        factory.return_value = mock_client

        results = search_repo.hybrid_search("PTO accrual", [0.1] * search_repo.VECTOR_DIMENSIONS, run_id="run-42", top=5)

        assert len(results) == 1
        assert results[0].id == "chunk-1"
        assert results[0].score == 0.83
        assert results[0].reranker_score == 2.9


def test_delete_old_run_deletes_matching_documents():
    with patch.object(search_repo, "_search_client") as factory:
        mock_client = MagicMock()
        mock_client.search.return_value = [{"id": "a"}, {"id": "b"}]
        factory.return_value = mock_client

        search_repo.delete_old_run("run-old")

        mock_client.delete_documents.assert_called_once_with(documents=[{"id": "a"}, {"id": "b"}])


def test_delete_old_run_noop_when_nothing_matches():
    with patch.object(search_repo, "_search_client") as factory:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        factory.return_value = mock_client

        search_repo.delete_old_run("run-old")

        mock_client.delete_documents.assert_not_called()
