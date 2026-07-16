"""Azure AI Search repository for the RAG chunk index (docs/plan.md Decision #2).

One persistent index, shared across ingestion runs. Every chunk document
carries `ingestion_run_id` as a filterable field; hybrid_search() always
filters to a specific run. That filter is what makes the atomic swap
(Decision #9) safe: a new run's documents sit in the same index as the
current run's, but are invisible to any query filtered on the *old*
run_id, until Postgres flips which run is current. delete_old_run() only
runs after that flip has committed -- see docs/phase-2.md.

Vector field dimensionality is fixed at 1536 regardless of embedding
model (see services/embedding.py) so swapping between text-embedding-3-small
and -large for the Phase 8 comparison never requires an index schema
change.
"""

from __future__ import annotations

from dataclasses import dataclass

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from app.core.config import get_settings

VECTOR_DIMENSIONS = 1536
VECTOR_PROFILE_NAME = "chunk-vector-profile"
VECTOR_ALGORITHM_NAME = "chunk-hnsw"
SEMANTIC_CONFIG_NAME = "chunk-semantic-config"


@dataclass
class ChunkSearchDocument:
    id: str
    content: str
    section_path: str
    document_id: str
    document_title: str
    ingestion_run_id: str
    chunk_index: int
    content_vector: list[float]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "section_path": self.section_path,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "ingestion_run_id": self.ingestion_run_id,
            "chunk_index": self.chunk_index,
            "content_vector": self.content_vector,
        }


@dataclass
class SearchResultChunk:
    id: str
    content: str
    section_path: str
    document_id: str
    document_title: str
    ingestion_run_id: str
    chunk_index: int
    score: float
    reranker_score: float | None = None


def _index_client() -> SearchIndexClient:
    settings = get_settings()
    return SearchIndexClient(settings.azure_search_endpoint, AzureKeyCredential(settings.azure_search_api_key))


def _search_client() -> SearchClient:
    settings = get_settings()
    return SearchClient(
        settings.azure_search_endpoint,
        settings.azure_search_index_name,
        AzureKeyCredential(settings.azure_search_api_key),
    )


def _build_index_definition(index_name: str) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="section_path", type=SearchFieldDataType.String),
        SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="document_title", type=SearchFieldDataType.String),
        SimpleField(name="ingestion_run_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME)],
        profiles=[
            VectorSearchProfile(name=VECTOR_PROFILE_NAME, algorithm_configuration_name=VECTOR_ALGORITHM_NAME)
        ],
    )

    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG_NAME,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="document_title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="section_path")],
                ),
            )
        ]
    )

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def create_index() -> None:
    """Idempotent: creates the index if it doesn't exist, otherwise updates
    it to match the current field/vector/semantic definition. Safe to call
    at the start of every ingestion run."""
    settings = get_settings()
    client = _index_client()
    index = _build_index_definition(settings.azure_search_index_name)
    client.create_or_update_index(index)


def upload_chunks(chunks: list[ChunkSearchDocument]) -> None:
    if not chunks:
        return
    client = _search_client()
    client.upload_documents(documents=[c.to_dict() for c in chunks])


def hybrid_search(query: str, vector: list[float], run_id: str, top: int) -> list[SearchResultChunk]:
    """Hybrid (keyword + vector) search with semantic ranking, filtered to
    a single ingestion_run_id -- see the module docstring for why that
    filter is what makes the atomic swap safe."""
    client = _search_client()
    results = client.search(
        search_text=query,
        vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=top, fields="content_vector")],
        filter=f"ingestion_run_id eq '{run_id}'",
        query_type="semantic",
        semantic_configuration_name=SEMANTIC_CONFIG_NAME,
        top=top,
        select=[
            "id",
            "content",
            "section_path",
            "document_id",
            "document_title",
            "ingestion_run_id",
            "chunk_index",
        ],
    )
    parsed: list[SearchResultChunk] = []
    for r in results:
        parsed.append(
            SearchResultChunk(
                id=r["id"],
                content=r["content"],
                section_path=r["section_path"],
                document_id=r["document_id"],
                document_title=r["document_title"],
                ingestion_run_id=r["ingestion_run_id"],
                chunk_index=r["chunk_index"],
                score=r["@search.score"],
                reranker_score=r.get("@search.reranker_score"),
            )
        )
    return parsed


def delete_old_run(run_id: str) -> None:
    """Deletes every document tagged with the given ingestion_run_id.
    Called only AFTER the Postgres atomic swap has committed -- see
    docs/phase-2.md. A no-op if nothing matches (safe to retry)."""
    client = _search_client()
    results = client.search(search_text="*", filter=f"ingestion_run_id eq '{run_id}'", select=["id"])
    ids_to_delete = [r["id"] for r in results]
    if not ids_to_delete:
        return
    client.delete_documents(documents=[{"id": doc_id} for doc_id in ids_to_delete])
