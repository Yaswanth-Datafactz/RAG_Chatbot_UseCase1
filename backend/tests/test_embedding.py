from unittest.mock import MagicMock

from app.services.embedding import EMBEDDING_DIMENSIONS, EmbeddingClient


def _fake_openai_client():
    client = MagicMock()

    def _create(model, input, dimensions):
        data = [MagicMock(embedding=[0.1] * dimensions) for _ in input]
        return MagicMock(data=data)

    client.embeddings.create.side_effect = _create
    return client


def test_embed_batch_calls_client_with_deployment_and_fixed_dimensions():
    fake_client = _fake_openai_client()
    embedder = EmbeddingClient(deployment="text-embedding-3-small", client=fake_client)

    vectors = embedder.embed_batch(["hello", "world"])

    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIMENSIONS for v in vectors)
    fake_client.embeddings.create.assert_called_once()
    _, kwargs = fake_client.embeddings.create.call_args
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["dimensions"] == EMBEDDING_DIMENSIONS
    assert kwargs["input"] == ["hello", "world"]


def test_embed_batch_empty_input_returns_empty_list_without_calling_client():
    fake_client = _fake_openai_client()
    embedder = EmbeddingClient(deployment="text-embedding-3-small", client=fake_client)

    assert embedder.embed_batch([]) == []
    fake_client.embeddings.create.assert_not_called()


def test_embed_one_returns_a_single_vector():
    embedder = EmbeddingClient(deployment="text-embedding-3-small", client=_fake_openai_client())

    vector = embedder.embed_one("hello")

    assert len(vector) == EMBEDDING_DIMENSIONS


def test_pluggable_to_large_model_keeps_the_same_fixed_dimension():
    fake_client = _fake_openai_client()
    embedder = EmbeddingClient(deployment="text-embedding-3-large", client=fake_client)

    vector = embedder.embed_one("hello")

    _, kwargs = fake_client.embeddings.create.call_args
    assert kwargs["model"] == "text-embedding-3-large"
    assert kwargs["dimensions"] == EMBEDDING_DIMENSIONS
    assert len(vector) == EMBEDDING_DIMENSIONS
