"""Tests for Gemini embedding service."""

from unittest.mock import patch

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.embeddings import EmbeddingService


@pytest.fixture
def mock_genai():
    """Mock google.generativeai module."""
    with patch("app.services.embeddings.genai") as mock:
        yield mock


@pytest.fixture
def embedding_service(mock_genai):
    """Create an EmbeddingService instance with mocked API."""
    return EmbeddingService()


def test_init_success(mock_genai):
    """Test successful initialization of embedding service."""
    service = EmbeddingService()
    assert service.model_name == "models/text-embedding-004"
    mock_genai.configure.assert_called_once()


def test_init_failure(mock_genai):
    """Test initialization failure."""
    mock_genai.configure.side_effect = Exception("API key invalid")

    with pytest.raises(DocumentProcessingError, match="Failed to initialize"):
        EmbeddingService()


def test_generate_embedding_success(embedding_service, mock_genai):
    """Test successful embedding generation."""
    # Mock the embed_content response
    mock_embedding = [0.1] * 768
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    text = "This is a test document."
    result = embedding_service.generate_embedding(text)

    assert result == mock_embedding
    assert len(result) == 768
    mock_genai.embed_content.assert_called_once_with(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document",
    )


def test_generate_embedding_empty_text(embedding_service):
    """Test embedding generation with empty text."""
    with pytest.raises(DocumentProcessingError, match="empty text"):
        embedding_service.generate_embedding("")

    with pytest.raises(DocumentProcessingError, match="empty text"):
        embedding_service.generate_embedding("   ")


def test_generate_embedding_wrong_dimensions(embedding_service, mock_genai):
    """Test embedding generation with wrong dimensions."""
    # Mock response with wrong dimensions
    mock_embedding = [0.1] * 512  # Wrong size
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    with pytest.raises(DocumentProcessingError, match="Expected 768 dimensions"):
        embedding_service.generate_embedding("test")


def test_generate_embedding_api_error(embedding_service, mock_genai):
    """Test embedding generation with API error."""
    mock_genai.embed_content.side_effect = Exception("API rate limit exceeded")

    with pytest.raises(DocumentProcessingError, match="Failed to generate embedding"):
        embedding_service.generate_embedding("test")


def test_generate_embeddings_batch_success(embedding_service, mock_genai):
    """Test successful batch embedding generation."""
    # Mock the embed_content response
    mock_embedding = [0.1] * 768
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    texts = ["Text 1", "Text 2", "Text 3"]
    results = embedding_service.generate_embeddings_batch(texts)

    assert len(results) == 3
    assert all(len(emb) == 768 for emb in results)
    assert mock_genai.embed_content.call_count == 3


def test_generate_embeddings_batch_empty_list(embedding_service):
    """Test batch generation with empty list."""
    with pytest.raises(DocumentProcessingError, match="empty list"):
        embedding_service.generate_embeddings_batch([])


def test_generate_embeddings_batch_with_empty_texts(embedding_service, mock_genai):
    """Test batch generation with some empty texts."""
    mock_embedding = [0.1] * 768
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    texts = ["Text 1", "", "Text 3", "   "]
    results = embedding_service.generate_embeddings_batch(texts)

    assert len(results) == 4
    # Empty texts should have zero vectors
    assert results[1] == [0.0] * 768
    assert results[3] == [0.0] * 768
    # Non-empty texts should have real embeddings
    assert results[0] == mock_embedding
    assert results[2] == mock_embedding
    # Only 2 API calls for non-empty texts
    assert mock_genai.embed_content.call_count == 2


def test_generate_embeddings_batch_large(embedding_service, mock_genai):
    """Test batch generation with large number of texts."""
    mock_embedding = [0.1] * 768
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    # Create 250 texts (more than default batch size of 100)
    texts = [f"Text {i}" for i in range(250)]
    results = embedding_service.generate_embeddings_batch(texts, batch_size=100)

    assert len(results) == 250
    assert all(len(emb) == 768 for emb in results)
    # Should have called API 250 times (once per text)
    assert mock_genai.embed_content.call_count == 250


def test_generate_embeddings_batch_custom_batch_size(embedding_service, mock_genai):
    """Test batch generation with custom batch size."""
    mock_embedding = [0.1] * 768
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    texts = [f"Text {i}" for i in range(10)]
    results = embedding_service.generate_embeddings_batch(texts, batch_size=5)

    assert len(results) == 10
    assert mock_genai.embed_content.call_count == 10


def test_generate_query_embedding_success(embedding_service, mock_genai):
    """Test successful query embedding generation."""
    mock_embedding = [0.2] * 768
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    query = "What is the capital of France?"
    result = embedding_service.generate_query_embedding(query)

    assert result == mock_embedding
    assert len(result) == 768
    mock_genai.embed_content.assert_called_once_with(
        model="models/text-embedding-004",
        content=query,
        task_type="retrieval_query",
    )


def test_generate_query_embedding_empty_query(embedding_service):
    """Test query embedding with empty query."""
    with pytest.raises(DocumentProcessingError, match="empty query"):
        embedding_service.generate_query_embedding("")

    with pytest.raises(DocumentProcessingError, match="empty query"):
        embedding_service.generate_query_embedding("   ")


def test_generate_query_embedding_wrong_dimensions(embedding_service, mock_genai):
    """Test query embedding with wrong dimensions."""
    mock_embedding = [0.1] * 512  # Wrong size
    mock_genai.embed_content.return_value = {"embedding": mock_embedding}

    with pytest.raises(DocumentProcessingError, match="Expected 768 dimensions"):
        embedding_service.generate_query_embedding("test query")


def test_generate_query_embedding_api_error(embedding_service, mock_genai):
    """Test query embedding with API error."""
    mock_genai.embed_content.side_effect = Exception("Network error")

    with pytest.raises(
        DocumentProcessingError, match="Failed to generate query embedding"
    ):
        embedding_service.generate_query_embedding("test query")


def test_embedding_dimensions_consistency(embedding_service, mock_genai):
    """Test that all embeddings have consistent dimensions."""
    mock_embedding_1 = [0.1] * 768
    mock_embedding_2 = [0.2] * 768

    # Different embeddings for different texts
    mock_genai.embed_content.side_effect = [
        {"embedding": mock_embedding_1},
        {"embedding": mock_embedding_2},
    ]

    text_emb = embedding_service.generate_embedding("document text")
    query_emb = embedding_service.generate_query_embedding("query text")

    assert len(text_emb) == len(query_emb) == 768


def test_batch_processing_maintains_order(embedding_service, mock_genai):
    """Test that batch processing maintains text order."""

    # Create unique embeddings for each text
    def create_mock_embedding(index):
        return {"embedding": [float(index)] * 768}

    texts = [f"Text {i}" for i in range(5)]

    # Mock different embeddings for each call
    mock_genai.embed_content.side_effect = [create_mock_embedding(i) for i in range(5)]

    results = embedding_service.generate_embeddings_batch(texts)

    # Check order is maintained
    for i, result in enumerate(results):
        assert result[0] == float(i)
