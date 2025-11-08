"""Tests for vector similarity search service."""

from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.vector_search import VectorSearchService


@pytest.fixture
def mock_db():
    """Mock DatabaseService."""
    mock = MagicMock()
    mock.fetch = AsyncMock()
    return mock


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService."""
    mock = MagicMock()
    mock.generate_query_embedding.return_value = [0.1] * 768  # 768-dim embedding
    return mock


@pytest.fixture
def vector_search_service(mock_db, mock_embedding_service):
    """Create VectorSearchService with mocked dependencies."""
    return VectorSearchService(
        db=mock_db,
        embedding_service=mock_embedding_service,
    )


@pytest.fixture
def sample_search_results():
    """Sample search results from database."""
    doc_id = str(uuid4())
    return [
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "This is the first chunk.",
            "contextual_content": "Document: test.pdf\n\nThis is the first chunk.",
            "similarity": 0.95,
            "metadata": {"chunk_index": 0},
        },
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "This is the second chunk.",
            "contextual_content": "Document: test.pdf\n\nThis is the second chunk.",
            "similarity": 0.88,
            "metadata": {"chunk_index": 1},
        },
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "This is the third chunk.",
            "contextual_content": "Document: test.pdf\n\nThis is the third chunk.",
            "similarity": 0.82,
            "metadata": {"chunk_index": 2},
        },
    ]


@pytest.mark.asyncio
async def test_search_success(
    vector_search_service, mock_db, mock_embedding_service, sample_search_results
):
    """Test successful vector similarity search."""
    # Mock database fetch
    mock_db.fetch.return_value = sample_search_results

    results = await vector_search_service.search("test query")

    assert len(results) == 3
    assert results[0]["similarity_score"] == 0.95
    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2
    assert results[2]["rank"] == 3

    # Verify embedding was generated
    mock_embedding_service.generate_query_embedding.assert_called_once_with(
        "test query"
    )

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_custom_parameters(
    vector_search_service, mock_db, sample_search_results
):
    """Test search with custom top_k and similarity_threshold."""
    mock_db.fetch.return_value = sample_search_results[:2]

    results = await vector_search_service.search(
        "test query", top_k=5, similarity_threshold=0.8
    )

    assert len(results) == 2

    # Check database call was made
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_no_results(vector_search_service, mock_db):
    """Test search with no matching results."""
    mock_db.fetch.return_value = []

    results = await vector_search_service.search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_search_none_results(vector_search_service, mock_db):
    """Test search when database returns None."""
    mock_db.fetch.return_value = None

    results = await vector_search_service.search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_search_formats_results_correctly(
    vector_search_service, mock_db, sample_search_results
):
    """Test that search results are formatted correctly."""
    mock_db.fetch.return_value = sample_search_results

    results = await vector_search_service.search("test query")

    # Check all expected fields are present
    for result in results:
        assert "chunk_id" in result
        assert "document_id" in result
        assert "content" in result
        assert "contextual_content" in result
        assert "similarity_score" in result
        assert "rank" in result
        assert "metadata" in result

    # Check rank ordering
    assert [r["rank"] for r in results] == [1, 2, 3]

    # Check similarity scores are floats
    assert all(isinstance(r["similarity_score"], float) for r in results)


@pytest.mark.asyncio
async def test_search_embedding_generation_failure(
    vector_search_service, mock_embedding_service
):
    """Test handling of embedding generation failure."""
    mock_embedding_service.generate_query_embedding.side_effect = (
        DocumentProcessingError("Embedding generation failed")
    )

    with pytest.raises(DocumentProcessingError, match="Embedding generation failed"):
        await vector_search_service.search("test query")


@pytest.mark.asyncio
async def test_search_database_error(vector_search_service, mock_db):
    """Test handling of database errors during search."""
    mock_db.fetch.side_effect = Exception("Database error")

    with pytest.raises(DocumentProcessingError, match="Vector search failed"):
        await vector_search_service.search("test query")


@pytest.mark.asyncio
async def test_search_by_document_success(
    vector_search_service, mock_db, mock_embedding_service, sample_search_results
):
    """Test successful search within a specific document."""
    document_id = str(uuid4())
    mock_db.fetch.return_value = sample_search_results

    results = await vector_search_service.search_by_document("test query", document_id)

    assert len(results) == 3

    # Verify embedding was generated
    mock_embedding_service.generate_query_embedding.assert_called_once()

    # Verify database fetch was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_by_document_custom_parameters(
    vector_search_service, mock_db, sample_search_results
):
    """Test search by document with custom parameters."""
    document_id = str(uuid4())
    mock_db.fetch.return_value = sample_search_results[:2]

    results = await vector_search_service.search_by_document(
        "test query", document_id, top_k=5, similarity_threshold=0.85
    )

    assert len(results) == 2
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_by_document_no_results(vector_search_service, mock_db):
    """Test search by document with no matching results."""
    document_id = str(uuid4())
    mock_db.fetch.return_value = []

    results = await vector_search_service.search_by_document("test query", document_id)

    assert results == []


@pytest.mark.asyncio
async def test_search_by_document_database_error(vector_search_service, mock_db):
    """Test handling of database errors during search by document."""
    document_id = str(uuid4())
    mock_db.fetch.side_effect = Exception("Database error")

    with pytest.raises(
        DocumentProcessingError, match="Vector search by document failed"
    ):
        await vector_search_service.search_by_document("test query", document_id)


@pytest.mark.asyncio
async def test_search_uses_default_settings(
    vector_search_service, mock_db, sample_search_results
):
    """Test that search uses default settings from config."""
    mock_db.fetch.return_value = sample_search_results

    await vector_search_service.search("test query")

    # Check database was called
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_search_result_without_contextual_content(vector_search_service, mock_db):
    """Test handling of results without contextual_content field."""
    # Result without contextual_content
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content",
            "similarity": 0.9,
            "metadata": {},
        }
    ]

    mock_db.fetch.return_value = result_data

    results = await vector_search_service.search("test query")

    # Should use content as fallback for contextual_content
    assert results[0]["contextual_content"] == "Test content"


@pytest.mark.asyncio
async def test_search_result_without_metadata(vector_search_service, mock_db):
    """Test handling of results without metadata field."""
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content",
            "contextual_content": "Context",
            "similarity": 0.9,
        }
    ]

    mock_db.fetch.return_value = result_data

    results = await vector_search_service.search("test query")

    # Should use empty dict as default metadata
    assert results[0]["metadata"] == {}


def test_service_initialization_creates_default_embedding_service(mock_db):
    """Test that service creates default embedding service if none provided."""
    service = VectorSearchService(db=mock_db)

    assert service.embedding_service is not None
    assert service.db is mock_db


def test_service_initialization_uses_provided_embedding_service(
    mock_db, mock_embedding_service
):
    """Test that service uses provided embedding service."""
    service = VectorSearchService(
        db=mock_db,
        embedding_service=mock_embedding_service,
    )

    assert service.embedding_service is mock_embedding_service


@pytest.mark.asyncio
async def test_search_logs_query(
    vector_search_service, mock_db, sample_search_results, caplog
):
    """Test that search logs the query."""
    import logging

    caplog.set_level(logging.INFO)

    mock_db.fetch.return_value = sample_search_results

    await vector_search_service.search("test query for logging")

    assert "Vector search for query" in caplog.text
    assert "test query for logging" in caplog.text


@pytest.mark.asyncio
async def test_search_logs_results_count(
    vector_search_service, mock_db, sample_search_results, caplog
):
    """Test that search logs the number of results found."""
    import logging

    caplog.set_level(logging.INFO)

    mock_db.fetch.return_value = sample_search_results

    await vector_search_service.search("test query")

    assert "Found 3 results" in caplog.text
