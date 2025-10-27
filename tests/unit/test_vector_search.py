"""Tests for vector similarity search service."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.vector_search import VectorSearchService


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService."""
    mock = MagicMock()
    mock.generate_query_embedding.return_value = [0.1] * 768  # 768-dim embedding
    return mock


@pytest.fixture
def vector_search_service(mock_supabase, mock_embedding_service):
    """Create VectorSearchService with mocked dependencies."""
    return VectorSearchService(
        supabase_client=mock_supabase,
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


def test_search_success(
    vector_search_service, mock_supabase, mock_embedding_service, sample_search_results
):
    """Test successful vector similarity search."""
    # Mock RPC call
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search("test query")

    assert len(results) == 3
    assert results[0]["similarity_score"] == 0.95
    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2
    assert results[2]["rank"] == 3

    # Verify embedding was generated
    mock_embedding_service.generate_query_embedding.assert_called_once_with(
        "test query"
    )

    # Verify RPC was called
    mock_supabase.rpc.assert_called_once()
    call_args = mock_supabase.rpc.call_args
    assert call_args[0][0] == "search_chunks"


def test_search_custom_parameters(
    vector_search_service, mock_supabase, sample_search_results
):
    """Test search with custom top_k and similarity_threshold."""
    mock_result = Mock()
    mock_result.data = sample_search_results[:2]
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search(
        "test query", top_k=5, similarity_threshold=0.8
    )

    assert len(results) == 2

    # Check RPC parameters
    call_args = mock_supabase.rpc.call_args[0][1]
    assert call_args["match_count"] == 5
    assert call_args["similarity_threshold"] == 0.8


def test_search_no_results(vector_search_service, mock_supabase):
    """Test search with no matching results."""
    mock_result = Mock()
    mock_result.data = []
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search("test query")

    assert results == []


def test_search_none_results(vector_search_service, mock_supabase):
    """Test search when database returns None."""
    mock_result = Mock()
    mock_result.data = None
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search("test query")

    assert results == []


def test_search_formats_results_correctly(
    vector_search_service, mock_supabase, sample_search_results
):
    """Test that search results are formatted correctly."""
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search("test query")

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


def test_search_embedding_generation_failure(
    vector_search_service, mock_embedding_service
):
    """Test handling of embedding generation failure."""
    mock_embedding_service.generate_query_embedding.side_effect = (
        DocumentProcessingError("Embedding generation failed")
    )

    with pytest.raises(DocumentProcessingError, match="Embedding generation failed"):
        vector_search_service.search("test query")


def test_search_database_error(vector_search_service, mock_supabase):
    """Test handling of database errors during search."""
    mock_supabase.rpc.return_value.execute.side_effect = Exception("Database error")

    with pytest.raises(DocumentProcessingError, match="Vector search failed"):
        vector_search_service.search("test query")


def test_search_by_document_success(
    vector_search_service, mock_supabase, mock_embedding_service, sample_search_results
):
    """Test successful search within a specific document."""
    document_id = str(uuid4())
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search_by_document("test query", document_id)

    assert len(results) == 3

    # Verify embedding was generated
    mock_embedding_service.generate_query_embedding.assert_called_once()

    # Verify correct RPC function was called
    call_args = mock_supabase.rpc.call_args
    assert call_args[0][0] == "search_chunks_by_document"
    assert call_args[0][1]["target_document_id"] == document_id


def test_search_by_document_custom_parameters(
    vector_search_service, mock_supabase, sample_search_results
):
    """Test search by document with custom parameters."""
    document_id = str(uuid4())
    mock_result = Mock()
    mock_result.data = sample_search_results[:2]
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search_by_document(
        "test query", document_id, top_k=5, similarity_threshold=0.85
    )

    assert len(results) == 2

    # Check RPC parameters
    call_args = mock_supabase.rpc.call_args[0][1]
    assert call_args["target_document_id"] == document_id
    assert call_args["match_count"] == 5
    assert call_args["similarity_threshold"] == 0.85


def test_search_by_document_no_results(vector_search_service, mock_supabase):
    """Test search by document with no matching results."""
    document_id = str(uuid4())
    mock_result = Mock()
    mock_result.data = []
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search_by_document("test query", document_id)

    assert results == []


def test_search_by_document_database_error(vector_search_service, mock_supabase):
    """Test handling of database errors during search by document."""
    document_id = str(uuid4())
    mock_supabase.rpc.return_value.execute.side_effect = Exception("Database error")

    with pytest.raises(
        DocumentProcessingError, match="Vector search by document failed"
    ):
        vector_search_service.search_by_document("test query", document_id)


def test_search_uses_default_settings(
    vector_search_service, mock_supabase, sample_search_results
):
    """Test that search uses default settings from config."""
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    vector_search_service.search("test query")

    # Check default values were used
    call_args = mock_supabase.rpc.call_args[0][1]
    assert "match_count" in call_args
    assert "similarity_threshold" in call_args
    # Values should be from settings.SEARCH_TOP_K and settings.SEARCH_SIMILARITY_THRESHOLD


def test_search_result_without_contextual_content(vector_search_service, mock_supabase):
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

    mock_result = Mock()
    mock_result.data = result_data
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search("test query")

    # Should use content as fallback for contextual_content
    assert results[0]["contextual_content"] == "Test content"


def test_search_result_without_metadata(vector_search_service, mock_supabase):
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

    mock_result = Mock()
    mock_result.data = result_data
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = vector_search_service.search("test query")

    # Should use empty dict as default metadata
    assert results[0]["metadata"] == {}


def test_service_initialization_creates_default_embedding_service(mock_supabase):
    """Test that service creates default embedding service if none provided."""
    service = VectorSearchService(supabase_client=mock_supabase)

    assert service.embedding_service is not None
    assert service.supabase is mock_supabase


def test_service_initialization_uses_provided_embedding_service(
    mock_supabase, mock_embedding_service
):
    """Test that service uses provided embedding service."""
    service = VectorSearchService(
        supabase_client=mock_supabase,
        embedding_service=mock_embedding_service,
    )

    assert service.embedding_service is mock_embedding_service


def test_search_logs_query(
    vector_search_service, mock_supabase, sample_search_results, caplog
):
    """Test that search logs the query."""
    import logging

    caplog.set_level(logging.INFO)

    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    vector_search_service.search("test query for logging")

    assert "Vector search for query" in caplog.text
    assert "test query for logging" in caplog.text


def test_search_logs_results_count(
    vector_search_service, mock_supabase, sample_search_results, caplog
):
    """Test that search logs the number of results found."""
    import logging

    caplog.set_level(logging.INFO)

    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    vector_search_service.search("test query")

    assert "Found 3 results" in caplog.text
