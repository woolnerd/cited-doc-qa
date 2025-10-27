"""Tests for full-text search service."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from app.core.exceptions import DocumentProcessingError
from app.services.full_text_search import FullTextSearchService


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    mock = MagicMock()
    return mock


@pytest.fixture
def full_text_search_service(mock_supabase):
    """Create FullTextSearchService with mocked dependencies."""
    return FullTextSearchService(supabase_client=mock_supabase)


@pytest.fixture
def sample_search_results():
    """Sample search results from database."""
    doc_id = str(uuid4())
    return [
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "Python is a programming language.",
            "contextual_content": "Document: test.pdf\n\nPython is a programming language.",
            "rank": 0.95,
            "metadata": {"chunk_index": 0},
        },
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "Python has many libraries for data science.",
            "contextual_content": "Document: test.pdf\n\nPython has many libraries for data science.",
            "rank": 0.88,
            "metadata": {"chunk_index": 1},
        },
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "content": "Programming in Python is efficient.",
            "contextual_content": "Document: test.pdf\n\nProgramming in Python is efficient.",
            "rank": 0.82,
            "metadata": {"chunk_index": 2},
        },
    ]


def test_search_success(full_text_search_service, mock_supabase, sample_search_results):
    """Test successful full-text search."""
    # Mock RPC call
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("Python programming")

    assert len(results) == 3
    assert results[0]["relevance_score"] == 0.95
    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2
    assert results[2]["rank"] == 3

    # Verify RPC was called
    mock_supabase.rpc.assert_called_once()
    call_args = mock_supabase.rpc.call_args
    assert call_args[0][0] == "search_chunks_fulltext"
    assert call_args[0][1]["search_query"] == "Python programming"


def test_search_custom_limit(
    full_text_search_service, mock_supabase, sample_search_results
):
    """Test search with custom limit."""
    mock_result = Mock()
    mock_result.data = sample_search_results[:2]
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("Python", limit=2)

    assert len(results) == 2

    # Check RPC parameters
    call_args = mock_supabase.rpc.call_args[0][1]
    assert call_args["match_limit"] == 2


def test_search_no_results(full_text_search_service, mock_supabase):
    """Test search with no matching results."""
    mock_result = Mock()
    mock_result.data = []
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("nonexistent query")

    assert results == []


def test_search_none_results(full_text_search_service, mock_supabase):
    """Test search when database returns None."""
    mock_result = Mock()
    mock_result.data = None
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("test query")

    assert results == []


def test_search_formats_results_correctly(
    full_text_search_service, mock_supabase, sample_search_results
):
    """Test that search results are formatted correctly."""
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("Python")

    # Check all expected fields are present
    for result in results:
        assert "chunk_id" in result
        assert "document_id" in result
        assert "content" in result
        assert "contextual_content" in result
        assert "relevance_score" in result
        assert "rank" in result
        assert "metadata" in result

    # Check rank ordering
    assert [r["rank"] for r in results] == [1, 2, 3]

    # Check relevance scores are floats
    assert all(isinstance(r["relevance_score"], float) for r in results)


def test_search_empty_query(full_text_search_service):
    """Test search with empty query."""
    with pytest.raises(DocumentProcessingError, match="Search query cannot be empty"):
        full_text_search_service.search("")


def test_search_whitespace_query(full_text_search_service):
    """Test search with whitespace-only query."""
    with pytest.raises(DocumentProcessingError, match="Search query cannot be empty"):
        full_text_search_service.search("   ")


def test_search_database_error(full_text_search_service, mock_supabase):
    """Test handling of database errors during search."""
    mock_supabase.rpc.return_value.execute.side_effect = Exception("Database error")

    with pytest.raises(DocumentProcessingError, match="Full-text search failed"):
        full_text_search_service.search("test query")


def test_search_by_document_success(
    full_text_search_service, mock_supabase, sample_search_results
):
    """Test successful search within a specific document."""
    document_id = str(uuid4())
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search_by_document("Python", document_id)

    assert len(results) == 3

    # Verify correct RPC function was called
    call_args = mock_supabase.rpc.call_args
    assert call_args[0][0] == "search_chunks_fulltext_by_document"
    assert call_args[0][1]["target_document_id"] == document_id


def test_search_by_document_custom_limit(
    full_text_search_service, mock_supabase, sample_search_results
):
    """Test search by document with custom limit."""
    document_id = str(uuid4())
    mock_result = Mock()
    mock_result.data = sample_search_results[:2]
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search_by_document(
        "Python", document_id, limit=2
    )

    assert len(results) == 2

    # Check RPC parameters
    call_args = mock_supabase.rpc.call_args[0][1]
    assert call_args["target_document_id"] == document_id
    assert call_args["match_limit"] == 2


def test_search_by_document_no_results(full_text_search_service, mock_supabase):
    """Test search by document with no matching results."""
    document_id = str(uuid4())
    mock_result = Mock()
    mock_result.data = []
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search_by_document("test query", document_id)

    assert results == []


def test_search_by_document_empty_query(full_text_search_service):
    """Test search by document with empty query."""
    document_id = str(uuid4())

    with pytest.raises(DocumentProcessingError, match="Search query cannot be empty"):
        full_text_search_service.search_by_document("", document_id)


def test_search_by_document_database_error(full_text_search_service, mock_supabase):
    """Test handling of database errors during search by document."""
    document_id = str(uuid4())
    mock_supabase.rpc.return_value.execute.side_effect = Exception("Database error")

    with pytest.raises(
        DocumentProcessingError, match="Full-text search by document failed"
    ):
        full_text_search_service.search_by_document("test query", document_id)


def test_search_uses_default_limit(
    full_text_search_service, mock_supabase, sample_search_results
):
    """Test that search uses default limit from config."""
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    full_text_search_service.search("test query")

    # Check default limit was used
    call_args = mock_supabase.rpc.call_args[0][1]
    assert "match_limit" in call_args
    # Value should be from settings.FULL_TEXT_SEARCH_LIMIT


def test_search_result_without_contextual_content(
    full_text_search_service, mock_supabase
):
    """Test handling of results without contextual_content field."""
    # Result without contextual_content
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content about Python",
            "rank": 0.9,
            "metadata": {},
        }
    ]

    mock_result = Mock()
    mock_result.data = result_data
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("Python")

    # Should use content as fallback for contextual_content
    assert results[0]["contextual_content"] == "Test content about Python"


def test_search_result_without_metadata(full_text_search_service, mock_supabase):
    """Test handling of results without metadata field."""
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content",
            "contextual_content": "Context",
            "rank": 0.9,
        }
    ]

    mock_result = Mock()
    mock_result.data = result_data
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("test")

    # Should use empty dict as default metadata
    assert results[0]["metadata"] == {}


def test_search_result_without_rank(full_text_search_service, mock_supabase):
    """Test handling of results without rank field."""
    result_data = [
        {
            "id": str(uuid4()),
            "document_id": str(uuid4()),
            "content": "Test content",
            "contextual_content": "Context",
            "metadata": {},
        }
    ]

    mock_result = Mock()
    mock_result.data = result_data
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    results = full_text_search_service.search("test")

    # Should use 0.0 as default relevance score
    assert results[0]["relevance_score"] == 0.0


def test_service_initialization(mock_supabase):
    """Test that service initializes correctly."""
    service = FullTextSearchService(supabase_client=mock_supabase)

    assert service.supabase is mock_supabase


def test_search_logs_query(
    full_text_search_service, mock_supabase, sample_search_results, caplog
):
    """Test that search logs the query."""
    import logging

    caplog.set_level(logging.INFO)

    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    full_text_search_service.search("Python programming query")

    assert "Full-text search for query" in caplog.text
    assert "Python programming query" in caplog.text


def test_search_logs_results_count(
    full_text_search_service, mock_supabase, sample_search_results, caplog
):
    """Test that search logs the number of results found."""
    import logging

    caplog.set_level(logging.INFO)

    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    full_text_search_service.search("Python")

    assert "Found 3 results for full-text query" in caplog.text


def test_search_with_special_characters(
    full_text_search_service, mock_supabase, sample_search_results
):
    """Test search with special characters in query."""
    mock_result = Mock()
    mock_result.data = sample_search_results
    mock_supabase.rpc.return_value.execute.return_value = mock_result

    # Query with special characters
    query = "Python & data-science | machine-learning"
    results = full_text_search_service.search(query)

    assert len(results) == 3

    # Verify query was passed correctly
    call_args = mock_supabase.rpc.call_args[0][1]
    assert call_args["search_query"] == query
